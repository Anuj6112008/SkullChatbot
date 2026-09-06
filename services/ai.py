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
            "Always reply in clean, natural, friendly Indian English. Keep replies short (1-3 lines). "
            "Do NOT use Telugu, Telglish, or regional language words — write in simple, polite English only. "
            "Never address users as bro, brother, sister, anna, akka. "
            "Be helpful, polite, and confident. If you don't know the exact answer, guide them to the support team."
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
                result["response"] = "I'm forwarding your query to our support team. They will get back to you shortly 😊"
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
                "Provide a helpful, natural, and concise response in clean, friendly Indian English (no Telugu or regional words). "
                "Keep it 1 to 2 lines only. Be warm, confident, and polite."
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
                result["response"] = "I understand your query. Please contact our support team for further assistance."
            return result
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            return {
                "intent": "GENERAL",
                "response": "I'm currently experiencing technical difficulties. Please try again later or contact support.",
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

    def generate_caption(self, intent: str, video_path: str) -> str:
        try:
            prompt = (
                f"Generate a short, helpful caption in clean, friendly English for a video about {intent}. "
                "Keep it under 60 words."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a caption generator. Keep it short, clean, and professional in English."},
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
                "Provide a helpful support acknowledgment in clean, friendly English. Keep it 1-2 lines."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a support agent from Team Skull. Reply in clean, friendly English."},
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
            return sanitize_text(response_text) or "Your support ticket has been created. Our team will review it and get back to you shortly."
        except Exception as e:
            logger.error(f"Support response generation failed: {e}")
            return "Your support ticket has been created. Our team will review it and get back to you shortly."

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
            prompt = f"User said: {user_message} at step {step}. Acknowledge warmly in 1 short line in clean, friendly English."
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha. Reply in 1 short line in clean, friendly English."},
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

    def generate_idle_followup(self, name: str = "", step: str = "", attempt: int = 1) -> str:
        """Step-specific, context-aware Day 1 follow-up in clean Indian English."""
        try:
            name_str = f"Hey {name}!" if name else "Hey!"

            step_contexts = {
                "awaiting_capital": "The user stopped while being asked how much trading capital in INR they have. Remind them to share their trading capital amount so we can suggest the right trading strategy/plan for them.",
                "awaiting_age_occupation": "The user stopped while being asked for their age and profession. Remind them to share their age and profession so we can guide them properly.",
                "awaiting_name": "The user stopped while being asked for their name. Remind them to share their name so we can introduce ourselves and proceed.",
                "awaiting_experience": "The user stopped while being asked if they have trading experience. Remind them to let us know if they have experience or are a beginner.",
                "awaiting_account_id": "The user stopped while being asked for their 9-digit Trading Account ID. Remind them to send their 9-digit account ID so we can verify and approve their VIP access.",
            }

            context_desc = step_contexts.get(step, "The user stopped replying mid-conversation. Remind them to continue where they left off.")

            prompt = (
                f"User name: {name or 'User'}\n"
                f"Current missing step: {step}\n"
                f"Context: {context_desc}\n"
                f"Follow-up Attempt: #{attempt}\n\n"
                "Write a short, friendly, and motivating check-in message in clean, natural Indian English (strictly NO Telugu/regional words). "
                "Specifically ask for the exact missing information mentioned in the context. "
                "Keep it 1 to 2 lines only. Warm, polite, and casual tone."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha from Team Skull. Write short, step-specific friendly reminders in clean English only."},
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

            fallbacks = {
                "awaiting_capital": f"{name_str} Please share how much trading capital you have in INR so we can suggest the right plan for you 😊",
                "awaiting_age_occupation": f"{name_str} Please let us know your age and profession so we can guide you in the best way 👍",
                "awaiting_name": "Hey! You forgot to tell us your name. What should we call you? 😊",
                "awaiting_experience": "Hey! Do you have any prior trading experience or are you starting from zero? Let us know so we can guide you 👍",
                "awaiting_account_id": f"{name_str} Please send your 9-digit Trading Account ID so our backend team can verify and approve your VIP access 👍",
            }
            fallback_text = fallbacks.get(step, f"{name_str} Just checking in — whenever you're free, let's complete your setup! 😊")

            return sanitize_text(text) or fallback_text
        except Exception as e:
            logger.error(f"Idle followup generation failed for step {step}: {e}")
            if step == "awaiting_capital":
                return f"Hey {name}! Please share how much trading capital you have in INR so we can suggest the right plan for you 😊" if name else "Hey! Please share how much trading capital you have in INR so we can suggest the right plan for you 😊"
            return "Hey, are you still there? Waiting for your reply 🙂"

    def generate_day2_followup(self, name: str = "", step: str = "", attempt: int = 1) -> str:
        """Step-specific Day 2+ follow-up in clean Indian English."""
        try:
            name_str = f"Hey {name}!" if name else "Hey!"

            step_contexts = {
                "awaiting_capital": "The user left yesterday while we were asking for their trading capital amount. Remind them to share their capital so we can finalize their trading plan.",
                "awaiting_age_occupation": "The user left yesterday while we were asking for their age and profession.",
                "awaiting_name": "The user left yesterday without sharing their name.",
                "awaiting_experience": "The user left yesterday without answering if they have trading experience.",
                "awaiting_account_id": "The user left yesterday without sending their 9-digit Trading Account ID.",
            }

            context_desc = step_contexts.get(step, "The user left our registration chat yesterday.")

            prompt = (
                f"User name: {name or 'User'}\n"
                f"Context: {context_desc}\n"
                f"Follow-up #{attempt} for Day 2+.\n\n"
                "Write a short, polite reminder in clean, friendly Indian English (strictly NO Telugu words) "
                "mentioning what they left incomplete and encouraging them to complete it whenever free. 1 to 2 lines only."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha from Team Skull. Write short, step-specific friendly reminders in clean English only."},
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

            fallbacks = {
                "awaiting_capital": f"{name_str} Looks like you left our chat yesterday. Whenever you're free, share your trading capital so we can get started 😊",
                "awaiting_account_id": f"{name_str} Looks like your VIP registration is almost done! Just send your 9-digit Trading Account ID whenever you're free 👍",
            }
            fallback_text = fallbacks.get(step, f"{name_str} Looks like you left our chat halfway — whenever you're free, let's complete your setup 😊")

            return sanitize_text(text) or fallback_text
        except Exception as e:
            logger.error(f"Day2 followup generation failed for step {step}: {e}")
            return "Hey, looks like you left our chat halfway — whenever you're free, let's complete your registration 😊"

    def generate_registration_nudge(self, name: str = "") -> str:
        try:
            name_note = f"User name is {name}." if name else ""
            prompt = (
                f"{name_note}\n"
                "The user was sent the registration joining link and steps but hasn't completed their registration yet. "
                "Write a warm, engaging, and persuasive reminder in clean, friendly Indian English (strictly NO Telugu words). "
                "Gently remind them that once they register and submit their 9-digit Trading ID, their VIP access and exclusive signals will be activated. "
                "Keep it 1 to 2 short lines only. Friendly and motivating tone."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha, a friendly support assistant from Team Skull. Write short, motivating messages in clean Indian English only."},
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
                "Hey! Looks like you haven't completed your registration yet. "
                "Complete your registration and send your 9-digit Trading ID so we can activate your VIP access right away 😊"
            )
        except Exception as e:
            logger.error(f"Registration nudge generation failed: {e}")
            return (
                "Hey! Looks like you haven't completed your registration yet. "
                "Complete your registration and send your 9-digit Trading ID so we can activate your VIP access right away 😊"
            )

    def generate_account_id_nudge(self, name: str = "", attempt: int = 1) -> str:
        """Persuasive English AI Nudge for missing 9-digit trading ID across attempts 1-5 and Day 2."""
        try:
            name_note = f"User name is {name}." if name else ""

            attempt_instructions = {
                1: "This is Follow-up 1 (15 min after steps). Gentle, polite check-in asking for their 9-digit Trading Account ID.",
                2: "This is Follow-up 2 (30 min after 1st). Warm check-in asking if they faced any difficulty finding their 9-digit ID on their broker profile.",
                3: "This is Follow-up 3 (1 hour after 2nd). Motivate them by mentioning that daily VIP signals & PMS training are waiting once their ID is verified.",
                4: "This is Follow-up 4 (5 hours after 3rd). Offer quick support if they got stuck during deposit or account setup.",
                5: "This is Follow-up 5 (12 hours after 4th). End-of-day check-in reminding them to drop their 9-digit ID whenever they're free to complete VIP setup.",
            }
            inst = attempt_instructions.get(attempt, "Friendly reminder asking them to send their 9-digit Trading ID to activate VIP access.")

            prompt = (
                f"{name_note}\n"
                f"{inst}\n"
                "Write a short, friendly message in clean, natural Indian English (strictly NO Telugu/regional words). "
                "Keep it 1 to 2 lines only. Friendly, casual, and motivating tone."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha from Team Skull. Write short, polite, engaging messages in clean Indian English only."},
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

            fallbacks = {
                1: "Hey! Just send your 9-digit Trading Account ID here so our team can verify and activate your VIP access 👍",
                2: "Hey! Did you face any issue finding your 9-digit Trading ID? Let me know if you need help finding it on your profile 😊",
                3: "Just checking in! Once you share your 9-digit Trading Account ID, our team will activate your VIP signals and classes 🚀",
                4: "Hey! Your VIP access is almost ready. Please send your 9-digit Trading Account ID to complete the verification today 👍",
                5: "Hey, hope you had a good day! Send your 9-digit Trading ID whenever you're free so we can complete your VIP setup 😊"
            }
            fallback_text = fallbacks.get(attempt, "Hey! Please send your 9-digit Trading Account ID here so our backend team can verify and approve your VIP access 👍")

            return sanitize_text(text) or fallback_text
        except Exception as e:
            logger.error(f"Account ID nudge generation failed for attempt {attempt}: {e}")
            return "Hey! Please send your 9-digit Trading Account ID here so our backend team can verify and approve your VIP access 👍"


ai_service = AIService()
