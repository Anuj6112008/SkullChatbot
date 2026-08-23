import os
import logging
from typing import Optional, Dict, Any
from telebot import TeleBot
from config import config
from database import database
from utils import get_media_path, validate_video_file, is_video_within_size_limit, get_file_size_mb

logger = logging.getLogger(__name__)

class VideoService:
    def __init__(self, bot: TeleBot):
        self.bot = bot
        self.video_cache = {}

    def get_video_path(self, intent: str) -> Optional[str]:
        try:
            media_item = database.get_media_by_intent(intent)
            if media_item:
                file_path = media_item.get("file_path")
                if file_path:
                    full_path = get_media_path(file_path)
                    if os.path.exists(full_path) and validate_video_file(file_path):
                        if is_video_within_size_limit(full_path):
                            return full_path
                        else:
                            logger.warning(f"Video file {file_path} exceeds size limit: {get_file_size_mb(full_path)}MB")
                            return None
                    else:
                        logger.warning(f"Video file not found or invalid: {full_path}")
                        return None
            faq_item = database.get_faq_item(intent)
            if faq_item:
                video_path = faq_item.get("video_path")
                if video_path:
                    full_path = get_media_path(video_path)
                    if os.path.exists(full_path) and validate_video_file(video_path):
                        if is_video_within_size_limit(full_path):
                            return full_path
                        else:
                            logger.warning(f"FAQ video file {video_path} exceeds size limit")
                            return None
                    else:
                        logger.warning(f"FAQ video file not found or invalid: {full_path}")
                        return None
            return None
        except Exception as e:
            logger.error(f"Failed to get video path for intent {intent}: {e}")
            return None

    def get_caption(self, intent: str) -> Optional[str]:
        try:
            media_item = database.get_media_by_intent(intent)
            if media_item:
                caption = media_item.get("caption")
                if caption:
                    return caption
            faq_item = database.get_faq_item(intent)
            if faq_item:
                caption = faq_item.get("caption")
                if caption:
                    return caption
            default_captions = {
                "REGISTRATION": "Registration process explained step by step in this video.",
                "DEPOSIT": "Learn how to deposit funds in this video.",
                "WITHDRAWAL": "Complete withdrawal process explained in this video.",
                "PAYMENT": "Payment methods and process explained in detail.",
                "COURSE": "Course overview and details in this video.",
                "ACCESS": "How to access courses and content explained here.",
                "LOGIN": "Login process and troubleshooting guide.",
                "ACCOUNT": "Account management and settings overview.",
                "GENERAL": "General information about our platform.",
                "SUPPORT": "Support and help resources available."
            }
            return default_captions.get(intent, "Please watch this video for detailed information.")
        except Exception as e:
            logger.error(f"Failed to get caption for intent {intent}: {e}")
            return None

    def send_video(self, chat_id: int, intent: str, caption: Optional[str] = None) -> Dict[str, Any]:
        try:
            video_path = self.get_video_path(intent)
            if not video_path:
                return {
                    "success": False,
                    "error": "Video not found",
                    "sent": False
                }
            if not caption:
                caption = self.get_caption(intent)
            with open(video_path, 'rb') as video_file:
                if caption:
                    result = self.bot.send_video(
                        chat_id,
                        video_file,
                        caption=caption,
                        supports_streaming=True
                    )
                else:
                    result = self.bot.send_video(
                        chat_id,
                        video_file,
                        supports_streaming=True
                    )
                logger.info(f"Video sent to {chat_id} for intent {intent}")
                return {
                    "success": True,
                    "message_id": result.message_id,
                    "sent": True,
                    "video_path": video_path
                }
        except Exception as e:
            logger.error(f"Failed to send video to {chat_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "sent": False
            }

    def send_video_with_fallback(self, chat_id: int, intent: str, fallback_text: str) -> Dict[str, Any]:
        try:
            result = self.send_video(chat_id, intent)
            if result.get("success"):
                return result
            self.bot.send_message(chat_id, fallback_text)
            return {
                "success": True,
                "sent": True,
                "fallback_used": True,
                "message": fallback_text
            }
        except Exception as e:
            logger.error(f"Failed to send video with fallback to {chat_id}: {e}")
            try:
                self.bot.send_message(chat_id, fallback_text)
            except:
                pass
            return {
                "success": False,
                "error": str(e),
                "sent": False
            }

    def send_welcome_video(self, chat_id: int) -> Dict[str, Any]:
        return self.send_video_with_fallback(
            chat_id,
            "WELCOME",
            "Welcome to our platform! Please use the registration button to get started."
        )

    def send_faq_video(self, chat_id: int, intent: str) -> Dict[str, Any]:
        default_messages = {
            "REGISTRATION": "Please complete your registration using the registration button.",
            "DEPOSIT": "Deposit information is available. Please contact support for detailed guidance.",
            "WITHDRAWAL": "Withdrawal process details are available. Contact support for assistance.",
            "PAYMENT": "Payment information is provided. Please check the course materials or contact support.",
            "COURSE": "Course details are available. Please check your access or contact support.",
            "ACCESS": "Access information is provided. Please verify your access or contact support.",
            "LOGIN": "Login help is available. Please check your credentials or contact support.",
            "ACCOUNT": "Account management details are available. Contact support for assistance.",
            "GENERAL": "General information is provided. Please contact support for specific questions.",
            "SUPPORT": "Support team will assist you shortly."
        }
        fallback = default_messages.get(intent, "Information is available. Please contact support for details.")
        return self.send_video_with_fallback(chat_id, intent, fallback)

    def get_available_intents(self) -> list:
        try:
            media_items = database.get_all_faq_items(enabled_only=True)
            intents = []
            for item in media_items:
                intent = item.get("intent")
                if intent:
                    intents.append(intent)
            return intents
        except Exception as e:
            logger.error(f"Failed to get available intents: {e}")
            return ["REGISTRATION", "DEPOSIT", "WITHDRAWAL", "PAYMENT", "COURSE", "ACCESS", "LOGIN", "ACCOUNT", "GENERAL", "SUPPORT"]

    def get_video_info(self, intent: str) -> Dict[str, Any]:
        try:
            video_path = self.get_video_path(intent)
            caption = self.get_caption(intent)
            return {
                "intent": intent,
                "video_path": video_path,
                "caption": caption,
                "exists": bool(video_path),
                "valid": bool(video_path and os.path.exists(video_path))
            }
        except Exception as e:
            logger.error(f"Failed to get video info for {intent}: {e}")
            return {
                "intent": intent,
                "video_path": None,
                "caption": None,
                "exists": False,
                "valid": False
            }