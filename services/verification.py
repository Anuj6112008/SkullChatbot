import os
import json
import logging
from typing import Dict, Any, Optional
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import config
from database import database
from services.channel import ChannelService
from utils import get_current_timestamp, get_user_full_name

logger = logging.getLogger(__name__)


class VerificationService:
    def __init__(self, bot: TeleBot):
        self.bot = bot
        self.channel_service = ChannelService(bot)
        self._register_callbacks()

    def get_verification_channel_id(self) -> Optional[int]:
        """Fetch strictly UPDATES_CHANNEL_ID from .env or config for approvals."""
        env_val = os.getenv("UPDATES_CHANNEL_ID")
        if env_val and str(env_val).strip():
            try:
                return int(str(env_val).strip())
            except Exception:
                pass

        if hasattr(config, "UPDATES_CHANNEL_ID") and config.UPDATES_CHANNEL_ID:
            try:
                return int(config.UPDATES_CHANNEL_ID)
            except Exception:
                pass

        return -1003713317887

    def get_paid_channel_id(self) -> Optional[int]:
        """Fetch PAID_CHANNEL_ID from .env or config."""
        env_val = os.getenv("PAID_CHANNEL_ID")
        if env_val and str(env_val).strip():
            try:
                return int(str(env_val).strip())
            except Exception:
                pass

        if hasattr(config, "PAID_CHANNEL_ID") and config.PAID_CHANNEL_ID:
            try:
                return int(config.PAID_CHANNEL_ID)
            except Exception:
                pass

        return -1004327136936

    def generate_one_time_vip_link(self) -> str:
        """Create a 1-time single-use invite link for the VIP paid channel."""
        paid_chan_id = self.get_paid_channel_id()
        try:
            invite = self.bot.create_chat_invite_link(
                chat_id=paid_chan_id,
                member_limit=1,
                name="VIP Approved Access"
            )
            return invite.invite_link
        except Exception as e:
            logger.error(f"Failed to generate 1-time invite link for {paid_chan_id}: {e}")
            try:
                db_link = database.get_setting("vip_channel_link")
                if db_link:
                    val = db_link.get("value") if isinstance(db_link, dict) else db_link
                    if val:
                        return str(val).strip()
            except Exception:
                pass
            if hasattr(config, "get_vip_channel_link"):
                return config.get_vip_channel_link()
            return "https://t.me/+3zlZ8oTobb5lODc9"

    def approve_registration(self, registration_id: int, admin_id: int) -> Dict[str, Any]:
        try:
            registration = database.get_registration(registration_id)
            if not registration:
                return {"success": False, "error": "Registration not found"}
            telegram_id = registration.get("telegram_id")

            now_ts = get_current_timestamp()
            user_data = database.get_user(telegram_id) or {}
            onboarding_data = user_data.get("onboarding_data") or {}
            if isinstance(onboarding_data, str):
                try:
                    onboarding_data = json.loads(onboarding_data)
                except Exception:
                    onboarding_data = {}

            onboarding_data["vip_approved_at"] = now_ts
            onboarding_data["vip_resources_sent"] = False

            database.update_registration(registration_id, {
                "verification_status": "approved",
                "verified_by": admin_id,
                "verified_at": now_ts
            })
            database.update_user(telegram_id, {
                "member_type": "vip",
                "verification_status": "approved",
                "registered_at": now_ts,
                "registration_status": "approved",
                "onboarding_state": "completed",
                "verified_at": now_ts,
                "onboarding_data": onboarding_data,
                "hot_lead_active": False
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

            # Generate 1-time VIP invite link
            vip_one_time_link = self.generate_one_time_vip_link()

            approval_msg = (
                "🎉 **CONGRATULATIONS!** 🎉\n\n"
                "Your 9-Digit Trading Account ID has been **APPROVED**! ✅\n\n"
                "Here is your **One-Time VIP Community Access Link**:\n"
                f"👉 {vip_one_time_link}\n\n"
                "⚠️ *Note: This link can only be used once. Join immediately!*"
            )

            try:
                self.bot.send_message(telegram_id, approval_msg, parse_mode="Markdown")
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

    def handle_wrong_id(self, registration_id: int, admin_id: int) -> Dict[str, Any]:
        """Admin clicked Wrong ID button."""
        try:
            registration = database.get_registration(registration_id)
            if not registration:
                return {"success": False, "error": "Registration not found"}
            telegram_id = registration.get("telegram_id")

            database.update_registration(registration_id, {
                "verification_status": "rejected",
                "verified_by": admin_id,
                "verified_at": get_current_timestamp(),
                "rejection_reason": "wrong_id"
            })
            database.update_user(telegram_id, {
                "member_type": "normal",
                "verification_status": "rejected",
                "registration_status": "rejected",
                "onboarding_state": "awaiting_account_id",
                "hot_lead_active": False
            })

            database.create_admin_log({
                "admin_id": admin_id,
                "action": "reject_wrong_id",
                "target_id": telegram_id,
                "target_type": "user",
                "details": {"registration_id": registration_id}
            })

            # Fetch joining link dynamically
            joining_link = "https://u3.shortink.io/register?utm_campaign=860595&utm_source=affiliate&utm_medium=sr&a=JP2W2GnQq591r7&al=1786780&ac=skull&cid=973092&code=50START"
            try:
                db_link = database.get_setting("registration_link")
                if db_link:
                    val = db_link.get("value") if isinstance(db_link, dict) else db_link
                    if val and str(val).strip():
                        joining_link = str(val).strip()
            except Exception:
                pass

            wrong_id_msg = (
                "❌ **Your trading Id is not under our Student Registration.**\n\n"
                "Your Acoount is not registered with our Link. "
                "Kindly use the link below and create a Fresh account 👇\n\n"
                f"🔗 {joining_link}\n\n"
                "Do not forget to deposit atleast 50$ , to get started, "
                "Kindly send your 9 digit trading id here 👇"
            )

            try:
                self.bot.send_message(telegram_id, wrong_id_msg, disable_web_page_preview=True)
            except Exception as e:
                logger.error(f"Failed to send wrong ID message to {telegram_id}: {e}")

            return {"success": True, "message": "Marked as Wrong ID"}
        except Exception as e:
            logger.error(f"Failed to handle wrong ID: {e}")
            return {"success": False, "error": str(e)}

    def handle_no_deposit(self, registration_id: int, admin_id: int) -> Dict[str, Any]:
        """Admin clicked No Deposit button."""
        try:
            registration = database.get_registration(registration_id)
            if not registration:
                return {"success": False, "error": "Registration not found"}
            telegram_id = registration.get("telegram_id")

            database.update_registration(registration_id, {
                "verification_status": "no_deposit",
                "verified_by": admin_id,
                "verified_at": get_current_timestamp(),
                "rejection_reason": "No Deposit"
            })
            database.update_user(telegram_id, {
                "verification_status": "no_deposit",
                "registration_status": "no_deposit",
                "onboarding_state": "awaiting_deposit_confirmation",
                "hot_lead_active": False
            })

            no_dep_text = (
                "Sorry, the VIP community is only for Serious Traders.\n\n"
                "Click “done ✅” if you have deposited money in your trading account"
            )

            done_keyboard = InlineKeyboardMarkup()
            done_keyboard.add(InlineKeyboardButton("Done ✅", callback_data=f"usr_done_dep_{registration_id}"))

            try:
                self.bot.send_message(telegram_id, no_dep_text, reply_markup=done_keyboard)
            except Exception as e:
                logger.error(f"Failed to send no deposit prompt to {telegram_id}: {e}")

            return {"success": True, "message": "Marked as No Deposit"}
        except Exception as e:
            logger.error(f"Failed to handle no deposit: {e}")
            return {"success": False, "error": str(e)}

    def notify_admin_about_registration(self, registration: Dict[str, Any]) -> bool:
        """Send verification request using exact Q&A data from onboarding_data or fallback to direct italic message."""
        try:
            if not registration:
                return False

            reg_id = registration.get("id") or 0
            telegram_id = registration.get("telegram_id")
            user = database.get_user(telegram_id) or {}
            reg_data = registration.get("registration_data", {})
            if isinstance(reg_data, str):
                try:
                    reg_data = json.loads(reg_data)
                except Exception:
                    reg_data = {}

            # Extract user's onboarding_data JSON from Supabase
            onboarding_data = user.get("onboarding_data") or {}
            if isinstance(onboarding_data, str):
                try:
                    onboarding_data = json.loads(onboarding_data)
                except Exception:
                    onboarding_data = {}

            # Trading ID extraction
            trading_id = (
                reg_data.get("trading_account_id")
                or reg_data.get("account_id")
                or onboarding_data.get("trading_account_id")
                or user.get("account_id")
                or "N/A"
            )

            # Name extraction
            full_name = (
                onboarding_data.get("name")
                or reg_data.get("full_name")
                or reg_data.get("name")
                or get_user_full_name(user)
                or "Trader"
            )

            username_val = user.get("username") or reg_data.get("username") or onboarding_data.get("username")
            username_display = f"@{username_val}" if username_val else "N/A"

            # Check Q&A fields: First priority = onboarding_data, Second = reg_data, Fallback = italic placeholder
            default_placeholder = "_The user has started bot directly_"

            raw_exp = onboarding_data.get("experience") or reg_data.get("experience") or user.get("experience")
            experience = str(raw_exp).strip() if raw_exp else default_placeholder

            raw_age = onboarding_data.get("age") or reg_data.get("age") or user.get("age")
            age = str(raw_age).strip() if raw_age else default_placeholder

            raw_prof = (
                onboarding_data.get("profession")
                or onboarding_data.get("occupation")
                or reg_data.get("profession")
                or reg_data.get("occupation")
                or user.get("profession")
            )
            profession = str(raw_prof).strip() if raw_prof else default_placeholder

            raw_cap = onboarding_data.get("capital") or reg_data.get("capital") or user.get("capital")
            capital = str(raw_cap).strip() if raw_cap else default_placeholder

            # Exact Universal Format Requested
            message = (
                "🆕 **New Registration Request**\n\n"
                f"👤 **Name:** {full_name}\n"
                f"🆔 **Telegram ID:** `{telegram_id}`\n"
                f"📱 **Username:** {username_display}\n"
                f"📊 **Experience:** {experience}\n"
                f"🎂 **Age:** {age}\n"
                f"💼 **Profession:** {profession}\n"
                f"💰 **Capital:** {capital}\n"
                f"💳 **Trading Account ID:** `{trading_id}`\n\n"
                f"📝 **Registration ID:** #{reg_id}"
            )

            # 3 Working Action Buttons
            keyboard = InlineKeyboardMarkup(row_width=2)
            btn_approve = InlineKeyboardButton("✅ Approve", callback_data=f"v_app_{reg_id}_{telegram_id}")
            btn_wrong = InlineKeyboardButton("❌ Wrong ID", callback_data=f"v_wrong_{reg_id}_{telegram_id}")
            btn_no_dep = InlineKeyboardButton("⚠️ No Deposit", callback_data=f"v_nodep_{reg_id}_{telegram_id}")
            keyboard.add(btn_approve, btn_wrong)
            keyboard.add(btn_no_dep)

            chan_id = self.get_verification_channel_id()
            if chan_id:
                try:
                    self.bot.send_message(
                        chat_id=chan_id,
                        text=message,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                    logger.info(f"Sent approval card #{reg_id} to Updates Channel {chan_id}")
                    return True
                except Exception as ce:
                    logger.error(f"Failed to post to verification channel {chan_id}: {ce}")

            return False
        except Exception as e:
            logger.error(f"Failed to notify admin about registration: {e}", exc_info=True)
            return False

    def _register_callbacks(self):
        """Auto-register button callbacks (supports both 'v_' and 'ss_' prefixes)."""
        bot = self.bot

        # 1. Admin Approve Callback (handles both v_app_ and ss_accept_)
        @bot.callback_query_handler(func=lambda call: call.data and (call.data.startswith("v_app_") or call.data.startswith("ss_accept_")))
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
                    bot.answer_callback_query(call.id, "Approved! 1-Time VIP Link Sent. ✅")
                else:
                    bot.answer_callback_query(call.id, f"Error: {result.get('error')}")
            except Exception as e:
                logger.error(f"Approve callback error: {e}")
                bot.answer_callback_query(call.id, "Error processing approval.")

        # 2. Admin Wrong ID Callback (handles both v_wrong_ and ss_reject_)
        @bot.callback_query_handler(func=lambda call: call.data and (call.data.startswith("v_wrong_") or call.data.startswith("ss_reject_")))
        def on_wrong_id(call: CallbackQuery):
            try:
                parts = call.data.split("_")
                reg_id = int(parts[2])
                admin_id = call.from_user.id
                result = self.handle_wrong_id(reg_id, admin_id)
                admin_tag = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name
                if result.get("success"):
                    bot.edit_message_text(
                        f"{call.message.text}\n\n━━━━━━━━━━━━━━━\n❌ 𝗠𝗔𝗥𝗞𝗘𝗗 𝗔𝗦 𝗪𝗥𝗢𝗡𝗚 𝗜𝗗 by {admin_tag}",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    bot.answer_callback_query(call.id, "Marked as Wrong ID! Re-entry requested. ❌")
                else:
                    bot.answer_callback_query(call.id, f"Error: {result.get('error')}")
            except Exception as e:
                logger.error(f"Wrong ID callback error: {e}")
                bot.answer_callback_query(call.id, "Error processing.")

        # 3. Admin No Deposit Callback (handles both v_nodep_ and ss_nodeposit_)
        @bot.callback_query_handler(func=lambda call: call.data and (call.data.startswith("v_nodep_") or call.data.startswith("ss_nodeposit_")))
        def on_no_deposit(call: CallbackQuery):
            try:
                parts = call.data.split("_")
                reg_id = int(parts[2])
                admin_id = call.from_user.id
                result = self.handle_no_deposit(reg_id, admin_id)
                admin_tag = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name
                if result.get("success"):
                    bot.edit_message_text(
                        f"{call.message.text}\n\n━━━━━━━━━━━━━━━\n⚠️ 𝗠𝗔𝗥𝗞𝗘𝗗 𝗔𝗦 𝗡𝗢 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 by {admin_tag}",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    bot.answer_callback_query(call.id, "Marked as No Deposit! Sent Done button. ⚠️")
                else:
                    bot.answer_callback_query(call.id, f"Error: {result.get('error')}")
            except Exception as e:
                logger.error(f"No Deposit callback error: {e}")
                bot.answer_callback_query(call.id, "Error processing.")

        # 4. User Clicked "Done ✅" After Depositing (handles usr_done_dep_ and ss_deposit_done_)
        @bot.callback_query_handler(func=lambda call: call.data and (call.data.startswith("usr_done_dep_") or call.data.startswith("ss_deposit_done_")))
        def on_user_done_deposit(call: CallbackQuery):
            try:
                parts = call.data.split("_")
                reg_id = int(parts[3])
                telegram_id = call.from_user.id

                database.update_registration(reg_id, {
                    "verification_status": "pending",
                    "verified_by": None,
                    "verified_at": None,
                    "rejection_reason": None
                })
                database.update_user(telegram_id, {
                    "verification_status": "pending",
                    "registration_status": "pending_verification",
                    "onboarding_state": "submitted_for_verification",
                    "last_activity": get_current_timestamp()
                })

                bot.edit_message_text(
                    "✅ Thank you! Your deposit confirmation has been submitted. Our team is verifying it now! ⏳",
                    call.message.chat.id,
                    call.message.message_id
                )
                bot.answer_callback_query(call.id, "Submitted for verification! ✅")

                registration = database.get_registration(reg_id)
                if registration:
                    self.notify_admin_about_registration(registration)

            except Exception as e:
                logger.error(f"User Done Deposit error: {e}")
                bot.answer_callback_query(call.id, "Error submitting. Please contact support.")

    def get_approval_text(self) -> str:
        return "🎉 **CONGRATULATIONS!** Your registration has been approved! Welcome to the VIP Community."

    def get_rejection_text(self) -> str:
        return "❌ Your registration was declined. Please ensure you registered via our official link and deposited $50+."

    def get_welcome_text(self) -> str:
        return "Welcome to Skull VIP Community!"

    def get_registration_cta_text(self) -> str:
        return "Please register to get started."

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
