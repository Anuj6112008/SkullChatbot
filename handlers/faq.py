import logging
import time
import random
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from config import config
from database import database
from services.ai import ai_service
from services.video import VideoService
from services.support import SupportService
from services.registration import RegistrationService
from services.onboarding import OnboardingService, ACTIVE_STATES
from keyboards import get_start_keyboard, get_back_keyboard
from utils import sanitize_text

logger = logging.getLogger(__name__)


def _send_typing(bot: TeleBot, chat_id: int, delay: float = 2.0):
    """Show realistic typing indicator. Delay based on reply length (5-10s range)."""
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
    # Base 5s + extra based on length, capped at 10s
    delay = 5.0 + min(length / 80.0, 5.0)
    # Small random variation so it feels human
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

                # Generate AI response first
                response = ai_service.generate_response(text, user)

                # Support ticket path
                if response.get("support_needed"):
                    ticket = self.support_service.create_ticket(
                        telegram_id,
                        text,
                        response.get("intent", "SUPPORT")
                    )
                    if ticket and ticket.get("id"):
                        self.support_service.notify_admin_about_ticket(ticket)
                    reply_text = response.get("response", "Mee query support team ki forward chesam. Thvaralo reply istharu.")
                    delay = _calc_typing_delay(reply_text)
                    _send_typing(bot, telegram_id, delay)
                    bot.send_message(telegram_id, reply_text)
                    return

                reply_text = response.get("response", "Mee question ardhamaindi. More details kosam support team ni contact avvandi.")

                # Realistic typing delay (5-10 seconds based on reply length)
                delay = _calc_typing_delay(reply_text)
                _send_typing(bot, telegram_id, delay)

                bot.send_message(telegram_id, reply_text)

                # If user is asking about registration / VIP join → also send registration video
                intent = (response.get("intent") or "").upper()
                text_lower = text.lower()
                registration_keywords = [
                    "register", "registration", "vip join", "vip lo", "join avvali",
                    "link pampu", "how to join", "how to register", "account create",
                    "registration ela", "vip registration", "join cheyyali"
                ]
                wants_registration = intent == "REGISTRATION" or any(k in text_lower for k in registration_keywords)

                if wants_registration:
                    try:
                        # Small extra pause then send registration video if available
                        time.sleep(1.2)
                        self.video_service.send_faq_video(telegram_id, "REGISTRATION")
                    except Exception as ve:
                        logger.warning(f"Could not send registration video to {telegram_id}: {ve}")

            except Exception as e:
                logger.error(f"FAQ handler failed for user {message.from_user.id}: {e}")
                try:
                    _send_typing(bot, message.from_user.id, 4.0)
                    bot.send_message(
                        message.from_user.id,
                        "Arre, konchem problem ayindi 😅 Malli try cheyyi or support ki message cheyyi."
                    )
                except Exception:
                    pass

        @bot.callback_query_handler(func=lambda call: call.data == "faq")
        def faq_callback(call: CallbackQuery):
            try:
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                bot.send_message(
                    call.from_user.id,
                    "❓ FAQ Assistant\n\nMee doubts edaina ikkada type cheyandi (Registration, Deposits, Withdrawals, Signals, etc.), nenu help chestha! 😊",
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
                    "Thank you! Feel free to ask anytime if you need help. 🙏"
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
