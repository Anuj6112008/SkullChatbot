import logging
import time
import json
import pytz
from datetime import datetime, timedelta, date, timezone
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
from utils import (
    get_current_datetime,
    get_current_timestamp,
    is_in_followup_quiet_hours,
    is_followup_window_closed,
    random_followup_due_time,
    to_scheduler_tz
)

logger = logging.getLogger(__name__)

# Day-1 hot lead: exactly 4 follow-ups.
# Gap after previous message/activity: 15m -> +45m -> +3h -> +12h.
DAY1_DELAYS_MIN = [15, 45, 180, 720]


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

        # Day 1: 4 nudges at 15m / +45m / +3h / +12h (env-overridable)
        self.day1_delays = config.HOT_LEAD_DAY1_DELAYS or DAY1_DELAYS_MIN
        self.idle_minutes = config.HOT_LEAD_IDLE_MINUTES

    def start(self):
        if self.running:
            return
        self.scheduler.start()
        self.running = True
        self.schedule_promo_sequence_check()
        self.schedule_registration_reminder_check()
        self.schedule_vip_resources_check()
        self.schedule_hot_lead_check()
        self.schedule_followup_check()
        self.schedule_scheduled_post_check()
        self.schedule_cleanup()
        logger.info(
            "Scheduler started: day-1 nudges at "
            f"{self.day1_delays} min, daily window "
            f"{config.FOLLOWUP_WINDOW_START_HOUR}:00-{config.FOLLOWUP_WINDOW_END_HOUR}:00, "
            f"quiet hours {config.FOLLOWUP_QUIET_START_HOUR}:00-{config.FOLLOWUP_QUIET_END_HOUR}:00, "
            f"daily days 1-{config.FOLLOWUP_DAILY_DAYS}, alternate till day {config.FOLLOWUP_MAX_DAYS}"
        )

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
        "asked_sent": 120,       # 15 min after ask -> Re-engagement
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
                        # Mark first to prevent double-sending (race condition fix)
                        self.onboarding_service.mark_registration_reminder_sent(telegram_id)
                        promo.send_20s_registration_reminder(self.bot, telegram_id)
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
    # 4. Hot-Lead Followups
    #    Day 1 : exactly 4 messages -> 15m, +45m, +3h, +12h
    #    Day 2-7   : 1 message/day, random time between 1 PM - 9 PM
    #    Day 8-30  : alternate days (8, 10, 12 ... 30), same random window
    #    Day 30+   : follow-ups stop
    #    1 AM - 9 AM : NOTHING is ever sent (deferred)
    # ------------------------------------------------------------------
    def schedule_hot_lead_check(self):
        try:
            self.scheduler.add_job(
                self.process_hot_leads,
                IntervalTrigger(minutes=1, timezone=_get_scheduler_tz()),
                id="hot_lead_check",
                replace_existing=True
            )
            logger.info("Hot-lead / daily follow-up check scheduled (1-min interval)")
        except Exception as e:
            logger.error(f"Failed to schedule hot-lead check: {e}")

    @staticmethod
    def _parse_date(value):
        """Parse a DATE column value (str or date/datetime) into a date."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except Exception:
                return None
        if hasattr(value, "year"):
            return value
        return None

    def process_hot_leads(self):
        if not self.onboarding_service:
            return
        try:
            now = get_current_datetime()

            # Quiet hours (1 AM - 9 AM): no follow-ups at all. The 1-minute
            # interval means everything due is picked up right after 9 AM.
            if is_in_followup_quiet_hours(now):
                return

            active_users = self.onboarding_service.get_active_onboarding_users()
            today = to_scheduler_tz(now).date()

            for user in active_users:
                try:
                    telegram_id = user.get("telegram_id")
                    if not telegram_id or user.get("blocked") or user.get("opt_out") or user.get("paid_user"):
                        continue
                    if user.get("verification_status") == "approved":
                        continue

                    act_dt = _parse_iso_datetime(user.get("last_activity"))
                    if not act_dt:
                        continue

                    idle_minutes = (now - act_dt).total_seconds() / 60
                    if idle_minutes < self.idle_minutes:
                        continue

                    first_seen_date = self._parse_date(user.get("hot_lead_first_seen_date"))
                    is_day1 = (first_seen_date is None) or (first_seen_date == today)

                    if is_day1:
                        self._process_day1_hot_lead(user, now)
                    else:
                        days_since = (today - first_seen_date).days
                        if days_since > config.FOLLOWUP_MAX_DAYS:
                            continue  # 30-day follow-up window finished
                        self._process_daily_followup(user, now, days_since)
                except Exception as e:
                    logger.error(f"Hot lead error for {user.get('telegram_id')}: {e}")
        except Exception as e:
            logger.error(f"Failed in process_hot_leads: {e}")

    def _process_day1_hot_lead(self, user, now):
        telegram_id = user.get("telegram_id")
        sent_count = user.get("hot_lead_day1_sent_count") or 0
        if sent_count >= len(self.day1_delays):
            return

        # Hard cap: never more than 4 day-1 messages, even if the chain
        # restarts because the user replied and went silent again.
        if self.onboarding_service.get_day1_followup_total(telegram_id) >= len(self.day1_delays):
            return

        last_sent_dt = _parse_iso_datetime(user.get("hot_lead_day1_last_sent_at"))
        last_act_dt = _parse_iso_datetime(user.get("last_activity"))

        if sent_count == 0:
            # 1st message: 15 min after the user's last activity
            if last_act_dt and (now - last_act_dt).total_seconds() / 60 >= self.day1_delays[0]:
                self._send_hot_lead_day1_nudge(user, attempt=1)
        else:
            if last_sent_dt:
                # 2nd: +45m, 3rd: +3h, 4th: +12h (measured from previous send)
                gap_minutes = self.day1_delays[sent_count] if sent_count < len(self.day1_delays) else self.day1_delays[-1]
                if (now - last_sent_dt).total_seconds() / 60 >= gap_minutes:
                    self._send_hot_lead_day1_nudge(user, attempt=sent_count + 1)

    def _send_hot_lead_day1_nudge(self, user, attempt):
        telegram_id = user.get("telegram_id")
        try:
            # Quiet hours (1 AM - 9 AM) -> hold, the next 1-min tick retries
            if is_in_followup_quiet_hours(get_current_datetime()):
                return

            from services.ai import ai_service
            name = self.onboarding_service.get_display_name(telegram_id)
            current_state = user.get("onboarding_state")
            history = self.onboarding_service.get_followup_history(telegram_id)

            nudge = ai_service.generate_idle_followup(
                name=name, step=current_state, attempt=attempt, history=history
            )

            try:
                self.bot.send_message(telegram_id, nudge)
                self.onboarding_service.record_followup(telegram_id, nudge, count_day1=True)
                self.onboarding_service.increment_hot_lead_day1(telegram_id)
                if attempt == 1:
                    self.onboarding_service.mark_hot_lead(telegram_id)
                logger.info(f"Sent Day 1 follow-up #{attempt} to {telegram_id}: '{nudge}'")
            except Exception as e:
                logger.error(f"Failed to send Day 1 nudge to {telegram_id}: {e}")
                if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    database.update_user(telegram_id, {"blocked": True})
        except Exception as e:
            logger.error(f"Day 1 nudge error for {telegram_id}: {e}")

    def _process_daily_followup(self, user, now, days_since):
        """Day 2-7: one message per day. Day 8-30: alternate days only.
        The exact moment is drawn randomly inside the 1 PM - 9 PM window."""
        telegram_id = user.get("telegram_id")
        state = self.onboarding_service.get_fu_state(telegram_id)
        today = to_scheduler_tz(now).date()
        today_str = today.isoformat()

        # Today already resolved (sent or window missed)
        if state.get("fu_handled_date") == today_str:
            return

        last_sent = self._parse_date(state.get("fu_last_sent_date"))

        # Day 8+ -> alternate days: at least 2 days between messages
        if days_since > config.FOLLOWUP_DAILY_DAYS and last_sent:
            if (today - last_sent).days < 2:
                return

        # Absolute rule: never 2 follow-ups on the same day
        if last_sent == today:
            self.onboarding_service.update_fu_state(telegram_id, {"fu_handled_date": today_str})
            return

        # Never message someone who just replied: require real silence first.
        # (If they become silent again later today, we simply send later.)
        act_dt = _parse_iso_datetime(user.get("last_activity"))
        if act_dt and (now - act_dt).total_seconds() / 60 < config.FOLLOWUP_MIN_IDLE_MINUTES:
            return

        # Choose today's random 1 PM - 9 PM moment exactly once
        if state.get("fu_due_date") != today_str:
            due = random_followup_due_time(today)
            due_utc = due.astimezone(timezone.utc).isoformat()
            self.onboarding_service.update_fu_state(telegram_id, {
                "fu_due_date": today_str,
                "fu_due_at": due_utc
            })
            state["fu_due_date"] = today_str
            state["fu_due_at"] = due_utc

        due_dt = _parse_iso_datetime(state.get("fu_due_at"))
        if not due_dt or now < due_dt:
            return

        # Today's window (ends 9 PM) is over -> resume tomorrow
        if is_followup_window_closed(now):
            self.onboarding_service.update_fu_state(telegram_id, {"fu_handled_date": today_str})
            return

        self._send_daily_followup(user, days_since, history=state.get("fu_history") or [])

    def _send_daily_followup(self, user, days_since, history=None):
        telegram_id = user.get("telegram_id")
        try:
            if is_in_followup_quiet_hours(get_current_datetime()):
                return

            from services.ai import ai_service
            name = self.onboarding_service.get_display_name(telegram_id)
            current_state = user.get("onboarding_state")

            msg = ai_service.generate_daily_followup(
                name=name, step=current_state, days_since=days_since, history=history
            )

            try:
                self.bot.send_message(telegram_id, msg)
                today_str = to_scheduler_tz(get_current_datetime()).date().isoformat()
                self.onboarding_service.record_followup(telegram_id, msg)
                self.onboarding_service.update_fu_state(telegram_id, {
                    "fu_last_sent_date": today_str,
                    "fu_handled_date": today_str
                })
                logger.info(f"Sent day-{days_since} daily follow-up to {telegram_id}: '{msg}'")
            except Exception as e:
                logger.error(f"Failed to send daily follow-up to {telegram_id}: {e}")
                if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    database.update_user(telegram_id, {"blocked": True})
        except Exception as e:
            logger.error(f"Daily follow-up error for {telegram_id}: {e}")

    # ------------------------------------------------------------------
    # 5. Generic Followups & Channel Posts
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

            now = get_current_datetime()

            # Quiet hours (1 AM - 9 AM): hold the message, retry on next tick
            if is_in_followup_quiet_hours(now):
                return

            # Respect the requested schedule
            scheduled = _parse_iso_datetime(followup.get("scheduled_for"))
            if scheduled and scheduled > now:
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
