import logging
import time
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from config import config
from database import database
from services.video import VideoService
from services.verification import VerificationService
from services.registration import RegistrationService
from services.support import SupportService
from services.channel import ChannelService
from services.onboarding import OnboardingService, STATE_AWAITING_EXPERIENCE, ACTIVE_STATES
from keyboards import get_start_keyboard, get_back_keyboard, get_registration_cancel_keyboard
from utils import get_current_timestamp

logger = logging.getLogger(__name__)


def _send_typing(bot: TeleBot, chat_id: int, delay: float = 1.5):
    """Show realistic 'typing...' indicator in chat header before sending message."""
    try:
        bot.send_chat_action(chat_id, "typing")
        time.sleep(delay)
    except Exception:
        pass


def register_start_handlers(
    bot: TeleBot,
    registration_service: RegistrationService = None,
    support_service: SupportService = None,
    onboarding_service: OnboardingService = None
):
    video_service = VideoService(bot)
    verification_service = VerificationService(bot)
    channel_service = ChannelService(bot)
    registration_service = registration_service or RegistrationService(bot)
    support_service = support_service or SupportService(bot)
    onboarding_service = onboarding_service or OnboardingService(bot)

    @bot.message_handler(commands=['start'])
    def start_command(message: Message):
        try:
            user = message.from_user
            telegram_id = user.id
            username = user.username
            first_name = user.first_name
            last_name = user.last_name

            user_data = database.get_user(telegram_id)
            if not user_data:
                user_data = database.create_user({
                    "telegram_id": telegram_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "member_type": "normal",
                    "joined_at": get_current_timestamp(),
                    "last_activity": get_current_timestamp()
                })
            else:
                database.update_user(telegram_id, {
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "last_activity": get_current_timestamp()
                })

            current_state = user_data.get("onboarding_state") if user_data else None

            # 1. If user is already an approved VIP member
            if user_data and user_data.get("verification_status") == "approved":
                _send_typing(bot, telegram_id, 1.2)
                bot.send_message(
                    telegram_id,
                    "Welcome back! You are an active VIP member. Feel free to ask any questions or reach out to support.",
                    reply_markup=get_start_keyboard()
                )
                return

            # 2. If user is already in the middle of registration
            if current_state in ACTIVE_STATES and current_state != STATE_AWAITING_EXPERIENCE:
                _send_typing(bot, telegram_id, 1.2)
                bot.send_message(
                    telegram_id,
                    "Mee registration inka process lo undi. Let's continue where we left off!"
                )
                return

            # 3. Check if user has joined or requested the dynamic Free Channel
            target_free_channel_id = int(config.get_free_channel_id()) if config.get_free_channel_id() else int(config.FREE_CHANNEL_ID)
            is_member = channel_service.is_user_in_channel(telegram_id, target_free_channel_id)

            if not is_member:
                free_link = config.get_free_channel_link() or "https://t.me/+3zlZ8oTobb5lODc9"
                _send_typing(bot, telegram_id, 1.5)
                bot.send_message(
                    telegram_id,
                    "Hello! 👋 Skull Trading Group lo participate cheyadaniki, mundu ga kinda link dwara maa Free Channel lo Join Request pettandi:\n\n"
                    f"👉 {free_link}\n\n"
                    "Mee join request approve avvagane, mana VIP onboarding start avthundi! 😊"
                )
                return

            # 4. Start Onboarding directly with typing pauses
            _send_typing(bot, telegram_id, 1.5)
            bot.send_message(telegram_id, "Hello, Im NIsha From Skull Support Team")

            _send_typing(bot, telegram_id, 1.5)
            bot.send_message(telegram_id, "Indake mee Joining request Accept chesa")

            _send_typing(bot, telegram_id, 1.2)
            bot.send_message(telegram_id, "Meeku Trading experience unda?")

            onboarding_service.set_state(telegram_id, STATE_AWAITING_EXPERIENCE)

        except Exception as e:
            logger.error(f"Start command failed for user {message.from_user.id}: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == "start_registration")
    def start_registration_callback(call: CallbackQuery):
        try:
            telegram_id = call.from_user.id
            user_data = database.get_user(telegram_id)
            if not user_data:
                return
            if user_data.get("verification_status") == "approved":
                bot.send_message(telegram_id, "You are already registered and verified! ✅")
                return
            _send_typing(bot, telegram_id, 1.0)
            bot.send_message(
                telegram_id,
                "📝 Registration\n\nPlease enter your trading account ID:",
                reply_markup=get_registration_cancel_keyboard()
            )
            registration_service.set_registration_state(telegram_id, "awaiting_account_id")
        except Exception as e:
            logger.error(f"Start registration callback failed: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == "faq")
    def faq_callback(call: CallbackQuery):
        try:
            _send_typing(bot, call.from_user.id, 1.0)
            bot.send_message(
                call.from_user.id,
                "❓ FAQ\n\nAsk me any question about registration, deposits, withdrawals, courses, or access.",
                reply_markup=get_back_keyboard("back_to_main")
            )
        except Exception as e:
            logger.error(f"FAQ callback failed: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == "support")
    def support_callback(call: CallbackQuery):
        try:
            telegram_id = call.from_user.id
            support_service.set_awaiting_support(telegram_id)
            _send_typing(bot, telegram_id, 1.0)
            bot.send_message(
                telegram_id,
                "🆘 Support\n\nPlease describe your issue in your next message and I'll create a support ticket.",
                reply_markup=get_back_keyboard("back_to_main")
            )
        except Exception as e:
            logger.error(f"Support callback failed: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
    def back_to_main_callback(call: CallbackQuery):
        try:
            welcome_text = verification_service.get_welcome_text()
            bot.edit_message_text(
                f"{welcome_text}\n\nChoose an option:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=get_start_keyboard()
            )
        except Exception as e:
            logger.error(f"Back to main callback failed: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == "noop")
    def noop_callback(call: CallbackQuery):
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    return registration_service, support_service
