import logging
from typing import Dict, Any, Optional
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import config
from database import database
from services.channel import ChannelService
from utils import get_current_timestamp, get_user_full_name, create_user_summary

logger = logging.getLogger(__name__)


class VerificationService:
    def __init__(self, bot: TeleBot):
        self.bot = bot
        self.channel_service = ChannelService(bot)
        self._register_callbacks()

    def get_verification_channel_id(self) -> Optional[int]:
        """Fetch verification / approvals channel ID dynamically."""
        # 1. Check Supabase database settings
        for key in ["verification_channel_id", "approvals_channel_id", "admin_channel_id"]:
            try:
                db_setting = database.get_setting(key)
                if db_setting:
                    val = db_setting.get("value") if isinstance(db_setting, dict) else db_setting
                    if val and str(val).strip():
                        return int(str(val).strip())
            except Exception:
                pass

        # 2. Check config attributes
        for attr in ["APPROVALS_CHANNEL_ID", "VERIFICATION_CHANNEL_ID", "ADMIN_CHANNEL_ID", "FREE_CHANNEL_ID"]:
            val = getattr(config, attr, None)
            if val:
                try:
                    return int(val)
                except Exception:
                    pass

        return None

    def approve_registration(self, registration_id: int, admin_id: int) -> Dict[str, Any]:
        try:
            registration = database.get_registration(registration_id)
            if not registration:
                return {"success": False, "error": "Registration not found"}
            telegram_id = registration.get("telegram_id")
            database.update_registration(registration_id, {
                "verification_status": "approved",
                "verified_by": admin_id,
                "verified_at": get_current_timestamp()
            })
            database.update_user(telegram_id, {
                "verification_status": "approved",
                "verified_at": get_current_timestamp(),
                "registered_at": get_current_timestamp(),
                "registration_status": "approved"
            })
            try:
                self.channel_service.grant_course_access(telegram_id)
                self.channel_service.grant_updates_access(telegram_id)
            except Exception as ge:
                logger.warning(f"Access grant warning: {ge}")

            database.create_admin_log({
                "admin_id": admin_id,
                "action": "approve_registration",
                "target_id": telegram_id,
                "target_type": "user",
                "details": {"registration_id": registration_id}
            })
            
            # Send approval message to user
            approval_text = self.get_approval_text()
            try:
                self.bot.send_message(telegram_id, approval_text, parse_mode="Markdown")
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
            telegram_id = registration.get("telegram_id")
            database.update_registration(registration_id, {
                "verification_status": "rejected",
                "verified_by": admin_id,
                "verified_at": get_current_timestamp(),
                "rejection_reason": reason
            })
            database.update_user(telegram_id, {
                "verification_status": "rejected",
                "registration_status": "rejected"
            })
            database.create_admin_log({
                "admin_id": admin_id,
                "action": "reject_registration",
                "target_id": telegram_id,
                "target_type": "user",
                "details": {"registration_id": registration_id, "reason": reason}
            })
            rejection_text = self.get_rejection_text()
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

    def mark_already_registered(self, registration_id: int, admin_id: int) -> Dict[str, Any]:
        try:
            registration = database.get_registration(registration_id)
            if not registration:
                return {"success": False, "error": "Registration not found"}
            telegram_id = registration.get("telegram_id")
            database.update_registration(registration_id, {
                "verification_status": "already_registered",
                "verified_by": admin_id,
                "verified_at": get_current_timestamp()
            })
            database.update_user(telegram_id, {
                "verification_status": "already_registered",
                "registration_status": "already_registered"
            })
            database.create_admin_log({
                "admin_id": admin_id,
                "action": "already_registered",
                "target_id": telegram_id,
                "target_type": "user",
                "details": {"registration_id": registration_id}
            })
            notice_text = (
                "⚠️ **Account Notice**\n\n"
                "This trading account ID is already registered or does not meet the eligibility requirements. "
                "Please create a fresh account using our official joining link or contact support for help."
            )
            try:
                self.bot.send_message(telegram_id, notice_text, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send already registered notice to {telegram_id}: {e}")
            return {
                "success": True,
                "message": "Marked as already registered",
                "user_id": telegram_id
            }
        except Exception as e:
            logger.error(f"Failed to mark already registered: {e}")
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
                val = setting.get("value") if isinstance(setting, dict) else setting
                if val:
                    return str(val)
            return "🎉 **CONGRATULATIONS!** Your registration has been approved! Welcome to the VIP Community."
        except Exception as e:
            logger.error(f"Failed to get approval text: {e}")
            return "🎉 **CONGRATULATIONS!** Your registration has been approved! Welcome to the VIP Community."

    def get_rejection_text(self) -> str:
        try:
            setting = database.get_setting("rejection_text")
            if setting:
                val = setting.get("value") if isinstance(setting, dict) else setting
                if val:
                    return str(val)
            return "❌ Your registration was declined. Please ensure you registered via our official link and deposited $50+."
        except Exception as e:
            logger.error(f"Failed to get rejection text: {e}")
            return "❌ Your registration was declined. Please ensure you registered via our official link and deposited $50+."

    def get_welcome_text(self) -> str:
        return "Welcome to Skull VIP Community!"

    def get_registration_cta_text(self) -> str:
        return "Please register to get started."

    def notify_admin_about_registration(self, registration: Dict[str, Any]) -> bool:
        """Send 9-Digit ID submission with exact format and 3 action buttons to Approval Channel & Admins."""
        try:
            if not registration:
                logger.error("notify_admin_about_registration called with empty data")
                return False

            reg_id = registration.get("id") or 0
            telegram_id = registration.get("telegram_id")
            user = database.get_user(telegram_id) or {}
            reg_data = registration.get("registration_data", {})

            trading_id = "N/A"
            if isinstance(reg_data, dict):
                trading_id = reg_data.get("trading_account_id") or reg_data.get("account_id") or "N/A"
            else:
                trading_id = str(reg_data)

            full_name = get_user_full_name(user) if user else (reg_data.get("full_name") or "Trader")
            username_val = user.get("username") or reg_data.get("username")
            username_display = f"@{username_val}" if username_val else "N/A"

            # Exact Requested Format for Channel
            message = (
                "🔔 𝗡𝗘𝗪 𝗧𝗥𝗔𝗗𝗜𝗡𝗚 𝗜𝗗 𝗦𝗨𝗕𝗠𝗜𝗦𝗦𝗜𝗢𝗡\n\n"
                f"📊 𝗧𝗿𝗮𝗱𝗶𝗻𝗴 𝗜𝗗: `{trading_id}`\n"
                f"👤 𝗨𝘀𝗲𝗿 𝗜𝗗: `{telegram_id}`\n"
                f"🏷️ 𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲: {username_display}\n"
                f"📛 𝗧𝗲𝗹𝗲𝗴𝗿𝗮𝗺 𝗡𝗮𝗺𝗲: {full_name}\n"
                f"📅 𝗗𝗮𝘁𝗲: {registration.get('created_at', get_current_timestamp())}"
            )

            # 3 Working Action Buttons
            keyboard = InlineKeyboardMarkup(row_width=2)
            btn_approve = InlineKeyboardButton("✅ Approve", callback_data=f"v_app_{reg_id}_{telegram_id}")
            btn_reject = InlineKeyboardButton("❌ Reject", callback_data=f"v_rej_{reg_id}_{telegram_id}")
            btn_already = InlineKeyboardButton("⚠️ Already Registered", callback_data=f"v_alr_{reg_id}_{telegram_id}")
            keyboard.add(btn_approve, btn_reject)
            keyboard.add(btn_already)

            sent_anywhere = False

            # 1. Primary: Send to Approval / Verification Channel
            chan_id = self.get_verification_channel_id()
            if chan_id:
                try:
                    self.bot.send_message(
                        chat_id=chan_id,
                        text=message,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                    sent_anywhere = True
                    logger.info(f"Verification request sent to Channel {chan_id}")
                except Exception as ce:
                    logger.error(f"Failed to post to channel {chan_id}: {ce}")

            # 2. Also send to individual Admins
            admin_ids = config.get_admin_ids()
            for admin_id in admin_ids:
                try:
                    self.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                    sent_anywhere = True
                except Exception as ae:
                    logger.error(f"Failed to send to admin {admin_id}: {ae}")

            return sent_anywhere

        except Exception as e:
            logger.error(f"Failed to notify admin about registration: {e}", exc_info=True)
            return False

    def _register_callbacks(self):
        """Auto-register button callbacks for Approve, Reject, and Already Registered."""
        bot = self.bot

        @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("v_app_"))
        def on_approve(call: CallbackQuery):
            try:
                parts = call.data.split("_")
                reg_id = int(parts[2])
                admin_id = call.from_user.id
                result = self.approve_registration(reg_id, admin_id)
                admin_tag = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name
                if result.get("success"):
                    bot.edit_message_text(
                        f"{call.message.text}\n\n━━━━━━━━━━━━━━━\n✅ 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 by {admin_tag}",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    bot.answer_callback_query(call.id, "Approved successfully! ✅")
                else:
                    bot.answer_callback_query(call.id, f"Error: {result.get('error')}")
            except Exception as e:
                logger.error(f"Approve callback error: {e}")
                bot.answer_callback_query(call.id, "Error processing approval.")

        @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("v_rej_"))
        def on_reject(call: CallbackQuery):
            try:
                parts = call.data.split("_")
                reg_id = int(parts[2])
                admin_id = call.from_user.id
                result = self.reject_registration(reg_id, admin_id)
                admin_tag = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name
                if result.get("success"):
                    bot.edit_message_text(
                        f"{call.message.text}\n\n━━━━━━━━━━━━━━━\n❌ 𝗥𝗘𝗝𝗘𝗖𝗧𝗘𝗗 by {admin_tag}",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    bot.answer_callback_query(call.id, "Rejected successfully! ❌")
                else:
                    bot.answer_callback_query(call.id, f"Error: {result.get('error')}")
            except Exception as e:
                logger.error(f"Reject callback error: {e}")
                bot.answer_callback_query(call.id, "Error processing rejection.")

        @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("v_alr_"))
        def on_already(call: CallbackQuery):
            try:
                parts = call.data.split("_")
                reg_id = int(parts[2])
                admin_id = call.from_user.id
                result = self.mark_already_registered(reg_id, admin_id)
                admin_tag = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name
                if result.get("success"):
                    bot.edit_message_text(
                        f"{call.message.text}\n\n━━━━━━━━━━━━━━━\n⚠️ 𝗠𝗔𝗥𝗞𝗘𝗗 𝗔𝗦 𝗔𝗟𝗥𝗘𝗔𝗗𝗬 𝗥𝗘𝗚𝗜𝗦𝗧𝗘𝗥𝗘𝗗 by {admin_tag}",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    bot.answer_callback_query(call.id, "Marked as already registered! ⚠️")
                else:
                    bot.answer_callback_query(call.id, f"Error: {result.get('error')}")
            except Exception as e:
                logger.error(f"Already registered callback error: {e}")
                bot.answer_callback_query(call.id, "Error processing.")

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
