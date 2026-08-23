import logging
import time
import html
from telebot import TeleBot
from telebot.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo
from config import config
from database import database
from keyboards import get_broadcast_preview_keyboard, get_start_keyboard, get_cancel_keyboard
from utils import get_current_timestamp, sanitize_text, chunk_list

logger = logging.getLogger(__name__)


class BroadcastHandler:
    """Admin broadcast handler.

    Supports sending:
      - Text messages (with bold/italic formatting preserved)
      - Photos with caption (caption keeps bold/italic)
      - Videos with caption (caption keeps bold/italic)

    Audience logic (per client):
      VIP    -> users whose registration request was ACCEPTED (member_type = vip / verification_status = approved)
      NORMAL -> users who have NOT sent a request yet OR whose request was REJECTED
      ALL    -> both VIP and NORMAL users
    """

    def __init__(self, bot: TeleBot):
        self.bot = bot
        self.broadcast_sessions = {}
        # module-level reference so admin handler can kick off a broadcast
        global broadcast_handler
        broadcast_handler = self

    def register(self):
        bot = self.bot

        # Legacy generic "admin_broadcast" entry (kept for compatibility)
        @bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
        def admin_broadcast_callback(call: CallbackQuery):
            try:
                if not config.is_admin(call.from_user.id):
                    try:
                        bot.answer_callback_query(call.id, "Unauthorized")
                    except:
                        pass
                    return
                try:
                    bot.answer_callback_query(call.id, "Creating broadcast...")
                except:
                    pass
                bot.send_message(
                    call.from_user.id,
                    "📢 Create Broadcast\n\nPlease enter your broadcast message (text, or send a photo/video with a caption):",
                    reply_markup=get_cancel_keyboard("broadcast_cancel")
                )
                self.broadcast_sessions[call.from_user.id] = {
                    "step": "message",
                    "message": None,
                    "caption": None,
                    "media_type": None,
                    "media_file_id": None,
                    "audience": None
                }
            except Exception as e:
                logger.error(f"Admin broadcast callback failed: {e}")
                try:
                    bot.answer_callback_query(call.id, "Error")
                except:
                    pass

        # Message input — accept text, photo, or video
        @bot.message_handler(func=lambda message: self.is_in_broadcast_session(message.from_user.id, "message"))
        def broadcast_message_input(message: Message):
            try:
                telegram_id = message.from_user.id
                session = self.broadcast_sessions.get(telegram_id)
                if not session:
                    return

                if message.photo:
                    session["media_type"] = "photo"
                    session["media_file_id"] = message.photo[-1].file_id
                    session["caption"] = message.caption or ""
                    session["message"] = message.caption or ""
                elif message.video:
                    session["media_type"] = "video"
                    session["media_file_id"] = message.video.file_id
                    session["caption"] = message.caption or ""
                    session["message"] = message.caption or ""
                elif message.text:
                    session["media_type"] = None
                    session["media_file_id"] = None
                    session["message"] = message.text
                    session["caption"] = None
                else:
                    bot.send_message(
                        telegram_id,
                        "Please send a text message, a photo (with caption), or a video (with caption).",
                        reply_markup=get_cancel_keyboard("broadcast_cancel")
                    )
                    return

                session["step"] = "audience"
                bot.send_message(
                    telegram_id,
                    "Select audience for this broadcast:",
                    reply_markup=self._audience_keyboard()
                )
            except Exception as e:
                logger.error(f"Broadcast message input failed: {e}")
                try:
                    bot.reply_to(message, "Error processing message")
                except:
                    pass

        @bot.callback_query_handler(func=lambda call: call.data.startswith("broadcast_audience_"))
        def broadcast_audience_callback(call: CallbackQuery):
            try:
                if not config.is_admin(call.from_user.id):
                    try:
                        bot.answer_callback_query(call.id, "Unauthorized")
                    except:
                        pass
                    return
                audience = call.data.split("_")[2]
                telegram_id = call.from_user.id
                session = self.broadcast_sessions.get(telegram_id)
                if not session:
                    try:
                        bot.answer_callback_query(call.id, "Session expired")
                    except:
                        pass
                    return
                session["audience"] = audience
                session["step"] = "preview"
                try:
                    bot.answer_callback_query(call.id, f"Audience: {audience}")
                except:
                    pass
                self._send_preview(telegram_id, session)
            except Exception as e:
                logger.error(f"Broadcast audience callback failed: {e}")
                try:
                    bot.answer_callback_query(call.id, "Error")
                except:
                    pass

        @bot.callback_query_handler(func=lambda call: call.data == "broadcast_send")
        def broadcast_send_callback(call: CallbackQuery):
            try:
                if not config.is_admin(call.from_user.id):
                    try:
                        bot.answer_callback_query(call.id, "Unauthorized")
                    except:
                        pass
                    return
                telegram_id = call.from_user.id
                session = self.broadcast_sessions.get(telegram_id)
                if not session:
                    try:
                        bot.answer_callback_query(call.id, "Session expired")
                    except:
                        pass
                    return
                try:
                    bot.answer_callback_query(call.id, "Sending broadcast...")
                except:
                    pass
                bot.send_message(telegram_id, "Broadcast is being sent. This may take a while...")
                result = self.send_broadcast(
                    session.get("message"),
                    session.get("audience"),
                    telegram_id,
                    media_type=session.get("media_type"),
                    media_file_id=session.get("media_file_id"),
                    caption=session.get("caption")
                )
                bot.send_message(
                    telegram_id,
                    f"✅ Broadcast completed!\n\nRecipients: {result['total']}\nSuccessful: {result['successful']}\nFailed: {result['failed']}\nBlocked: {result['blocked']}",
                    reply_markup=get_start_keyboard()
                )
                del self.broadcast_sessions[telegram_id]
            except Exception as e:
                logger.error(f"Broadcast send failed: {e}")
                try:
                    bot.answer_callback_query(call.id, "Error sending broadcast")
                except:
                    pass

        @bot.callback_query_handler(func=lambda call: call.data == "broadcast_edit")
        def broadcast_edit_callback(call: CallbackQuery):
            try:
                if not config.is_admin(call.from_user.id):
                    try:
                        bot.answer_callback_query(call.id, "Unauthorized")
                    except:
                        pass
                    return
                telegram_id = call.from_user.id
                session = self.broadcast_sessions.get(telegram_id)
                if not session:
                    try:
                        bot.answer_callback_query(call.id, "Session expired")
                    except:
                        pass
                    return
                try:
                    bot.answer_callback_query(call.id, "Edit your message")
                except:
                    pass
                session["step"] = "message"
                bot.send_message(
                    telegram_id,
                    "Please enter your updated broadcast message (text, or send a photo/video with caption):",
                    reply_markup=get_cancel_keyboard("broadcast_cancel")
                )
            except Exception as e:
                logger.error(f"Broadcast edit failed: {e}")
                try:
                    bot.answer_callback_query(call.id, "Error")
                except:
                    pass

        @bot.callback_query_handler(func=lambda call: call.data == "broadcast_cancel")
        def broadcast_cancel_callback(call: CallbackQuery):
            try:
                telegram_id = call.from_user.id
                if telegram_id in self.broadcast_sessions:
                    del self.broadcast_sessions[telegram_id]
                try:
                    bot.answer_callback_query(call.id, "Broadcast cancelled")
                except:
                    pass
                bot.send_message(
                    telegram_id,
                    "Broadcast cancelled.",
                    reply_markup=get_start_keyboard()
                )
            except Exception as e:
                logger.error(f"Broadcast cancel failed: {e}")
                try:
                    bot.answer_callback_query(call.id, "Error")
                except:
                    pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def is_in_broadcast_session(self, telegram_id: int, step: str) -> bool:
        session = self.broadcast_sessions.get(telegram_id)
        return session is not None and session.get("step") == step

    def _audience_keyboard(self):
        from keyboards import get_broadcast_audience_keyboard
        return get_broadcast_audience_keyboard()

    def _send_preview(self, telegram_id, session):
        """Send a preview of the broadcast to the admin."""
        try:
            audience = session.get("audience")
            media_type = session.get("media_type")
            media_file_id = session.get("media_file_id")
            caption = session.get("caption")
            message = session.get("message")

            preview_header = f"📢 Broadcast Preview\n\nAudience: {audience}\n\n"
            if media_type == "photo":
                preview_text = preview_header + f"Photo with caption:\n{caption or '(no caption)'}\n\nSend this broadcast?"
                try:
                    self.bot.send_photo(telegram_id, media_file_id, caption=preview_text,
                                        reply_markup=get_broadcast_preview_keyboard())
                except Exception:
                    self.bot.send_message(telegram_id, preview_text,
                                          reply_markup=get_broadcast_preview_keyboard())
            elif media_type == "video":
                preview_text = preview_header + f"Video with caption:\n{caption or '(no caption)'}\n\nSend this broadcast?"
                try:
                    self.bot.send_video(telegram_id, media_file_id, caption=preview_text,
                                        reply_markup=get_broadcast_preview_keyboard(),
                                        supports_streaming=True)
                except Exception:
                    self.bot.send_message(telegram_id, preview_text,
                                          reply_markup=get_broadcast_preview_keyboard())
            else:
                preview_text = preview_header + f"Message:\n{message}\n\nSend this broadcast?"
                self.bot.send_message(telegram_id, preview_text,
                                      reply_markup=get_broadcast_preview_keyboard())
        except Exception as e:
            logger.error(f"Failed to send broadcast preview: {e}")

    def start_broadcast_with_audience(self, admin_id: int, audience: str, bot: TeleBot = None):
        """Called by the admin handler when an admin clicks VIP/Normal/All broadcast."""
        try:
            self.broadcast_sessions[admin_id] = {
                "step": "message",
                "message": None,
                "caption": None,
                "media_type": None,
                "media_file_id": None,
                "audience": audience
            }
            b = bot or self.bot
            b.send_message(
                admin_id,
                f"📢 {audience} Broadcast\n\nPlease enter your broadcast message "
                "(text, or send a photo/video with a caption). "
                "Bold, italic and other formatting will be preserved:",
                reply_markup=get_cancel_keyboard("broadcast_cancel")
            )
        except Exception as e:
            logger.error(f"start_broadcast_with_audience failed: {e}")

    # ------------------------------------------------------------------
    # Audience selection (per client):
    #   VIP    -> accepted registration (member_type vip / verification_status approved)
    #   NORMAL -> no request yet OR rejected
    #   ALL    -> both
    # ------------------------------------------------------------------
    def get_audience_users(self, audience: str):
        try:
            if audience == "ALL":
                users = database.select("users")
                return users if users else []

            all_users = database.select("users") or []
            if audience == "VIP":
                result = []
                for u in all_users:
                    if u.get("blocked"):
                        continue
                    is_vip = (
                        u.get("member_type") == "vip"
                        or u.get("verification_status") == "approved"
                    )
                    if is_vip:
                        result.append(u)
                return result

            if audience == "NORMAL":
                result = []
                for u in all_users:
                    if u.get("blocked"):
                        continue
                    status = u.get("verification_status")
                    # no request yet, or rejected
                    if status in (None, "pending", "rejected") and u.get("member_type") != "vip":
                        result.append(u)
                return result

            return all_users
        except Exception as e:
            logger.error(f"Failed to get audience users: {e}")
            return []

    # ------------------------------------------------------------------
    # Sending — preserves bold/italic via parse_mode HTML
    # ------------------------------------------------------------------
    def send_broadcast(self, message: str, audience: str, admin_id: int,
                       media_type: str = None, media_file_id: str = None, caption: str = None):
        try:
            users = self.get_audience_users(audience)
            total = len(users)
            successful = 0
            failed = 0
            blocked = 0

            broadcast_data = {
                "message_content": message or caption or "",
                "audience": audience,
                "total_recipients": total,
                "status": "sending",
                "created_by": admin_id,
                "sent_at": get_current_timestamp()
            }
            broadcast = database.create_broadcast(broadcast_data)
            broadcast_id = broadcast.get("id") if broadcast else None

            for user_batch in chunk_list(users, config.BROADCAST_BATCH_SIZE):
                for user in user_batch:
                    try:
                        if user.get("blocked"):
                            blocked += 1
                            continue
                        target = user.get("telegram_id")
                        if not target:
                            continue
                        if media_type == "photo":
                            self.bot.send_photo(target, media_file_id, caption=caption or "")
                        elif media_type == "video":
                            self.bot.send_video(target, media_file_id, caption=caption or "",
                                                supports_streaming=True)
                        else:
                            # Text message — send as-is so Telegram renders **bold**, _italic_, etc.
                            self.bot.send_message(target, message)
                        successful += 1
                        time.sleep(config.BROADCAST_DELAY_SECONDS)
                    except Exception as e:
                        logger.error(f"Broadcast failed for user {user.get('telegram_id')}: {e}")
                        if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                            blocked += 1
                            database.update_user(user.get("telegram_id"), {"blocked": True})
                        else:
                            failed += 1
                time.sleep(1)

            if broadcast_id:
                database.update_broadcast(broadcast_id, {
                    "successful": successful,
                    "failed": failed,
                    "blocked": blocked,
                    "status": "completed",
                    "completed_at": get_current_timestamp()
                })
            return {
                "total": total,
                "successful": successful,
                "failed": failed,
                "blocked": blocked
            }
        except Exception as e:
            logger.error(f"Failed to send broadcast: {e}")
            return {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "blocked": 0
            }


# module-level reference so the admin handler can start a broadcast
broadcast_handler = None


def register_broadcast_handlers(bot: TeleBot):
    handler = BroadcastHandler(bot)
    handler.register()
    return handler
