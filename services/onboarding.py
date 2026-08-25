import logging
import re
from typing import Dict, Any, Optional
from telebot import TeleBot
from database import database
from utils import get_current_timestamp, get_current_datetime

logger = logging.getLogger(__name__)

# Complete Onboarding States (No Screenshot)
STATE_AWAITING_EXPERIENCE = "awaiting_experience"
STATE_AWAITING_NAME = "awaiting_name"
STATE_AWAITING_AGE_OCCUPATION = "awaiting_age_occupation"
STATE_AWAITING_CAPITAL = "awaiting_capital"
STATE_AWAITING_POSITIVE_INTENT = "awaiting_positive_intent"
STATE_AWAITING_ACCOUNT_ID = "awaiting_account_id"
STATE_PENDING_APPROVAL = "pending_approval"
STATE_COMPLETED = "completed"

# All active onboarding states owned by the fixed Q&A flow
ACTIVE_STATES = {
    STATE_AWAITING_EXPERIENCE,
    STATE_AWAITING_NAME,
    STATE_AWAITING_AGE_OCCUPATION,
    STATE_AWAITING_CAPITAL,
    STATE_AWAITING_POSITIVE_INTENT,
    STATE_AWAITING_ACCOUNT_ID,
}

POSITIVE_INTENT_PATTERNS = [
    r"\byes\b", r"\bya\b", r"\byep\b", r"\bok\b", r"\bokay\b", r"\bokie\b",
    r"\bstart\b", r"\blet'?s\s*start\b", r"\binterested\b", r"\bjoin\b",
    r"\bi\s*want\s*to\s*join\b", r"\bready\b", r"\bsure\b", r"\bhaa\b",
    r"\bha\b", r"\byeah\b", r"\bchalo\b", r"\bdone\b", r"\bprocess\b",
    r"\blink\b", r"\bdetails\b"
]


