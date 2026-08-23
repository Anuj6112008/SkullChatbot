import logging
import re
import time
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

        # 6. Screenshot Handler
        @bot.message_handler(content_types=['photo'], func=lambda m: svc.is_awaiting_screenshot(m.from_user.id))
        def handle_screenshot(message: Message):
            self._handle_screenshot(message)

        # Admin Review Callbacks
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

        if is_beginner:
            self.bot.send_message(telegram_id, "Parledu, nen kooda 2 years back Zero🤭 nunde start chesa")
        else:
            self.bot.send_message(telegram_id, "oh NIce")

        self.bot.send_message(telegram_id, "Sorry, adagadam marchipoya - what's your Name?")
        svc.set_state(telegram_id, STATE_AWAITING_NAME)

    # ------------------------------------------------------------------
    # Step 2: Name -> EXACTLY 2 messages
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

        self.bot.send_message(telegram_id, f"Nice to meet you, {name}!🤝")
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

        # Both present
        if final_age and final_prof:
            svc.save_answers_dict(telegram_id, {
                "age": str(final_age),
                "profession": str(final_prof)
            })
            self.bot.send_message(telegram_id, "GOOD !  As of now me daggara 𝐓𝐫𝐚𝐝𝐢𝐧𝐠 𝐜𝐚𝐩𝐢𝐭𝐚𝐥 entha undi in 𝐈𝐍𝐑?")
            svc.set_state(telegram_id, STATE_AWAITING_CAPITAL)
            return

        # Only Age present
        if final_age and not final_prof:
            svc.save_answer(telegram_id, "age", str(final_age))
            self.bot.send_message(telegram_id, "Mee 𝐏𝐫𝐨𝐟𝐞𝐬𝐬𝐢𝐨𝐧 cheppadam marchipoyaru, please mee 𝐏𝐫𝐨𝐟𝐞𝐬𝐬𝐢𝐨𝐧 kooda cheppandi.")
            return

        # Only Profession present
        if final_prof and not final_age:
            svc.save_answer(telegram_id, "profession", str(final_prof))
            self.bot.send_message(telegram_id, "Mee 𝐀𝐠𝐞 cheppadam marchipoyaru, please mee 𝐀𝐠𝐞 kooda cheppandi.")
            return

        # Neither parsed
        self.bot.send_message(telegram_id, "Mee 𝐀𝐠𝐞 and 𝐏𝐫𝐨𝐟𝐞𝐬𝐬𝐢𝐨𝐧 rendu cheppandi (e.g. 24 Software Engineer).")

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
            self.bot.send_message(telegram_id, "Mee 𝐓𝐫𝐚𝐝𝐢𝐧𝐠 𝐜𝐚𝐩𝐢𝐭𝐚𝐥 amount entha undo numbers lo cheppandi (e.g. 5000 or 10000):")
            return

        svc.save_answer(telegram_id, "capital", text)
        svc.save_answer(telegram_id, "capital_amount", parsed_amount)

        response_text = promo.get_capital_response(parsed_amount)
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

        # Stage 1: User replies right after Capital answer -> Send Testimonials
        if current_promo_stage is None:
            promo.send_testimonials(self.bot, telegram_id)
            svc.set_promo_stage(telegram_id, "testimonials_sent")
            return

        # Stage 2: User replies after Testimonials -> Send No-Fee message + VIP Benefits
        if current_promo_stage == "testimonials_sent":
            promo.send_no_fee_message(self.bot, telegram_id)
            time.sleep(1)
            promo.send_vip_benefits(self.bot, telegram_id)
            svc.set_promo_stage(telegram_id, "benefits_sent")
            return

        # Stage 3: User replies after VIP Benefits -> Send "Want to join the VIP community?"
        if current_promo_stage in ["fee_sent", "benefits_sent"]:
            promo.send_ask_to_join(self.bot, telegram_id)
            svc.set_promo_stage(telegram_id, "asked_sent")
            return

        # Stage 4: User replies to "Want to join..." -> Send Registration Steps + Link + Video
        if current_promo_stage in ["asked_sent", "reengagement_sent"]:
            svc.clear_promo_stage(telegram_id)
            promo.send_registration_steps(self.bot, telegram_id)
            svc.mark_registration_steps_sent(telegram_id)
            svc.set_state(telegram_id, STATE_AWAITING_SCREENSHOT)
            return

    # ------------------------------------------------------------------
    # Step 6: Screenshot Handling + Review Card
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
            data = svc.get_data(telegram_id)

            registration_data = dict(data)
            registration_data["screenshot_file_id"] = file_id
            registration_data["full_name"] = data.get("name", user.get("first_name", ""))
            registration_data["username"] = user.get("username", "")

            reg = database.create_registration({
                "telegram_id": telegram_id,
                "registration_data": registration_data,
                "verification_status": "pending"
            })

            if not reg or not reg.get("id"):
                self.bot.send_message(telegram_id, "Sorry, something went wrong. Please send the screenshot again.")
                return

            registration_id = reg.get("id")
            database.update_user(telegram_id, {
                "registration_status": "pending_verification",
                "last_activity": get_current_timestamp(),
                "registration_nudge_sent": False
            })

            svc.set_state(telegram_id, STATE_PENDING_APPROVAL)

            self.bot.send_message(
                telegram_id,
                "Mee registration verification kosam team ki send chesam. "
                "Approve avvagane meeku ikkade update vasthundi."
            )

            self._notify_admin_channel(registration_id, registration_data, user)
        except Exception as e:
            logger.error(f"Failed to handle screenshot: {e}")

    def _notify_admin_channel(self, registration_id, registration_data, user):
        try:
            caption = "🆕 New Registration Screenshot\n\n"
            caption += f"👤 Name: {registration_data.get('full_name', 'N/A')}\n"
            caption += f"🆔 Telegram ID: {user.get('telegram_id')}\n"
            if registration_data.get("username"):
                caption += f"📱 Username: @{registration_data.get('username')}\n"
            caption += f"📊 Experience: {registration_data.get('experience', 'N/A')}\n"
            caption += f"🎂 Age: {registration_data.get('age', 'N/A')}\n"
            caption += f"💼 Profession: {registration_data.get('profession', 'N/A')}\n"
            caption += f"💰 Capital: {registration_data.get('capital', 'N/A')}\n"
            caption += f"\n📝 Registration ID: #{registration_id}"

            file_id = registration_data.get("screenshot_file_id")
            recipients = []
            if config.UPDATES_CHANNEL_ID:
                recipients.append(int(config.UPDATES_CHANNEL_ID))
            for admin_id in config.get_admin_ids():
                if admin_id not in recipients:
                    recipients.append(admin_id)

            for chat_id in recipients:
                try:
                    if file_id:
                        self.bot.send_photo(
                            chat_id,
                            file_id,
                            caption=caption,
                            reply_markup=get_screenshot_review_keyboard(registration_id)
                        )
                    else:
                        self.bot.send_message(
                            chat_id,
                            caption,
                            reply_markup=get_screenshot_review_keyboard(registration_id)
                        )
                except Exception as e:
                    logger.error(f"Failed to notify {chat_id} about registration {registration_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to notify admin channel: {e}")

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