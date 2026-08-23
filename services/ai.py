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
            "You are Nisha, a warm, friendly female support assistant from Team Skull based in Hyderabad. "
            "Reply in natural, conversational Telglish (Telugu written in English letters) or simple, friendly English. "
            "Keep replies short (1-3 lines). Be helpful, polite, and confident. Never use broken Telugu scripts. "
            "Never address users as bro, brother, sister, anna, akka. "
            "If you don't know the exact answer, guide them to the support team."
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
            "COURSE": ["course", "class", "lesson", "module", "learn", "study", "nerchukovadaniki"],
            "ACCESS": ["access", "login", "password", "otp", "verify", "vip access"],
            "LOGIN": ["login", "sign in", "password", "username", "credential"],
            "ACCOUNT": ["account", "profile", "setting", "update", "change"],
            "SUPPORT": ["help", "support", "problem", "issue", "not working", "error", "wrong", "complaint", "urgent", "sahayam"]
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
                "Provide a helpful, natural, and concise response in conversational Telglish (Telugu in English letters) or simple English. "
                "Keep it 1 to 2 lines only. Be warm, confident, and polite. Never use broken Telugu scripts."
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
                result["response"] = "Mee doubt ardhamaindi. More details kosam support team ni contact avvandi."
            return result
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            return {
                "intent": "GENERAL",
                "response": "Technical issue valla reply late avthondi. Emanna urgent unte support team ni reach avvandi.",
                "video": None,
                "caption": None,
                "support_needed": True,
                "error": str(e)
            }

    def is_support_question(self, message: str) -> bool:
        support_keywords = ["help", "support", "problem", "issue", "not working", "error", "wrong", "complaint", "urgent", "sahayam"]
        message_lower = message.lower()
        for keyword in support_keywords:
            if keyword in message_lower:
                return True
        return False

    def generate_caption(self, intent: str, video_path: str) -> str:
        try:
            prompt = (
                f"Generate a short, helpful caption in Telglish or English for a video about {intent}. "
                "Keep it under 60 words."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a caption generator. Keep it short and professional."},
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
            caption = sanitize_text(caption)
            if not caption:
                caption = f"Here is a video about {intent}. Please watch it for complete information."
            return caption
        except Exception as e:
            logger.error(f"Caption generation failed: {e}")
            return f"Here is a video about {intent}. Please watch it for complete information."

    def generate_support_response(self, ticket_id: int, message: str, user_data: Dict[str, Any]) -> str:
        try:
            prompt = (
                f"A user requested support with message: {message}\n"
                f"User: {user_data.get('first_name', 'User')}, Ticket #{ticket_id}\n\n"
                "Provide a helpful support acknowledgment in natural Telglish / English. Keep it 1-2 lines."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a support agent from Team Skull. Reply in natural Telglish / English."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 200,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(response_text) or "Mee support ticket create ayindi. Maa team thvaralo review chesi reply istharu."
        except Exception as e:
            logger.error(f"Support response generation failed: {e}")
            return "Mee support ticket create ayindi. Maa team thvaralo review chesi reply istharu."

    def detect_question(self, message: str, current_question: str, name: str = "") -> bool:
        try:
            name_note = f"The user's name is {name}. " if name else ""
            prompt = (
                f"{name_note}The user is currently being asked this question: \"{current_question}\"\n"
                f"The user replied: \"{message}\"\n\n"
                "Decide: does this reply plausibly ANSWER the question above — or is it a side question / doubt?\n"
                "Reply with exactly one word: ANSWER or NOT_ANSWER"
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Reply with exactly one word: ANSWER or NOT_ANSWER."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 200,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            result = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
            return "NOT_ANSWER" in result
        except Exception as e:
            logger.error(f"Question detection failed: {e}")
            return False

    def generate_onboarding_reply(self, step: str, user_message: str, name: str = "") -> str:
        try:
            prompt = f"User said: {user_message} at step {step}. Acknowledge warmly in 1 short line in natural Telglish."
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha. Reply in 1 short line in Telglish."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 150,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(text) or "Got it, noted!"
        except Exception as e:
            logger.error(f"Onboarding reply failed: {e}")
            return "Got it, noted!"

    def extract_age_profession(self, text: str) -> dict:
        try:
            prompt = (
                f"Extract age and profession from: \"{text}\"\n"
                "Format (2 lines):\n"
                "AGE: <number or NONE>\n"
                "PROFESSION: <text or NONE>"
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Extract structured data strictly."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 150,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            age = None
            profession = None
            for line in content.splitlines():
                line = line.strip()
                if line.upper().startswith("AGE:"):
                    val = line.split(":", 1)[1].strip()
                    if val and val.upper() != "NONE":
                        age = val
                elif line.upper().startswith("PROFESSION:"):
                    val = line.split(":", 1)[1].strip()
                    if val and val.upper() != "NONE":
                        profession = val
            return {"age": age, "profession": profession}
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return {"age": None, "profession": None}

    def generate_registration_nudge(self, name: str = "") -> str:
        """Persuasive / Engaging Telglish AI Nudge for missing screenshot."""
        try:
            name_note = f"User name is {name}." if name else ""
            prompt = (
                f"{name_note}\n"
                "The user was sent the registration joining link and steps but hasn't sent the registration screenshot yet. "
                "Write a warm, engaging, and persuasive nudge in conversational Telglish (Telugu in English letters). "
                "Gently remind them that once they register and send the screenshot, their VIP access and exclusive signals will be activated. "
                "Keep it 1 to 2 short lines only. No spammy tone. Warm and friendly."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha, a friendly assistant from Team Skull. Write short, natural Telglish messages."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 200,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(text) or (
                "Hey, mee registration screenshot inka raledu. "
                "Account create chesi screenshot send chesthe turant mee VIP access activate chestham 😊"
            )
        except Exception as e:
            logger.error(f"Registration nudge generation failed: {e}")
            return (
                "Hey, mee registration screenshot inka raledu. "
                "Account create chesi screenshot send chesthe turant mee VIP access activate chestham 😊"
            )

    def generate_account_id_nudge(self, name: str = "") -> str:
        """Persuasive Telglish AI Nudge for missing 9-digit trading ID."""
        try:
            name_note = f"User name is {name}." if name else ""
            prompt = (
                f"{name_note}\n"
                "The user sent their registration screenshot, but they forgot to send their 9-digit Trading Account ID in text. "
                "Write a short, friendly reminder in conversational Telglish (Telugu in English letters). "
                "Explain that their screenshot is received, but our team needs their 9-digit ID to verify and approve their VIP joining link. "
                "Keep it 1 to 2 short lines only."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha from Team Skull. Write short, natural Telglish messages."},
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
            return sanitize_text(text) or (
                "Mee screenshot receive ayindi! Just mee 9-digit Trading Account ID text ga send cheyandi, "
                "mana team verify chesi VIP link approve chestharu 👍"
            )
        except Exception as e:
            logger.error(f"Account ID nudge generation failed: {e}")
            return (
                "Mee screenshot receive ayindi! Just mee 9-digit Trading Account ID text ga send cheyandi, "
                "mana team verify chesi VIP link approve chestharu 👍"
            )

    def generate_idle_followup(self, name: str = "", attempt: int = 1) -> str:
        try:
            name_note = f"User name is {name}." if name else ""
            prompt = (
                f"{name_note}\n"
                f"The user stopped replying mid-conversation (Follow-up attempt #{attempt}). "
                "Write a short, casual, friendly check-in message in conversational Telglish (Telugu in English letters). "
                "One or two lines only."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha from Team Skull. Write short, friendly Telglish messages."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 200,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(text) or "Hey, are we still connected? Waiting for your reply 🙂"
        except Exception as e:
            logger.error(f"Idle followup generation failed: {e}")
            return "Hey, are we still connected? Waiting for your reply 🙂"

    def generate_day2_followup(self, name: str = "", attempt: int = 1) -> str:
        try:
            name_note = f"User name is {name}." if name else ""
            prompt = (
                f"{name_note}\n"
                "This user left our chat halfway yesterday and hasn't finished registration. "
                "Write a short, friendly reminder in conversational Telglish (Telugu in English letters) "
                "encouraging them to complete registration whenever they are free. One or two lines only."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha from Team Skull. Write short, friendly Telglish messages."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 200,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(text) or "Hey, mee registration inka complete avvaledu — free unnapudu complete cheyandi, let's start! 😊"
        except Exception as e:
            logger.error(f"Day2 followup generation failed: {e}")
            return "Hey, mee registration inka complete avvaledu — free unnapudu complete cheyandi, let's start! 😊"


ai_service = AIService()
