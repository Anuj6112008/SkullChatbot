import logging
import os
import sys
from telebot import TeleBot
from config import config
from database import database
from services.scheduler import SchedulerService
from services.onboarding import OnboardingService
from handlers import (
    register_start_handlers,
    register_join_request_handlers,
    register_registration_handlers,
    register_onboarding_handlers,
    register_faq_handlers,
    register_support_handlers,
    register_broadcast_handlers,
    register_admin_handlers
)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

bot = TeleBot(config.BOT_TOKEN, threaded=False)
onboarding_service = OnboardingService(bot)
scheduler = SchedulerService(bot, onboarding_service)

def register_all_handlers():
    registration_service, support_service = register_start_handlers(bot)
    register_join_request_handlers(bot, onboarding_service)
    register_registration_handlers(bot, registration_service)
    register_onboarding_handlers(bot, onboarding_service)
    register_faq_handlers(bot, registration_service, support_service, onboarding_service)
    register_support_handlers(bot, support_service)
    register_broadcast_handlers(bot)
    register_admin_handlers(bot)
    logger.info("All handlers registered")

def start_scheduler():
    scheduler.start()
    logger.info("Scheduler started")

def start_bot_polling():
    logger.info("Starting bot polling...")
    import time
    while True:
        try:
            bot.polling(non_stop=True, timeout=60, long_polling_timeout=60)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
            logger.info("Reconnecting in 5 seconds...")
            try:
                bot.stop_polling()
            except Exception:
                pass
            time.sleep(5)

def main():
    try:
        logger.info("Starting Telegram Course Bot...")
        logger.info(f"Bot Token: {config.BOT_TOKEN[:10]}...")
        logger.info(f"Admin ID: {config.ADMIN_ID}")
        logger.info(f"Free Channel: {config.FREE_CHANNEL_ID}")
        register_all_handlers()
        start_scheduler()
        bot_info = bot.get_me()
        logger.info(f"Bot started: @{bot_info.username} (ID: {bot_info.id})")
        logger.info("Bot is running...")
        start_bot_polling()
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        scheduler.stop()
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        sys.exit(1)