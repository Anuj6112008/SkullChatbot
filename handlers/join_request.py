import logging
import time
from telebot import TeleBot
from telebot.types import ChatJoinRequest, Message
from config import config
from database import database
from services.channel import ChannelService
from services.verification import VerificationService
from services.onboarding import OnboardingService, STATE_AWAITING_EXPERIENCE
from utils import get_current_timestamp

logger = logging.getLogger(__name__)


def _send_typing(bot: TeleBot, chat_id: int, delay: float = 1.5):
    """Show realistic 'typing...' indicator in chat header before sending message."""
    try:
        bot.send_chat_action(chat_id, "typing")
        time.sleep(delay)
    except Exception:
        pass


def register_join_request_handlers(bot: TeleBot, onboarding_service: OnboardingService = None):
    channel_service = ChannelService(bot)
    verification_service = VerificationService(bot)
    onboarding_service = onboarding_service or OnboardingService(bot)

    @bot.chat_join_request_handler()
    def handle_chat_join_request(join_request: ChatJoinRequest):
        try:
            user = join_request.from_user
            telegram_id = user.id
            username = user.username
            first_name = user.first_name
            last_name = user.last_name
            chat_id = join_request.chat.id

            # Dynamic Free Channel ID check
            target_free_channel = str(config.get_free_channel_id())
            if str(chat_id) != target_free_channel:
                return

            logger.info(f"Join request received from user {telegram_id} for target channel {chat_id}")

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

            result = channel_service.handle_join_request(join_request)

            if result.get("success") and result.get("action") == "approved":
                try:
                    # Client's exact Telglish Intro with realistic typing pauses
                    _send_typing(bot, telegram_id, 1.5)
                    bot.send_message(telegram_id, "Hello, Im NIsha From Skull Support Team")

                    _send_typing(bot, telegram_id, 1.5)
                    bot.send_message(telegram_id, "Indake mee Joining request Accept chesa")

                    _send_typing(bot, telegram_id, 1.2)
                    bot.send_message(telegram_id, "Meeku Trading experience unda?")

                    onboarding_service.set_state(telegram_id, STATE_AWAITING_EXPERIENCE)
                except Exception as e:
                    logger.error(f"Failed to send onboarding intro to user {telegram_id}: {e}")
            elif result.get("success") and result.get("action") == "pending":
                try:
                    _send_typing(bot, telegram_id, 1.0)
                    bot.send_message(
                        telegram_id,
                        "Welcome! Your join request has been received. Our team will review it shortly."
                    )
                except Exception as e:
                    logger.error(f"Failed to send pending message to user {telegram_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to handle join request: {e}")

    @bot.message_handler(commands=['approve_join'])
    def approve_join_command(message: Message):
        try:
            if not config.is_admin(message.from_user.id):
                bot.reply_to(message, "You are not authorized to use this command.")
                return
            parts = message.text.split()
            if len(parts) < 2:
                bot.reply_to(message, "Usage: /approve_join <user_id>")
                return
            try:
                user_id = int(parts[1])
            except ValueError:
                bot.reply_to(message, "Invalid user ID")
                return
            user = database.get_user(user_id)
            if not user:
                bot.reply_to(message, "User not found")
                return
            try:
                target_channel_id = int(config.get_free_channel_id())
                bot.approve_chat_join_request(target_channel_id, user_id)
                bot.reply_to(message, f"Join request approved for user {user_id}")
                try:
                    _send_typing(bot, user_id, 1.0)
                    bot.send_message(
                        user_id,
                        "Your join request has been approved! Welcome to the channel."
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {user_id}: {e}")
            except Exception as e:
                bot.reply_to(message, f"Failed to approve join request: {e}")
        except Exception as e:
            logger.error(f"Approve join command failed: {e}")
            bot.reply_to(message, "Error processing request")

    @bot.message_handler(commands=['decline_join'])
    def decline_join_command(message: Message):
        try:
            if not config.is_admin(message.from_user.id):
                bot.reply_to(message, "You are not authorized to use this command.")
                return
            parts = message.text.split()
            if len(parts) < 2:
                bot.reply_to(message, "Usage: /decline_join <user_id>")
                return
            try:
                user_id = int(parts[1])
            except ValueError:
                bot.reply_to(message, "Invalid user ID")
                return
            user = database.get_user(user_id)
            if not user:
                bot.reply_to(message, "User not found")
                return
            try:
                target_channel_id = int(config.get_free_channel_id())
                bot.decline_chat_join_request(target_channel_id, user_id)
                bot.reply_to(message, f"Join request declined for user {user_id}")
            except Exception as e:
                bot.reply_to(message, f"Failed to decline join request: {e}")
        except Exception as e:
            logger.error(f"Decline join command failed: {e}")
            bot.reply_to(message, "Error processing request")
