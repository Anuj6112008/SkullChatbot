"""Offline logic tests for the new follow-up rules (no DB, no network, no AI)."""
import os
import sys
import types
import datetime

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT)
sys.path.insert(0, PROJECT)

# ---- Fake DB first so importing services.ai (via services/__init__) is offline ----
import database as dbmod  # noqa: E402

dbmod.database.get_all_faq_items = lambda enabled_only=True: []  # no Supabase call


class FakeDB:
    def __init__(self):
        self.users = {}

    def get_user(self, tid):
        return self.users.get(tid)

    def update_user(self, tid, data):
        u = self.users.setdefault(tid, {"telegram_id": tid})
        u.update(data)
        return u

    def select(self, table, match_conditions=None, **kw):
        if table != "users" or not match_conditions:
            return list(self.users.values())
        return [
            u for u in self.users.values()
            if all(u.get(k) == v for k, v in match_conditions.items())
        ]

    def update(self, table, data, match_conditions):
        return []

    def get_setting(self, key):
        return None

    def get_all_faq_items(self, enabled_only=True):
        return []


fake_db = FakeDB()
dbmod.database = fake_db

# ---- Stub services.ai: scheduler must never call Groq in these tests ----
ai_stub = types.ModuleType("services.ai")


class StubAI:
    def __init__(self):
        self.calls = []

    def generate_idle_followup(self, name="", step="", attempt=1, history=None):
        self.calls.append(("day1", attempt, list(history or [])))
        return f"day1-nudge-{attempt}-{len(self.calls)}"

    def generate_daily_followup(self, name="", step="", days_since=2, history=None):
        self.calls.append(("daily", days_since, list(history or [])))
        return f"daily-day{days_since}-{len(self.calls)}"

    def generate_day2_followup(self, name="", step="", attempt=1, days_idle=1, history=None):
        return self.generate_daily_followup(name=name, step=step,
                                            days_since=max(2, days_idle), history=history)


ai_stub.ai_service = StubAI()
ai_stub.AIService = object  # re-exported by services/__init__.py
sys.modules["services.ai"] = ai_stub

import services.onboarding as obmod  # noqa: E402
obmod.database = fake_db

import services.scheduler as sch  # noqa: E402
sch.database = fake_db

# Real AIService class for helper-function tests (offline: faq items stubbed above)
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "real_services_ai", os.path.join(PROJECT, "services", "ai.py")
)
real_ai = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(real_ai)
AIService = real_ai.AIService

from services.onboarding import OnboardingService  # noqa: E402
from utils import (  # noqa: E402
    is_in_followup_quiet_hours, is_followup_window_closed,
    random_followup_due_time,
)
from config import config  # noqa: E402
import pytz  # noqa: E402

IST = pytz.timezone("Asia/Kolkata")
NOW = {"dt": None}


def set_now(y, m, d, h, mi):
    NOW["dt"] = IST.localize(datetime.datetime(y, m, d, h, mi, 0)).astimezone(datetime.timezone.utc)


def ist_iso(y, m, d, h, mi):
    return IST.localize(datetime.datetime(y, m, d, h, mi, 0)).astimezone(datetime.timezone.utc).isoformat()


sch.get_current_datetime = lambda: NOW["dt"]
sch.is_in_followup_quiet_hours = lambda dt=None: is_in_followup_quiet_hours(NOW["dt"])
sch.is_followup_window_closed = lambda dt=None: is_followup_window_closed(NOW["dt"])

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  [{extra}]" if extra and not cond else ""))


class FakeBot:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))
        return True


bot = FakeBot()
svc = OnboardingService(bot)
sched = sch.SchedulerService(bot, svc)
TODAY = "2026-09-30"


def make_user(tid, first_seen, idle_min=300, state="awaiting_name", **extra):
    set_now(2026, 9, 30, 15, 0)  # 3 PM IST default
    last_act = NOW["dt"] - datetime.timedelta(minutes=idle_min)
    u = {
        "telegram_id": tid,
        "onboarding_state": state,
        "last_activity": last_act.isoformat(),
        "hot_lead_first_seen_date": first_seen,
        "hot_lead_day1_sent_count": extra.pop("day1_count", 0),
        "blocked": False, "opt_out": False, "paid_user": False,
        "verification_status": "pending",
    }
    u.update(extra)
    fake_db.users[tid] = u
    return u


