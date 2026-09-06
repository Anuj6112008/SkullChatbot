import logging
from typing import Dict, Any, Optional
import httpx
from config import config
from database import database
from utils import sanitize_text

logger = logging.getLogger(__name__)


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
            "You are Nisha, a very friendly, playful, casual girl helping users complete VIP trading onboarding. "
            "Mix English and natural Roman Telugu (English alphabet only, e.g., 'Em chestunnav?', 'Busy ga unnav aa?'). "
            "NEVER use Telugu Unicode characters. Use warm emojis (😊, 😌, 🫶, 😉). NEVER use laughing emojis (😂, 🤣). "
            "When users chat casually, chat naturally and smoothly bridge them back to their pending onboarding step."
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
            "REGISTRATION": ["register", "registration", "sign up", "signup", "join", "account create", "ela join avvali"],
            "DEPOSIT": ["deposit", "add money", "fund", "payment", "pay", "charge", "recharge", "dabbu ela veyyali"],
            "WITHDRAWAL": ["withdraw", "withdrawal", "cash out", "payout", "nikalna", "dabbu ela teeskovali"],
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
                result["response"] = "Mee query support team ki forward chesthunna. Thvaralo maa team meeku help chestharu 😊"
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
                "Respond naturally, warmly, and concisely as Nisha using natural Roman Telugu + English. "
                "Keep it 1 to 2 short lines. Use warm emojis (😊, 😌, 🫶). Never use Telugu script or laughing emojis."
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
                result["response"] = "Mee doubt ardhamaindi 😊 More details kosam support team ni reach avvandi."
            return result
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            return {
                "intent": "GENERAL",
                "response": "Technical issue valla reply late avthondi. Urgent unte support team ni reach avvandi 😊",
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
        """The Bridge-Back Engine: Chats naturally about the user's casual topic and bridges them back to the pending step."""
        try:
            step_pending_guides = {
                "awaiting_capital": "User needs to share their trading capital in INR.",
                "awaiting_account_id": "User needs to send their 9-digit Trading Account ID.",
                "awaiting_age_occupation": "User needs to share their age and profession.",
                "awaiting_experience": "User needs to answer if they have trading experience.",
                "awaiting_name": "User needs to tell their name.",
                "awaiting_positive_intent": "User was asked if they want to join the VIP community."
            }

            pending_goal = step_pending_guides.get(step, "User needs to complete their pending registration step.")

            prompt = (
                f"User name: {name or 'there'}\n"
                f"User just said: \"{message}\"\n"
                f"Pending onboarding requirement: {pending_goal}\n"
                f"Current step: {step}\n\n"
                "Task:\n"
                "1. Acknowledge and respond naturally, playfully, and warmly to whatever the user just said (e.g. work, chilling, lunch, asking who you are, asking for Instagram/phone/date, etc.).\n"
                "2. Then smoothly and gently bridge the conversation back to the pending requirement and ask them to provide that exact missing detail.\n"
                "Rules:\n"
                "- Write in natural Roman Telugu + English (English alphabet only, e.g., 'Em chestunnav?', 'Btw, mana pending step complete cheddam').\n"
                "- NEVER write Telugu script.\n"
                "- Keep it 2 to 3 short lines max.\n"
                "- Use warm/playful emojis (😊, 😌, 🫶, 😉). NEVER use laughing emojis (😂, 🤣).\n"
                "- Sound like a friendly girl chatting on Telegram, NOT a customer service bot."
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

            # Reliable fallbacks if API is slow
            fallbacks = {
                "awaiting_capital": f"Ahh okay 😊 Btw, nuvvu madhyalone aapesav kada. As of now ne daggara entha trading capital undi? Cheppu, mana setup finish cheddam 😌",
                "awaiting_account_id": f"Okayy 😊 Btw, mana VIP access verify avvadaniki mee 9-digit Trading Account ID send cheyyi, I'll help you with the rest 👍",
                "awaiting_age_occupation": f"Nice 😊 Btw, mee age and profession kooda cheppandi, mana trading guidance finish cheddam 👍",
            }
            return sanitize_text(text) or fallbacks.get(step, "Ahh okay 😊 Btw, mana pending registration step complete cheddam, let's start!")
        except Exception as e:
            logger.error(f"Conversational bridge failed for step {step}: {e}")
            if step == "awaiting_capital":
                return "Ahh okay 😊 Btw, nuvvu madhyalone aapesav kada. As of now ne daggara entha trading capital undi? Cheppu, let's setup your plan 😌"
            elif step == "awaiting_account_id":
                return "Okayy 😊 Btw, mana VIP access verify avvadaniki mee 9-digit Trading Account ID send cheyyi, team approve chestharu 👍"
            return "Ahh okay 😊 Free ayyaka mana pending step complete cheddam, ping cheyyi!"

    def generate_idle_followup(self, name: str = "", step: str = "", attempt: int = 1) -> str:
        """Casual, non-promotional check-in follow-up in Roman Telugu + English."""
        try:
            name_note = f"User name: {name}" if name else ""

            attempt_styles = {
                1: "First follow-up (15 min after ghosting). Very short, casual check-in. E.g., 'Heyy, em chestunnav? 😊' or 'Busy ga unnav aa?' Do NOT mention registration yet.",
                2: "Second follow-up (45 min). Casual and warm check-in. E.g., 'Busy ga unnav aa? 😊' or 'Everything okay?'",
                3: "Third follow-up (2 hours). Playful check-in. E.g., 'Where did you disappear? 😌' or 'Ekkada disappear ayyav?'",
                4: "Fourth follow-up (4 hours). Slightly teasing. E.g., 'Enti silent aipoyav? 😌' or 'Reply ivvadaniki appointment book cheskovala? 😉'",
                5: "Fifth follow-up (8 hours). Caring check-in. E.g., 'Emaina problem aa? Free ayyaka ping cheyyi 🫶'",
                6: "Sixth follow-up (12 hours). Casual check-in. E.g., 'Heyy, free avaleda inka? 😊'"
            }
            inst = attempt_styles.get(attempt, "Short, casual check-in in Roman Telugu. Friendly and warm.")

            prompt = (
                f"{name_note}\n"
                f"{inst}\n\n"
                "Rules:\n"
                "- Write in Roman Telugu + English (English letters only).\n"
                "- NEVER write Telugu script.\n"
                "- Keep it 1 short line.\n"
                "- Use warm/playful emojis (😊, 😌, 🫶, 😉). NEVER use laughing emojis (😂, 🤣)."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 150,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            fallbacks = {
                1: "Heyy, em chestunnav? 😊",
                2: "Busy ga unnav aa? 😊",
                3: "Where did you disappear? 😌",
                4: "Enti silent aipoyav? 😌",
                5: "Emaina problem aa? Free ayyaka ping cheyyi 🫶",
                6: "Heyy, free avaleda inka? 😊"
            }
            return sanitize_text(text) or fallbacks.get(attempt, "Heyy, em chestunnav? 😊")
        except Exception as e:
            logger.error(f"Idle followup generation failed: {e}")
            return "Heyy, em chestunnav? 😊"

    def generate_day2_followup(self, name: str = "", step: str = "", attempt: int = 1) -> str:
        """Day 2+ follow-up in Roman Telugu + English."""
        try:
            name_note = f"User name: {name}" if name else ""
            prompt = (
                f"{name_note}\n"
                "User left the chat yesterday. Write a short, friendly, teasing reminder in Roman Telugu + English "
                "(e.g., 'Ninna madhyalone disappear aipoyav 😌', 'Marchipoyava? 😌', 'Free ayyaka mana registration finish cheddam 😊'). "
                "Keep it 1 line. Warm emojis only."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 150,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            fallbacks = {
                1: "Ninna madhyalone disappear aipoyav 😌 Free ayyaka ping cheyyi.",
                2: "Marchipoyava? 😌 Free unnapudu mana registration finish cheddam 😊"
            }
            return sanitize_text(text) or fallbacks.get(attempt, "Ninna madhyalone disappear aipoyav 😌 Free ayyaka ping cheyyi.")
        except Exception as e:
            logger.error(f"Day2 followup failed: {e}")
            return "Ninna madhyalone disappear aipoyav 😌 Free ayyaka ping cheyyi."

    def generate_caption(self, intent: str, video_path: str) -> str:
        try:
            prompt = f"Generate a short helpful caption for {intent} video in Roman Telugu + English. 1-2 lines."
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a caption generator. Roman Telugu + English only."},
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
            prompt = f"User support message: {message}. Ticket #{ticket_id}. Acknowledge warmly in Roman Telugu + English. 1-2 lines."
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha. Support acknowledgment in Roman Telugu + English."},
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
            return sanitize_text(text) or "Mee support ticket create ayindi. Maa team thvaralo review chesi reply istharu 😊"
        except Exception as e:
            logger.error(f"Support response generation failed: {e}")
            return "Mee support ticket create ayindi. Maa team thvaralo review chesi reply istharu 😊"


ai_service = AIService()
