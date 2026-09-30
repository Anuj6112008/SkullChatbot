import logging
import time
import random
import re
import threading
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from config import config
from database import database
from services.ai import ai_service
from services.video import VideoService
from services.support import SupportService
from services.registration import RegistrationService
from services.onboarding import OnboardingService, ACTIVE_STATES
from services import promo
from services.verification import VerificationService
from keyboards import get_start_keyboard, get_back_keyboard
from utils import sanitize_text, get_current_timestamp

logger = logging.getLogger(__name__)

_pending_messages = {}
_pending_lock = threading.Lock()
DEBOUNCE_SECONDS = 1.5


def _send_typing(bot: TeleBot, chat_id: int, delay: float = 1.5):
    try:
        bot.send_chat_action(chat_id, "typing")
        time.sleep(delay)
    except Exception:
        pass


def _calc_typing_delay(text: str) -> float:
    if not text:
        return 2.0
    length = len(text)
    delay = 2.0 + min(length / 100.0, 3.0)
    delay += random.uniform(-0.2, 0.3)
    return max(2.0, min(delay, 5.0))


def _extract_exact_9digit_id(text: str) -> str | None:
    """Strictly returns 9-digit trading ID only."""
    if not text:
        return None
    cleaned = re.sub(r"[\s\-#:]", "", text.strip())
    # Exact 9 digits
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


def _is_already_registered_intent(text: str) -> bool:
    """Detect if user is saying they have already registered or already have an account."""
    t = text.lower()
    phrases = [
        "already registered", "already register", "already have account",
        "already created", "already done", "already account", "i have registered",
        "i have already", "already joined", "already deposit", "already open",
        "account undi", "register aindi", "already reg"
    ]
    return any(p in t for p in phrases)