print("\n=== 1. Time window / quiet hours utilities ===")
check("01:00 IST is quiet", is_in_followup_quiet_hours(IST.localize(datetime.datetime(2026, 9, 30, 1, 0))))
check("03:00 IST is quiet", is_in_followup_quiet_hours(IST.localize(datetime.datetime(2026, 9, 30, 3, 0))))
check("08:59 IST is quiet", is_in_followup_quiet_hours(IST.localize(datetime.datetime(2026, 9, 30, 8, 59))))
check("09:00 IST not quiet", not is_in_followup_quiet_hours(IST.localize(datetime.datetime(2026, 9, 30, 9, 0))))
check("00:30 IST not in 1-9 window", not is_in_followup_quiet_hours(IST.localize(datetime.datetime(2026, 9, 30, 0, 30))))
check("12:59 IST not quiet", not is_in_followup_quiet_hours(IST.localize(datetime.datetime(2026, 9, 30, 12, 59))))
check("window closed at 21:00", is_followup_window_closed(IST.localize(datetime.datetime(2026, 9, 30, 21, 0))))
check("window open at 20:59", not is_followup_window_closed(IST.localize(datetime.datetime(2026, 9, 30, 20, 59))))

picks = [random_followup_due_time(datetime.date(2026, 9, 30)) for _ in range(500)]
check("all random due times inside 13:00-21:00 IST",
      all(datetime.time(13, 0) <= p.astimezone(IST).time() < datetime.time(21, 0) for p in picks))
check("random due times actually vary", len({p.hour * 60 + p.minute for p in picks}) > 100)

print("\n=== 2. Day-1 hot lead: 4 messages at 15m / +45m / +3h / +12h ===")
bot.sent.clear(); ai_stub.ai_service.calls.clear()
make_user(1, "2026-09-30", idle_min=16, day1_count=0)
sched.process_hot_leads()
check("msg1 after 15 min of last activity", len(bot.sent) == 1, str(bot.sent))
check("day1 counter = 1", fake_db.users[1]["hot_lead_day1_sent_count"] == 1)
check("fu_day1_total = 1", svc.get_day1_followup_total(1) == 1)
check("history recorded", svc.get_followup_history(1) == ["day1-nudge-1-1"], str(svc.get_followup_history(1)))

fake_db.users[1]["hot_lead_day1_last_sent_at"] = (NOW["dt"] - datetime.timedelta(minutes=44)).isoformat()
bot.sent.clear(); sched.process_hot_leads()
check("msg2 NOT sent before 45 min gap", len(bot.sent) == 0, str(bot.sent))

fake_db.users[1]["hot_lead_day1_last_sent_at"] = (NOW["dt"] - datetime.timedelta(minutes=46)).isoformat()
sched.process_hot_leads()
check("msg2 sent after 45 min gap", len(bot.sent) == 1, str(bot.sent))

fake_db.users[1]["hot_lead_day1_sent_count"] = 2
fake_db.users[1]["hot_lead_day1_last_sent_at"] = (NOW["dt"] - datetime.timedelta(minutes=179)).isoformat()
bot.sent.clear(); sched.process_hot_leads()
check("msg3 NOT sent before 3h gap", len(bot.sent) == 0, str(bot.sent))
fake_db.users[1]["hot_lead_day1_last_sent_at"] = (NOW["dt"] - datetime.timedelta(minutes=181)).isoformat()
sched.process_hot_leads()
check("msg3 sent after 3h gap", len(bot.sent) == 1, str(bot.sent))

fake_db.users[1]["hot_lead_day1_sent_count"] = 3
fake_db.users[1]["hot_lead_day1_last_sent_at"] = (NOW["dt"] - datetime.timedelta(minutes=719)).isoformat()
bot.sent.clear(); sched.process_hot_leads()
check("msg4 NOT sent before 12h gap", len(bot.sent) == 0, str(bot.sent))
fake_db.users[1]["hot_lead_day1_last_sent_at"] = (NOW["dt"] - datetime.timedelta(minutes=721)).isoformat()
sched.process_hot_leads()
check("msg4 sent after 12h gap (4th = last)", len(bot.sent) == 1, str(bot.sent))

fake_db.users[1]["hot_lead_day1_sent_count"] = 0
fake_db.users[1]["hot_lead_day1_last_sent_at"] = None
fake_db.users[1]["last_activity"] = (NOW["dt"] - datetime.timedelta(minutes=60)).isoformat()
bot.sent.clear(); sched.process_hot_leads()
check("NO 5th day-1 message (hard cap 4)", len(bot.sent) == 0, str(bot.sent))

