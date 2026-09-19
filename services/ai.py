import logging
import re
import random
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
            "Mix English and natural Roman Telugu (English alphabet only). "
            "NEVER use Telugu Unicode characters. Use emojis sparingly and only when they feel natural. "
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
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
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
                result["response"] = "Mee query support team ki forward chesthunna. Thvaralo maa team meeku help chestharu."
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
                "Respond naturally and human-like as Nisha using Roman Telugu + English mix. "
                "Keep it 1 to 2 short lines. Use emojis only if they feel natural — many messages should have zero emojis. "
                "Never start every message the same way. Sound like a real person texting."
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
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            result["response"] = sanitize_text(response_text)
            if not result["response"]:
                result["response"] = "Mee doubt ardhamaindi. More details kosam support team ni reach avvandi."
            return result
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            return {
                "intent": "GENERAL",
                "response": "Technical issue valla reply late avthondi. Urgent unte support team ni reach avvandi.",
                "video": None,
                "caption": None,
                "support_needed": True,
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
                "Task:\n"
                "1. Acknowledge and respond naturally to whatever the user just said.\n"
                "2. Then smoothly bridge back to the pending requirement.\n"
                "Rules:\n"
                "- Write in natural Roman Telugu + English mix.\n"
                "- NEVER use Telugu script.\n"
                "- Keep it 2 to 3 short lines max.\n"
                "- Use emojis sparingly. Many replies should have no emoji at all.\n"
                "- Sound like a real girl texting, not a bot. Never start with the same phrase repeatedly."
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
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            fallbacks = {
                "awaiting_name": "Haha em ledu, neethone matladutunna. Btw, ne peru cheppaledu kada? What's your name?",
                "awaiting_capital": "Okay, understood. Btw, nuvvu madhyalone aapesav. As of now ne daggara entha trading capital undi? Cheppu, setup finish cheddam.",
                "awaiting_account_id": "Okay. Mana VIP access verify avvadaniki mee 9-digit Trading Account ID send cheyyi, I'll help you with the rest.",
                "awaiting_age_occupation": "Nice. Btw, mee age and profession kooda cheppandi, mana trading guidance finish cheddam.",
            }
            return sanitize_text(text) or fallbacks.get(step, "Okay. Btw, mana pending step complete cheddam, tell me.")
        except Exception as e:
            logger.error(f"Conversational bridge failed for step {step}: {e}")
            if step == "awaiting_name":
                return "Haha em ledu, neethone matladutunna. Btw, ne peru cheppaledu inka? What's your name?"
            elif step == "awaiting_capital":
                return "Okay. Btw, nuvvu madhyalone aapesav. As of now ne daggara entha trading capital undi? Cheppu, let's finish the setup."
            return "Okay. Free ayyaka mana pending step complete cheddam, ping cheyyi."

    def generate_idle_followup(self, name: str = "", step: str = "", attempt: int = 1) -> str:
        """Casual, non-promotional check-in follow-up in Roman Telugu + English for Day 1."""
        try:
            name_note = f"User name: {name}" if name else ""

            attempt_styles = {
                1: "First follow-up. Short casual check-in asking what they are doing. DO NOT mention registration. Use a completely different opening.",
                2: "Second follow-up. Ask if they are busy with work. Friendly and natural. Different opening from previous.",
                3: "Third follow-up. Playfully ask where they disappeared. Warm tone. Completely different sentence structure.",
                4: "Fourth follow-up. Slightly teasing why they went silent. New opening.",
                5: "Fifth follow-up. Caring check-in asking if everything is okay. Fresh style.",
                6: "Sixth follow-up. Casual check-in asking if they are free now. Different from all previous."
            }
            inst = attempt_styles.get(attempt, "Short, casual check-in in Roman Telugu + English. Friendly and natural.")

            prompt = (
                f"{name_note}\n"
                f"{inst}\n"
                f"Attempt number: {attempt}\n\n"
                "Task: Write ONE unique short casual message (max 1 line) in natural Roman Telugu + English.\n"
                "STRICT RULES:\n"
                "- NEVER start with 'Em chestunnav' if this is not the first attempt.\n"
                "- NEVER repeat the same sentence structure.\n"
                "- Vary the opening every single time.\n"
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
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Large varied fallback pool — different for every attempt
            fallbacks = {
                1: [
                    f"Em chestunnav {name}?".strip() if name else "Em chestunnav?",
                    f"Free unnava {name}?".strip() if name else "Free unnava?",
                    f"Emi chestunnav ippudu {name}?".strip() if name else "Emi chestunnav ippudu?"
                ],
                2: [
                    f"Work lo busy ga unnava {name}?".strip() if name else "Work lo busy ga unnava?",
                    f"Busy aa {name}?".strip() if name else "Busy aa?",
                    f"Ippudu free ga unnava {name}?".strip() if name else "Ippudu free ga unnava?"
                ],
                3: [
                    f"Ekkadiki vellipoyav {name}?".strip() if name else "Ekkadiki vellipoyav?",
                    f"Malli silent aipoyav {name}?".strip() if name else "Malli silent aipoyav?",
                    f"Enti, disappear aipoyav {name}?".strip() if name else "Enti, disappear aipoyav?"
                ],
                4: [
                    f"Enti, sudden ga silent aipoyav {name}?".strip() if name else "Enti, sudden ga silent aipoyav?",
                    f"Reply ivvatledu enti {name}?".strip() if name else "Reply ivvatledu enti?",
                    f"Madhyalone vadilesav enti {name}?".strip() if name else "Madhyalone vadilesav enti?"
                ],
                5: [
                    f"Emaina problem aa {name}? Free ayyaka ping cheyyi.".strip() if name else "Emaina problem aa? Free ayyaka ping cheyyi.",
                    f"Antha okay na {name}?".strip() if name else "Antha okay na?",
                    f"Everything fine aa {name}?".strip() if name else "Everything fine aa?"
                ],
                6: [
                    f"Inka free avaleda {name}?".strip() if name else "Inka free avaleda?",
                    f"Ippudu free ayyava {name}?".strip() if name else "Ippudu free ayyava?",
                    f"Free unte ping cheyyi {name}.".strip() if name else "Free unte ping cheyyi."
                ]
            }

            options = fallbacks.get(attempt, ["Em chestunnav?"])
            fallback = random.choice(options)

            return sanitize_text(text) or fallback
        except Exception as e:
            logger.error(f"Idle followup generation failed: {e}")
            return "Em chestunnav?"

    def generate_day2_followup(self, name: str = "", step: str = "", attempt: int = 1, days_idle: int = 1) -> str:
        """Day 2+ follow-up with rich variation across days & attempts."""
        try:
            name_str = f"{name}" if name else ""

            if days_idle == 1:
                day_context = "User left the registration chat yesterday. Tease them gently about disappearing or ask if they forgot."
            elif days_idle == 2:
                day_context = "User left the chat 2 days ago. Ask playfully if they forgot about their VIP setup or if they are still busy."
            elif days_idle == 3:
                day_context = "User has been inactive for a few days. Ask casually if they had lunch or what they are doing."
            else:
                day_context = "User has been inactive for multiple days. Warm, casual check-in asking if they are free to connect."

            prompt = (
                f"User name: {name_str or 'there'}\n"
                f"Days since inactive: {days_idle} days\n"
                f"Today's follow-up attempt: #{attempt}\n"
                f"Context: {day_context}\n\n"
                "Task: Write a fresh, unique, 1-line friendly follow-up in Roman Telugu + English.\n"
                "STRICT RULES:\n"
                "- DO NOT start with 'Em chestunnav' or any previously used opening.\n"
                "- Vary the sentence structure completely every time.\n"
                "- Keep it casual and human.\n"
                "- Max 1 to 2 lines.\n"
                "- NEVER use Telugu Unicode characters.\n"
                "- Use emojis only if they feel natural. Many messages should have zero emojis."
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
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Large varied fallback pool
            varied_fallbacks = [
                f"Marchipoyava {name_str}? Free unnapudu mana registration finish cheddam.".strip(),
                f"Inka busy neena {name_str}? Free ayyaka ping cheyyi.".strip(),
                f"Lunch ayyinda {name_str}? Free unnapudu ping cheyyi.".strip(),
                f"Gurthu unda inka? Free ayyaka ping cheyyi.".strip(),
                f"Work lo full busy aa {name_str}? Whenever free, let's complete your VIP access.".strip(),
                f"Malli silent aipoyav. Free unnapudu message cheyyi.".strip(),
                f"Eppudu free avuthav {name_str}?".strip(),
                f"Madhyalone vadilesav enti {name_str}?".strip(),
                f"Ippudu free ga unte ping cheyyi {name_str}.".strip(),
                f"Antha okay na {name_str}? Free unte continue cheddam.".strip()
            ]
            fallback_choice = random.choice(varied_fallbacks)

            return sanitize_text(text) or fallback_choice
        except Exception as e:
            logger.error(f"Day2 followup failed: {e}")
            return f"Marchipoyava {name or ''}? Free unnapudu ping cheyyi.".strip()

    def generate_caption(self, intent: str, video_path: str) -> str:
        try:
            prompt = f"Generate a short helpful caption for {intent} video in Roman Telugu + English. 1-2 lines. Keep it natural."
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a caption generator. Roman Telugu + English only. Natural tone."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 200,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            caption = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(caption) or f"Here is a video about {intent}. Please watch it for complete information."
        except Exception as e:
            logger.error(f"Caption generation failed: {e}")
            return f"Here is a video about {intent}. Please watch it for complete information."

    def generate_support_response(self, ticket_id: int, message: str, user_data: Dict[str, Any]) -> str:
        try:
            prompt = f"User support message: {message}. Ticket #{ticket_id}. Acknowledge warmly in Roman Telugu + English. 1-2 lines. Natural tone."
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha. Support acknowledgment in Roman Telugu + English. Keep it human."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 200,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(text) or "Mee support ticket create ayindi. Maa team thvaralo review chesi reply istharu."
        except Exception as e:
            logger.error(f"Support response generation failed: {e}")
            return "Mee support ticket create ayindi. Maa team thvaralo review chesi reply istharu."


ai_service = AIService()
