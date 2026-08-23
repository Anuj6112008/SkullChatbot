import logging
import re
import time
import html
import threading
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from config import config
from database import database
from services.channel import ChannelService
from services.onboarding import (
    OnboardingService,
    STATE_AWAITING_EXPERIENCE,
    STATE_AWAITING_NAME,
    STATE_AWAITING_AGE_OCCUPATION,
    STATE_AWAITING_CAPITAL,
    STATE_AWAITING_POSITIVE_INTENT,
    STATE_AWAITING_SCREENSHOT,
    STATE_AWAITING_ACCOUNT_ID,
    STATE_PENDING_APPROVAL,
    STATE_COMPLETED
)
from services import promo
from keyboards import get_screenshot_review_keyboard
from utils import sanitize_text, get_current_timestamp

logger = logging.getLogger(__name__)

STOPWORDS = {
    "my", "is", "am", "i", "im", "i'm", "age", "years", "old", "yr", "yrs",
    "the", "a", "an", "and", "in", "at", "to", "for", "of", "currently",
    "working", "as", "profession", "job", "doing", "na", "nadi", "lo", "unna", "unnaru"
}


def _send_typing(bot: TeleBot, chat_id: int, delay: float = 1.5):
    """Show realistic 'typing...' indicator in chat header for 1.5 seconds before message."""
    try:
        bot.send_chat_action(chat_id, "typing")
        time.sleep(delay)
    except Exception:
        pass


