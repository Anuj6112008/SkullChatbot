import os
import sys
from dotenv import load_dotenv

load_dotenv()


def _resolve_timezone():
    """Resolve a canonical timezone string recognized by pytz and APScheduler."""
    raw = os.getenv("SCHEDULER_TIMEZONE", "Asia/Kolkata") or "Asia/Kolkata"
    if "calcutta" in raw.lower():
        raw = "Asia/Kolkata"

    try:
        import pytz
        if raw in pytz.all_timezones:
            return raw
        if "Asia/Kolkata" in pytz.all_timezones:
            return "Asia/Kolkata"
    except Exception:
        pass
    return "UTC"


class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    ADMIN_ID = os.getenv("ADMIN_ID")
    FREE_CHANNEL_ID = os.getenv("FREE_CHANNEL_ID")
    PAID_CHANNEL_ID = os.getenv("PAID_CHANNEL_ID", "")
    UPDATES_CHANNEL_ID = os.getenv("UPDATES_CHANNEL_ID", "")
    MEDIA_DIR = os.getenv("MEDIA_DIR", "media")
    PROMPTS_DIR = os.getenv("PROMPTS_DIR", "prompts")
    SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.txt")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "bot.log")

    # Followup / scheduler
    FOLLOWUP_INTERVAL_HOURS = int(os.getenv("FOLLOWUP_INTERVAL_HOURS", "24"))
    MAX_FOLLOWUP_DAYS = int(os.getenv("MAX_FOLLOWUP_DAYS", "30"))
    DAILY_SCHEDULED_POSTS = int(os.getenv("DAILY_SCHEDULED_POSTS", "10"))
    SCHEDULER_TIMEZONE = _resolve_timezone()

    BROADCAST_BATCH_SIZE = int(os.getenv("BROADCAST_BATCH_SIZE", "50"))
    BROADCAST_DELAY_SECONDS = float(os.getenv("BROADCAST_DELAY_SECONDS", "1.0"))
    RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))
    RETRY_DELAY_SECONDS = float(os.getenv("RETRY_DELAY_SECONDS", "2.0"))

    # AI
    AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.7"))
    AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "512"))
    AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-oss-120b")

    # Contact / links
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "")
    SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "")
    REGISTRATION_LINK = os.getenv("REGISTRATION_LINK", "")

    # Media / video
    ALLOWED_VIDEO_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv"]
    MAX_VIDEO_SIZE_MB = int(os.getenv("MAX_VIDEO_SIZE_MB", "50"))

    # ---- Client-specific flow config ----
    # Registration / joining link shown to users (Student Joining Link)
    STUDENT_JOINING_LINK = os.getenv("STUDENT_JOINING_LINK", "")
    # Free channel link sent on profit questions
    FREE_CHANNEL_LINK = os.getenv("FREE_CHANNEL_LINK", "")

    # Capital thresholds (INR)
    CAPITAL_LOW_THRESHOLD = int(os.getenv("CAPITAL_LOW_THRESHOLD", "4999"))
    CAPITAL_MID_THRESHOLD = int(os.getenv("CAPITAL_MID_THRESHOLD", "9999"))

    # Hot-lead followup timings (in minutes) for the FIRST DAY only
    HOT_LEAD_DAY1_DELAYS = [
        int(x) for x in os.getenv(
            "HOT_LEAD_DAY1_DELAYS", "15,30,60,300"
        ).split(",") if x.strip()
    ]
    # Max followups on day 2 and beyond (per day)
    HOT_LEAD_DAY2_PER_DAY = int(os.getenv("HOT_LEAD_DAY2_PER_DAY", "2"))
    # Idle minutes before a user is considered "left mid-conversation"
    HOT_LEAD_IDLE_MINUTES = int(os.getenv("HOT_LEAD_IDLE_MINUTES", "10"))

    # Testimonials media
    TESTIMONIALS_DIR = os.getenv("TESTIMONIALS_DIR", "media/testimonials")
    TESTIMONIALS_COUNT = int(os.getenv("TESTIMONIALS_COUNT", "8"))

    # Registration tutorial video (filename inside MEDIA_DIR)
    REGISTRATION_VIDEO_FILE = os.getenv("REGISTRATION_VIDEO_FILE", "registration.mp4")

    def __init__(self):
        self.validate()

    def validate(self):
        required = [
            ("BOT_TOKEN", self.BOT_TOKEN),
            ("GROQ_API_KEY", self.GROQ_API_KEY),
            ("SUPABASE_URL", self.SUPABASE_URL),
            ("SUPABASE_KEY", self.SUPABASE_KEY),
            ("ADMIN_ID", self.ADMIN_ID),
            ("FREE_CHANNEL_ID", self.FREE_CHANNEL_ID),
        ]
        missing = [name for name, value in required if not value]
        if missing:
            sys.exit(f"Missing required environment variables: {', '.join(missing)}")

        try:
            int(self.ADMIN_ID)
        except ValueError:
            sys.exit("ADMIN_ID must be a valid integer")

        try:
            int(self.FREE_CHANNEL_ID)
        except ValueError:
            sys.exit("FREE_CHANNEL_ID must be a valid integer")

        if self.PAID_CHANNEL_ID:
            try:
                int(self.PAID_CHANNEL_ID)
            except ValueError:
                sys.exit("PAID_CHANNEL_ID must be a valid integer")

        if self.UPDATES_CHANNEL_ID:
            try:
                int(self.UPDATES_CHANNEL_ID)
            except ValueError:
                sys.exit("UPDATES_CHANNEL_ID must be a valid integer")

        if not os.path.exists(self.MEDIA_DIR):
            try:
                os.makedirs(self.MEDIA_DIR, exist_ok=True)
            except OSError:
                sys.exit(f"Failed to create media directory: {self.MEDIA_DIR}")

        if not os.path.exists(self.PROMPTS_DIR):
            try:
                os.makedirs(self.PROMPTS_DIR, exist_ok=True)
            except OSError:
                sys.exit(f"Failed to create prompts directory: {self.PROMPTS_DIR}")

        # testimonials directory
        if not os.path.exists(self.TESTIMONIALS_DIR):
            try:
                os.makedirs(self.TESTIMONIALS_DIR, exist_ok=True)
            except OSError:
                pass

        if self.LOG_LEVEL.upper() not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            sys.exit("LOG_LEVEL must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL")

        if self.FOLLOWUP_INTERVAL_HOURS < 1:
            sys.exit("FOLLOWUP_INTERVAL_HOURS must be at least 1")

        if self.MAX_FOLLOWUP_DAYS < 1:
            sys.exit("MAX_FOLLOWUP_DAYS must be at least 1")

        if self.DAILY_SCHEDULED_POSTS < 1:
            sys.exit("DAILY_SCHEDULED_POSTS must be at least 1")

        if self.BROADCAST_BATCH_SIZE < 1:
            sys.exit("BROADCAST_BATCH_SIZE must be at least 1")

        if self.AI_TEMPERATURE < 0 or self.AI_TEMPERATURE > 2:
            sys.exit("AI_TEMPERATURE must be between 0 and 2")

        if self.AI_MAX_TOKENS < 1:
            sys.exit("AI_MAX_TOKENS must be at least 1")

        if self.MAX_VIDEO_SIZE_MB < 1:
            sys.exit("MAX_VIDEO_SIZE_MB must be at least 1")

    def get_admin_ids(self):
        ids = [int(self.ADMIN_ID)]
        extra = os.getenv("EXTRA_ADMIN_IDS", "")
        if extra:
            for item in extra.split(","):
                item = item.strip()
                if item:
                    try:
                        ids.append(int(item))
                    except ValueError:
                        pass
        return ids

    def is_admin(self, telegram_id):
        return telegram_id in self.get_admin_ids()

    def get_channel_ids(self):
        channels = [int(self.FREE_CHANNEL_ID)]
        if self.PAID_CHANNEL_ID:
            channels.append(int(self.PAID_CHANNEL_ID))
        if self.UPDATES_CHANNEL_ID:
            channels.append(int(self.UPDATES_CHANNEL_ID))
        return channels

    def get_media_path(self, filename):
        return os.path.join(self.MEDIA_DIR, filename)

    def get_prompt_path(self, filename=None):
        if filename is None:
            filename = self.SYSTEM_PROMPT_FILE
        return os.path.join(self.PROMPTS_DIR, filename)

    def get_joining_link(self):
        """Return the user-facing Student Joining Link (checks Supabase dynamic setting first, fallback to .env)."""
        try:
            from database import database
            setting = database.get_setting("student_joining_link")
            if setting and setting.get("value"):
                val = str(setting["value"]).strip()
                if val:
                    return val
        except Exception:
            pass
        return self.STUDENT_JOINING_LINK or self.REGISTRATION_LINK or ""

    def get_vip_resources_message(self):
        """Return dynamic VIP resources message & links from Supabase settings."""
        try:
            from database import database
            setting = database.get_setting("vip_resources_message")
            if setting and setting.get("value"):
                val = str(setting["value"]).strip()
                if val:
                    return val
        except Exception:
            pass
        return (
            "Here are the VIP resources 👇\n\n"
            "📚 Complete Trading Course & Lessons\n"
            "📈 VIP Signals Channel Access\n"
            "🚀 PMS Compounding Strategy Calculator\n"
            "🤖 Automated Bot Beta Access\n\n"
            "Mee trading start cheyandi and doubts unte support team ni contact avvandi!"
        )

    def get_free_channel_link(self):
        return self.FREE_CHANNEL_LINK or ""

    def get_testimonials_path(self):
        return self.TESTIMONIALS_DIR

    def get_registration_video_path(self):
        return os.path.join(self.MEDIA_DIR, self.REGISTRATION_VIDEO_FILE)


config = Config()