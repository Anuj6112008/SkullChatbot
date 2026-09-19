import logging
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from config import config
from database import database
from services.ai import ai_service
from services.support import SupportService as SupportServiceClass
from keyboards import get_start_keyboard, get_support_ticket_actions_keyboard, get_cancel_keyboard, get_back_keyboard, get_end_faq_keyboard
from utils import sanitize_text, get_user_full_name, get_current_timestamp

logger = logging.getLogger(__name__)

class SupportHandler:
    def __init__(self, bot: TeleBot, support_service: SupportServiceClass = None):
        self.bot = bot
        self.support_service = support_service or SupportServiceClass(bot)

    def register(self):
        bot = self.bot

        @bot.message_handler(commands=['support'])
        def support_command(message: Message):
            try:
                telegram_id = message.from_user.id
                bot.send_message(
                    telegram_id,
                    "🆘 Support\n\nPlease describe your issue in detail. I'll help you or forward your message to our support team.",
                    reply_markup=get_back_keyboard("back_to_main")
                )
            except Exception as e:
                logger.error(f"Support command failed: {e}")
                try:
                    bot.reply_to(message, "Error accessing support")
                except:
                    pass

        @bot.message_handler(func=lambda message: message.text and message.text.lower().startswith('support'))
        def support_keyword_handler(message: Message):
            try:
                telegram_id = message.from_user.id
                text = sanitize_text(message.text)
                if len(text) < 10:
                    bot.send_message(
                        telegram_id,
                        "Please provide more details about your issue so we can assist you better.",
                        reply_markup=get_back_keyboard("back_to_main")
                    )
                    return
                user = database.get_user(telegram_id)
                if not user:
                    bot.send_message(
                        telegram_id,
                        "Please start the bot with /start first.",
                        reply_markup=get_start_keyboard()
                    )
                    return
                bot.send_chat_action(telegram_id, "typing")
                ticket = self.support_service.create_ticket(telegram_id, text, "SUPPORT")
                if ticket and ticket.get("id"):
                    self.support_service.notify_admin_about_ticket(ticket)
                    response = ai_service.generate_support_response(ticket.get("id"), text, user)
                    bot.send_message(
                        telegram_id,
                        f"{response}\n\nTicket ID: #{ticket.get('id')}\n\nOur team will review your issue and get back to you shortly.",
                        reply_markup=get_end_faq_keyboard()
                    )
                    logger.info(f"Support ticket {ticket.get('id')} created for user {telegram_id}")
                else:
                    bot.send_message(
                        telegram_id,
                        "Sorry, we couldn't create a support ticket. Please try again later.",
                        reply_markup=get_back_keyboard("back_to_main")
                    )
            except Exception as e:
                logger.error(f"Support keyword handler failed: {e}")
                try:
                    bot.send_message(
                        message.from_user.id,
                        "Sorry, I encountered an error. Please try again later.",
                        reply_markup=get_back_keyboard("back_to_main")
                    )
                except:
                    pass

        @bot.message_handler(func=lambda message: self.support_service.is_awaiting_support(message.from_user.id))
        def awaiting_support_message_handler(message: Message):
            try:
                telegram_id = message.from_user.id
                text = sanitize_text(message.text) if message.text else ""
                self.support_service.clear_awaiting_support(telegram_id)
                if not text:
                    bot.send_message(
                        telegram_id,
                        "Please describe your issue in text so I can create a ticket.",
                        reply_markup=get_back_keyboard("back_to_main")
                    )
                    return
                user = database.get_user(telegram_id)
                if not user:
                    bot.send_message(
                        telegram_id,
                        "Please start the bot with /start first.",
                        reply_markup=get_start_keyboard()
                    )
                    return
                bot.send_chat_action(telegram_id, "typing")
                ticket = self.support_service.create_ticket(telegram_id, text, "SUPPORT")
                if ticket and ticket.get("id"):
                    self.support_service.notify_admin_about_ticket(ticket)
                    response = ai_service.generate_support_response(ticket.get("id"), text, user)
                    bot.send_message(
                        telegram_id,
                        f"{response}\n\nTicket ID: #{ticket.get('id')}\n\nOur team will review your issue and get back to you shortly.",
                        reply_markup=get_end_faq_keyboard()
                    )
                    logger.info(f"Support ticket {ticket.get('id')} created for user {telegram_id}")
                else:
                    bot.send_message(
                        telegram_id,
                        "Sorry, we couldn't create a support ticket. Please try again later.",
                        reply_markup=get_back_keyboard("back_to_main")
                    )
            except Exception as e:
                logger.error(f"Awaiting support message handler failed: {e}")
                try:
                    bot.send_message(
                        message.from_user.id,
                        "Sorry, I encountered an error. Please try again later.",
                        reply_markup=get_back_keyboard("back_to_main")
                    )
                except:
                    pass

        @bot.callback_query_handler(func=lambda call: call.data.startswith("ticket_resolve_"))
        def resolve_ticket_callback(call: CallbackQuery):
            try:
                if not config.is_admin(call.from_user.id):
                    try:
                        bot.answer_callback_query(call.id, "Unauthorized")
                    except:
                        pass
                    return
                ticket_id = int(call.data.split("_")[2])
                try:
                    bot.answer_callback_query(call.id, "Resolving ticket...")
                except:
                    pass
                bot.send_message(
                    call.from_user.id,
                    f"Please enter resolution notes for ticket #{ticket_id}:",
                    reply_markup=get_cancel_keyboard("ticket_cancel")
                )
                self.support_service.set_pending_ticket_resolution(call.from_user.id, ticket_id)
            except Exception as e:
                logger.error(f"Resolve ticket callback failed: {e}")
                try:
                    bot.answer_callback_query(call.id, "Error")
                except:
                    pass

        @bot.callback_query_handler(func=lambda call: call.data.startswith("ticket_assign_"))
        def assign_ticket_callback(call: CallbackQuery):
            try:
                if not config.is_admin(call.from_user.id):
                    try:
                        bot.answer_callback_query(call.id, "Unauthorized")
                    except:
                        pass
                    return
                ticket_id = int(call.data.split("_")[2])
                result = self.support_service.assign_ticket(ticket_id, call.from_user.id)
                if result.get("success"):
                    try:
                        bot.answer_callback_query(call.id, "Ticket assigned to you")
                    except:
                        pass
                    bot.send_message(
                        call.from_user.id,
                        f"Ticket #{ticket_id} assigned to you."
                    )
                else:
                    try:
                        bot.answer_callback_query(call.id, f"Error: {result.get('error')}")
                    except:
                        pass
            except Exception as e:
                logger.error(f"Assign ticket callback failed: {e}")
                try:
                    bot.answer_callback_query(call.id, "Error")
                except:
                    pass

        @bot.callback_query_handler(func=lambda call: call.data.startswith("ticket_escalate_"))
        def escalate_ticket_callback(call: CallbackQuery):
            try:
                if not config.is_admin(call.from_user.id):
                    try:
                        bot.answer_callback_query(call.id, "Unauthorized")
                    except:
                        pass
                    return
                ticket_id = int(call.data.split("_")[2])
                result = self.support_service.escalate_ticket(ticket_id)
                if result.get("success"):
                    try:
                        bot.answer_callback_query(call.id, "Ticket escalated")
                    except:
                        pass
                    bot.send_message(
                        call.from_user.id,
                        f"Ticket #{ticket_id} has been escalated."
                    )
                else:
                    try:
                        bot.answer_callback_query(call.id, f"Error: {result.get('error')}")
                    except:
                        pass
            except Exception as e:
                logger.error(f"Escalate ticket callback failed: {e}")
                try:
                    bot.answer_callback_query(call.id, "Error")
                except:
                    pass

        @bot.message_handler(func=lambda message: self.support_service.is_pending_ticket_resolution(message.from_user.id))
        def ticket_resolution_message(message: Message):
            try:
                admin_id = message.from_user.id
                ticket_id = self.support_service.get_pending_ticket_id(admin_id)
                if not ticket_id:
                    return
                resolution_notes = sanitize_text(message.text)
                result = self.support_service.resolve_ticket(ticket_id, admin_id, resolution_notes)
                if result.get("success"):
                    bot.send_message(
                        admin_id,
                        f"Ticket #{ticket_id} resolved successfully."
                    )
                    ticket = database.get_support_ticket(ticket_id)
                    if ticket:
                        try:
                            bot.send_message(
                                ticket.get("telegram_id"),
                                f"Your support ticket #{ticket_id} has been resolved.\n\nResolution: {resolution_notes}\n\nThank you for contacting us."
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify user about ticket resolution: {e}")
                else:
                    bot.send_message(
                        admin_id,
                        f"Failed to resolve ticket: {result.get('error')}"
                    )
                self.support_service.clear_pending_ticket_resolution(admin_id)
            except Exception as e:
                logger.error(f"Ticket resolution message failed: {e}")
                try:
                    bot.reply_to(message, "Error processing resolution")
                except:
                    pass

        @bot.callback_query_handler(func=lambda call: call.data == "ticket_cancel")
        def ticket_cancel_callback(call: CallbackQuery):
            try:
                admin_id = call.from_user.id
                self.support_service.clear_pending_ticket_resolution(admin_id)
                try:
                    bot.answer_callback_query(call.id, "Cancelled")
                except:
                    pass
                bot.send_message(
                    admin_id,
                    "Ticket resolution cancelled.",
                    reply_markup=get_admin_main_keyboard()
                )
            except Exception as e:
                logger.error(f"Ticket cancel callback failed: {e}")
                try:
                    bot.answer_callback_query(call.id, "Error")
                except:
                    pass

        @bot.callback_query_handler(func=lambda call: call.data == "end_faq")
        def end_faq_callback(call: CallbackQuery):
            try:
                try:
                    bot.answer_callback_query(call.id, "Ending session...")
                except:
                    pass
                welcome_text = "Thank you for being a member of our community! 🙏\n\nWe're here to help you anytime."
                bot.send_message(
                    call.from_user.id,
                    welcome_text,
                    reply_markup=get_start_keyboard()
                )
            except Exception as e:
                logger.error(f"End FAQ callback failed: {e}")
                try:
                    bot.answer_callback_query(call.id, "Error")
                except:
                    pass

def register_support_handlers(bot: TeleBot, support_service: SupportServiceClass = None):
    handler = SupportHandler(bot, support_service)
    handler.register()