class OnboardingHandler:
    def __init__(self, bot: TeleBot, onboarding_service: OnboardingService = None):
        self.bot = bot
        self.onboarding_service = onboarding_service or OnboardingService(bot)
        self.channel_service = ChannelService(bot)

    def register(self):
        bot = self.bot
        svc = self.onboarding_service

        # 1. Experience Step
        @bot.message_handler(func=lambda m: bool(m.text) and not m.text.startswith('/') and svc.get_state(m.from_user.id) == STATE_AWAITING_EXPERIENCE)
        def handle_experience(message: Message):
            self._handle_experience_step(message)

        # 2. Name Step
        @bot.message_handler(func=lambda m: bool(m.text) and not m.text.startswith('/') and svc.get_state(m.from_user.id) == STATE_AWAITING_NAME)
        def handle_name(message: Message):
            self._handle_name_step(message)

        # 3. Age & Profession Step
        @bot.message_handler(func=lambda m: bool(m.text) and not m.text.startswith('/') and svc.get_state(m.from_user.id) == STATE_AWAITING_AGE_OCCUPATION)
        def handle_age_occupation(message: Message):
            self._handle_age_profession_step(message)

        # 4. Capital Step
        @bot.message_handler(func=lambda m: bool(m.text) and not m.text.startswith('/') and svc.get_state(m.from_user.id) == STATE_AWAITING_CAPITAL)
        def handle_capital(message: Message):
            self._handle_capital_step(message)

        # 5. Interactive Pitching / Positive Intent Step
        @bot.message_handler(func=lambda m: bool(m.text) and not m.text.startswith('/') and svc.get_state(m.from_user.id) == STATE_AWAITING_POSITIVE_INTENT)
        def handle_positive_intent(message: Message):
            self._handle_positive_intent_step(message)

        # 6. Screenshot Step -> Ask 9-digit Trading ID
        @bot.message_handler(content_types=['photo'], func=lambda m: svc.is_awaiting_screenshot(m.from_user.id))
        def handle_screenshot(message: Message):
            self._handle_screenshot(message)

        # 7. 9-Digit Trading Account ID Step -> Submit Verification
        @bot.message_handler(func=lambda m: bool(m.text) and not m.text.startswith('/') and svc.is_awaiting_account_id(m.from_user.id))
        def handle_account_id(message: Message):
            self._handle_account_id_step(message)

        # Admin Review Callbacks (Updates Channel Only)
        @bot.callback_query_handler(func=lambda call: call.data.startswith("ss_accept_"))
        def handle_accept(call: CallbackQuery):
            self._handle_admin_decision(call, accept=True)

        @bot.callback_query_handler(func=lambda call: call.data.startswith("ss_reject_"))
        def handle_reject(call: CallbackQuery):
            self._handle_admin_decision(call, accept=False)

    # ------------------------------------------------------------------
    # Step 1: Experience
    # ------------------------------------------------------------------
    def _handle_experience_step(self, message: Message):
        telegram_id = message.from_user.id
        text = sanitize_text(message.text)
        if not text:
            return

        svc = self.onboarding_service
        svc.clear_hot_lead(telegram_id)
        svc.save_answer(telegram_id, "experience", text)

        clean = text.lower()
        no_exp_words = ["no", "never", "zero", "beginner", "fresher", "new", "start", "starting", "le", "ledu", "nill", "nil", "none", "not"]
        is_beginner = any(re.search(rf"\b{k}\b", clean) for k in no_exp_words)

        _send_typing(self.bot, telegram_id, 1.5)
        if is_beginner:
            self.bot.send_message(telegram_id, "Parledu, nen kooda 2 years back zero nunde start chesa 😊")
        else:
            self.bot.send_message(telegram_id, "oh NIce")

        _send_typing(self.bot, telegram_id, 1.2)
        self.bot.send_message(telegram_id, "Sorry, adagadam marchipoya - what's your Name?")
        svc.set_state(telegram_id, STATE_AWAITING_NAME)

    # ------------------------------------------------------------------
    # Step 2: Name -> EXACTLY 2 messages with typing
    # ------------------------------------------------------------------
    def _handle_name_step(self, message: Message):
        telegram_id = message.from_user.id
        raw_name = sanitize_text(message.text)
        if not raw_name:
            return

        name = re.sub(r"^(?:my\s+name\s+is|i\s+am|i'm|im|this\s+is|na\s+peru)\s+", "", raw_name, flags=re.IGNORECASE).strip().title()
        if not name:
            name = raw_name.strip().title()

        svc = self.onboarding_service
        svc.clear_hot_lead(telegram_id)
        svc.save_answer(telegram_id, "name", name)

        _send_typing(self.bot, telegram_id, 1.5)
        self.bot.send_message(telegram_id, f"Nice to meet you, {name}!")

        _send_typing(self.bot, telegram_id, 1.5)
        self.bot.send_message(telegram_id, f"{name}, Mi age and aee profession lo unnaru?")

        svc.set_state(telegram_id, STATE_AWAITING_AGE_OCCUPATION)

    # ------------------------------------------------------------------
    # Step 3: Age + Profession Strict Isolation
    # ------------------------------------------------------------------
    def _handle_age_profession_step(self, message: Message):
        telegram_id = message.from_user.id
        text = sanitize_text(message.text)
        if not text:
            return

        svc = self.onboarding_service
        svc.clear_hot_lead(telegram_id)
        existing_data = svc.get_data(telegram_id)

        current_age = existing_data.get("age")
        current_prof = existing_data.get("profession")

        extracted_age, extracted_prof = self._extract_age_and_profession(text)

        final_age = extracted_age or current_age
        final_prof = extracted_prof or current_prof

        if final_age and final_prof:
            svc.save_answers_dict(telegram_id, {
                "age": str(final_age),
                "profession": str(final_prof)
            })
            _send_typing(self.bot, telegram_id, 1.5)
            self.bot.send_message(telegram_id, "GOOD !  As of now me daggara trading capital entha undi in INR?")
            svc.set_state(telegram_id, STATE_AWAITING_CAPITAL)
            return

        if final_age and not final_prof:
            svc.save_answer(telegram_id, "age", str(final_age))
            _send_typing(self.bot, telegram_id, 1.5)
            self.bot.send_message(telegram_id, "Mee profession cheppadam marchipoyaru, please mee profession kooda cheppandi.")
            return

        if final_prof and not final_age:
            svc.save_answer(telegram_id, "profession", str(final_prof))
            _send_typing(self.bot, telegram_id, 1.5)
            self.bot.send_message(telegram_id, "Mee age cheppadam marchipoyaru, please mee age kooda cheppandi.")
            return

        _send_typing(self.bot, telegram_id, 1.5)
        self.bot.send_message(telegram_id, "Mee age and profession rendu cheppandi (e.g. 24 Software Engineer).")

    def _extract_age_and_profession(self, text: str):
        clean_text = text.strip()

        if clean_text.isdigit():
            val = int(clean_text)
            if 15 <= val <= 85:
                return val, None

        age_match = re.search(r"\b(?:age\s*(?:is|=|:)?\s*)?([1-9][0-9])\b", clean_text, flags=re.IGNORECASE)
        if age_match:
            potential_age = int(age_match.group(1))
            if 15 <= potential_age <= 85:
                age = potential_age
                rem = clean_text[:age_match.start()] + " " + clean_text[age_match.end():]
                tokens = re.findall(r"[a-zA-Z]+", rem)
                meaningful = [t for t in tokens if t.lower() not in STOPWORDS]
                profession = " ".join(meaningful).title() if meaningful else None
                return age, profession

        tokens = re.findall(r"[a-zA-Z]+", clean_text)
        meaningful = [t for t in tokens if t.lower() not in STOPWORDS]
        profession = " ".join(meaningful).title() if meaningful else None

        return None, profession

    # ------------------------------------------------------------------
    # Step 4: Capital
    # ------------------------------------------------------------------
    def _handle_capital_step(self, message: Message):
        telegram_id = message.from_user.id
        text = sanitize_text(message.text)
        if not text:
            return

        svc = self.onboarding_service
        svc.clear_hot_lead(telegram_id)

        parsed_amount = svc.parse_capital_amount(text)
        if parsed_amount is None:
            _send_typing(self.bot, telegram_id, 1.2)
            self.bot.send_message(telegram_id, "Mee trading capital amount entha undo numbers lo cheppandi (e.g. 5000 or 10000):")
            return

        svc.save_answer(telegram_id, "capital", text)
        svc.save_answer(telegram_id, "capital_amount", parsed_amount)

        response_text = promo.get_capital_response(parsed_amount)
        _send_typing(self.bot, telegram_id, 1.5)
        self.bot.send_message(telegram_id, response_text)

        svc.set_state(telegram_id, STATE_AWAITING_POSITIVE_INTENT)
        svc.clear_promo_stage(telegram_id)

    # ------------------------------------------------------------------
    # Step 5: Multi-Stage Interactive Pitching Flow
    # ------------------------------------------------------------------
    def _handle_positive_intent_step(self, message: Message):
        telegram_id = message.from_user.id
        text = sanitize_text(message.text)
        if not text:
            return

        svc = self.onboarding_service
        svc.clear_hot_lead(telegram_id)

        current_promo_stage = svc.get_promo_stage(telegram_id)

        if current_promo_stage is None:
            _send_typing(self.bot, telegram_id, 1.5)
            promo.send_testimonials(self.bot, telegram_id)
            svc.set_promo_stage(telegram_id, "testimonials_sent")
            return

        if current_promo_stage == "testimonials_sent":
            _send_typing(self.bot, telegram_id, 1.5)
            promo.send_no_fee_message(self.bot, telegram_id)
            _send_typing(self.bot, telegram_id, 1.2)
            promo.send_vip_benefits(self.bot, telegram_id)
            svc.set_promo_stage(telegram_id, "benefits_sent")
            return

        if current_promo_stage in ["fee_sent", "benefits_sent"]:
            _send_typing(self.bot, telegram_id, 1.5)
            promo.send_ask_to_join(self.bot, telegram_id)
            svc.set_promo_stage(telegram_id, "asked_sent")
            return

        if current_promo_stage in ["asked_sent", "reengagement_sent"]:
            svc.clear_promo_stage(telegram_id)
            _send_typing(self.bot, telegram_id, 1.5)
            promo.send_registration_steps(self.bot, telegram_id)
            svc.mark_registration_steps_sent(telegram_id)
            svc.set_state(telegram_id, STATE_AWAITING_SCREENSHOT)
            return

    # ------------------------------------------------------------------
    # Step 6: Screenshot Received -> Ask for 9-Digit Account ID
    # ------------------------------------------------------------------
    def _handle_screenshot(self, message: Message):
        telegram_id = message.from_user.id
        svc = self.onboarding_service
        try:
            user = database.get_user(telegram_id)
            if not user:
                return

            svc.clear_hot_lead(telegram_id)
            svc.clear_promo_stage(telegram_id)

            photo = message.photo[-1]
            file_id = photo.file_id

            svc.save_answer(telegram_id, "screenshot_file_id", file_id)
            svc.set_state(telegram_id, STATE_AWAITING_ACCOUNT_ID)

            _send_typing(self.bot, telegram_id, 1.5)
            self.bot.send_message(
                telegram_id,
                "Mee registration screenshot successfully receive ayindi, thank you! 👍"
            )
            _send_typing(self.bot, telegram_id, 1.5)
            self.bot.send_message(
                telegram_id,
                "Ippudu mee screenshot lo unna 9 Digit Trading Account ID ni ikkada message ga send cheyandi (e.g. 123554267)."
            )
            logger.info(f"Received screenshot from {telegram_id}, now awaiting 9-digit trading ID")
        except Exception as e:
            logger.error(f"Failed to handle screenshot: {e}")
            try:
                self.bot.send_message(telegram_id, "Sorry, something went wrong. Please send the screenshot again.")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Step 7: 9-Digit Account ID Received -> Submit Complete Verification
    # ------------------------------------------------------------------
    def _handle_account_id_step(self, message: Message):
        telegram_id = message.from_user.id
        text = sanitize_text(message.text)
        if not text:
            return

        svc = self.onboarding_service
        user = database.get_user(telegram_id)
        if not user:
            return

        svc.clear_hot_lead(telegram_id)

        account_id_match = re.search(r"\b(\d{6,14})\b", text)
        account_id = account_id_match.group(1) if account_id_match else text.strip()

        if not account_id:
            _send_typing(self.bot, telegram_id, 1.2)
            self.bot.send_message(
                telegram_id,
                "Please mee 9 digit trading account ID ni ikkada text ga send cheyandi:"
            )
            return

        svc.save_answer(telegram_id, "trading_account_id", account_id)

        data = svc.get_data(telegram_id)
        registration_data = dict(data)
        registration_data["trading_account_id"] = account_id
        registration_data["full_name"] = data.get("name", user.get("first_name", ""))
        registration_data["username"] = user.get("username", "")

        try:
            reg = database.create_registration({
                "telegram_id": telegram_id,
                "registration_data": registration_data,
                "verification_status": "pending"
            })

            if not reg or not reg.get("id"):
                self.bot.send_message(telegram_id, "Sorry, something went wrong. Please send your account ID again.")
                return

            registration_id = reg.get("id")
            database.update_user(telegram_id, {
                "registration_status": "pending_verification",
                "last_activity": get_current_timestamp(),
                "registration_nudge_sent": False
            })

            svc.set_state(telegram_id, STATE_PENDING_APPROVAL)

            _send_typing(self.bot, telegram_id, 1.5)
            self.bot.send_message(
                telegram_id,
                f"Thank you! Mee screenshot and Trading Account ID ({account_id}) verification kosam team ki forward chesam. "
                "Approve avvagane meeku ikkade update vasthundi. 🎉"
            )

            # Send review card ONLY to Updates Channel with click-to-copy HTML code format
            self._notify_updates_channel_only(registration_id, registration_data, user)
            logger.info(f"Verification submitted for {telegram_id} with Account ID: {account_id}")

        except Exception as e:
            logger.error(f"Failed to submit account ID registration for {telegram_id}: {e}")

    def _notify_updates_channel_only(self, registration_id, registration_data, user):
        """Send verification card ONLY to Updates Channel with <code>account_id</code> for 1-tap copy."""
        if not config.UPDATES_CHANNEL_ID:
            logger.warning("UPDATES_CHANNEL_ID is not configured, cannot post review card.")
            return

        try:
            chat_id = int(config.UPDATES_CHANNEL_ID)
            file_id = registration_data.get("screenshot_file_id")

            caption = "🆕 <b>New Registration Request</b>\n\n"
            caption += f"👤 <b>Name:</b> {html.escape(str(registration_data.get('full_name', 'N/A')))}\n"
            caption += f"🆔 <b>Telegram ID:</b> <code>{user.get('telegram_id')}</code>\n"
            if registration_data.get("username"):
                caption += f"📱 <b>Username:</b> @{html.escape(str(registration_data.get('username')))}\n"
            caption += f"📊 <b>Experience:</b> {html.escape(str(registration_data.get('experience', 'N/A')))}\n"
            caption += f"🎂 <b>Age:</b> {html.escape(str(registration_data.get('age', 'N/A')))}\n"
            caption += f"💼 <b>Profession:</b> {html.escape(str(registration_data.get('profession', 'N/A')))}\n"
            caption += f"💰 <b>Capital:</b> {html.escape(str(registration_data.get('capital', 'N/A')))}\n"
            caption += f"💳 <b>Trading Account ID:</b> <code>{html.escape(str(registration_data.get('trading_account_id', 'N/A')))}</code>\n"
            caption += f"\n📝 <b>Registration ID:</b> #{registration_id}"

            if file_id:
                self.bot.send_photo(
                    chat_id,
                    file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=get_screenshot_review_keyboard(registration_id)
                )
            else:
                self.bot.send_message(
                    chat_id,
                    caption,
                    parse_mode="HTML",
                    reply_markup=get_screenshot_review_keyboard(registration_id)
                )
            logger.info(f"Sent review card for #{registration_id} exclusively to Updates Channel {chat_id}")
        except Exception as e:
            logger.error(f"Failed to post to Updates Channel: {e}")

    # ------------------------------------------------------------------
    # Admin Accept / Reject Decision with 1-Time VIP Link & 2-Minute Resources
    # ------------------------------------------------------------------
    def _handle_admin_decision(self, call: CallbackQuery, accept: bool):
        try:
            if not config.is_admin(call.from_user.id):
                try:
                    self.bot.answer_callback_query(call.id, "Unauthorized")
                except Exception:
                    pass
                return

            registration_id = int(call.data.split("_")[2])
            registration = database.get_registration(registration_id)
            if not registration or registration.get("verification_status") != "pending":
                try:
                    self.bot.answer_callback_query(call.id, "Already processed")
                except Exception:
                    pass
                return

            telegram_id = registration.get("telegram_id")

            if accept:
                try:
                    self.bot.answer_callback_query(call.id, "Accepting & generating VIP link...")
                except Exception:
                    pass

                now_ts = get_current_timestamp()
                user_data = database.get_user(telegram_id) or {}
                onboarding_data = user_data.get("onboarding_data") or {}
                if isinstance(onboarding_data, str):
                    try:
                        import json
                        onboarding_data = json.loads(onboarding_data)
                    except Exception:
                        onboarding_data = {}

                onboarding_data["vip_approved_at"] = now_ts
                onboarding_data["vip_resources_sent"] = False

                database.update_registration(registration_id, {
                    "verification_status": "approved",
                    "verified_by": call.from_user.id,
                    "verified_at": now_ts
                })
                database.update_user(telegram_id, {
                    "member_type": "vip",
                    "verification_status": "approved",
                    "registration_status": "registered",
                    "onboarding_state": STATE_COMPLETED,
                    "verified_at": now_ts,
                    "onboarding_data": onboarding_data,
                    "hot_lead_active": False
                })

                try:
                    self.channel_service.grant_course_access(telegram_id)
                    self.channel_service.grant_updates_access(telegram_id)
                except Exception as e:
                    logger.error(f"Failed to grant access after approval: {e}")

                invite_link = None
                if config.PAID_CHANNEL_ID:
                    try:
                        invite_link = self.channel_service.create_single_use_invite_link(
                            chat_id=int(config.PAID_CHANNEL_ID),
                            name=f"VIP_{telegram_id}"
                        )
                    except Exception as e:
                        logger.error(f"Error creating single use link: {e}")

                if invite_link:
                    approval_msg = (
                        "Mee registration request approve ayindi ✅ and mee VIP access active ayindi! 🎉\n\n"
                        "Idi mee exclusive one-time VIP Community Joining Link 👇\n"
                        f"{invite_link}\n\n"
                        "⚠️ Note: Ee link okkasari matrame pani chesthundi. Join avvagane expire avthundi."
                    )
                else:
                    approval_msg = (
                        "Mee registration request approve ayindi ✅ and mee VIP access active ayindi! Welcome to VIP Community! 🎉"
                    )

                try:
                    _send_typing(self.bot, telegram_id, 1.5)
                    self.bot.send_message(telegram_id, approval_msg)
                except Exception as e:
                    logger.error(f"Failed to notify user {telegram_id} of approval: {e}")

                # DIRECT 2-MINUTE TIMER: Guaranteed delivery of VIP resources in 120s
                def _send_delayed_vip_resources(tid):
                    try:
                        time.sleep(120)
                        u = database.get_user(tid)
                        if u and u.get("verification_status") == "approved":
                            odata = u.get("onboarding_data") or {}
                            if isinstance(odata, str):
                                try:
                                    import json
                                    odata = json.loads(odata)
                                except Exception:
                                    odata = {}
                            if not odata.get("vip_resources_sent"):
                                _send_typing(self.bot, tid, 1.5)
                                promo.send_vip_resources(self.bot, tid)
                                odata["vip_resources_sent"] = True
                                database.update_user(tid, {"onboarding_data": odata})
                                logger.info(f"Direct timer sent VIP resources to {tid}")
                    except Exception as ex:
                        logger.error(f"Failed delayed VIP resources timer for {tid}: {ex}")

                threading.Thread(target=_send_delayed_vip_resources, args=(telegram_id,), daemon=True).start()

                try:
                    if call.message.caption:
                        self.bot.edit_message_caption(
                            caption=f"{call.message.caption}\n\n✅ ACCEPTED",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id
                        )
                    else:
                        self.bot.edit_message_text(
                            f"{call.message.text}\n\n✅ ACCEPTED",
                            call.message.chat.id,
                            call.message.message_id
                        )
                except Exception:
                    pass
            else:
                try:
                    self.bot.answer_callback_query(call.id, "Rejecting...")
                except Exception:
                    pass

                database.update_registration(registration_id, {
                    "verification_status": "rejected",
                    "verified_by": call.from_user.id,
                    "verified_at": get_current_timestamp(),
                    "rejection_reason": "Registration declined by admin"
                })
                database.update_user(telegram_id, {
                    "member_type": "normal",
                    "verification_status": "rejected",
                    "registration_status": "rejected",
                    "onboarding_state": STATE_COMPLETED,
                    "hot_lead_active": False
                })

                link = config.get_joining_link() or ""
                reject_msg = (
                    "❌ Mee registration request reject ayindi because meeru maa VIP link dwara join avvaledu."
                )
                if link:
                    reject_msg += f"\n\nEe platform link use chesi register avvandi:\n{link}"

                try:
                    _send_typing(self.bot, telegram_id, 1.2)
                    self.bot.send_message(telegram_id, reject_msg)
                except Exception as e:
                    logger.error(f"Failed to notify user {telegram_id} of rejection: {e}")

                try:
                    if call.message.caption:
                        self.bot.edit_message_caption(
                            caption=f"{call.message.caption}\n\n❌ REJECTED",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id
                        )
                    else:
                        self.bot.edit_message_text(
                            f"{call.message.text}\n\n❌ REJECTED",
                            call.message.chat.id,
                            call.message.message_id
                        )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Failed to handle admin decision: {e}")


def register_onboarding_handlers(bot: TeleBot, onboarding_service: OnboardingService = None):
    handler = OnboardingHandler(bot, onboarding_service)
    handler.register()
    return handler.onboarding_service
