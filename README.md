# SkullChatbot

Telegram VIP onboarding bot (Nisha - Team Skull).

## Follow-up rules (client spec)

| Rule | Behaviour |
|---|---|
| Out-of-scope questions | Bot replies with exactly: `I'll discuss about this with my team and inform you.` |
| No repeats | Every follow-up is checked against the user's sent-message history (`onboarding_data.fu_history`) - both AI output and fallbacks. A repeat is regenerated/rejected. |
| Language | All bot messages (chat + follow-ups) are pure Indian English. Telugu / Roman Telugu is never generated. |
| Day 1 (hot lead) | Exactly **4** messages: 15 min after last activity, then +45 min, then +3 hours, then +12 hours. Hard cap of 4/day-1. |
| Days 2-7 | Exactly **1** message per day at a **random** time between **1:00 PM - 9:00 PM** (Asia/Kolkata). |
| Days 8-30 | **Alternate days** only (day 8, 10, 12 ... 30), same random 1 PM - 9 PM window. |
| Day 31+ | Follow-ups stop permanently. |
| Quiet hours | **1:00 AM - 9:00 AM: no follow-ups at all.** Anything due is deferred and sent after 9 AM. |
| Safety | Never 2 follow-ups on the same day; nobody gets messaged within 2 hours of their last reply; blocked / opt-out / paid / approved users are skipped. |

All values are configurable in `.env`:

```
HOT_LEAD_DAY1_DELAYS=15,45,180,720      # gaps in minutes (4 messages)
FOLLOWUP_WINDOW_START_HOUR=13           # 1:00 PM
FOLLOWUP_WINDOW_END_HOUR=21             # 9:00 PM
FOLLOWUP_QUIET_START_HOUR=1             # 1:00 AM
FOLLOWUP_QUIET_END_HOUR=9               # 9:00 AM
FOLLOWUP_DAILY_DAYS=7                   # days 1-7 = daily
FOLLOWUP_MAX_DAYS=30                    # stop after day 30
FOLLOWUP_MIN_IDLE_MINUTES=120           # min silence before a daily message
HOT_LEAD_IDLE_MINUTES=10                # min silence before the chain may start
```

No database migration is required - all follow-up state is stored inside the
existing `users.onboarding_data` JSONB column.

## Run

```
pip install -r requirements.txt
python main.py
```

## Tests

```
python tests/test_followup_logic.py
```

Offline (no DB / no network / no AI): verifies day-1 timing, daily window,
alternate-day cadence, quiet hours, 30-day stop, caps and no-repeat helpers.

## Groq rate limits (429)

Free-tier limits are **identical for both `openai/gpt-oss-120b` and
`openai/gpt-oss-20b`** (per organization + per model, from Groq's docs and
verified live):

| Limit | Value |
|---|---|
| RPM (requests/min) | 30 |
| RPD (requests/day) | 1,000 |
| TPM (tokens/min) | 8,000 |
| TPD (tokens/day) | 200,000 |

The 429 body shows exactly what is left:

```
Rate limit reached for model `openai/gpt-oss-20b` ... on tokens per day (TPD):
Limit 200000, Used 199419 ... Please try again in 11m27s
```

Current model is **`openai/gpt-oss-20b`** (set in `.env`). Chosen after a
head-to-head benchmark of both models on the bot's real paths - same limits,
but 20b kept working while 120b's quota was spent, with 9/11 exact spec
compliance (now 11/11 after prompt hardening) at ~0.7s average latency.

What the bot does automatically (`AIService._post` in `services/ai.py`):

- Parses `retry-after` / `x-ratelimit-reset-tokens`.
- Reset <= 30s (per-minute token bursts) -> waits and retries **once**.
- Reset > 30s (daily quota) -> gives up immediately, callers fall back to
  their English fallback text - no long blocking wait.

If the daily quota is exhausted, wait for the reset shown in the message (it
rolls continuously, not at midnight) or switch `AI_MODEL` in `.env` - the
other model has its own separate 200K/day quota.
