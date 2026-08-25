import logging
import time
import json
import pytz
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from telebot import TeleBot
from config import config
from database import database
from services.channel import ChannelService
from services.onboarding import (
    STATE_AWAITING_POSITIVE_INTENT,
    STATE_AWAITING_ACCOUNT_ID
)
from services import promo
from utils import get_current_datetime, get_current_timestamp

logger = logging.getLogger(__name__)

DAY1_DELAYS_MIN = [15, 30, 60, 300]


def _get_scheduler_tz():
    try:
        return pytz.timezone("Asia/Kolkata")
    except Exception:
        return pytz.UTC


def _parse_iso_datetime(dt_val):
    if not dt_val:
        return None
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            return dt_val.replace(tzinfo=pytz.UTC)
        return dt_val
    if isinstance(dt_val, str):
        try:
            clean_str = dt_val.replace('Z', '+00:00')
            parsed = datetime.fromisoformat(clean_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=pytz.UTC)
            return parsed
        except Exception:
            return None
    return None


class SchedulerService:
    def __init__(self, bot: TeleBot, onboarding_service=None):
        self.bot = bot
        self.channel_service = ChannelService(bot)
        self.onboarding_service = onboarding_service
        self.scheduler = BackgroundScheduler(
            timezone=_get_scheduler_tz(),
            job_defaults={"max_instances": 2, "coalesce": True}
        )
        self.running = False

        try:
            self.day1_delays = config.HOT_LEAD_DAY1_DELAYS or DAY1_DELAYS_MIN
        except Exception:
            self.day1_delays = DAY1_DELAYS_MIN

        self.day2_per_day = getattr(config, "HOT_LEAD_DAY2_PER_DAY", 2)
        self.idle_minutes = getattr(config, "HOT_LEAD_IDLE_MINUTES", 10)

    def start(self):
        if self.running:
            return
        self.scheduler.start()
        self.running = True
        self.schedule_promo_sequence_check()
        self.schedule_registration_reminder_check()
        self.schedule_vip_resources_check()
        self.schedule_account_id_nudge_check()
        self.schedule_hot_lead_check()
        self.schedule_followup_check()
        self.schedule_scheduled_post_check()
        self.schedule_cleanup()
        logger.info("Scheduler started successfully with Asia/Kolkata timezone")

    def stop(self):
        if not self.running:
            return
        self.scheduler.shutdown()
        self.running = False
        logger.info("Scheduler stopped")

    # ------------------------------------------------------------------
    # 1. Capital No-Response Drip Sequence
    # ------------------------------------------------------------------
    PROMO_STAGE_DELAYS = {
        None: 120,               # 2 min after capital response -> Testimonials
        "testimonials_sent": 120,# 2 min after testimonials -> No Fee
        "fee_sent": 10,          # 10 sec after no fee -> VIP Benefits
        "benefits_sent": 90,     # 90 sec after benefits -> Want to join?
        "asked_sent": 900,       # 15 min after ask -> Re-engagement
        "reengagement_sent": None
    }
    PROMO_STAGE_ORDER = [
        "testimonials_sent",
        "fee_sent",
        "benefits_sent",
        "asked_sent",
        "reengagement_sent"
    ]

    def schedule_promo_sequence_check(self):
        try:
            self.scheduler.add_job(
                self.process_promo_sequence,
                IntervalTrigger(seconds=15, timezone=_get_scheduler_tz()),
                id="promo_sequence_check",
                replace_existing=True
            )
        except Exception as e:
            logger.error(f"Failed to schedule promo sequence check: {e}")

    def process_promo_sequence(self):
        if not self.onboarding_service:
            return
        try:
            users = self.onboarding_service.get_users_awaiting_positive_intent()
            now = get_current_datetime()

            for user in users:
                try:
                    telegram_id = user.get("telegram_id")
                    if not telegram_id or user.get("blocked"):
                        continue

                    current_state = user.get("onboarding_state")
                    if current_state != STATE_AWAITING_POSITIVE_INTENT:
                        continue

                    onboarding_data = user.get("onboarding_data") or {}
                    if isinstance(onboarding_data, str):
                        try:
                            onboarding_data = json.loads(onboarding_data)
                        except Exception:
                            onboarding_data = {}

                    current_stage = onboarding_data.get("promo_stage")
                    stage_at = onboarding_data.get("promo_stage_at")
                    ref_dt = _parse_iso_datetime(stage_at or user.get("last_activity"))

                    if not ref_dt:
                        continue

                    delay_seconds = self.PROMO_STAGE_DELAYS.get(current_stage)
                    if delay_seconds is None:
                        continue

                    elapsed = (now - ref_dt).total_seconds()
                    if elapsed < delay_seconds:
                        continue

                    next_index = 0 if current_stage is None else self.PROMO_STAGE_ORDER.index(current_stage) + 1
                    if next_index >= len(self.PROMO_STAGE_ORDER):
                        continue

                    next_stage = self.PROMO_STAGE_ORDER[next_index]

                    if next_stage == "testimonials_sent":
                        promo.send_testimonials(self.bot, telegram_id)
                    elif next_stage == "fee_sent":
                        promo.send_no_fee_message(self.bot, telegram_id)
                    elif next_stage == "benefits_sent":
                        promo.send_vip_benefits(self.bot, telegram_id)
                    elif next_stage == "asked_sent":
                        promo.send_ask_to_join(self.bot, telegram_id)
                    elif next_stage == "reengagement_sent":
                        promo.send_reengagement_message(self.bot, telegram_id)

                    self.onboarding_service.set_promo_stage(telegram_id, next_stage)
                    logger.info(f"Sent promo stage '{next_stage}' to user {telegram_id}")
                except Exception as e:
                    logger.error(f"Promo step error for user {user.get('telegram_id')}: {e}")
        except Exception as e:
            logger.error(f"Failed in process_promo_sequence: {e}")

    # ------------------------------------------------------------------
    # 2. 20-Second Post-Registration Steps Reminder (NOTE + GIF Prompt)
    # ------------------------------------------------------------------
    def schedule_registration_reminder_check(self):
        try:
            self.scheduler.add_job(
                self.process_registration_reminders,
                IntervalTrigger(seconds=10, timezone=_get_scheduler_tz()),
                id="reg_reminder_check",
                replace_existing=True
            )
        except Exception as e:
            logger.error(f"Failed to schedule registration reminder check: {e}")

    def process_registration_reminders(self):
        if not self.onboarding_service:
            return
        try:
            users = self.onboarding_service.get_users_awaiting_account_id()
            now = get_current_datetime()

            for user in users:
                try:
                    telegram_id = user.get("telegram_id")
                    if not telegram_id or user.get("blocked"):
                        continue

                    onboarding_data = user.get("onboarding_data") or {}
                    if isinstance(onboarding_data, str):
                        try:
                            onboarding_data = json.loads(onboarding_data)
                        except Exception:
                            onboarding_data = {}

                    if onboarding_data.get("registration_reminder_sent"):
                        continue

                    sent_at = onboarding_data.get("registration_steps_sent_at")
                    sent_dt = _parse_iso_datetime(sent_at)
                    if not sent_dt:
                        continue

                    if (now - sent_dt).total_seconds() >= 20:
                        promo.send_20s_registration_reminder(self.bot, telegram_id)
                        self.onboarding_service.mark_registration_reminder_sent(telegram_id)
                        logger.info(f"Sent 20-second NOTE + GIF reminder to {telegram_id}")
                except Exception as e:
                    logger.error(f"Registration reminder error for {user.get('telegram_id')}: {e}")
        except Exception as e:
            logger.error(f"Failed in process_registration_reminders: {e}")

    # ------------------------------------------------------------------
    # 3. 2-Minute Post-Approval VIP Resources Delivery
    # ------------------------------------------------------------------
    def schedule_vip_resources_check(self):
        try:
            self.scheduler.add_job(
                self.process_vip_resources_delivery,
                IntervalTrigger(seconds=15, timezone=_get_scheduler_tz()),
                id="vip_resources_check",
                replace_existing=True
            )
            logger.info("VIP resources 2-minute post-approval check scheduled")
        except Exception as e:
            logger.error(f"Failed to schedule VIP resources check: {e}")

    def process_vip_resources_delivery(self):
        try:
            approved_users = database.select("users", match_conditions={"verification_status": "approved"})
            if not approved_users:
                return

            now = get_current_datetime()
            for user in approved_users:
                try:
                    telegram_id = user.get("telegram_id")
                    if not telegram_id or user.get("blocked"):
                        continue

                    onboarding_data = user.get("onboarding_data") or {}
                    if isinstance(onboarding_data, str):
                        try:
                            onboarding_data = json.loads(onboarding_data)
                        except Exception:
                            onboarding_data = {}

                    if onboarding_data.get("vip_resources_sent"):
                        continue

                    verified_raw = onboarding_data.get("vip_approved_at") or user.get("verified_at") or user.get("updated_at")
                    verified_dt = _parse_iso_datetime(verified_raw)

                    if not verified_dt:
                        continue

                    if (now - verified_dt).total_seconds() >= 120:
                        promo.send_vip_resources(self.bot, telegram_id)
                        onboarding_data["vip_resources_sent"] = True
                        database.update_user(telegram_id, {"onboarding_data": onboarding_data})
                        logger.info(f"Delivered 2-minute post-approval VIP resources to {telegram_id}")
                except Exception as e:
                    logger.error(f"Error delivering VIP resources to {user.get('telegram_id')}: {e}")
        except Exception as e:
            logger.error(f"Failed in process_vip_resources_delivery: {e}")

    # ------------------------------------------------------------------
    # 4. Missing 9-Digit Trading Account ID Nudge (15 minutes)
    # ------------------------------------------------------------------
    def schedule_account_id_nudge_check(self):
        try:
            self.scheduler.add_job(
                self.process_account_id_nudges,
                IntervalTrigger(minutes=2, timezone=_get_scheduler_tz()),
                id="account_id_nudge_check",
                replace_existing=True
            )
            logger.info("Account ID nudge check scheduled")
        except Exception as e:
            logger.error(f"Failed to schedule account ID nudge check: {e}")

    def process_account_id_nudges(self):
        if not self.onboarding_service:
            return
        try:
            users = self.onboarding_service.get_users_awaiting_account_id()
            now = get_current_datetime()

            for user in users:
                try:
                    telegram_id = user.get("telegram_id")
                    if not telegram_id or user.get("blocked"):
                        continue

                    onboarding_data = user.get("onboarding_data") or {}
                    if isinstance(onboarding_data, str):
                        try:
                            onboarding_data = json.loads(onboarding_data)
                        except Exception:
                            onboarding_data = {}

                    if onboarding_data.get("account_id_nudge_sent"):
                        continue

                    act_dt = _parse_iso_datetime(user.get("last_activity"))
                    if not act_dt:
                        continue

                    if (now - act_dt).total_seconds() / 60 >= 15:
                        from services.ai import ai_service
                        name = self.onboarding_service.get_display_name(telegram_id)
                        msg = ai_service.generate_account_id_nudge(name)
                        try:
                            self.bot.send_message(telegram_id, msg)
                            onboarding_data["account_id_nudge_sent"] = True
                            database.update_user(telegram_id, {"onboarding_data": onboarding_data})
                            logger.info(f"Sent 15-minute Account ID nudge to {telegram_id}")
                        except Exception as e:
                            logger.error(f"Failed to send account ID nudge to {telegram_id}: {e}")
                except Exception as e:
                    logger.error(f"Account ID nudge error for {user.get('telegram_id')}: {e}")
        except Exception as e:
            logger.error(f"Failed in process_account_id_nudges: {e}")

    # ------------------------------------------------------------------
    # 5. Hot-Lead Followups
    # ------------------------------------------------------------------
    def schedule_hot_lead_check(self):
        try:
            self.scheduler.add_job(
                self.process_hot_leads,
                IntervalTrigger(minutes=3, timezone=_get_scheduler_tz()),
                id="hot_lead_check",
                replace_existing=True
            )
        except Exception as e:
            logger.error(f"Failed to schedule hot-lead check: {e}")

    def process_hot_leads(self):
        if not self.onboarding_service:
            return
        try:
            active_users = self.onboarding_service.get_active_onboarding_users()
            now = get_current_datetime()

            for user in active_users:
                try:
                    telegram_id = user.get("telegram_id")
                    if not telegram_id or user.get("blocked"):
                        continue

                    if user.get("onboarding_state") in [STATE_AWAITING_POSITIVE_INTENT, STATE_AWAITING_ACCOUNT_ID]:
                        continue

                    act_dt = _parse_iso_datetime(user.get("last_activity"))
                    if not act_dt:
                        continue

                    idle_minutes = (now - act_dt).total_seconds() / 60
                    if idle_minutes < self.idle_minutes:
                        continue

                    first_seen = user.get("hot_lead_first_seen_date")
                    today = now.date()
                    first_seen_date = None

                    if first_seen:
                        if isinstance(first_seen, str):
                            try:
                                first_seen_date = date.fromisoformat(first_seen)
                            except Exception:
                                first_seen_date = None
                        elif hasattr(first_seen, 'year'):
                            first_seen_date = first_seen

                    is_day1 = (first_seen_date is None) or (first_seen_date == today)

                    if is_day1:
                        self._process_day1_hot_lead(user, now)
                    else:
                        self._process_day2_plus_hot_lead(user, now)
                except Exception as e:
                    logger.error(f"Hot lead error for {user.get('telegram_id')}: {e}")
        except Exception as e:
            logger.error(f"Failed in process_hot_leads: {e}")

    def _process_day1_hot_lead(self, user, now):
        telegram_id = user.get("telegram_id")
        sent_count = user.get("hot_lead_day1_sent_count") or 0
        if sent_count >= len(self.day1_delays):
            return

        last_sent_dt = _parse_iso_datetime(user.get("hot_lead_day1_last_sent_at"))
        last_act_dt = _parse_iso_datetime(user.get("last_activity"))

        if sent_count == 0:
            if last_act_dt and (now - last_act_dt).total_seconds() / 60 >= self.day1_delays[0]:
                self._send_hot_lead_day1_nudge(telegram_id, attempt=1)
        else:
            if last_sent_dt:
                gap_minutes = self.day1_delays[sent_count] if sent_count < len(self.day1_delays) else 300
                if (now - last_sent_dt).total_seconds() / 60 >= gap_minutes:
                    self._send_hot_lead_day1_nudge(telegram_id, attempt=sent_count + 1)

    def _send_hot_lead_day1_nudge(self, telegram_id, attempt):
        try:
            from services.ai import ai_service
            name = self.onboarding_service.get_display_name(telegram_id)
            nudge = ai_service.generate_idle_followup(name, attempt=attempt)
            try:
                self.bot.send_message(telegram_id, nudge)
                self.onboarding_service.increment_hot_lead_day1(telegram_id)
                database.update_user(telegram_id, {"last_followup_at": get_current_timestamp()})
                if attempt == 1:
                    self.onboarding_service.mark_hot_lead(telegram_id)
                logger.info(f"Sent day-1 hot-lead nudge #{attempt} to {telegram_id}")
            except Exception as e:
                logger.error(f"Failed to send day-1 nudge to {telegram_id}: {e}")
                if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    database.update_user(telegram_id, {"blocked": True})
        except Exception as e:
            logger.error(f"Day-1 nudge error for {telegram_id}: {e}")

    def _process_day2_plus_hot_lead(self, user, now):
        telegram_id = user.get("telegram_id")
        self.onboarding_service.reset_hot_lead_day2_if_new_day(telegram_id)
        sent_today = user.get("hot_lead_day2_sent_count") or 0
        if sent_today >= self.day2_per_day:
            return

        last_followup_dt = _parse_iso_datetime(user.get("last_followup_at") or user.get("hot_lead_day1_last_sent_at"))
        if last_followup_dt:
            if (now - last_followup_dt).total_seconds() / 60 < 240:
                return

        self._send_day2_followup(telegram_id, attempt=sent_today + 1)

    def _send_day2_followup(self, telegram_id, attempt):
        try:
            from services.ai import ai_service
            name = self.onboarding_service.get_display_name(telegram_id)
            msg = ai_service.generate_day2_followup(name, attempt=attempt)
            try:
                self.bot.send_message(telegram_id, msg)
                self.onboarding_service.increment_hot_lead_day2(telegram_id)
                database.update_user(telegram_id, {"last_followup_at": get_current_timestamp()})
                logger.info(f"Sent day-2+ followup #{attempt} to {telegram_id}")
            except Exception as e:
                logger.error(f"Failed to send day-2 followup to {telegram_id}: {e}")
                if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    database.update_user(telegram_id, {"blocked": True})
        except Exception as e:
            logger.error(f"Day-2 followup error for {telegram_id}: {e}")

    # ------------------------------------------------------------------
    # 6. Generic Followups & Channel Posts
    # ------------------------------------------------------------------
    def schedule_followup_check(self):
        try:
            self.scheduler.add_job(
                self.process_due_followups,
                IntervalTrigger(minutes=5, timezone=_get_scheduler_tz()),
                id="followup_check",
                replace_existing=True
            )
        except Exception as e:
            logger.error(f"Failed to schedule followup check: {e}")

    def process_due_followups(self):
        try:
            due_followups = database.get_due_followups()
            if not due_followups:
                return
            for followup in due_followups:
                self.send_followup(followup)
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"Failed to process due followups: {e}")

    def send_followup(self, followup: Dict[str, Any]):
        try:
            telegram_id = followup.get("telegram_id")
            message_content = followup.get("message_content")
            followup_id = followup.get("id")
            user = database.get_user(telegram_id)

            if not user or user.get("blocked") or user.get("opt_out"):
                database.update_followup(followup_id, {"sent": True, "enabled": False})
                return

            try:
                self.bot.send_message(telegram_id, message_content)
                database.update_followup(followup_id, {
                    "sent": True,
                    "sent_at": get_current_timestamp()
                })
            except Exception as e:
                if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    database.update_user(telegram_id, {"blocked": True})
                database.update_followup(followup_id, {"sent": True, "enabled": False})
        except Exception as e:
            logger.error(f"Failed to send followup {followup.get('id')}: {e}")

    def schedule_scheduled_post_check(self):
        try:
            self.scheduler.add_job(
                self.process_due_scheduled_messages,
                IntervalTrigger(minutes=2, timezone=_get_scheduler_tz()),
                id="scheduled_post_check",
                replace_existing=True
            )
        except Exception as e:
            logger.error(f"Failed to schedule scheduled post check: {e}")

    def process_due_scheduled_messages(self):
        try:
            due_messages = database.get_due_scheduled_messages()
            if not due_messages:
                return
            for message in due_messages:
                self.send_scheduled_message(message)
                time.sleep(0.3)
        except Exception as e:
            logger.error(f"Failed to process scheduled messages: {e}")

    def send_scheduled_message(self, message: Dict[str, Any]):
        try:
            message_id = message.get("id")
            channel_id = message.get("channel_id")
            message_content = message.get("message_content")

            if not channel_id or not message_content:
                database.update_scheduled_message(message_id, {"sent": True})
                return

            result = self.channel_service.send_message_to_channel(channel_id, message_content)
            database.update_scheduled_message(message_id, {
                "sent": True,
                "sent_at": get_current_timestamp()
            })
        except Exception as e:
            logger.error(f"Scheduled message error {message.get('id')}: {e}")
            database.update_scheduled_message(message.get("id"), {"sent": True})

    def cleanup_old_records(self):
        try:
            cutoff = (get_current_datetime() - timedelta(days=90)).isoformat()
            old_followups = database.select("followups", match_conditions={"sent": True})
            if old_followups:
                for item in old_followups:
                    if item.get("sent_at") and item["sent_at"] < cutoff:
                        database.delete("followups", {"id": item["id"]})
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    def schedule_cleanup(self):
        try:
            self.scheduler.add_job(
                self.cleanup_old_records,
                CronTrigger(hour=3, minute=0, timezone=_get_scheduler_tz()),
                id="cleanup_job",
                replace_existing=True
            )
        except Exception as e:
            logger.error(f"Failed to schedule cleanup: {e}")
