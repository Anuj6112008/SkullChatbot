import logging
from typing import Dict, Any, Optional
from telebot import TeleBot
from config import config
from database import database
from services.channel import ChannelService
from utils import get_current_timestamp, get_user_full_name, create_user_summary

logger = logging.getLogger(__name__)

class VerificationService:
    def __init__(self, bot: TeleBot):
        self.bot = bot
        self.channel_service = ChannelService(bot)

    def approve_registration(self, registration_id: int, admin_id: int) -> Dict[str, Any]:
        try:
            registration = database.get_registration(registration_id)
            if not registration:
                return {"success": False, "error": "Registration not found"}
            if registration.get("verification_status") != "pending":
                return {"success": False, "error": f"Registration is already {registration.get('verification_status')}"}
            telegram_id = registration.get("telegram_id")
            database.update_registration(registration_id, {
                "verification_status": "approved",
                "verified_by": admin_id,
                "verified_at": get_current_timestamp()
            })
            database.update_user(telegram_id, {
                "verification_status": "approved",
                "verified_at": get_current_timestamp(),
                "registered_at": get_current_timestamp()
            })
            self.channel_service.grant_course_access(telegram_id)
            self.channel_service.grant_updates_access(telegram_id)
            database.create_admin_log({
                "admin_id": admin_id,
                "action": "approve_registration",
                "target_id": telegram_id,
                "target_type": "user",
                "details": {"registration_id": registration_id}
            })
            user = database.get_user(telegram_id)
            if user:
                approval_text = self.get_approval_text()
                try:
                    self.bot.send_message(telegram_id, approval_text)
                except Exception as e:
                    logger.error(f"Failed to send approval message to user {telegram_id}: {e}")
            return {
                "success": True,
                "message": "Registration approved",
                "user_id": telegram_id
            }
        except Exception as e:
            logger.error(f"Failed to approve registration: {e}")
            return {"success": False, "error": str(e)}

    def reject_registration(self, registration_id: int, admin_id: int, reason: Optional[str] = None) -> Dict[str, Any]:
        try:
            registration = database.get_registration(registration_id)
            if not registration:
                return {"success": False, "error": "Registration not found"}
            if registration.get("verification_status") != "pending":
                return {"success": False, "error": f"Registration is already {registration.get('verification_status')}"}
            telegram_id = registration.get("telegram_id")
            database.update_registration(registration_id, {
                "verification_status": "rejected",
                "verified_by": admin_id,
                "verified_at": get_current_timestamp(),
                "rejection_reason": reason
            })
            database.update_user(telegram_id, {
                "verification_status": "rejected"
            })
            database.create_admin_log({
                "admin_id": admin_id,
                "action": "reject_registration",
                "target_id": telegram_id,
                "target_type": "user",
                "details": {"registration_id": registration_id, "reason": reason}
            })
            rejection_text = self.get_rejection_text()
            if reason:
                rejection_text = f"{rejection_text}\n\nReason: {reason}"
            try:
                self.bot.send_message(telegram_id, rejection_text)
            except Exception as e:
                logger.error(f"Failed to send rejection message to user {telegram_id}: {e}")
            return {
                "success": True,
                "message": "Registration rejected",
                "user_id": telegram_id
            }
        except Exception as e:
            logger.error(f"Failed to reject registration: {e}")
            return {"success": False, "error": str(e)}

    def get_pending_verifications(self) -> list:
        try:
            return database.get_pending_verifications()
        except Exception as e:
            logger.error(f"Failed to get pending verifications: {e}")
            return []

    def get_approval_text(self) -> str:
        try:
            setting = database.get_setting("approval_text")
            if setting:
                return setting.get("value", "Your registration has been approved! Welcome to the course.")
            return "Your registration has been approved! Welcome to the course."
        except Exception as e:
            logger.error(f"Failed to get approval text: {e}")
            return "Your registration has been approved! Welcome to the course."

    def get_rejection_text(self) -> str:
        try:
            setting = database.get_setting("rejection_text")
            if setting:
                return setting.get("value", "Your registration has been rejected. Please contact support for more information.")
            return "Your registration has been rejected. Please contact support for more information."
        except Exception as e:
            logger.error(f"Failed to get rejection text: {e}")
            return "Your registration has been rejected. Please contact support for more information."

    def get_welcome_text(self) -> str:
        try:
            setting = database.get_setting("welcome_text")
            if setting:
                return setting.get("value", "Welcome to our platform!")
            return "Welcome to our platform!"
        except Exception as e:
            logger.error(f"Failed to get welcome text: {e}")
            return "Welcome to our platform!"

    def get_registration_cta_text(self) -> str:
        try:
            setting = database.get_setting("registration_cta_text")
            if setting:
                return setting.get("value", "Please register to get started.")
            return "Please register to get started."
        except Exception as e:
            logger.error(f"Failed to get registration CTA text: {e}")
            return "Please register to get started."

    def notify_admin_about_registration(self, registration: Dict[str, Any]) -> bool:
        try:
            if not registration:
                logger.error("notify_admin_about_registration called with empty registration data")
                return False
            telegram_id = registration.get("telegram_id")
            user = database.get_user(telegram_id)
            if not user:
                return False
            admin_ids = config.get_admin_ids()
            message = f"🔔 NEW REGISTRATION\n\n"
            message += f"👤 Name: {get_user_full_name(user)}\n"
            message += f"🆔 Telegram ID: {telegram_id}\n"
            if user.get("username"):
                message += f"📱 Username: @{user.get('username')}\n"
            message += f"\n📋 Registration Details:\n"
            reg_data = registration.get("registration_data", {})
            if isinstance(reg_data, dict):
                for key, value in reg_data.items():
                    if key not in ["telegram_id", "id", "created_at", "updated_at"]:
                        message += f"{key.title()}: {value}\n"
            else:
                message += f"{str(reg_data)}\n"
            message += f"\n📅 Registered: {registration.get('created_at', 'N/A')}"
            for admin_id in admin_ids:
                try:
                    self.bot.send_message(admin_id, message)
                    logger.info(f"Registration notification sent to admin {admin_id}")
                except Exception as e:
                    logger.error(f"Failed to send notification to admin {admin_id}: {e}")
            return True
        except Exception as e:
            logger.error(f"Failed to notify admin about registration: {e}")
            return False

    def get_user_verification_status(self, telegram_id: int) -> Dict[str, Any]:
        try:
            user = database.get_user(telegram_id)
            if not user:
                return {"exists": False, "status": "not_found"}
            registration = database.get_registration_by_user(telegram_id)
            return {
                "exists": True,
                "user_status": user.get("status"),
                "verification_status": user.get("verification_status"),
                "registration_status": user.get("registration_status"),
                "registration_id": registration.get("id") if registration else None,
                "registration_verified": registration.get("verification_status") if registration else None,
                "course_access": user.get("course_access", False),
                "updates_access": user.get("updates_access", False),
                "paid_user": user.get("paid_user", False)
            }
        except Exception as e:
            logger.error(f"Failed to get user verification status: {e}")
            return {"exists": False, "status": "error", "error": str(e)}