class FAQHandler:
    def __init__(
        self,
        bot: TeleBot,
        registration_service: RegistrationService = None,
        support_service: SupportService = None,
        onboarding_service: OnboardingService = None
    ):
        self.bot = bot
        self.video_service = VideoService(bot)
        self.support_service = support_service or SupportService(bot)
        self.registration_service = registration_service or RegistrationService(bot)
        self.onboarding_service = onboarding_service or OnboardingService(bot)
        self.verification_service = VerificationService(bot)

    def _submit_account_id(self, telegram_id: int, account_id: str, user: dict):
        """Submit exact 9-digit trading account ID to VIP approval channel."""
        bot = self.bot
        try:
            if user.get("verification_status") == "approved":
                _send_typing(bot, telegram_id, 1.5)
                bot.send_message(telegram_id, "You are already a verified VIP member! ✅")
                return

            if user.get("registration_status") == "pending_verification":
                _send_typing(bot, telegram_id, 1.5)
                bot.send_message(
                    telegram_id,
                    "Your registration is already pending verification. Please wait for admin approval. ⏳"
                )
                return

            first_name = user.get("first_name") or ""
            last_name = user.get("last_name") or ""
            full_name = f"{first_name} {last_name}".strip() or "Trader"
            username = user.get("username") or ""

            experience = user.get("experience") or user.get("trading_experience")
            age = user.get("age")
            profession = user.get("profession") or user.get("occupation")
            capital = user.get("capital") or user.get("trading_capital")

            registration_data = {
                "telegram_id": telegram_id,
                "registration_data": {
                    "trading_account_id": str(account_id),
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
                "account_id": str(account_id),
                "registration_status": "pending_verification",
                "onboarding_state": "submitted_for_verification",
                "last_activity": get_current_timestamp()
            })

            _send_typing(bot, telegram_id, 1.5)
            bot.send_message(
                telegram_id,
                f"✅ **Account ID Received:** `{account_id}`\n\n"
                "Your registration is now pending manual verification. ⏳\n"
                "Once approved, your **1-Time VIP Access Link** will be sent here!",
                parse_mode="Markdown"
            )

            if registration:
                try:
                    self.verification_service.notify_admin_about_registration(registration)
                except Exception as ne:
                    logger.error(f"Failed to notify channel for registration {telegram_id}: {ne}")

            logger.info(f"9-digit account ID submitted by {telegram_id}: {account_id}")
        except Exception as e:
            logger.error(f"Account ID submit failed for {telegram_id}: {e}", exc_info=True)
            bot.send_message(telegram_id, "Something went wrong while submitting your ID. Please try again.")

    def _process_combined_message(self, telegram_id: int, combined_text: str, user: dict):
        """Process user message with strict checks."""
        try:
            bot = self.bot
            text = sanitize_text(combined_text)
            if not text:
                return

            # 1. Strict 9-Digit Trading Account ID Check
            account_id_9 = _extract_exact_9digit_id(text)
            if account_id_9:
                self._submit_account_id(telegram_id, account_id_9, user)
                return

            # 2. Strict Check for Non-9-Digit Number Attempts (e.g. 5, 8, 10, 11 digits)
            if _is_invalid_number_attempt(text):
                _send_typing(bot, telegram_id, 1.0)
                bot.send_message(
                    telegram_id,
                    "⚠️ **Invalid Account ID**\n\n"
                    "Your Trading account Id must strictly be only 9 digits.\n\n"
                    "👉 **Example:** `123456789`\n\n"
                    "Kindly resend your 9 digit trading ID correctly! 📝",
                    parse_mode="Markdown"
                )
                return

            # 3. Check 'Already Registered' Intent (Do NOT send video, ask for ID)
            if _is_already_registered_intent(text):
                _send_typing(bot, telegram_id, 1.2)
                already_reg_reply = (
                    "That’s great! Since you're already registered, we just need to verify your account. "
                    "Please send your **9-digit Trading Account ID** here so I can get your VIP access approved! 🆔\n\n"
                    "👉 **Example:** `123456789`"
                )
                bot.send_message(telegram_id, already_reg_reply, parse_mode="Markdown")
                self.registration_service.set_registration_state(telegram_id, "awaiting_account_id")
                return

            # 4. Check VIP and Registration Intent (Send Video)
            text_lower = text.lower().strip()
            exact_vip_words = {"vip", "v.i.p", "viip", "join"}
            words_in_text = set(re.findall(r'\b\w+\b', text_lower))

            registration_keywords = [
                "vip join", "join vip", "how to join", "how to register",
                "joining link", "registration link", "account create", "vip registration",
                "want vip", "join the vip", "vip process", "vip steps", "full process",
                "registration video", "vip video", "process video", "registration process",
                "vip reg", "regesitt", "link pampu", "join link", "vip link", "send link", "send video"
            ]

            # Exact 'register' word only if not saying 'already'
            if "register" in words_in_text and "already" not in text_lower:
                is_direct_vip = True
            else:
                is_direct_vip = bool(words_in_text & exact_vip_words) or any(k in text_lower for k in registration_keywords)

            if is_direct_vip:
                try:
                    bot.send_chat_action(telegram_id, "upload_video")
                except Exception:
                    pass
                time.sleep(0.5)
                promo.send_registration_steps(bot, telegram_id)
                return

            # 5. Route text/words/questions (e.g. 'Brooo', 'Abc', general chat) to AI FAQ
            response = ai_service.generate_response(text, user)

            if response.get("support_needed"):
                ticket = self.support_service.create_ticket(
                    telegram_id, text, response.get("intent", "SUPPORT")
                )
                if ticket and ticket.get("id"):
                    self.support_service.notify_admin_about_ticket(ticket)
                reply_text = response.get(
                    "response",
                    "I have forwarded your query to the support team. They will get back to you shortly."
                )
                delay = _calc_typing_delay(reply_text)
                _send_typing(bot, telegram_id, delay)
                bot.send_message(telegram_id, reply_text)
                return

            reply_text = response.get(
                "response",
                "I understood your question. Type VIP to get the registration video and steps!"
            )

            intent = (response.get("intent") or "").upper()
            ai_mentions_video = any(
                phrase in reply_text.lower()
                for phrase in ["sending the vip", "registration video", "sending the video", "vip registration video"]
            )

            if intent == "REGISTRATION" or ai_mentions_video:
                if not _is_already_registered_intent(text):
                    try:
                        bot.send_chat_action(telegram_id, "upload_video")
                    except Exception:
                        pass
                    time.sleep(0.5)
                    promo.send_registration_steps(bot, telegram_id)
                    return
                else:
                    reply_text = "Please send your 9-digit Trading Account ID so we can verify your VIP access! 🆔"

            delay = _calc_typing_delay(reply_text)
            _send_typing(bot, telegram_id, delay)
            bot.send_message(telegram_id, reply_text)

        except Exception as e:
            logger.error(f"FAQ process failed for user {telegram_id}: {e}", exc_info=True)
            try:
                self.bot.send_message(
                    telegram_id,
                    "Write **VIP** to receive the registration video and VIP joining steps! 🔥",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    def _flush_pending(self, telegram_id: int):
        with _pending_lock:
            entry = _pending_messages.pop(telegram_id, None)
        if not entry:
            return
        texts = entry.get("texts") or []
        user = entry.get("user") or {}
        combined = " ".join(t.strip() for t in texts if t and t.strip())
        if combined:
            self._process_combined_message(telegram_id, combined, user)

    def register(self):
        bot = self.bot

        def is_faq_eligible(message: Message) -> bool:
            if not message.text or message.text.startswith('/'):
                return False
            telegram_id = message.from_user.id
            if self.support_service.is_awaiting_support(telegram_id):
                return False
            return True

        @bot.message_handler(func=is_faq_eligible, content_types=['text'])
        def handle_faq_message(message: Message):
            try:
                telegram_id = message.from_user.id
                user = database.get_user(telegram_id)
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

                text = sanitize_text(message.text)
                if not text:
                    return

                # Instant processing for direct triggers
                if (
                    text.lower() in ["vip", "v.i.p"]
                    or _extract_exact_9digit_id(text)
                    or _is_invalid_number_attempt(text)
                    or _is_already_registered_intent(text)
                ):
                    self._process_combined_message(telegram_id, text, user)
                    return

                # Conversational AI debounce
                with _pending_lock:
                    entry = _pending_messages.get(telegram_id)
                    if entry:
                        try:
                            entry["timer"].cancel()
                        except Exception:
                            pass
                        entry["texts"].append(text)
                        entry["user"] = user
                    else:
                        entry = {"texts": [text], "user": user, "timer": None}
                        _pending_messages[telegram_id] = entry

                    timer = threading.Timer(
                        DEBOUNCE_SECONDS,
                        self._flush_pending,
                        args=(telegram_id,)
                    )
                    timer.daemon = True
                    entry["timer"] = timer
                    timer.start()

                try:
                    bot.send_chat_action(telegram_id, "typing")
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"FAQ handler failed for user {message.from_user.id}: {e}", exc_info=True)

        @bot.callback_query_handler(func=lambda call: call.data == "faq")
        def faq_callback(call: CallbackQuery):
            try:
                bot.answer_callback_query(call.id)
                bot.send_message(
                    call.from_user.id,
                    "You can ask me anything about registration, deposits, withdrawals, courses, or access. Just type your question here 😊",
                    reply_markup=get_back_keyboard("back_to_main")
                )
            except Exception as e:
                logger.error(f"FAQ callback failed: {e}")

        @bot.callback_query_handler(func=lambda call: call.data == "end_faq")
        def end_faq_callback(call: CallbackQuery):
            try:
                bot.answer_callback_query(call.id)
                bot.send_message(call.from_user.id, "Thank you! Feel free to ask anytime if you need help.")
            except Exception as e:
                logger.error(f"End FAQ callback failed: {e}")


def register_faq_handlers(
    bot: TeleBot,
    registration_service: RegistrationService = None,
    support_service: SupportService = None,
    onboarding_service: OnboardingService = None
):
    handler = FAQHandler(bot, registration_service, support_service, onboarding_service)
    handler.register()
