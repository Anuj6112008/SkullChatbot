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
            "You are Nisha, a warm, casual support assistant from Team Skull. "
            "Always reply in clean, grammatically correct English. "
            "Keep replies short (1-4 sentences). Never make grammatical mistakes. "
            "Never invent business rules, fees, timelines, guarantees, or policies. "
            "If you don't know the answer, guide the user to support."
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
            "REGISTRATION": ["register", "registration", "sign up", "signup", "enroll", "join", "new user", "account create"],
            "DEPOSIT": ["deposit", "add money", "fund", "payment", "pay", "charge", "recharge"],
            "WITHDRAWAL": ["withdraw", "withdrawal", "cash out", "payout", "nikalna"],
            "PAYMENT": ["payment", "pay", "card", "upi", "bank", "transfer", "paytm", "google pay", "phone pe"],
            "COURSE": ["course", "class", "lesson", "module", "learn", "study"],
            "ACCESS": ["access", "login", "log in", "sign in", "password", "otp", "verify"],
            "LOGIN": ["login", "log in", "sign in", "password", "username", "credential"],
            "ACCOUNT": ["account", "profile", "setting", "update", "change"],
            "SUPPORT": ["help", "support", "problem", "issue", "not working", "error", "wrong", "bad", "complaint", "unhappy", "angry", "frustrated", "confused", "emergency", "urgent"]
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
                result["response"] = "I'm forwarding your question to our support team. They will get back to you shortly."
                return result
            system_prompt = self.system_prompt
            user_info = ""
            if user_data:
                name = user_data.get("first_name", "")
                if name:
                    user_info = f"User: {name}\n"
                paid = user_data.get("paid_user", False)
                if paid:
                    user_info += "User is a paid member.\n"
            full_prompt = (
                f"{user_info}\n"
                f"User message: {message}\n\n"
                "Provide a helpful, natural, and concise response in clean, grammatically correct English. "
                "Keep it friendly and professional. Never make grammatical mistakes. "
                "If you don't have the exact information, guide to support. "
                "Always be safe and never invent policies or fees."
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
                result["response"] = "I understand your question. Please contact our support team for detailed assistance."
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
        support_keywords = ["help", "support", "problem", "issue", "not working", "error", "wrong", "bad", "complaint", "unhappy", "angry", "frustrated", "confused", "emergency", "urgent"]
        message_lower = message.lower()
        for keyword in support_keywords:
            if keyword in message_lower:
                return True
        return False

    def generate_caption(self, intent: str, video_path: str) -> str:
        try:
            prompt = (
                f"Generate a short, professional caption for a video about {intent} in our course platform. "
                "Write in clean, grammatically correct English. Keep it under 100 words. Make it engaging and helpful.\n\nCaption:"
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a caption generator. Keep it short and professional. Always use grammatically correct English."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 300,
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
                f"You are a professional support agent.\n"
                f"A user has requested support with the following message:\n{message}\n\n"
                f"User: {user_data.get('first_name', 'User')}\n"
                f"Ticket: #{ticket_id}\n\n"
                "Provide a professional, empathetic, and helpful support response in clean, grammatically correct English. "
                "Acknowledge their issue and let them know it's been received and will be handled. "
                "Keep it concise and professional. Never make grammatical mistakes.\n\nResponse:"
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a professional support agent. Always reply in grammatically correct English."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 350,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(response_text) or "Thank you for contacting support. We have received your query and will get back to you shortly."
        except Exception as e:
            logger.error(f"Support response generation failed: {e}")
            return "Thank you for contacting support. We have received your query and will get back to you shortly."

    def detect_question(self, message: str, current_question: str, name: str = "") -> bool:
        try:
            name_note = f"The user's name is {name}. " if name else ""
            prompt = (
                f"{name_note}The user is currently being asked this exact question: \"{current_question}\"\n\n"
                f"The user just replied: \"{message}\"\n\n"
                "Decide: does this reply plausibly ANSWER the specific question above with the requested information — "
                "or is it something else (a side question, confusion, an unrelated comment, asking \"who/what/why\", "
                "asking for clarification, expressing doubt, etc.)?\n\n"
                "Rules:\n"
                "- Short acknowledgments like \"okay\", \"hmm\", \"got it\" with no real answer content count as NOT_ANSWER.\n"
                "- If the reply doesn't reasonably correspond to what was asked, it is NOT_ANSWER.\n"
                "- If it plausibly provides the requested information, it is ANSWER.\n"
                "- Do not use keyword matching — understand actual intent.\n\n"
                "Reply with exactly one word: ANSWER or NOT_ANSWER"
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a precise classifier. Reply with exactly one word: ANSWER or NOT_ANSWER. No punctuation, no explanation."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 300,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            result = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
            if "NOT_ANSWER" in result:
                return True
            if "ANSWER" in result:
                return False
            return True
        except Exception as e:
            logger.error(f"Question detection failed: {e}")
            return False

    def generate_onboarding_reply(self, step: str, user_message: str, name: str = "") -> str:
        """Generate a short, warm acknowledgement in clean English for each onboarding step."""
        try:
            name_note = f"The user's name is {name}. Address them by name only if it fits naturally." if name else "You don't know the user's name yet."
            step_context = {
                "experience": "The user just told you whether they are a beginner or experienced trader. React briefly and naturally to what they said.",
                "name": "The user just told you their name. Acknowledge it briefly and warmly.",
                "age": "The user just told you their age and/or profession. Acknowledge it briefly and naturally.",
                "capital": "The user just told you how much trading capital they have. Reply with a single short, neutral acknowledgement only (e.g. \"Got it, noted!\"). Do NOT comment on whether the amount is good, bad, low, high, sufficient, or insufficient. Do NOT mention profits, growth, consistency, or give any reassurance either way about the amount. Do NOT suggest a different or larger amount.",
            }
            instruction = step_context.get(step, "Acknowledge the user's message briefly and naturally.")

            prompt = (
                f"{name_note}\n"
                f"User just said: \"{user_message}\"\n"
                f"Current step: {step}\n\n"
                f"{instruction}\n\n"
                "Reply in clean, grammatically correct English — 1-2 short lines, no formal or robotic phrasing, "
                "no stacked emojis, no bullet points, no paragraphs. Never make grammatical mistakes. "
                "Only acknowledge what the user just said for THIS step — do not bring up money, capital, profits, "
                "trading amounts, or give any financial advice or reassurance unless the current step is literally "
                "'capital', and even then only a bare neutral acknowledgement as instructed above."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha, a warm, casual, human-sounding community assistant. You always reply in clean, grammatically correct English. You never write like a formal bot. You reply in short, natural, human-like lines. Never make grammatical mistakes. You never comment on money amounts, profits, or give financial reassurance unless explicitly told to for the current step."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 300,
                "reasoning_effort": "low"
            }
            response = self.client.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return sanitize_text(text) or "Got it, noted!"
        except Exception as e:
            logger.error(f"Onboarding reply generation failed: {e}")
            return "Got it, noted!"

    def extract_age_profession(self, text: str) -> dict:
        """Independently extract age and/or profession from free text. Either field
        may be missing — the caller decides what to ask for next."""
        try:
            prompt = (
                f"Extract the person's age and occupation/profession from this message: \"{text}\"\n\n"
                "Reply in exactly this format (two lines, nothing else):\n"
                "AGE: <the age as a number, or NONE if not mentioned>\n"
                "PROFESSION: <the occupation/profession, or NONE if not mentioned>"
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You extract structured data. Follow the exact output format requested, nothing else, no explanation."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 200,
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
            logger.error(f"Age/profession extraction failed: {e}")
            return {"age": None, "profession": None}

    def generate_idle_followup(self, name: str = "", attempt: int = 1) -> str:
        """Day-1 hot-lead nudge. attempt=1..4. Short, warm, clean English."""
        try:
            name_note = f"Their name is {name}." if name else ""
            attempt_tone = {
                1: "This is the first nudge — very gentle, like a friend checking in.",
                2: "Second nudge — still warm but a little more direct.",
                3: "Third nudge — remind them of the opportunity, keep it short.",
                4: "Final nudge for today — remind them to come back and finish registration.",
            }.get(attempt, "Gentle nudge.")
            prompt = (
                f"{name_note}\n"
                f"The user stopped replying mid-conversation a while ago. "
                f"{attempt_tone}\n"
                "Write a short, casual, human-like nudge message in clean, grammatically correct English. "
                "One or two lines only. No formal tone, no stacked emojis. Never make grammatical mistakes."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha, a warm, casual, human-sounding community assistant. Always reply in clean, grammatically correct English. Never make grammatical mistakes."},
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
        """Day-2+ followup. Max 2/day. Reminds user they left the chat halfway."""
        try:
            name_note = f"Their name is {name}." if name else ""
            prompt = (
                f"{name_note}\n"
                "This user left our chat halfway through yesterday (or earlier) and hasn't come back. "
                "Write a short, friendly reminder in clean, grammatically correct English telling them they "
                "left the registration conversation incomplete and encouraging them to complete it. "
                "One or two lines only. No formal tone, no stacked emojis. Never make grammatical mistakes. "
                f"This is followup #{attempt} for today."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha, a warm, casual, human-sounding community assistant. Always reply in clean, grammatically correct English. Never make grammatical mistakes."},
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
            return sanitize_text(text) or "Hey, you left our chat halfway — whenever you're free, let's complete your registration 😊"
        except Exception as e:
            logger.error(f"Day2 followup generation failed: {e}")
            return "Hey, you left our chat halfway — whenever you're free, let's complete your registration 😊"

    def generate_registration_nudge(self, name: str = "") -> str:
        """Nudge a user who was sent the joining link/steps but hasn't sent a screenshot."""
        try:
            name_note = f"Their name is {name}." if name else ""
            prompt = (
                f"{name_note}\n"
                "The user was sent the registration joining link and steps but hasn't sent the registration "
                "screenshot yet. Gently request them to complete the registration and send the screenshot so "
                "the team can verify and approve VIP access. "
                "Write in clean, grammatically correct English. One or two short lines. Warm and polite. "
                "Never make grammatical mistakes."
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nisha, a warm, casual, human-sounding community assistant. Always reply in clean, grammatically correct English. Never make grammatical mistakes."},
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
                "Looks like you haven't sent the registration screenshot yet. Please complete the "
                "registration and send the screenshot so our team can verify and approve your VIP access 😊"
            )
        except Exception as e:
            logger.error(f"Registration nudge generation failed: {e}")
            return (
                "Looks like you haven't sent the registration screenshot yet. Please complete the "
                "registration and send the screenshot so our team can verify and approve your VIP access 😊"
            )


ai_service = AIService()
