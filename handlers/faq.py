import logging
import time
import random
import re
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
from services.verification import VerificationService
from keyboards import get_start_keyboard, get_back_keyboard
from utils import sanitize_text, get_current_timestamp

logger = logging.getLogger(__name__)

# Buffer for fragmented messages: wait 10 seconds for more input before processing
_pending_messages = {}  # telegram_id -> {"texts": [], "timer": Timer, "user": dict}
_pending_lock = threading.Lock()
DEBOUNCE_SECONDS = 10


def _send_typing(bot: TeleBot, chat_id: int, delay: float = 1.5):
    """Show realistic typing indicator."""
    try:
        bot.send_chat_action(chat_id, "typing")
        time.sleep(delay)
    except Exception:
        pass


def _calc_typing_delay(text: str) -> float:
    """Typing delay 3–8 seconds based on reply length (target ~10s max total feel)."""
    if not text:
        return 3.5
    length = len(text)
    delay = 3.0 + min(length / 100.0, 4.5)
    delay += random.uniform(-0.3, 0.5)
    return max(3.0, min(delay, 8.0))


def _looks_like_account_id(text: str) -> str | None:
    """If message is primarily a trading account ID (7-12 digits), return the digits."""
    if not text:
        return None
    cleaned = re.sub(r"[\s\-#]", "", text.strip())
    # Pure digits 7-12 length
    if cleaned.isdigit() and 7 <= len(cleaned) <= 12:
        return cleaned
    # "account id 123456789" style
    m = re.search(r"(?:account\s*id|id|acc(?:ount)?)\s*[:\-]?\s*(\d{7,12})", text, re.I)
    if m:
        return m.group(1)
    # Standalone long number in short message
    m2 = re.search(r"\b(\d{8,12})\b", text)
    if m2 and len(text) < 40:
        return m2.group(1)
    return None


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
        self.verification_service = VerificationService(bot)

    def _submit_account_id(self, telegram_id: int, account_id: str, user: dict):
        """Submit trading account ID to VIP approval even if user started directly."""
        bot = self.bot
        try:
            if user.get("verification_status") == "approved":
                _send_typing(bot, telegram_id, 2.0)
                bot.send_message(telegram_id, "You are already a verified VIP member! ✅")
                return

            if user.get("registration_status") == "pending_verification":
                _send_typing(bot, telegram_id, 2.0)
                bot.send_message(
                    telegram_id,
                    "Your registration is already pending verification. Please wait for admin approval. ⏳"
                )
                return

            first_name = user.get("first_name") or ""
            last_name = user.get("last_name") or ""
            full_name = f"{first_name} {last_name}".strip() or "Trader"
            username = user.get("username") or ""

            registration_data = {
                "telegram_id": telegram_id,
                "registration_data": {
                    "trading_account_id": account_id,
                    "full_name": full_name,
                    "username": username,
                    "source": "direct_chat"
                },
                "verification_status": "pending"
            }
            registration = database.create_registration(registration_data)
            database.update_user(telegram_id, {
                "registration_status": "pending_verification",
                "last_activity": get_current_timestamp()
            })

            _send_typing(bot, telegram_id, 2.5)
            bot.send_message(
                telegram_id,
                "✅ Got your Account ID!\n\n"
                "Your registration is now pending verification.\n"
                "You will be notified once an admin reviews it."
            )

            if registration:
                try:
                    self.verification_service.notify_admin_about_registration(registration)
                except Exception as ne:
                    logger.error(f"Failed to notify admin for direct registration {telegram_id}: {ne}")

            logger.info(f"Direct account ID submitted by {telegram_id}: {account_id}")
        except Exception as e:
            logger.error(f"Direct account ID submit failed for {telegram_id}: {e}")
            bot.send_message(telegram_id, "Something went wrong while submitting your ID. Please try again.")

    def _process_combined_message(self, telegram_id: int, combined_text: str, user: dict):
        """Process the (possibly combined) user message after debounce."""
        try:
            bot = self.bot
            text = sanitize_text(combined_text)
            if not text:
                return

            # If message looks like trading account ID → submit to VIP approval
            account_id = _looks_like_account_id(text)
            if account_id:
                self._submit_account_id(telegram_id, account_id, user)
                return

            # Check direct "VIP" keywords before calling AI to make it instant and accurate
            text_lower = text.lower().strip()
            exact_vip_words = {"vip", "v.i.p", "viip", "join", "register"}
            words_in_text = set(re.findall(r'\b\w+\b', text_lower))

            registration_keywords = [
                "register", "registration", "vip join", "join vip", "how to join",
                "how to register", "joining link", "registration link", "account create",
                "vip registration", "want vip", "join the vip", "vip process", "vip steps",
                "full process", "registration video", "vip video", "process video",
                "registration process", "vip reg", "regesitt", "registation", "regestration",
                "link pampu", "join link", "vip link", "send link", "send video"
            ]

            is_direct_vip = bool(words_in_text & exact_vip_words) or any(k in text_lower for k in registration_keywords)

            if is_direct_vip:
                try:
                    bot.send_chat_action(telegram_id, "upload_video")
                except Exception:
                    pass
                time.sleep(0.5)
                promo.send_registration_steps(bot, telegram_id)
                return

            # If not direct VIP, check AI response
            response = ai_service.generate_response(text, user)

            if response.get("support_needed"):
                ticket = self.support_service.create_ticket(
                    telegram_id, text, response.get("intent", "SUPPORT")
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

            # Check if AI intent is REGISTRATION or AI text mentions sending registration video
            intent = (response.get("intent") or "").upper()
            ai_mentions_video = any(
                phrase in reply_text.lower()
                for phrase in ["sending the vip", "registration video", "sending the video", "vip registration video"]
            )

            wants_registration = intent == "REGISTRATION" or ai_mentions_video

            if wants_registration:
                try:
                    bot.send_chat_action(telegram_id, "upload_video")
                except Exception:
                    pass
                time.sleep(0.5)
                promo.send_registration_steps(bot, telegram_id)
                return

            # Normal AI reply (non-registration)
            delay = _calc_typing_delay(reply_text)
            _send_typing(bot, telegram_id, delay)
            bot.send_message(telegram_id, reply_text)

        except Exception as e:
            logger.error(f"FAQ process failed for user {telegram_id}: {e}")
            try:
                _send_typing(self.bot, telegram_id, 3.0)
                self.bot.send_message(
                    telegram_id,
                    "Sorry, something went wrong for a moment. Please try again."
                )
            except Exception:
                pass

    def _flush_pending(self, telegram_id: int):
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

                # 10 second debounce for fragmented messages
                with _pending_lock:
                    entry = _pending_messages.get(telegram_id)
                    if entry:
                        try:
                            entry["timer"].cancel()
                        except Exception:
                            pass
                        entry["texts"].append(text)
                        entry["user"] = user
                    else:
                        entry = {"texts": [text], "user": user, "timer": None}
                        _pending_messages[telegram_id] = entry

                    timer = threading.Timer(
                        DEBOUNCE_SECONDS,
                        self._flush_pending,
                        args=(telegram_id,)
                    )
                    timer.daemon = True
                    entry["timer"] = timer
                    timer.start()

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
                bot.send_message(call.from_user.id, "Thank you! Feel free to ask anytime if you need help.")
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
