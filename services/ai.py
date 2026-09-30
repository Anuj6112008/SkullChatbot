import logging
import re
import random
import time
from typing import Dict, Any, Optional
import httpx
from config import config
from database import database
from utils import sanitize_text

logger = logging.getLogger(__name__)

COMMON_NON_NAMES = {
    "emle", "cheppu", "emledu", "nothing", "chilling", "fine", "hi", "hello",
    "hey", "heyy", "busy", "work", "sleeping", "lunch", "tinnava", "enti",
    "kadu", "kaadu", "ledu", "ha", "haa", "yeah", "ok", "okay", "yep",
    "who", "why", "enduku", "telidu", "em", "nenu", "nuvvu", "edo", "ala"
}

# Client template used when a question is out of scope / we have no information.
NO_INFO_MESSAGE = "I'll discuss about this with my team and inform you."

# Marker the model returns when it has no information to answer.
NO_INFO_MARKER = "NO_INFO"

# Facts Nisha is allowed to answer from. Anything beyond this -> NO_INFO template.
KNOWN_FACTS = """
Known facts you may answer from:
- Joining the VIP community is FREE (no joining fee).
- Registration steps: create an account via the joining link -> get the 50% bonus -> deposit $50+ -> send the 9-digit trading account ID -> manual verification -> VIP access.
- Minimum deposit to qualify is $50.
- VIP includes: community access, lifetime access, live trading sessions, exclusive signals, live + recorded classes, recorded courses & lessons, basic-to-advanced trading, A-to-Z PMS compounding strategy, AI trading tools, upcoming automated trading bot, bonuses, 50% deposit bonus and support team.
- Courses, signals and VIP resources unlock only after the 9-digit account ID is verified.
- Deposits/withdrawals/payment issues on the trading platform: guide them to the basic steps only; specifics must go to the support team.
- Anything about Nisha's personal life, prices/profits/guarantees we never promised, technical platform internals, unrelated topics (movies, news, weather, coding, etc.) -> you do NOT have that information.
"""