print("\n=== 3. Quiet hours: nothing at all between 1 AM - 9 AM ===")
bot.sent.clear(); ai_stub.ai_service.calls.clear()
make_user(2, "2026-09-30", idle_min=20, day1_count=0)
set_now(2026, 9, 30, 3, 0)
fake_db.users[2]["last_activity"] = (NOW["dt"] - datetime.timedelta(minutes=20)).isoformat()
sched.process_hot_leads()
check("no day-1 nudge at 3 AM", len(bot.sent) == 0, str(bot.sent))
sched._send_daily_followup(fake_db.users[2], 2, history=[])
check("_send_daily_followup refuses at 3 AM", len(bot.sent) == 0, str(bot.sent))
fake_db.users[2]["blocked"] = True  # keep quiet for later tests

print("\n=== 4. Daily follow-up day 2-7: one random 1PM-9PM message/day ===")
bot.sent.clear(); ai_stub.ai_service.calls.clear()

# 4a: fresh day-2 user gets a random due time inside the window
make_user(30, "2026-09-28", idle_min=300)
sched.process_hot_leads()
st = svc.get_fu_state(30)
check("random due time created for today", st["fu_due_date"] == TODAY, str(st))
due = datetime.datetime.fromisoformat(st["fu_due_at"])
check("due time inside 1PM-9PM IST", datetime.time(13, 0) <= due.astimezone(IST).time() < datetime.time(21, 0), str(due))
# pin it late so this user never fires during other tests
svc.update_fu_state(30, {"fu_due_at": ist_iso(2026, 9, 30, 20, 0)})

# 4b: due time still in the future -> nothing sent
bot.sent.clear()
make_user(3, "2026-09-28", idle_min=300)  # day 2
svc.update_fu_state(3, {"fu_due_date": TODAY, "fu_due_at": ist_iso(2026, 9, 30, 20, 0)})
sched.process_hot_leads()
check("no message before due time", len(bot.sent) == 0, str(bot.sent))

# 4c: due time passed -> exactly one message, then day is closed
svc.update_fu_state(3, {"fu_due_at": (NOW["dt"] - datetime.timedelta(minutes=5)).isoformat()})
sched.process_hot_leads()
check("message sent once due time passed", len(bot.sent) == 1, str(bot.sent))
st = svc.get_fu_state(3)
check("fu_last_sent_date = today", st["fu_last_sent_date"] == TODAY, str(st))
check("fu_handled_date = today", st["fu_handled_date"] == TODAY, str(st))
check("history contains daily message", any(m.startswith("daily-day2-") for m in svc.get_followup_history(3)))

svc.update_fu_state(3, {"fu_handled_date": None})
bot.sent.clear(); sched.process_hot_leads()
check("still only 1 message/day (last_sent guard)", len(bot.sent) == 0, str(bot.sent))
check("handled re-marked", svc.get_fu_state(3)["fu_handled_date"] == TODAY)

print("\n=== 5. Min-idle: never message someone who just replied ===")
bot.sent.clear()
make_user(4, "2026-09-28", idle_min=30)  # replied 30 min ago
sched.process_hot_leads()
st = svc.get_fu_state(4)
check("no send while recently active", len(bot.sent) == 0, str(bot.sent))
check("no due drawn while recently active", st["fu_due_date"] != TODAY, str(st))

print("\n=== 6. Days 8-30: alternate days only (8,10,...30) ===")
bot.sent.clear()
make_user(5, "2026-09-22", idle_min=300)  # day 8, but day 7 already got a message
svc.update_fu_state(5, {"fu_last_sent_date": "2026-09-29"})
sched.process_hot_leads()
check("day 8 skipped when day 7 got a message", len(bot.sent) == 0, str(bot.sent))

bot.sent.clear(); ai_stub.ai_service.calls.clear()
make_user(6, "2026-09-21", idle_min=300)  # day 9, last message day 7 (gap = 2)
svc.update_fu_state(6, {"fu_last_sent_date": "2026-09-28",
                        "fu_due_date": TODAY,
                        "fu_due_at": (NOW["dt"] - datetime.timedelta(minutes=5)).isoformat()})
sched.process_hot_leads()
check("send when >=2 days since last message", len(bot.sent) == 1, str(bot.sent))
check("sent message is a day-9 daily follow-up", any("daily-day9" in m for _, m in bot.sent), str(bot.sent))

bot.sent.clear()
make_user(7, "2026-09-20", idle_min=300)  # day 10, last message day 9 -> skip
svc.update_fu_state(7, {"fu_last_sent_date": "2026-09-29"})
sched.process_hot_leads()
check("day 10 skipped right after day-9 send", len(bot.sent) == 0, str(bot.sent))

