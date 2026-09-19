import logging
from typing import Dict, Any, Optional
from telebot import TeleBot
from config import config
from database import database
from services.ai import ai_service
from utils import get_current_timestamp, get_user_full_name

logger = logging.getLogger(__name__)

class SupportService:
    def __init__(self, bot: TeleBot):
        self.bot = bot
        self.pending_resolutions = {}
        self.awaiting_support = {}

    def set_awaiting_support(self, telegram_id: int):
        self.awaiting_support[telegram_id] = True

    def is_awaiting_support(self, telegram_id: int) -> bool:
        return self.awaiting_support.get(telegram_id, False)

    def clear_awaiting_support(self, telegram_id: int):
        if telegram_id in self.awaiting_support:
            del self.awaiting_support[telegram_id]

    def create_ticket(self, telegram_id: int, message: str, intent: str = "SUPPORT") -> Dict[str, Any]:
        try:
            ticket_data = {
                "telegram_id": telegram_id,
                "message": message,
                "intent": intent,
                "status": "open"
            }
            result = database.create_support_ticket(ticket_data)
            if result:
                logger.info(f"Support ticket {result.get('id')} created for user {telegram_id}")
                return result
            return {"success": False, "error": "Failed to create ticket"}
        except Exception as e:
            logger.error(f"Failed to create support ticket: {e}")
            return {"success": False, "error": str(e)}

    def notify_admin_about_ticket(self, ticket: Dict[str, Any]) -> bool:
        try:
            telegram_id = ticket.get("telegram_id")
            if not telegram_id:
                logger.error("Ticket has no telegram_id")
                return False
            user = database.get_user(telegram_id)
            admin_ids = config.get_admin_ids()
            message = f"🎫 SUPPORT REQUIRED\n\n"
            message += f"👤 User: {get_user_full_name(user) if user else 'Unknown'}\n"
            message += f"🆔 Telegram ID: {telegram_id}\n"
            if user and user.get("username"):
                message += f"📱 Username: @{user.get('username')}\n"
            message += f"📝 Ticket #{ticket.get('id')}\n"
            message += f"📌 Intent: {ticket.get('intent', 'SUPPORT')}\n"
            message += f"\n💬 Message:\n{ticket.get('message', '')[:500]}\n"
            message += f"\n📅 Created: {ticket.get('created_at', 'N/A')}"
            for admin_id in admin_ids:
                try:
                    self.bot.send_message(admin_id, message)
                    logger.info(f"Support ticket notification sent to admin {admin_id}")
                except Exception as e:
                    logger.error(f"Failed to send notification to admin {admin_id}: {e}")
            return True
        except Exception as e:
            logger.error(f"Failed to notify admin about ticket: {e}")
            return False

    def resolve_ticket(self, ticket_id: int, admin_id: int, resolution_notes: str) -> Dict[str, Any]:
        try:
            ticket = database.get_support_ticket(ticket_id)
            if not ticket:
                return {"success": False, "error": "Ticket not found"}
            if ticket.get("status") == "resolved":
                return {"success": False, "error": "Ticket already resolved"}
            database.update_support_ticket(ticket_id, {
                "status": "resolved",
                "assigned_to": admin_id,
                "resolved_at": get_current_timestamp(),
                "resolution_notes": resolution_notes
            })
            database.create_admin_log({
                "admin_id": admin_id,
                "action": "resolve_ticket",
                "target_id": ticket_id,
                "target_type": "support_ticket",
                "details": {"resolution_notes": resolution_notes}
            })
            logger.info(f"Support ticket {ticket_id} resolved by admin {admin_id}")
            return {"success": True, "message": "Ticket resolved"}
        except Exception as e:
            logger.error(f"Failed to resolve ticket: {e}")
            return {"success": False, "error": str(e)}

    def assign_ticket(self, ticket_id: int, admin_id: int) -> Dict[str, Any]:
        try:
            ticket = database.get_support_ticket(ticket_id)
            if not ticket:
                return {"success": False, "error": "Ticket not found"}
            database.update_support_ticket(ticket_id, {
                "assigned_to": admin_id,
                "status": "assigned"
            })
            database.create_admin_log({
                "admin_id": admin_id,
                "action": "assign_ticket",
                "target_id": ticket_id,
                "target_type": "support_ticket",
                "details": {"assigned_to": admin_id}
            })
            return {"success": True, "message": "Ticket assigned"}
        except Exception as e:
            logger.error(f"Failed to assign ticket: {e}")
            return {"success": False, "error": str(e)}

    def escalate_ticket(self, ticket_id: int) -> Dict[str, Any]:
        try:
            ticket = database.get_support_ticket(ticket_id)
            if not ticket:
                return {"success": False, "error": "Ticket not found"}
            database.update_support_ticket(ticket_id, {
                "status": "escalated"
            })
            admin_ids = config.get_admin_ids()
            message = f"⬆️ TICKET ESCALATED\n\n"
            message += f"Ticket #{ticket_id}\n"
            message += f"User: {ticket.get('telegram_id')}\n"
            message += f"Message: {ticket.get('message', '')[:200]}"
            for admin_id in admin_ids:
                try:
                    self.bot.send_message(admin_id, message)
                except Exception as e:
                    logger.error(f"Failed to send escalation notification: {e}")
            return {"success": True, "message": "Ticket escalated"}
        except Exception as e:
            logger.error(f"Failed to escalate ticket: {e}")
            return {"success": False, "error": str(e)}

    def set_pending_ticket_resolution(self, admin_id: int, ticket_id: int):
        self.pending_resolutions[admin_id] = ticket_id

    def get_pending_ticket_id(self, admin_id: int) -> Optional[int]:
        return self.pending_resolutions.get(admin_id)

    def clear_pending_ticket_resolution(self, admin_id: int):
        if admin_id in self.pending_resolutions:
            del self.pending_resolutions[admin_id]

    def is_pending_ticket_resolution(self, admin_id: int) -> bool:
        return admin_id in self.pending_resolutions