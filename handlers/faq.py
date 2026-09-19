import logging
import time
import random
import threading
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from config import config
from database import database
from services.ai import ai_service
from services.video import VideoService
from services.support import SupportService
from services.registration import RegistrationService
from services.onboarding import OnboardingService, ACTIVE_STATES
from services import promo
from keyboards import get_start_keyboard, get_back_keyboard
from utils import sanitize_text

logger = logging.getLogger(__name__)

# Buffer for fragmented messages: wait 10 seconds for more input before processing
_pending_messages = {}  # telegram_id -> {"texts": [], "timer": Timer, "user": dict}
_pending_lock = threading.Lock()
DEBOUNCE_SECONDS = 10


def _send_typing(bot: TeleBot, chat_id: int, delay: float = 2.0):
    """Show realistic typing indicator."""
    try:
        bot.send_chat_action(chat_id, "typing")
        time.sleep(delay)
    except Exception:
        pass


def _calc_typing_delay(text: str) -> float:
    """Calculate realistic typing delay based on reply length (5 to 10 seconds)."""
    if not text:
        return 5.0
    length = len(text)
    delay = 5.0 + min(length / 80.0, 5.0)
    delay += random.uniform(-0.5, 0.8)
    return max(5.0, min(delay, 10.0))


class FAQHandler:
    def __init__(
        self,
        bot: TeleBot,
        registration_service: RegistrationService = None,
        support_service: SupportService = None,
        onboarding_service: OnboardingService = None
    ):
        self.bot = bot
        self.video_service = VideoService(bot)
        self.support_service = support_service or SupportService(bot)
        self.registration_service = registration_service or RegistrationService(bot)
        self.onboarding_service = onboarding_service or OnboardingService(bot)

    def _process_combined_message(self, telegram_id: int, combined_text: str, user: dict):
        """Actually process the (possibly combined) user message after debounce."""
        try:
            bot = self.bot
            text = sanitize_text(combined_text)
            if not text:
                return

            response = ai_service.generate_response(text, user)

            if response.get("support_needed"):
                ticket = self.support_service.create_ticket(
                    telegram_id,
                    text,
                    response.get("intent", "SUPPORT")
                )
                if ticket and ticket.get("id"):
                    self.support_service.notify_admin_about_ticket(ticket)
                reply_text = response.get(
                    "response",
                    "I have forwarded your query to the support team. They will get back to you shortly."
                )
                delay = _calc_typing_delay(reply_text)
                _send_typing(bot, telegram_id, delay)
                bot.send_message(telegram_id, reply_text)
                return

            reply_text = response.get(
                "response",
                "I understood your question. If you need more help, just tell me."
            )

            delay = _calc_typing_delay(reply_text)
            _send_typing(bot, telegram_id, delay)
            bot.send_message(telegram_id, reply_text)

            # If registration intent → send registration video + perfect caption
            intent = (response.get("intent") or "").upper()
            text_lower = text.lower()
            registration_keywords = [
                "register", "registration", "vip join", "join vip", "how to join",
                "how to register", "joining link", "registration link", "account create",
                "vip registration", "want vip", "join the vip"
            ]
            wants_registration = intent == "REGISTRATION" or any(k in text_lower for k in registration_keywords)

            if wants_registration:
                try:
                    time.sleep(1.0)
                    promo.send_registration_steps(bot, telegram_id)
                    # Also try video with perfect caption
                    from services.promo import send_registration_video
                    if callable(send_registration_video):
                        send_registration_video(bot, telegram_id)
                except Exception as ve:
                    logger.warning(f"Could not send registration content to {telegram_id}: {ve}")
                    try:
                        # Fallback: send video via video service
                        self.video_service.send_faq_video(telegram_id, "REGISTRATION")
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"FAQ process failed for user {telegram_id}: {e}")
            try:
                _send_typing(self.bot, telegram_id, 4.0)
                self.bot.send_message(
                    telegram_id,
                    "Sorry, something went wrong for a moment. Please try again or message support."
                )
            except Exception:
                pass

    def _flush_pending(self, telegram_id: int):
        """Called when debounce timer fires — combine buffered texts and process."""
        with _pending_lock:
            entry = _pending_messages.pop(telegram_id, None)
        if not entry:
            return
        texts = entry.get("texts") or []
        user = entry.get("user") or {}
        combined = " ".join(t.strip() for t in texts if t and t.strip())
        if combined:
            self._process_combined_message(telegram_id, combined, user)

    def register(self):
        bot = self.bot

        def is_faq_eligible(message: Message) -> bool:
            if not message.text or message.text.startswith('/'):
                return False
            telegram_id = message.from_user.id

            if self.onboarding_service.is_in_onboarding(telegram_id):
                return False

            state = self.onboarding_service.get_state(telegram_id)
            if state in ACTIVE_STATES:
                return False

            if self.registration_service.is_awaiting_account_id(telegram_id):
                return False
            if self.registration_service.is_in_registration(telegram_id):
                return False
            if self.support_service.is_awaiting_support(telegram_id):
                return False
            if self.onboarding_service.is_pending_rejection(telegram_id):
                return False

            return True

        @bot.message_handler(func=is_faq_eligible)
        def handle_faq_message(message: Message):
            try:
                telegram_id = message.from_user.id
                user = database.get_user(telegram_id)
                if not user:
                    bot.send_message(
                        telegram_id,
                        "Please start the bot with /start first.",
                        reply_markup=get_start_keyboard()
                    )
                    return

                text = sanitize_text(message.text)
                if not text:
                    return

                # --- 10 second debounce for fragmented messages ---
                with _pending_lock:
                    entry = _pending_messages.get(telegram_id)
                    if entry:
                        # Cancel previous timer and append new text
                        try:
                            entry["timer"].cancel()
                        except Exception:
                            pass
                        entry["texts"].append(text)
                        entry["user"] = user
                    else:
                        entry = {
                            "texts": [text],
                            "user": user,
                            "timer": None
                        }
                        _pending_messages[telegram_id] = entry

                    timer = threading.Timer(
                        DEBOUNCE_SECONDS,
                        self._flush_pending,
                        args=(telegram_id,)
                    )
                    timer.daemon = True
                    entry["timer"] = timer
                    timer.start()

                # Show typing briefly so user knows bot received something
                try:
                    bot.send_chat_action(telegram_id, "typing")
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"FAQ handler failed for user {message.from_user.id}: {e}")

        @bot.callback_query_handler(func=lambda call: call.data == "faq")
        def faq_callback(call: CallbackQuery):
            try:
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                bot.send_message(
                    call.from_user.id,
                    "You can ask me anything about registration, deposits, withdrawals, courses, or access. Just type your question here 😊",
                    reply_markup=get_back_keyboard("back_to_main")
                )
            except Exception as e:
                logger.error(f"FAQ callback failed: {e}")

        @bot.callback_query_handler(func=lambda call: call.data == "end_faq")
        def end_faq_callback(call: CallbackQuery):
            try:
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                bot.send_message(
                    call.from_user.id,
                    "Thank you! Feel free to ask anytime if you need help."
                )
            except Exception as e:
                logger.error(f"End FAQ callback failed: {e}")


def register_faq_handlers(
    bot: TeleBot,
    registration_service: RegistrationService = None,
    support_service: SupportService = None,
    onboarding_service: OnboardingService = None
):
    handler = FAQHandler(bot, registration_service, support_service, onboarding_service)
    handler.register()