class OnboardingService:
    def __init__(self, bot: TeleBot):
        self.bot = bot
        self.pending_rejection = {}

    def set_pending_rejection(self, admin_id: int, registration_id: int):
        self.pending_rejection[admin_id] = registration_id

    def get_pending_rejection(self, admin_id: int) -> Optional[int]:
        return self.pending_rejection.get(admin_id)

    def clear_pending_rejection(self, admin_id: int):
        if admin_id in self.pending_rejection:
            del self.pending_rejection[admin_id]

    def is_pending_rejection(self, admin_id: int) -> bool:
        return admin_id in self.pending_rejection

    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        return database.get_user(telegram_id)

    def get_state(self, telegram_id: int) -> Optional[str]:
        user = self.get_user(telegram_id)
        if not user:
            return None
        return user.get("onboarding_state")

    def get_data(self, telegram_id: int) -> Dict[str, Any]:
        user = self.get_user(telegram_id)
        if not user:
            return {}
        data = user.get("onboarding_data")
        return data if isinstance(data, dict) else {}

    def set_state(self, telegram_id: int, state: str):
        try:
            database.update_user(telegram_id, {
                "onboarding_state": state,
                "last_activity": get_current_timestamp()
            })
        except Exception as e:
            logger.error(f"Failed to set onboarding state for {telegram_id}: {e}")

    def save_answer(self, telegram_id: int, key: str, value: Any):
        try:
            data = self.get_data(telegram_id)
            data[key] = value
            database.update_user(telegram_id, {
                "onboarding_data": data,
                "last_activity": get_current_timestamp(),
                "last_followup_at": None
            })
        except Exception as e:
            logger.error(f"Failed to save onboarding answer for {telegram_id}: {e}")

    def save_answers_dict(self, telegram_id: int, updates: Dict[str, Any]):
        try:
            data = self.get_data(telegram_id)
            data.update(updates)
            database.update_user(telegram_id, {
                "onboarding_data": data,
                "last_activity": get_current_timestamp(),
                "last_followup_at": None
            })
        except Exception as e:
            logger.error(f"Failed to save onboarding updates for {telegram_id}: {e}")

    def is_in_onboarding(self, telegram_id: int) -> bool:
        state = self.get_state(telegram_id)
        return state in ACTIVE_STATES

    def is_awaiting_account_id(self, telegram_id: int) -> bool:
        return self.get_state(telegram_id) == STATE_AWAITING_ACCOUNT_ID

    def get_display_name(self, telegram_id: int) -> str:
        data = self.get_data(telegram_id)
        if data.get("name"):
            return str(data["name"]).strip()
        user = self.get_user(telegram_id)
        if user and user.get("first_name"):
            return str(user["first_name"]).strip()
        return ""

    def get_active_onboarding_users(self):
        try:
            results = []
            for state in ACTIVE_STATES:
                users = database.select("users", match_conditions={"onboarding_state": state})
                if users:
                    results.extend(users)
            return results
        except Exception as e:
            logger.error(f"Failed to get active onboarding users: {e}")
            return []

    def is_positive_intent(self, text: str) -> bool:
        if not text:
            return False
        clean = text.lower().strip()
        for pattern in POSITIVE_INTENT_PATTERNS:
            if re.search(pattern, clean):
                return True
        return False

    def parse_capital_amount(self, text: str) -> Optional[int]:
        if not text:
            return None
        clean = text.lower().replace(",", "").replace("$", "").replace("₹", "").replace("rs", "").strip()

        k_match = re.search(r"(\d+(?:\.\d+)?)\s*k\b", clean)
        if k_match:
            try:
                return int(float(k_match.group(1)) * 1000)
            except Exception:
                pass

        num_match = re.search(r"\b(\d{3,7})\b", clean)
        if num_match:
            try:
                return int(num_match.group(1))
            except Exception:
                pass

        num_short = re.search(r"\b(\d{1,2})\b", clean)
        if num_short and "$" in text:
            try:
                return int(num_short.group(1)) * 85
            except Exception:
                pass

        return None

    def mark_hot_lead(self, telegram_id: int):
        try:
            today = get_current_datetime().date().isoformat()
            database.update_user(telegram_id, {
                "hot_lead_active": True,
                "hot_lead_first_seen_date": today
            })
        except Exception as e:
            logger.error(f"Failed to mark hot lead for {telegram_id}: {e}")

    def clear_hot_lead(self, telegram_id: int):
        try:
            database.update_user(telegram_id, {
                "hot_lead_active": False,
                "hot_lead_day1_sent_count": 0,
                "hot_lead_day1_last_sent_at": None,
                "hot_lead_day2_sent_count": 0,
                "hot_lead_day2_last_sent_date": None,
                "last_activity": get_current_timestamp()
            })
        except Exception as e:
            logger.error(f"Failed to clear hot lead for {telegram_id}: {e}")

    def increment_hot_lead_day1(self, telegram_id: int):
        try:
            user = self.get_user(telegram_id)
            count = (user.get("hot_lead_day1_sent_count") or 0) + 1 if user else 1
            database.update_user(telegram_id, {
                "hot_lead_day1_sent_count": count,
                "hot_lead_day1_last_sent_at": get_current_timestamp()
            })
            return count
        except Exception as e:
            logger.error(f"Failed to increment hot lead day1 for {telegram_id}: {e}")
            return 0

    def increment_hot_lead_day2(self, telegram_id: int):
        try:
            user = self.get_user(telegram_id)
            count = (user.get("hot_lead_day2_sent_count") or 0) + 1 if user else 1
            today = get_current_datetime().date().isoformat()
            database.update_user(telegram_id, {
                "hot_lead_day2_sent_count": count,
                "hot_lead_day2_last_sent_date": today
            })
            return count
        except Exception as e:
            logger.error(f"Failed to increment hot lead day2 for {telegram_id}: {e}")
            return 0

    def reset_hot_lead_day2_if_new_day(self, telegram_id: int):
        try:
            user = self.get_user(telegram_id)
            if not user:
                return
            today = get_current_datetime().date().isoformat()
            last_date = user.get("hot_lead_day2_last_sent_date")
            if last_date and str(last_date) < today:
                database.update_user(telegram_id, {"hot_lead_day2_sent_count": 0})
        except Exception as e:
            logger.error(f"Failed to reset hot lead day2 for {telegram_id}: {e}")

    def mark_registration_nudge_sent(self, telegram_id: int):
        try:
            database.update_user(telegram_id, {
                "registration_nudge_sent": True,
                "last_activity": get_current_timestamp()
            })
        except Exception as e:
            logger.error(f"Failed to mark registration nudge for {telegram_id}: {e}")

    def get_users_awaiting_account_id(self):
        try:
            return database.select("users", match_conditions={"onboarding_state": STATE_AWAITING_ACCOUNT_ID})
        except Exception as e:
            logger.error(f"Failed to get users awaiting account ID: {e}")
            return []

    def get_users_awaiting_positive_intent(self):
        try:
            return database.select("users", match_conditions={"onboarding_state": STATE_AWAITING_POSITIVE_INTENT})
        except Exception as e:
            logger.error(f"Failed to get users awaiting positive intent: {e}")
            return []

    def get_promo_stage(self, telegram_id: int) -> Optional[str]:
        data = self.get_data(telegram_id)
        return data.get("promo_stage")

    def set_promo_stage(self, telegram_id: int, stage: str):
        try:
            data = self.get_data(telegram_id)
            data["promo_stage"] = stage
            data["promo_stage_at"] = get_current_timestamp()
            database.update_user(telegram_id, {"onboarding_data": data})
        except Exception as e:
            logger.error(f"Failed to set promo stage for {telegram_id}: {e}")

    def clear_promo_stage(self, telegram_id: int):
        try:
            data = self.get_data(telegram_id)
            data.pop("promo_stage", None)
            data.pop("promo_stage_at", None)
            database.update_user(telegram_id, {"onboarding_data": data})
        except Exception as e:
            logger.error(f"Failed to clear promo stage for {telegram_id}: {e}")

    def mark_registration_steps_sent(self, telegram_id: int):
        try:
            data = self.get_data(telegram_id)
            data["registration_steps_sent_at"] = get_current_timestamp()
            data["registration_reminder_sent"] = False
            database.update_user(telegram_id, {"onboarding_data": data})
        except Exception as e:
            logger.error(f"Failed to mark registration steps sent for {telegram_id}: {e}")

    def mark_registration_reminder_sent(self, telegram_id: int):
        try:
            data = self.get_data(telegram_id)
            data["registration_reminder_sent"] = True
            database.update_user(telegram_id, {"onboarding_data": data})
        except Exception as e:
            logger.error(f"Failed to mark registration reminder sent for {telegram_id}: {e}")