print("\n=== 7. Day 31+: follow-ups stop completely ===")
bot.sent.clear()
make_user(8, "2026-08-30", idle_min=300)  # day 31
sched.process_hot_leads()
st = svc.get_fu_state(8)
check("no message after day 30", len(bot.sent) == 0, str(bot.sent))
check("no due time after day 30", st["fu_due_date"] is None, str(st))

print("\n=== 8. Window closed (after 9 PM): no send, day closed ===")
bot.sent.clear()
make_user(9, "2026-09-28", idle_min=300)
svc.update_fu_state(9, {"fu_due_date": TODAY, "fu_due_at": ist_iso(2026, 9, 30, 17, 30)})
set_now(2026, 9, 30, 21, 30)
fake_db.users[9]["last_activity"] = (NOW["dt"] - datetime.timedelta(minutes=300)).isoformat()
sched.process_hot_leads()
check("no send after 9 PM", len(bot.sent) == 0, str(bot.sent))
check("day marked handled so tomorrow starts fresh", svc.get_fu_state(9)["fu_handled_date"] == TODAY)

print("\n=== 9. Ineligible users are never followed up ===")
fake_db.users.clear()
bot.sent.clear()
for tid, extra in [(10, {"blocked": True}), (11, {"opt_out": True}),
                   (12, {"paid_user": True}), (13, {"verification_status": "approved"})]:
    make_user(tid, "2026-09-28", idle_min=300, **extra)
sched.process_hot_leads()
check("blocked/opt-out/paid/approved skipped", len(bot.sent) == 0, str(bot.sent))

print("\n=== 10. No-repeat helpers ===")
hist = ["Busy right now?", "You went quiet on me"]
check("_is_repeated detects exact match", AIService._is_repeated("Busy right now?", hist))
check("_is_repeated ignores whitespace/case", AIService._is_repeated("  busy   RIGHT NOW? ", hist))
check("_is_repeated false for new text", not AIService._is_repeated("Free later?", hist))
pool = ["a", "b", "c"]
check("_pick_unused never returns an already-sent message",
      all(AIService._pick_unused(pool, ["a"]) != "a" for _ in range(50)))
block = AIService._history_block(hist)
check("_history_block lists past messages", "1. Busy right now?" in block and "NEVER repeat" in block)

print("\n=== 11. Day-1 nudge cap & history wiring ===")
fake_db.users.clear()
bot.sent.clear(); ai_stub.ai_service.calls.clear()
make_user(20, "2026-09-30", idle_min=60, day1_count=0)
svc.update_fu_state(20, {"fu_day1_total": 4})
sched.process_hot_leads()
check("hard cap respected via fu_day1_total", len(bot.sent) == 0, str(bot.sent))

u2 = make_user(21, "2026-09-30", idle_min=60, day1_count=0)
u2["onboarding_data"] = {"fu_history": ["some old follow-up"]}
bot.sent.clear(); ai_stub.ai_service.calls.clear()
sched.process_hot_leads()
hist_passed = ai_stub.ai_service.calls[0][2] if ai_stub.ai_service.calls else []
check("history passed into nudge generator", "some old follow-up" in hist_passed, str(hist_passed))
check("day-1 nudge actually sent", len(bot.sent) == 1, str(bot.sent))

print("\n=== 12. Config values reflect the client spec ===")
check("day-1 delays = 15,45,180,720 min", config.HOT_LEAD_DAY1_DELAYS == [15, 45, 180, 720], str(config.HOT_LEAD_DAY1_DELAYS))
check("window 13:00-21:00", (config.FOLLOWUP_WINDOW_START_HOUR, config.FOLLOWUP_WINDOW_END_HOUR) == (13, 21))
check("quiet 01:00-09:00", (config.FOLLOWUP_QUIET_START_HOUR, config.FOLLOWUP_QUIET_END_HOUR) == (1, 9))
check("daily for 7 days", config.FOLLOWUP_DAILY_DAYS == 7)
check("max 30 days", config.FOLLOWUP_MAX_DAYS == 30)
check("min idle 120 min", config.FOLLOWUP_MIN_IDLE_MINUTES == 120)
check("scheduler uses config delays", sched.day1_delays == [15, 45, 180, 720], str(sched.day1_delays))
check("scheduler idle gate from config", sched.idle_minutes == config.HOT_LEAD_IDLE_MINUTES)

print(f"\n{'=' * 50}\nPASSED: {len(PASS)}   FAILED: {len(FAIL)}")
if FAIL:
    print("FAILED TESTS:")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("ALL TESTS PASSED")