class AIService:
    def __init__(self):
        self.api_key = config.GROQ_API_KEY
        self.model = config.AI_MODEL
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.system_prompt = self.load_system_prompt()
        self.intent_mapping = self.load_intent_mapping()
        self.client = httpx.Client(timeout=60.0)

    # Longest we will pause a caller while waiting for the rate-limit window.
    MAX_RATE_LIMIT_WAIT = 30.0

    def _post(self, payload: Dict[str, Any]) -> httpx.Response:
        """POST to Groq chat completions, retrying once when rate limited (429).

        The free tier allows a small token budget per minute that refills
        within seconds, so waiting for the announced reset and retrying once
        turns most 429s into a normal response instead of a fallback apology.
        """
        response = self.client.post(self.api_url, headers=self.headers, json=payload)
        if response.status_code == 429:
            wait = self._rate_limit_wait(response)
            if wait is None:
                logger.warning("Groq rate limit (429): reset too far away, not retrying")
            else:
                logger.warning(f"Groq rate limit (429): waiting {wait:.1f}s before one retry")
                if wait > 0:
                    time.sleep(wait)
                response = self.client.post(self.api_url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response

    @classmethod
    def _rate_limit_wait(cls, response: httpx.Response) -> Optional[float]:
        """Seconds to wait before retrying a 429, or None for "do not retry"."""
        for header in ("retry-after", "x-ratelimit-reset-tokens"):
            seconds = cls._parse_duration(response.headers.get(header, ""))
            if seconds is not None:
                if seconds > cls.MAX_RATE_LIMIT_WAIT:
                    return None
                return seconds
        # No usable header: assume a short transient burst.
        return 5.0

    @staticmethod
    def _parse_duration(value: str) -> Optional[float]:
        """Parse '5', '622ms', '45.5s', '2m52.8s' into seconds."""
        value = (value or "").strip()
        if not value:
            return None
        if value.isdigit():
            return float(value)
        parts = re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", value)
        if not parts or "".join(f"{n}{u}" for n, u in parts) != value:
            return None
        units = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
        return sum(float(n) * units[u] for n, u in parts)

    def load_system_prompt(self):
        try:
            prompt_path = config.get_prompt_path()
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.warning(f"System prompt file not found at {prompt_path}, using default")
            return self.get_default_system_prompt()
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            return self.get_default_system_prompt()

    def get_default_system_prompt(self):
        return (
            "You are Nisha, a friendly and natural girl from Team Skull helping users complete VIP onboarding. "
            "Write in pure, natural Indian English only. NEVER use Telugu or Roman Telugu, in any message. "
            "Use emojis sparingly and only when they feel natural. "
            "Never repeat the same message format. Sound human and conversational."
        )

    def load_intent_mapping(self):
        try:
            faq_items = database.get_all_faq_items(enabled_only=True)
            mapping = {}
            for item in faq_items:
                intent = item.get("intent", "").upper()
                if intent:
                    mapping[intent] = item
            return mapping
        except Exception as e:
            logger.error(f"Failed to load intent mapping: {e}")
            return {}

    def classify_intent(self, message: str) -> str:
        if not message:
            return "GENERAL"
        message_lower = message.lower()
        keyword_map = {
            "REGISTRATION": ["register", "registration", "sign up", "signup", "join", "account create", "how to join"],
            "DEPOSIT": ["deposit", "add money", "fund", "payment", "pay", "charge", "recharge", "how to deposit"],
            "WITHDRAWAL": ["withdraw", "withdrawal", "cash out", "payout", "nikalna", "how to withdraw"],
            "PAYMENT": ["payment", "pay", "card", "upi", "bank", "transfer", "paytm", "google pay", "phone pe"],
            "COURSE": ["course", "class", "lesson", "module", "learn", "study"],
            "ACCESS": ["access", "login", "password", "otp", "verify", "vip access"],
            "LOGIN": ["login", "sign in", "password", "username", "credential"],
            "ACCOUNT": ["account", "profile", "setting", "update", "change"],
            "SUPPORT": ["help", "support", "problem", "issue", "not working", "error", "wrong", "complaint", "urgent"]
        }
        for intent, keywords in keyword_map.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return intent
        return "GENERAL"

    def check_if_name(self, text: str) -> Optional[str]:
        """Check if user input is an actual personal name or a casual chat reply."""
        if not text:
            return None

        clean = text.strip()
        words = clean.lower().split()

        if len(words) >= 2 and all(w in COMMON_NON_NAMES for w in words):
            return None
        if len(words) == 1 and words[0] in COMMON_NON_NAMES:
            return None
        if "?" in clean or any(w in clean.lower() for w in ["who are you", "why", "insta", "number", "date", "enti", "cheppu", "emle", "emledu", "kaadu", "kadu"]):
            return None

        extracted = re.sub(r"^(?:my\s+name\s+is|i\s+am|i'm|im|this\s+is|na\s+peru|peru)\s+", "", clean, flags=re.IGNORECASE).strip()
        
        if re.match(r"^[a-zA-Z]{2,20}$", extracted) and extracted.lower() not in COMMON_NON_NAMES:
            return extracted.title()

        try:
            prompt = (
                f"The user was previously asked for their personal name.\n"
                f"The user just sent: \"{clean}\"\n\n"
                "Determine if the user is providing their actual first/full name.\n"
                "- If the user is chatting casually, replying to a check-in (e.g. 'Emle cheppu', 'Nothing much', 'Work lo unna', 'Timepass', 'Who are you?'), they are NOT giving a name.\n"
                "- If they are giving a real name (e.g. 'Anuj', 'Rajat', 'My name is Sai', 'Na peru Shiva'), extract the name.\n\n"
                "Output strictly in this format:\n"
                "IS_NAME: <Name or NO>"
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a precise name detector. Follow the output format strictly."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 60,
                "reasoning_effort": "low"
            }
            response = self._post(payload)
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            if "IS_NAME:" in content:
                val = content.split("IS_NAME:", 1)[1].strip()
                if val and val.upper() != "NO" and len(val.split()) <= 3 and val.lower() not in COMMON_NON_NAMES:
                    return val.title()
            return None
        except Exception as e:
            logger.error(f"Name check failed: {e}")
            if len(words) <= 2 and not any(w in COMMON_NON_NAMES for w in words):
                return extracted.title()
            return None

    def generate_response(self, message: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            intent = self.classify_intent(message)
            result = {
                "intent": intent,
                "response": "",
                "video": None,
                "caption": None,
                "support_needed": False,
                "error": None
            }
            faq_item = self.intent_mapping.get(intent)
            if faq_item and faq_item.get("enabled"):
                result["video"] = faq_item.get("video_path")
                result["caption"] = faq_item.get("caption")

            if intent == "SUPPORT" or (intent == "GENERAL" and self.is_support_question(message)):
                result["support_needed"] = True
                result["response"] = "I have forwarded your query to the support team. They will help you shortly."
                return result

            system_prompt = self.system_prompt
            user_info = ""
            if user_data:
                name = user_data.get("first_name", "")
                if name:
                    user_info = f"User name: {name}\n"
                if user_data.get("member_type") == "vip" or user_data.get("verification_status") == "approved":
                    user_info += "User is a verified VIP community member.\n"

            full_prompt = (
                f"{user_info}\n"
                f"User message: {message}\n\n"
                f"{KNOWN_FACTS}\n"
                "Respond naturally and human-like as Nisha in pure Indian English only. "
                "NEVER use Telugu or Roman Telugu words. "
                "Keep it 1 to 2 short lines. Use emojis only if they feel natural — many messages should have zero emojis. "
                "Never start every message the same way. Sound like a real person texting.\n\n"
                "NO INFORMATION RULE (highest priority): if the question is out of scope, or you have no real "
                "information to answer it - profit or return promises, guarantees, Nisha's personal life, prices "
                "we never quoted, news, weather, sports, general knowledge, technical topics - reply with ONLY "
                f"this exact marker and nothing else: {NO_INFO_MARKER}\n"
                "Do not answer it, do not add a disclaimer, do not give a partial or safety-style answer: marker only. "
                "Greetings, small talk and anything covered by the known facts must still be answered normally."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_prompt}
                ],
                "temperature": config.AI_TEMPERATURE,
                "max_tokens": config.AI_MAX_TOKENS,
                "reasoning_effort": "low"
            }
            response = self._post(payload)
            data = response.json()
            response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Out-of-scope / no-information question -> client's template
            if response_text.strip().upper().startswith(NO_INFO_MARKER):
                result["response"] = NO_INFO_MESSAGE
                return result

            result["response"] = sanitize_text(response_text)
            if not result["response"]:
                result["response"] = NO_INFO_MESSAGE
            return result
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            # Soft fallback - never show "technical issue" for normal chat
            return {
                "intent": "GENERAL",
                "response": "Sorry, that took a moment 😅 Please say that again, I am here to help.",
                "video": None,
                "caption": None,
                "support_needed": False,
                "error": str(e)
            }

    def is_support_question(self, message: str) -> bool:
        support_keywords = ["help", "support", "problem", "issue", "not working", "error", "wrong", "complaint", "urgent"]
        message_lower = message.lower()
        for keyword in support_keywords:
            if keyword in message_lower:
                return True
        return False

    def generate_conversational_bridge(self, message: str, name: str, step: str, user_data: Dict[str, Any] = None) -> str:
        """The Bridge-Back Engine: Chats naturally with the user and smoothly pulls them back to the pending question."""
        try:
            step_pending_guides = {
                "awaiting_name": "User stopped before telling their name. We need their NAME.",
                "awaiting_age_occupation": "User stopped before telling their age and profession. We need their AGE and PROFESSION.",
                "awaiting_capital": "User stopped before telling their trading capital. We need their TRADING CAPITAL in INR.",
                "awaiting_account_id": "User needs to send their 9-digit Trading Account ID.",
                "awaiting_experience": "User needs to answer if they have trading experience.",
                "awaiting_positive_intent": "User was asked if they want to join the VIP community."
            }

            pending_goal = step_pending_guides.get(step, "User needs to complete their pending onboarding step.")

            prompt = (
                f"User name: {name or 'there'}\n"
                f"User just said: \"{message}\"\n"
                f"Pending onboarding requirement: {pending_goal}\n"
                f"Current step: {step}\n\n"
                f"{KNOWN_FACTS}\n"
                "Task:\n"
                f"1. FIRST check for scope: if the user asked something out of scope, or you have no real "
                f"information about it (profit promises, guarantees, Nisha's personal life, news, weather, "
                f"general knowledge, technical topics, how-does-X-work questions), output ONLY the marker "
                f"{NO_INFO_MARKER} and STOP - skip rules 2 and 3 completely. "
                "No answer, no disclaimer, no partial reply.\n"
                "2. Only if rule 1 does NOT apply: acknowledge and respond naturally to whatever the user just said.\n"
                "3. Then smoothly bridge back to the pending requirement.\n"
                "Rules:\n"
                "- Write in pure, natural Indian English.\n"
                "- NEVER use Telugu or Roman Telugu words.\n"
                "- Keep it 2 to 3 short lines max.\n"
                "- Use emojis sparingly. Many replies should have no emoji at all.\n"
                "- Sound like a real person texting, not a bot. Never start with the same phrase repeatedly."
            )

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 250,
                "reasoning_effort": "low"
            }
            response = self._post(payload)
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if text.strip().upper().startswith(NO_INFO_MARKER):
                return NO_INFO_MESSAGE

            fallbacks = {
                "awaiting_name": "Haha, nothing much 😄 Btw, you still haven't told me your name — what should I call you?",
                "awaiting_capital": "Okay, got it. Btw, we were at your trading capital — how much do you have right now? Let's finish that.",
                "awaiting_account_id": "Okay. To verify your VIP access, please send me your 9-digit Trading Account ID and I'll take it from there.",
                "awaiting_age_occupation": "Nice. Btw, we still need your age and profession — tell me both and we'll wrap this up.",
            }
            return sanitize_text(text) or fallbacks.get(step, "Okay. Let's finish the pending step — tell me.")
        except Exception as e:
            logger.error(f"Conversational bridge failed for step {step}: {e}")
            if step == "awaiting_name":
                return "Haha, nothing much 😄 Btw, what's your name? I don't think you told me yet."
            elif step == "awaiting_capital":
                return "Okay. Btw, how much trading capital do you have right now? Let's finish the setup."
            return "Okay. Ping me when you're free and we'll finish the pending step."

    # ------------------------------------------------------------------
    # Helpers for "never repeat a follow-up"
    # ------------------------------------------------------------------
    @staticmethod
    def _history_block(history) -> str:
        history = [h for h in (history or []) if h]
        if not history:
            return "Messages already sent to this user: none yet (still, write something fresh)."
        lines = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(history[-15:]))
        return (
            "Messages already sent to this user (NEVER repeat, copy or rephrase any of them):\n"
            f"{lines}"
        )

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip().lower()

    @classmethod
    def _is_repeated(cls, text: str, history) -> bool:
        normalized = cls._normalize(text)
        if not normalized:
            return True
        return any(normalized == cls._normalize(h) for h in (history or []))

    @classmethod
    def _pick_unused(cls, pool, history):
        """Choose a fallback the user has never seen before."""
        unused = [p for p in pool if p and not cls._is_repeated(p, history)]
        return random.choice(unused or [p for p in pool if p])

    def generate_idle_followup(self, name: str = "", step: str = "", attempt: int = 1, history=None) -> str:
        """Day-1 hot-lead nudge (exactly 4 per first day). Pure English, never a repeat."""
        history = [h for h in (history or []) if h]
        try:
            name_note = f"User name: {name}" if name else ""
            history_block = self._history_block(history)

            attempt_styles = {
                1: "First follow-up. Short casual check-in asking what they are doing right now. DO NOT mention registration. Completely new opening.",
                2: "Second follow-up. Ask if they are busy with work or finally free. Friendly and natural. Different opening from the previous one.",
                3: "Third follow-up. Playfully ask where they disappeared to. Warm tone. Completely different sentence structure.",
                4: "Fourth and final follow-up. Lightly tease that they went quiet, then a soft 'reply whenever you are free'. Fresh opening.",
            }
            inst = attempt_styles.get(
                attempt,
                "Short, casual check-in. Friendly, natural, brand new pattern."
            )

            prompt = (
                f"{name_note}\n"
                f"{inst}\n"
                f"Attempt number: {attempt} out of 4\n\n"
                f"{history_block}\n\n"
                "Task: Write ONE unique short casual message (max 1 line) in pure Indian English.\n"
                "STRICT RULES:\n"
                "- NEVER use Telugu or Roman Telugu words.\n"
                "- NEVER repeat any sentence, opening or pattern from the list above.\n"
                "- Start differently every time; no two messages may share the same first 3 words.\n"
                "- Use emojis only if natural. Many messages should have zero emojis.\n"
                "- Sound completely human."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.9,
                "max_tokens": 120,
                "reasoning_effort": "low"
            }
            response = self._post(payload)
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            cleaned = sanitize_text(text)
            if cleaned and not self._is_repeated(cleaned, history):
                return cleaned

            # AI repeated itself -> use an unseen fallback
            return self._pick_unused(self._day1_fallbacks(name, attempt), history)
        except Exception as e:
            logger.error(f"Idle followup generation failed: {e}")
            return self._pick_unused(self._day1_fallbacks(name, attempt), history)

    @staticmethod
    def _day1_fallbacks(name: str, attempt: int) -> list:
        """Large English pool, different pattern per attempt. All safe for day-1 nudges."""
        suffix = f" {name.strip()}" if name and name.strip() else ""
        pools = {
            1: [
                f"What are you up to right now{suffix}?",
                f"Busy right now{suffix}?",
                "Quick check — what are you doing at the moment?",
                f"Free at the moment{suffix}?",
            ],
            2: [
                f"Got some free time now{suffix}?",
                "Done with work for the day?",
                "Still stuck with work?",
                f"You free now{suffix}?",
            ],
            3: [
                f"Where did you disappear{suffix}?",
                "You went quiet on me 😄",
                "Vanished again, huh?",
                f"Still around{suffix}?",
            ],
            4: [
                f"Should I take it you are busy today{suffix}?",
                "Silent treatment, huh?",
                "All good? You have gone quiet.",
                "Reply whenever you are free — no pressure.",
            ],
        }
        default_pool = [
            f"Hey{suffix}, you around?",
            "Still free, or should I catch you later?",
            "Everything okay on your side?",
            f"Free now{suffix}? We can finish the pending step.",
        ]
        return pools.get(attempt, default_pool)

    def generate_daily_followup(self, name: str = "", step: str = "", days_since: int = 2, history=None) -> str:
        """Day 2-30 follow-up: 1 message/day (days 2-7) or alternate days (8-30).

        Pure English, unique every time - never repeats a previously sent follow-up.
        """
        history = [h for h in (history or []) if h]
        name_str = (name or "").strip()
        try:
            history_block = self._history_block(history)

            if days_since <= 2:
                day_context = "They left the registration chat a day or two ago. Light, friendly check-in — they may have simply gotten busy."
            elif days_since <= config.FOLLOWUP_DAILY_DAYS:
                day_context = "They have been silent for a few days mid-week. Warm casual check-in, no pressure."
            elif days_since <= 14:
                day_context = "Over a week of silence. Gentle, slightly more direct re-engagement — remind them their VIP setup is still pending."
            else:
                day_context = "They have been inactive for a long time (close to the end of the 30-day window). Short, warm, final-style check-in."

            prompt = (
                f"User name: {name_str or 'there'}\n"
                f"Days since they last replied: {days_since}\n"
                f"Context: {day_context}\n\n"
                f"{history_block}\n\n"
                "Task: Write a fresh, unique, 1-2 line friendly follow-up in pure Indian English.\n"
                "STRICT RULES:\n"
                "- NEVER use Telugu or Roman Telugu words.\n"
                "- NEVER repeat or rephrase anything from the list above.\n"
                "- Completely different sentence structure every time; no two messages may share the same first 3 words.\n"
                "- Vary the opening, length, tone and emoji usage.\n"
                "- Keep it casual and human. Many messages should have zero emojis."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.9,
                "max_tokens": 150,
                "reasoning_effort": "low"
            }
            response = self._post(payload)
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            cleaned = sanitize_text(text)
            if cleaned and not self._is_repeated(cleaned, history):
                return cleaned

            return self._pick_unused(self._daily_fallbacks(name_str), history)
        except Exception as e:
            logger.error(f"Daily followup generation failed: {e}")
            return self._pick_unused(self._daily_fallbacks(name_str), history)

    @staticmethod
    def _daily_fallbacks(name: str) -> list:
        """Large English pool for day 2-30 daily/alternate follow-ups."""
        suffix = f" {name.strip()}" if name and name.strip() else ""
        return [
            f"Hey{suffix}, you went quiet — all good on your side?",
            f"Still busy{suffix}? Your VIP setup is waiting whenever you are free.",
            "Just checking in — did you get busy with work today?",
            f"Been a while{suffix}. Reply whenever you have a minute.",
            "No pressure at all, but your registration is still pending.",
            f"You around{suffix}? Happy to finish the remaining step in 2 minutes.",
            "Thought I'd check — how has your day been going?",
            f"Silent again{suffix} 😄 — free at any point today?",
            "If now is a bad time, no worries — just drop a reply when you can.",
            "Your VIP access is one step away. Want to complete it today?",
            "Quick hello 👋 — are you still interested in the VIP community?",
            f"Free for 2 minutes{suffix}? We can wrap up your pending step.",
        ]


    def generate_day2_followup(self, name: str = "", step: str = "", attempt: int = 1, days_idle: int = 1, history=None) -> str:
        """Backward-compatible wrapper around generate_daily_followup (day 2-30)."""
        return self.generate_daily_followup(
            name=name, step=step, days_since=max(2, days_idle), history=history
        )

    def generate_caption(self, intent: str, video_path: str) -> str:
        try:
            prompt = f"Generate a short helpful caption for {intent} video in pure Indian English. 1-2 lines. Keep it natural. No Telugu."
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a caption generator. Pure Indian English only. Natural tone."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 200,
                "reasoning_effort": "low"
            }
            response = self._post(payload)
            data = response.json()
            caption = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(caption) or f"Here is a video about {intent}. Please watch it for complete information."
        except Exception as e:
            logger.error(f"Caption generation failed: {e}")
            return f"Here is a video about {intent}. Please watch it for complete information."

    def generate_support_response(self, ticket_id: int, message: str, user_data: Dict[str, Any]) -> str:
        try:
            prompt = f"User support message: {message}. Ticket #{ticket_id}. Acknowledge warmly in pure Indian English (no Telugu). 1-2 lines. Natural tone."
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha. Support acknowledgment in pure Indian English. Keep it human."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 200,
                "reasoning_effort": "low"
            }
            response = self._post(payload)
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(text) or "Your support ticket has been created. Our team will review it and get back to you shortly."
        except Exception as e:
            logger.error(f"Support response generation failed: {e}")
            return "Your support ticket has been created. Our team will review it and get back to you shortly."


ai_service = AIService()
