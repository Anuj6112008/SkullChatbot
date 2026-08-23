import logging
import time
from typing import Dict, Any, Optional
from telebot import TeleBot
from telebot.types import ChatJoinRequest
from config import config
from database import database
from utils import get_current_timestamp

logger = logging.getLogger(__name__)


class ChannelService:
    def __init__(self, bot: TeleBot):
        self.bot = bot
        self.free_channel_id = int(config.FREE_CHANNEL_ID)
        self.paid_channel_id = int(config.PAID_CHANNEL_ID) if config.PAID_CHANNEL_ID else None
        self.updates_channel_id = int(config.UPDATES_CHANNEL_ID) if config.UPDATES_CHANNEL_ID else None

    def create_single_use_invite_link(
        self,
        chat_id: Optional[int] = None,
        name: Optional[str] = None,
        expire_hours: int = 24
    ) -> Optional[str]:
        """Create a single-use (member_limit=1) Telegram invite link that expires after 1 join."""
        target_chat = chat_id or self.paid_channel_id
        if not target_chat:
            logger.warning("No target chat configured for single-use invite link.")
            return None

        try:
            expire_date = int(time.time()) + (expire_hours * 3600)
            invite = self.bot.create_chat_invite_link(
                chat_id=target_chat,
                member_limit=1,
                expire_date=expire_date,
                name=name or "VIP_1Time_Access"
            )
            logger.info(f"Generated 1-time invite link for chat {target_chat}: {invite.invite_link}")
            return invite.invite_link
        except Exception as e:
            logger.error(f"Failed to create single-use invite link for chat {target_chat}: {e}")
            return None

    def handle_join_request(self, join_request: ChatJoinRequest) -> Dict[str, Any]:
        try:
            user = join_request.from_user
            telegram_id = user.id
            username = user.username
            first_name = user.first_name
            last_name = user.last_name
            chat_id = join_request.chat.id

            user_data = database.get_user(telegram_id)
            if not user_data:
                user_data = database.create_user({
                    "telegram_id": telegram_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
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

            auto_approve = self.get_auto_approve_setting()
            if auto_approve:
                self.approve_join_request(join_request)
                return {
                    "success": True,
                    "action": "approved",
                    "user_id": telegram_id,
                    "chat_id": chat_id
                }
            else:
                return {
                    "success": True,
                    "action": "pending",
                    "user_id": telegram_id,
                    "chat_id": chat_id
                }
        except Exception as e:
            logger.error(f"Failed to handle join request: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def approve_join_request(self, join_request: ChatJoinRequest) -> bool:
        try:
            self.bot.approve_chat_join_request(join_request.chat.id, join_request.from_user.id)
            logger.info(f"Approved join request for user {join_request.from_user.id} in chat {join_request.chat.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to approve join request: {e}")
            return False

    def decline_join_request(self, join_request: ChatJoinRequest) -> bool:
        try:
            self.bot.decline_chat_join_request(join_request.chat.id, join_request.from_user.id)
            logger.info(f"Declined join request for user {join_request.from_user.id} in chat {join_request.chat.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to decline join request: {e}")
            return False

    def get_auto_approve_setting(self) -> bool:
        try:
            setting = database.get_setting("auto_approve_join_requests")
            if setting:
                value = setting.get("value", "true")
                return value.lower() == "true"
            return True
        except Exception as e:
            logger.error(f"Failed to get auto approve setting: {e}")
            return True

    def grant_course_access(self, telegram_id: int) -> Dict[str, Any]:
        try:
            user = database.get_user(telegram_id)
            if not user:
                return {"success": False, "error": "User not found"}
            database.update_user(telegram_id, {"course_access": True})
            return {"success": True, "message": "Course access granted"}
        except Exception as e:
            logger.error(f"Failed to grant course access: {e}")
            return {"success": False, "error": str(e)}

    def revoke_course_access(self, telegram_id: int) -> Dict[str, Any]:
        try:
            user = database.get_user(telegram_id)
            if not user:
                return {"success": False, "error": "User not found"}
            database.update_user(telegram_id, {"course_access": False})
            return {"success": True, "message": "Course access revoked"}
        except Exception as e:
            logger.error(f"Failed to revoke course access: {e}")
            return {"success": False, "error": str(e)}

    def grant_updates_access(self, telegram_id: int) -> Dict[str, Any]:
        try:
            user = database.get_user(telegram_id)
            if not user:
                return {"success": False, "error": "User not found"}
            database.update_user(telegram_id, {"updates_access": True})
            return {"success": True, "message": "Updates access granted"}
        except Exception as e:
            logger.error(f"Failed to grant updates access: {e}")
            return {"success": False, "error": str(e)}

    def revoke_updates_access(self, telegram_id: int) -> Dict[str, Any]:
        try:
            user = database.get_user(telegram_id)
            if not user:
                return {"success": False, "error": "User not found"}
            database.update_user(telegram_id, {"updates_access": False})
            return {"success": True, "message": "Updates access revoked"}
        except Exception as e:
            logger.error(f"Failed to revoke updates access: {e}")
            return {"success": False, "error": str(e)}

    def mark_paid_user(self, telegram_id: int) -> Dict[str, Any]:
        try:
            user = database.get_user(telegram_id)
            if not user:
                return {"success": False, "error": "User not found"}
            database.update_user(telegram_id, {"paid_user": True})
            self.disable_user_followups(telegram_id)
            return {"success": True, "message": "User marked as paid"}
        except Exception as e:
            logger.error(f"Failed to mark paid user: {e}")
            return {"success": False, "error": str(e)}

    def mark_unpaid_user(self, telegram_id: int) -> Dict[str, Any]:
        try:
            user = database.get_user(telegram_id)
            if not user:
                return {"success": False, "error": "User not found"}
            database.update_user(telegram_id, {"paid_user": False})
            return {"success": True, "message": "User marked as unpaid"}
        except Exception as e:
            logger.error(f"Failed to mark unpaid user: {e}")
            return {"success": False, "error": str(e)}

    def disable_user_followups(self, telegram_id: int) -> Dict[str, Any]:
        try:
            followups = database.get_user_followups(telegram_id)
            for followup in followups:
                database.update_followup(followup["id"], {"enabled": False})
            return {"success": True, "message": "User followups disabled"}
        except Exception as e:
            logger.error(f"Failed to disable user followups: {e}")
            return {"success": False, "error": str(e)}

    def enable_user_followups(self, telegram_id: int) -> Dict[str, Any]:
        try:
            followups = database.get_user_followups(telegram_id)
            for followup in followups:
                database.update_followup(followup["id"], {"enabled": True})
            return {"success": True, "message": "User followups enabled"}
        except Exception as e:
            logger.error(f"Failed to enable user followups: {e}")
            return {"success": False, "error": str(e)}

    def send_message_to_channel(self, channel_id: int, message: str) -> Dict[str, Any]:
        try:
            result = self.bot.send_message(channel_id, message)
            return {"success": True, "message_id": result.message_id}
        except Exception as e:
            logger.error(f"Failed to send message to channel: {e}")
            return {"success": False, "error": str(e)}
