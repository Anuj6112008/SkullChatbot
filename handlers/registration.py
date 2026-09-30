import re
import logging
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from config import config
from database import database
from services.verification import VerificationService
from services.registration import RegistrationService
from services.ai import ai_service
from keyboards import get_start_keyboard, get_registration_cancel_keyboard
from utils import get_current_timestamp, sanitize_text, get_user_full_name

logger = logging.getLogger(__name__)


def _extract_exact_9digit_id(text: str) -> str | None:
    """Strictly extracts 9-digit trading ID only."""
    if not text:
        return None
    cleaned = re.sub(r"[\s\-#:]", "", text.strip())
    if cleaned.isdigit() and len(cleaned) == 9:
        return cleaned
    m = re.search(r"(?:account\s*id|id|acc(?:ount)?)\s*[:\-]?\s*(\d{9})\b", text, re.I)
    if m:
        return m.group(1)
    return None


def _is_invalid_number_attempt(text: str) -> bool:
    """Check if input is pure numbers but NOT 9 digits."""
    if not text:
        return False
    cleaned = re.sub(r"[\s\-#:]", "", text.strip())
    if cleaned.isdigit() and len(cleaned) != 9:
        return True
    return False


class RegistrationHandler:
    def __init__(self, bot: TeleBot, registration_service: RegistrationService = None):
        self.bot = bot
        self.verification_service = VerificationService(bot)
        self.registration_service = registration_service or RegistrationService(bot)
        self.user_sessions = {}

    def register(self):
        bot = self.bot

        @bot.message_handler(func=lambda message: self.registration_service.is_awaiting_account_id(message.from_user.id), content_types=['text'])
        def registration_account_id_handler(message: Message):
            try:
                telegram_id = message.from_user.id
                raw_text = sanitize_text(message.text)
                if not raw_text:
                    bot.send_message(
                        telegram_id,
                        "Please enter your **9-digit Trading Account ID** (Example: 123456789):",
                        reply_markup=get_registration_cancel_keyboard(),
                        parse_mode="Markdown"
                    )
                    return

                user = database.get_user(telegram_id) or {}
                if not user:
                    user = database.create_user({
                        "telegram_id": telegram_id,
                        "username": message.from_user.username or "",
                        "first_name": message.from_user.first_name or "",
                        "last_name": message.from_user.last_name or "",
                        "member_type": "normal",
                        "joined_at": get_current_timestamp(),
                        "last_activity": get_current_timestamp()
                    })

                # 1. Exact 9-Digit Trading Account ID Validation
                account_id_9 = _extract_exact_9digit_id(raw_text)
                if account_id_9:
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

                    first_name = user.get("first_name") or message.from_user.first_name or ""
                    last_name = user.get("last_name") or message.from_user.last_name or ""
                    full_name = f"{first_name} {last_name}".strip() or "Trader"
                    username = user.get("username") or message.from_user.username or ""

                    experience = user.get("experience") or user.get("trading_experience")
                    age = user.get("age")
                    profession = user.get("profession") or user.get("occupation")
                    capital = user.get("capital") or user.get("trading_capital")

                    registration_data = {
                        "telegram_id": telegram_id,
                        "registration_data": {
                            "trading_account_id": str(account_id_9),
                            "full_name": full_name,
                            "username": username,
                            "experience": experience,
                            "age": age,
                            "profession": profession,
                            "capital": capital,
                            "source": "direct_chat"
                        },
                        "verification_status": "pending"
                    }

                    registration = database.create_registration(registration_data)
                    database.update_user(telegram_id, {
                        "account_id": str(account_id_9),
                        "registration_status": "pending_verification",
                        "onboarding_state": "submitted_for_verification",
                        "last_activity": get_current_timestamp()
                    })
                    self.registration_service.clear_registration_state(telegram_id)

                    bot.send_message(
                        telegram_id,
                        f"✅ **Account ID Received:** `{account_id_9}`\n\n"
                        "Your registration is now pending manual verification. ⏳\n"
                        "Once approved, your **1-Time VIP Access Link** will be sent here!",
                        parse_mode="Markdown"
                    )

                    if registration:
                        self.verification_service.notify_admin_about_registration(registration)

                    logger.info(f"Valid 9-digit account ID submitted by {telegram_id}: {account_id_9}")
                    return

                # 2. Check if user entered numbers of INVALID length (e.g. 5, 8, 10, 11 digits)
                if _is_invalid_number_attempt(raw_text):
                    bot.send_message(
                        telegram_id,
                        "⚠️ **Invalid Account ID**\n\n"
                        "Your Trading account Id must strictly be only 9 digits\n\n"
                        "👉 **Example:** `123456789`\n\n"
                        "Kindly resend your 9 digit trading ID correctly 📝",
                        reply_markup=get_registration_cancel_keyboard(),
                        parse_mode="Markdown"
                    )
                    return

                # 3. If user sent words (e.g. 'Brooo', 'Abc', questions) -> Route to AI
                response = ai_service.generate_response(raw_text, user)
                reply_text = response.get(
                    "response",
                    "Please send your **9-digit Trading Account ID** so we can verify your VIP access! 🆔"
                )
                bot.send_message(telegram_id, reply_text)

            except Exception as e:
                logger.error(f"Registration account ID handler failed: {e}", exc_info=True)
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
