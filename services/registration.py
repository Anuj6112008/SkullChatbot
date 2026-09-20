import os
import logging
import time
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import config
from database import database
from utils import get_current_timestamp

logger = logging.getLogger(__name__)

# State constants
STATE_AWAITING_ACCOUNT_ID = "awaiting_account_id"


class RegistrationService:
    def __init__(self, bot: TeleBot):
        self.bot = bot

    def get_registration_link(self) -> str:
        """Fetch registration link dynamically from database settings, fallback to config."""
        try:
            db_link = database.get_setting("registration_link")
            if db_link and str(db_link).strip():
                return str(db_link).strip()
        except Exception as e:
            logger.warning(f"Could not fetch registration link from DB: {e}")

        # Fallback to config if available
        if hasattr(config, "get_registration_link"):
            return config.get_registration_link()
        return getattr(config, "REGISTRATION_LINK", "https://u3.shortink.io/register?utm_campaign=860595&utm_source=affiliate&utm_medium=sr&a=JP2W2GnQq591r7&al=1786780&ac=skull&cid=973092&code=50START")

    def get_registration_video_source(self):
        """Fetch registration video ID or URL dynamically from database settings."""
        try:
            db_video = database.get_setting("registration_video_source")
            if db_video and str(db_video).strip():
                return str(db_video).strip()
        except Exception as e:
            logger.warning(f"Could not fetch registration video source from DB: {e}")

        if hasattr(config, "get_registration_video_url"):
            return config.get_registration_video_url()
        return getattr(config, "REGISTRATION_VIDEO_URL", None)

    def get_registration_caption(self) -> str:
        """Exact 5-steps registration message with dynamic database link."""
        link = self.get_registration_link()
        return (
            "🔥 𝗝𝗢𝗜𝗡 𝗧𝗛𝗘 𝗩𝗜𝗣 𝗖𝗢𝗠𝗠𝗨𝗡𝗜𝗧𝗬 🔥\n\n"
            "𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲 𝘁𝗵𝗲𝘀𝗲 𝟱 𝘀𝗶𝗺𝗽𝗹𝗲 𝘀𝘁𝗲𝗽𝘀 👇\n\n"
            "🔗 𝗝𝗢𝗜𝗡𝗜𝗡𝗚 𝗟𝗜𝗡𝗞\n"
            f"{link}\n\n"
            "𝟭️⃣ 𝗖𝗥𝗘𝗔𝗧𝗘 𝗔𝗖𝗖𝗢𝗨𝗡𝗧\n"
            "Register a new trading account using the link above. 📝\n\n"
            "𝟮️⃣ 𝗚𝗘𝗧 𝟱𝟬% 𝗕𝗢𝗡𝗨𝗦 🎁\n"
            "Use the joining link to receive a 𝟱𝟬% deposit bonus, subject to platform terms.\n\n"
            "𝟯️⃣ 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 $𝟱𝟬+ 💵\n"
            "Make a minimum deposit of $𝟱𝟬.\n\n"
            "𝟰️⃣ 𝗦𝗘𝗡𝗗 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗜𝗗 🆔\n"
            "Send your 𝟵-𝗱𝗶𝗴𝗶𝘁 trading account ID for manual verification. ✅\n\n"
            "𝗘𝘅𝗮𝗺𝗽𝗹𝗲: 𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵\n\n"
            "𝟱️⃣ 𝗝𝗢𝗜𝗡 𝗩𝗜𝗣 👑\n"
            "Once verified, you’ll be added to the 𝗩𝗜𝗣 𝗖𝗼𝗺𝗺𝘂𝗻𝗶𝘁𝘆.\n\n"
            "💬 𝗡𝗘𝗘𝗗 𝗛𝗘𝗟𝗣?\n"
            "Message me here!"
        )

    def send_registration_steps(self, chat_id: int):
        """Send the registration video along with the dynamic 5-steps caption."""
        caption = self.get_registration_caption()
        video_source = self.get_registration_video_source()

        # Show typing / upload action
        try:
            self.bot.send_chat_action(chat_id, "upload_video")
            time.sleep(1.0)
        except Exception:
            pass

        # 1. Try sending via Database / Config Video Source (File ID or URL)
        if video_source:
            try:
                self.bot.send_video(
                    chat_id=chat_id,
                    video=video_source,
                    caption=caption
                )
                self.set_registration_state(chat_id, STATE_AWAITING_ACCOUNT_ID)
                return
            except Exception as e:
                logger.warning(f"Failed to send video from source '{video_source}': {e}")

        # 2. Try sending from local media folder if available
        local_video_paths = [
            "media/registration.mp4",
            "media/registration_video.mp4",
            "assets/registration.mp4"
        ]
        for path in local_video_paths:
            if os.path.exists(path):
                try:
                    with open(path, "rb") as vf:
                        self.bot.send_video(
                            chat_id=chat_id,
                            video=vf,
                            caption=caption
                        )
                    self.set_registration_state(chat_id, STATE_AWAITING_ACCOUNT_ID)
                    return
                except Exception as e:
                    logger.warning(f"Failed to send local video file {path}: {e}")

        # 3. Fallback to clean formatted text message if video stream is unavailable
        try:
            self.bot.send_message(
                chat_id=chat_id,
                text=caption,
                disable_web_page_preview=True
            )
            self.set_registration_state(chat_id, STATE_AWAITING_ACCOUNT_ID)
        except Exception as e:
            logger.error(f"Failed to send registration message fallback: {e}")

    def set_registration_state(self, telegram_id: int, state: str):
        """Update onboarding / registration state in DB."""
        try:
            database.update_user(telegram_id, {
                "onboarding_state": state,
                "last_activity": get_current_timestamp()
            })
        except Exception as e:
            logger.error(f"Error setting registration state for {telegram_id}: {e}")

    def clear_registration_state(self, telegram_id: int):
        """Clear registration state."""
        self.set_registration_state(telegram_id, "completed")
