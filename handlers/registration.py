import logging
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from config import config
from database import database
from services.verification import VerificationService
from services.registration import RegistrationService
from keyboards import get_start_keyboard, get_registration_cancel_keyboard
from utils import get_current_timestamp, sanitize_text, get_user_full_name

logger = logging.getLogger(__name__)

class RegistrationHandler:
    def __init__(self, bot: TeleBot, registration_service: RegistrationService = None):
        self.bot = bot
        self.verification_service = VerificationService(bot)
        self.registration_service = registration_service or RegistrationService(bot)
        self.user_sessions = {}

    def register(self):
        bot = self.bot

        @bot.message_handler(func=lambda message: self.registration_service.is_awaiting_account_id(message.from_user.id))
        def registration_account_id_handler(message: Message):
            try:
                telegram_id = message.from_user.id
                account_id = sanitize_text(message.text)
                if not account_id:
                    bot.send_message(
                        telegram_id,
                        "Please enter a valid trading account ID:",
                        reply_markup=get_registration_cancel_keyboard()
                    )
                    return
                user = database.get_user(telegram_id)
                if not user:
                    bot.send_message(
                        telegram_id,
                        "User not found. Please start with /start first.",
                        reply_markup=get_start_keyboard()
                    )
                    self.registration_service.clear_registration_state(telegram_id)
                    return
                if user.get("verification_status") == "approved":
                    bot.send_message(
                        telegram_id,
                        "You are already registered and verified! ✅",
                        reply_markup=get_start_keyboard()
                    )
                    self.registration_service.clear_registration_state(telegram_id)
                    return
                if user.get("registration_status") == "pending_verification":
                    bot.send_message(
                        telegram_id,
                        "Your registration is already pending verification. ⏳",
                        reply_markup=get_start_keyboard()
                    )
                    self.registration_service.clear_registration_state(telegram_id)
                    return
                registration_data = {
                    "telegram_id": telegram_id,
                    "registration_data": {
                        "trading_account_id": account_id,
                        "full_name": user.get("first_name", ""),
                        "username": user.get("username", "")
                    },
                    "verification_status": "pending"
                }
                registration = database.create_registration(registration_data)
                database.update_user(telegram_id, {
                    "registration_status": "pending_verification"
                })
                self.registration_service.clear_registration_state(telegram_id)
                bot.send_message(
                    telegram_id,
                    "✅ Registration submitted!\n\nYour registration is now pending verification.\n\nYou will be notified once an admin approves your registration.",
                    reply_markup=get_start_keyboard()
                )
                self.verification_service.notify_admin_about_registration(registration)
                logger.info(f"Registration completed for user {telegram_id} with account ID: {account_id}")
            except Exception as e:
                logger.error(f"Registration account ID handler failed: {e}")
                bot.send_message(
                    message.from_user.id,
                    "Error processing your registration. Please try again.",
                    reply_markup=get_start_keyboard()
                )
                self.registration_service.clear_registration_state(message.from_user.id)

        @bot.message_handler(func=lambda message: self.is_in_registration(message.from_user.id))
        def registration_answer(message: Message):
            try:
                telegram_id = message.from_user.id
                session = self.user_sessions.get(telegram_id)
                if not session:
                    return
                question_index = session["step"] - 1
                questions = session["questions"]
                if question_index < 0 or question_index >= len(questions):
                    return
                question_key = questions[question_index].get("key")
                if question_key:
                    session["answers"][question_key] = sanitize_text(message.text)
                session["step"] += 1
                if session["step"] > len(questions):
                    self.complete_registration(telegram_id)
                else:
                    self.ask_next_question(telegram_id)
            except Exception as e:
                logger.error(f"Registration answer failed: {e}")
                bot.send_message(
                    message.from_user.id,
                    "Error processing your answer. Please try again."
                )

        @bot.callback_query_handler(func=lambda call: call.data == "cancel_registration")
        def cancel_registration_callback(call: CallbackQuery):
            try:
                telegram_id = call.from_user.id
                if telegram_id in self.user_sessions:
                    del self.user_sessions[telegram_id]
                self.registration_service.clear_registration_state(telegram_id)
                bot.answer_callback_query(call.id, "Registration cancelled")
                bot.send_message(
                    telegram_id,
                    "Registration cancelled. You can start again anytime.",
                    reply_markup=get_start_keyboard()
                )
            except Exception as e:
                logger.error(f"Cancel registration failed: {e}")
                bot.answer_callback_query(call.id, "Error")

    def get_registration_questions(self):
        try:
            questions = [
                {"key": "full_name", "question": "Please enter your full name:"},
                {"key": "email", "question": "Please enter your email address:"},
                {"key": "phone", "question": "Please enter your phone number:"},
                {"key": "city", "question": "Please enter your city:"}
            ]
            return questions
        except Exception as e:
            logger.error(f"Failed to get registration questions: {e}")
            return [
                {"key": "full_name", "question": "Please enter your full name:"},
                {"key": "email", "question": "Please enter your email address:"}
            ]

    def ask_next_question(self, telegram_id: int):
        try:
            session = self.user_sessions.get(telegram_id)
            if not session:
                return
            questions = session["questions"]
            step = session["step"]
            if step < len(questions):
                question = questions[step]
                self.bot.send_message(
                    telegram_id,
                    f"📝 Question {step + 1}/{len(questions)}\n\n{question['question']}",
                    reply_markup=get_registration_cancel_keyboard()
                )
            else:
                self.complete_registration(telegram_id)
        except Exception as e:
            logger.error(f"Failed to ask next question: {e}")
            self.bot.send_message(
                telegram_id,
                "Error in registration. Please try again."
            )

    def complete_registration(self, telegram_id: int):
        try:
            session = self.user_sessions.get(telegram_id)
            if not session:
                return
            user = database.get_user(telegram_id)
            if not user:
                self.bot.send_message(telegram_id, "User not found. Please start over.")
                return
            registration_data = {
                "telegram_id": telegram_id,
                "registration_data": session["answers"],
                "verification_status": "pending"
            }
            registration = database.create_registration(registration_data)
            database.update_user(telegram_id, {
                "registration_status": "pending_verification"
            })
            del self.user_sessions[telegram_id]
            self.bot.send_message(
                telegram_id,
                "✅ Registration complete!\n\nYour registration is now pending verification.\n\nYou will be notified once an admin approves your registration.",
                reply_markup=get_start_keyboard()
            )
            self.verification_service.notify_admin_about_registration(registration)
            logger.info(f"Registration completed for user {telegram_id}")
        except Exception as e:
            logger.error(f"Failed to complete registration: {e}")
            self.bot.send_message(
                telegram_id,
                "Error completing registration. Please try again."
            )

    def is_in_registration(self, telegram_id: int) -> bool:
        session = self.user_sessions.get(telegram_id)
        return session is not None and session.get("step", 0) > 0

def register_registration_handlers(bot: TeleBot, registration_service: RegistrationService = None):
    handler = RegistrationHandler(bot, registration_service)
    handler.register()
    return handler.registration_service