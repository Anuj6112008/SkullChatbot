import logging
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from config import config
from database import database
from services.verification import VerificationService
from services.channel import ChannelService
from services.support import SupportService
from keyboards import (
    get_admin_main_keyboard,
    get_verification_keyboard,
    get_start_keyboard,
    get_cancel_keyboard,
    get_support_ticket_actions_keyboard
)
from utils import get_user_full_name, create_registration_summary

logger = logging.getLogger(__name__)

admin_sessions = {}


def register_admin_handlers(bot: TeleBot):
    logger.info("Registering admin handlers...")

    @bot.message_handler(commands=['admin'])
    def admin_command(message: Message):
        logger.info(f"Admin command received from {message.from_user.id}")
        try:
            if not config.is_admin(message.from_user.id):
                bot.reply_to(message, "You are not authorized to use this command.")
                return
            bot.send_message(
                message.from_user.id,
                "🔐 Admin Panel\n\nWelcome to the admin dashboard. Select an option:\n\n"
                "• VIP Broadcast\n• Normal Broadcast\n• All Broadcast\n• Statistics",
                reply_markup=get_admin_main_keyboard()
            )
            logger.info(f"Admin menu sent to {message.from_user.id}")
        except Exception as e:
            logger.error(f"Admin command failed: {e}")
            bot.reply_to(message, "Error accessing admin panel")

    # ------------------------------------------------------------------
    # Pending verifications (kept — accessible from verification keyboards)
    # ------------------------------------------------------------------
    @bot.callback_query_handler(func=lambda call: call.data == "admin_verify")
    def admin_verify_callback(call: CallbackQuery):
        try:
            if not config.is_admin(call.from_user.id):
                try:
                    bot.answer_callback_query(call.id, "Unauthorized")
                except:
                    pass
                return
            try:
                bot.answer_callback_query(call.id, "Fetching pending verifications...")
            except:
                pass
            pending = database.get_pending_verifications()
            if not pending:
                bot.send_message(
                    call.from_user.id,
                    "No pending verifications.",
                    reply_markup=get_admin_main_keyboard()
                )
                return
            for registration in pending[:5]:
                telegram_id = registration.get("telegram_id")
                user = database.get_user(telegram_id)
                if user:
                    name = get_user_full_name(user)
                    username = user.get("username", "N/A")
                    reg_data = registration.get("registration_data", {})
                    account_id = reg_data.get("trading_account_id", reg_data.get("capital", "N/A"))
                    msg = (
                        f"👤 {name}\n🆔 {telegram_id}\n📱 @{username}\n\n"
                        f"📊 Trading Account ID: {account_id}\n"
                        f"📝 Registration ID: {registration.get('id')}"
                    )
                    bot.send_message(
                        call.from_user.id,
                        msg,
                        reply_markup=get_verification_keyboard(registration.get("id"), telegram_id)
                    )
            if len(pending) > 5:
                bot.send_message(
                    call.from_user.id,
                    f"Showing 5 of {len(pending)} pending verifications."
                )
        except Exception as e:
            logger.error(f"Admin verify callback failed: {e}")
            try:
                bot.answer_callback_query(call.id, "Error")
            except:
                pass

    @bot.callback_query_handler(func=lambda call: call.data.startswith("verify_approve_"))
    def verify_approve_callback(call: CallbackQuery):
        try:
            if not config.is_admin(call.from_user.id):
                try:
                    bot.answer_callback_query(call.id, "Unauthorized")
                except:
                    pass
                return
            parts = call.data.split("_")
            registration_id = int(parts[2])
            telegram_id = int(parts[3])
            try:
                bot.answer_callback_query(call.id, "Approving...")
            except:
                pass
            verification_service = VerificationService(bot)
            result = verification_service.approve_registration(registration_id, call.from_user.id)
            if result.get("success"):
                try:
                    bot.edit_message_text(
                        f"✅ Approved user {telegram_id}",
                        call.message.chat.id,
                        call.message.message_id
                    )
                except:
                    pass
                try:
                    bot.send_message(
                        telegram_id,
                        "✅ Your registration request has been approved officially!\n\nWelcome to the community! 🎉"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {telegram_id}: {e}")
                bot.send_message(
                    call.from_user.id,
                    f"User {telegram_id} approved successfully.",
                    reply_markup=get_admin_main_keyboard()
                )
            else:
                bot.send_message(
                    call.from_user.id,
                    f"Approval failed: {result.get('error')}",
                    reply_markup=get_admin_main_keyboard()
                )
        except Exception as e:
            logger.error(f"Verify approve callback failed: {e}")
            try:
                bot.answer_callback_query(call.id, "Error")
            except:
                pass

    @bot.callback_query_handler(func=lambda call: call.data.startswith("verify_reject_"))
    def verify_reject_callback(call: CallbackQuery):
        try:
            if not config.is_admin(call.from_user.id):
                try:
                    bot.answer_callback_query(call.id, "Unauthorized")
                except:
                    pass
                return
            parts = call.data.split("_")
            registration_id = int(parts[2])
            telegram_id = int(parts[3])
            try:
                bot.answer_callback_query(call.id, "Rejecting...")
            except:
                pass
            verification_service = VerificationService(bot)
            result = verification_service.reject_registration(registration_id, call.from_user.id, "Registration declined by admin")
            if result.get("success"):
                try:
                    bot.edit_message_text(
                        f"❌ Rejected user {telegram_id}",
                        call.message.chat.id,
                        call.message.message_id
                    )
                except:
                    pass
                try:
                    bot.send_message(
                        telegram_id,
                        "❌ Your registration request has been rejected because you have not joined our program via VIP link."
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {telegram_id}: {e}")
                bot.send_message(
                    call.from_user.id,
                    f"User {telegram_id} rejected successfully.",
                    reply_markup=get_admin_main_keyboard()
                )
            else:
                bot.send_message(
                    call.from_user.id,
                    f"Rejection failed: {result.get('error')}",
                    reply_markup=get_admin_main_keyboard()
                )
        except Exception as e:
            logger.error(f"Verify reject callback failed: {e}")
            try:
                bot.answer_callback_query(call.id, "Error")
            except:
                pass

    # ------------------------------------------------------------------
    # Users list (kept — useful)
    # ------------------------------------------------------------------
    @bot.callback_query_handler(func=lambda call: call.data == "admin_users")
    def admin_users_callback(call: CallbackQuery):
        try:
            if not config.is_admin(call.from_user.id):
                try:
                    bot.answer_callback_query(call.id, "Unauthorized")
                except:
                    pass
                return
            try:
                bot.answer_callback_query(call.id, "Fetching users...")
            except:
                pass
            users = database.select("users", order_by={"created_at": "desc"}, limit=10)
            if not users:
                bot.send_message(
                    call.from_user.id,
                    "No users found.",
                    reply_markup=get_admin_main_keyboard()
                )
                return
            msg = "👥 Recent Users\n\n"
            for user in users[:10]:
                name = get_user_full_name(user)
                status = user.get("verification_status", "pending")
                paid = "💰" if user.get("paid_user") else "🆓"
                msg += f"{paid} {name} - {status} (ID: {user.get('telegram_id')})\n"
            msg += f"\nTotal users: {database.count('users')}"
            bot.send_message(
                call.from_user.id,
                msg,
                reply_markup=get_admin_main_keyboard()
            )
        except Exception as e:
            logger.error(f"Admin users callback failed: {e}")
            try:
                bot.answer_callback_query(call.id, "Error")
            except:
                pass

    # ------------------------------------------------------------------
    # Statistics (kept — one of the 4 admin options)
    # ------------------------------------------------------------------
    @bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
    def admin_stats_callback(call: CallbackQuery):
        try:
            if not config.is_admin(call.from_user.id):
                try:
                    bot.answer_callback_query(call.id, "Unauthorized")
                except:
                    pass
                return
            try:
                bot.answer_callback_query(call.id, "Fetching statistics...")
            except:
                pass
            counts = database.get_user_counts()
            tickets = database.count("support_tickets", match_conditions={"status": "open"})
            scheduled = database.count("scheduled_messages", match_conditions={"sent": False, "enabled": True})
            msg = "📊 Statistics\n\n"
            msg += f"👥 Total Users: {counts['total']}\n"
            msg += f"💎 VIP Members: {counts['vip']}\n"
            msg += f"👤 Normal Members: {counts['normal']}\n"
            msg += f"⏳ Pending Verification: {counts['pending_verification']}\n"
            msg += f"🎫 Open Support Tickets: {tickets}\n"
            msg += f"📅 Pending Scheduled Posts: {scheduled}"
            bot.send_message(
                call.from_user.id,
                msg,
                reply_markup=get_admin_main_keyboard()
            )
        except Exception as e:
            logger.error(f"Admin stats callback failed: {e}")
            try:
                bot.answer_callback_query(call.id, "Error")
            except:
                pass

    # ------------------------------------------------------------------
    # Support tickets (kept — for ticket action keyboards)
    # ------------------------------------------------------------------
    @bot.callback_query_handler(func=lambda call: call.data == "admin_support")
    def admin_support_callback(call: CallbackQuery):
        try:
            if not config.is_admin(call.from_user.id):
                try:
                    bot.answer_callback_query(call.id, "Unauthorized")
                except:
                    pass
                return
            try:
                bot.answer_callback_query(call.id, "Fetching tickets...")
            except:
                pass
            tickets = database.select("support_tickets", match_conditions={"status": "open"}, order_by={"created_at": "desc"}, limit=10)
            if not tickets:
                bot.send_message(
                    call.from_user.id,
                    "No open support tickets.",
                    reply_markup=get_admin_main_keyboard()
                )
                return
            for ticket in tickets[:5]:
                user = database.get_user(ticket.get("telegram_id"))
                name = get_user_full_name(user) if user else "Unknown"
                msg = f"🎫 Ticket #{ticket.get('id')}\n"
                msg += f"👤 {name}\n"
                msg += f"🆔 {ticket.get('telegram_id')}\n"
                msg += f"📝 {ticket.get('message', '')[:200]}\n"
                msg += f"📅 {ticket.get('created_at', 'N/A')}"
                bot.send_message(
                    call.from_user.id,
                    msg,
                    reply_markup=get_support_ticket_actions_keyboard(ticket.get("id"))
                )
            if len(tickets) > 5:
                bot.send_message(
                    call.from_user.id,
                    f"Showing 5 of {len(tickets)} tickets."
                )
        except Exception as e:
            logger.error(f"Admin support callback failed: {e}")
            try:
                bot.answer_callback_query(call.id, "Error")
            except:
                pass

    # ------------------------------------------------------------------
    # Broadcast shortcuts — VIP / Normal / All
    # (these forward into the broadcast handler's flow)
    # ------------------------------------------------------------------
    @bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast_vip")
    def admin_broadcast_vip_callback(call: CallbackQuery):
        _start_broadcast(bot, call, audience="VIP")

    @bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast_normal")
    def admin_broadcast_normal_callback(call: CallbackQuery):
        _start_broadcast(bot, call, audience="NORMAL")

    @bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast_all")
    def admin_broadcast_all_callback(call: CallbackQuery):
        _start_broadcast(bot, call, audience="ALL")

    @bot.callback_query_handler(func=lambda call: call.data == "admin_cancel")
    def admin_cancel_callback(call: CallbackQuery):
        try:
            telegram_id = call.from_user.id
            if telegram_id in admin_sessions:
                del admin_sessions[telegram_id]
            try:
                bot.answer_callback_query(call.id, "Cancelled")
            except:
                pass
            bot.send_message(
                telegram_id,
                "Operation cancelled.",
                reply_markup=get_admin_main_keyboard()
            )
        except Exception as e:
            logger.error(f"Admin cancel callback failed: {e}")
            try:
                bot.answer_callback_query(call.id, "Error")
            except:
                pass

    logger.info("Admin handlers registered successfully")


def _start_broadcast(bot, call: CallbackQuery, audience: str):
    """Pre-select the audience and jump straight into the broadcast message input."""
    try:
        if not config.is_admin(call.from_user.id):
            try:
                bot.answer_callback_query(call.id, "Unauthorized")
            except:
                pass
            return
        try:
            bot.answer_callback_query(call.id, f"Broadcast: {audience}")
        except:
            pass
        # Delegate to BroadcastHandler by emitting the same signals it expects.
        from handlers.broadcast import broadcast_handler
        if broadcast_handler:
            broadcast_handler.start_broadcast_with_audience(
                call.from_user.id, audience, bot
            )
        else:
            bot.send_message(
                call.from_user.id,
                "📢 Broadcast\n\nPlease enter your broadcast message (text/photo/video with caption):",
                reply_markup=get_cancel_keyboard("broadcast_cancel")
            )
    except Exception as e:
        logger.error(f"Start broadcast failed: {e}")
        try:
            bot.answer_callback_query(call.id, "Error")
        except:
            pass
