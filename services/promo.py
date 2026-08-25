import os
import re
import json
import time
import logging
from telebot import TeleBot
from telebot.types import InputMediaPhoto, InputMediaVideo
from config import config
from database import database

logger = logging.getLogger(__name__)

CAPITAL_RESP_LOW = "Eyy,☹️\nNe capital chala takkuva ga undi, deenitho start cheyyochu but chala Slow and Careful ga Trades teeskovali - atleast 6k tho Start cheyyandi"
CAPITAL_RESP_MID = "Haa parledu😉, chinnaga start chesi, gradual ga daily profits book cheskovachu"
CAPITAL_RESP_HIGH = "Nice😎, daily consistent ga profits kosam idi satipothadi"

TESTIMONIAL_INTRO_TEXT = "Look at these Results ☝🏻\n\nThese are the results of our VIP students Using PMS Compounding Strategy for daily trading - Last week aee trading cheyyadam Nerchukunnaru"

NO_FEE_TEXT = "Dont worry, joining 𝐅𝐞𝐞 em Ledu, but only serious Learners kae 𝐅𝐫𝐞𝐞 ga join ayye opportunity dorkuthundi."

VIP_BENEFITS_TEXT = (
    "𝐇𝐞𝐫𝐞 𝐚𝐫𝐞 𝐭𝐡𝐞 𝐯𝐢𝐩 𝐛𝐞𝐧𝐞𝐟𝐢𝐭𝐬 👇\n"
    "👑 𝐄𝐱𝐜𝐥𝐮𝐬𝐢𝐯𝐞 𝐕𝐈𝐏 𝐂𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐀𝐜𝐜𝐞𝐬𝐬 \n"
    "♾️ 𝐋𝐢𝐟𝐞𝐭𝐢𝐦𝐞 𝐂𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐀𝐜𝐜𝐞𝐬𝐬\n"
    "🔴 𝐋𝐢𝐯𝐞 𝐓𝐫𝐚𝐝𝐢𝐧𝐠 𝐒𝐞𝐬𝐬𝐢𝐨𝐧𝐬 \n"
    "📈 𝐄𝐱𝐜𝐥𝐮𝐬𝐢𝐯𝐞 𝐒𝐢𝐠𝐧𝐚𝐥𝐬\n"
    "🎓 𝐋𝐢𝐯𝐞 𝐂𝐥𝐚𝐬𝐬𝐞𝐬 \n"
    "🎥 𝐑𝐞𝐜𝐨𝐫𝐝𝐞𝐝 𝐂𝐥𝐚𝐬𝐬𝐞𝐬 \n"
    "📚 𝐑𝐞𝐜𝐨𝐫𝐝𝐞𝐝 𝐂𝐨𝐮𝐫𝐬𝐞𝐬 & 𝐋𝐞𝐬𝐬𝐨𝐧𝐬\n"
    "💰 𝐁𝐚𝐬𝐢𝐜 𝐭𝐨 𝐀𝐝𝐯𝐚𝐧𝐜𝐞 𝐓𝐫𝐚𝐝𝐢𝐧𝐠\n"
    "🚀 𝐀-𝐭𝐨-𝐙 𝐏𝐌𝐒 𝐂𝐨𝐦𝐩𝐨𝐮𝐧𝐝𝐢𝐧𝐠 𝐒𝐭𝐫𝐚𝐭𝐞𝐠𝐲\n"
    "🧠 𝐀𝐈 𝐓𝐫𝐚𝐝𝐢𝐧𝐠 𝐓𝐨𝐨𝐥𝐬\n"
    "🤖 𝐔𝐩𝐜𝐨𝐦𝐢𝐧𝐠 𝐀𝐈-𝐈𝐧𝐭𝐞𝐠𝐫𝐚𝐭𝐞𝐝 𝐀𝐮𝐭𝐨𝐦𝐚𝐭𝐞𝐝 𝐓𝐫𝐚𝐝𝐢𝐧𝐠 𝐁𝐨𝐭\n"
    "🎁 𝐄𝐱𝐜𝐥𝐮𝐬𝐢𝐯𝐞 𝐁𝐨𝐧𝐮𝐬𝐞𝐬\n"
    "💵 𝟓𝟎% 𝐃𝐞𝐩𝐨𝐬𝐢𝐭 𝐁𝐨𝐧𝐮𝐬\n"
    "🛡️ 𝐒𝐤𝐮𝐥𝐥 𝐓𝐫𝐚𝐝𝐞𝐫 𝐒𝐮𝐩𝐩𝐨𝐫𝐭 𝐓𝐞𝐚𝐦\n"
    "🔥 𝐅𝐮𝐭𝐮𝐫𝐞 𝐄𝐱𝐜𝐥𝐮𝐬𝐢𝐯𝐞 𝐕𝐈𝐏 𝐑𝐞𝐬𝐨𝐮𝐫𝐜𝐞𝐬 & 𝐁𝐞𝐧𝐞𝐟𝐢𝐭𝐬\n\n"
    "Even though Meeku trading lo ZERO Knowlege unna kani VIP COMMUNITY lo A to Z nerchukovachu"
)

ASK_TO_JOIN_TEXT = "Want to join the 𝐕𝐈𝐏 𝐂𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 🔥?"

REENGAGEMENT_TEXT = (
    "Hey, mee VIP access registration inka complete avvaledu. "
    "Mee registration complete chesi VIP group lo join avvadaniki interest unda? "
    "Emanna doubts unte adagandi 😊"
)

REGISTRATION_STEPS_CAPTION = (
    "Joining Link : {link}\n\n"
    "Step 1: Register and open a new trading account using the link below.\n\n"
    "Step 2: You will automatically get a 50% bonus on your deposit if you use this link.\n\n"
    "Step 3: Deposit at least $50 to generate consistent profits.\n\n"
    "Step 4: Send your trading account ID (e.g. 12355426789). "
    "Our team will manually verify it and approve your joining ASAP.\n\n"
    "Step 5: Once verified, you will be added to the VIP community and "
    "receive all the exclusive VIP resources."
)

FINAL_NOTE = (
    "🔴 NOTE — Only after completing ALL steps correctly will you get VIP student access. "
    "𝘽𝙚𝙘𝙖𝙪𝙨𝙚 𝙤𝙣𝙡𝙮 𝙨𝙚𝙧𝙞𝙤𝙪𝙨 𝙩𝙧𝙖𝙙𝙚𝙧𝙨 𝙬𝙞𝙡𝙡 𝙗𝙚 𝙃𝙚𝙡𝙥𝙚𝙙 𝙉𝙤𝙩 𝙂𝙖𝙢𝙗𝙡𝙚𝙧𝙨"
)

ACCOUNT_ID_PROMPT_CAPTION = (
    "𝐌𝐞 𝟗 𝐃𝐢𝐠𝐢𝐭 𝐓𝐫𝐚𝐝𝐢𝐧𝐠 𝐀𝐜𝐜𝐨𝐮𝐧𝐭 𝐈𝐝 🪪 send chesthe ne, Verify avthundi."
)

REJECTION_MESSAGE_TEMPLATE = (
    "❌ Mi Registration Decline ayyindi \n\n"
    "Kindly create account through our Student link to get VIP access\n\n"
    "Kindly use this link👇👇\n"
    "{link}"
)


def _send_typing(bot: TeleBot, chat_id: int, delay: float = 1.5):
    try:
        bot.send_chat_action(chat_id, "typing")
        time.sleep(delay)
    except Exception:
        pass


def _send_upload_action(bot: TeleBot, chat_id: int, action: str = "upload_photo", delay: float = 1.0):
    try:
        bot.send_chat_action(chat_id, action)
        time.sleep(delay)
    except Exception:
        pass


def _parse_telegram_post_link(url_str: str):
    """Parse both Public (t.me/channel/12) and Private (t.me/c/12345/12) Telegram post links."""
    if not url_str:
        return None, None
    clean = url_str.strip()

    # 1. Private Channel Link: t.me/c/1234567890/45
    private_match = re.search(r"t\.me/c/(\d+)/(\d+)", clean)
    if private_match:
        raw_id = private_match.group(1)
        msg_id = int(private_match.group(2))
        from_chat = int(f"-100{raw_id}") if not raw_id.startswith("-100") else int(raw_id)
        return from_chat, msg_id

    # 2. Public Channel Link: t.me/channel_username/45
    public_match = re.search(r"t\.me/([a-zA-Z0-9_]+)/(\d+)", clean)
    if public_match:
        channel_username = public_match.group(1)
        msg_id = int(public_match.group(2))
        if channel_username.lower() != "c":
            from_chat = f"@{channel_username}"
            return from_chat, msg_id

    return None, None


def get_capital_response(amount: int) -> str:
    if amount < 5000:
        return CAPITAL_RESP_LOW
    elif 5000 <= amount <= 9999:
        return CAPITAL_RESP_MID
    else:
        return CAPITAL_RESP_HIGH


def send_testimonials(bot: TeleBot, telegram_id: int):
    """Send testimonials album from dynamic Supabase links (or fallback to local disk)."""
    try:
        _send_upload_action(bot, telegram_id, "upload_photo", 1.2)

        # 1. Check dynamic testimonial media sources from Supabase
        setting = database.get_setting("testimonial_media_sources")
        dynamic_sources = []
        if setting and setting.get("value"):
            try:
                dynamic_sources = json.loads(setting["value"])
            except Exception:
                dynamic_sources = [s.strip() for s in setting["value"].split(",") if s.strip()]

        if dynamic_sources and len(dynamic_sources) > 0:
            media_group = []
            for i, src in enumerate(dynamic_sources[:8]):
                caption = TESTIMONIAL_INTRO_TEXT if i == 0 else None
                media_group.append(InputMediaPhoto(src, caption=caption))
            try:
                bot.send_media_group(telegram_id, media_group)
                logger.info(f"Sent dynamic testimonials album to {telegram_id}")
                return
            except Exception as e:
                logger.warning(f"Failed sending dynamic media group: {e}")

        # 2. Fallback to cached file_ids
        cached = database.get_setting("cached_testimonial_file_ids")
        if cached and cached.get("value"):
            file_ids = [fid.strip() for fid in cached["value"].split(",") if fid.strip()]
            if file_ids:
                media_group = []
                for i, fid in enumerate(file_ids[:8]):
                    caption = TESTIMONIAL_INTRO_TEXT if i == 0 else None
                    media_group.append(InputMediaPhoto(fid, caption=caption))
                try:
                    bot.send_media_group(telegram_id, media_group)
                    return
                except Exception as e:
                    logger.warning(f"Failed sending cached media group: {e}")

        # 3. Fallback to local testimonials folder
        tdir = config.get_testimonials_path()
        if not os.path.isdir(tdir):
            bot.send_message(telegram_id, TESTIMONIAL_INTRO_TEXT)
            return

        files = sorted(
            [f for f in os.listdir(tdir) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        )
        count = config.TESTIMONIALS_COUNT or 8
        files = files[:count]

        if not files:
            bot.send_message(telegram_id, TESTIMONIAL_INTRO_TEXT)
            return

        media_group = []
        opened_files = []
        for i, fname in enumerate(files):
            fpath = os.path.join(tdir, fname)
            fp = open(fpath, "rb")
            opened_files.append(fp)
            caption = TESTIMONIAL_INTRO_TEXT if i == 0 else None
            media_group.append(InputMediaPhoto(fp, caption=caption))

        try:
            sent_msgs = bot.send_media_group(telegram_id, media_group)
            if sent_msgs:
                new_fids = []
                for m in sent_msgs:
                    if m.photo:
                        new_fids.append(m.photo[-1].file_id)
                if new_fids:
                    database.set_setting("cached_testimonial_file_ids", ",".join(new_fids))
        finally:
            for fp in opened_files:
                try:
                    fp.close()
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Failed to send testimonials album to {telegram_id}: {e}")
        try:
            bot.send_message(telegram_id, TESTIMONIAL_INTRO_TEXT)
        except Exception:
            pass


def send_no_fee_message(bot: TeleBot, telegram_id: int):
    try:
        _send_typing(bot, telegram_id, 1.5)
        bot.send_message(telegram_id, NO_FEE_TEXT)
    except Exception as e:
        logger.error(f"Failed to send no-fee message to {telegram_id}: {e}")


def send_vip_benefits(bot: TeleBot, telegram_id: int):
    try:
        _send_typing(bot, telegram_id, 1.5)
        bot.send_message(telegram_id, VIP_BENEFITS_TEXT)
    except Exception as e:
        logger.error(f"Failed to send VIP benefits to {telegram_id}: {e}")


def send_ask_to_join(bot: TeleBot, telegram_id: int):
    try:
        _send_typing(bot, telegram_id, 1.2)
        bot.send_message(telegram_id, ASK_TO_JOIN_TEXT)
    except Exception as e:
        logger.error(f"Failed to send ask-to-join message to {telegram_id}: {e}")


def send_reengagement_message(bot: TeleBot, telegram_id: int):
    try:
        _send_typing(bot, telegram_id, 1.5)
        bot.send_message(telegram_id, REENGAGEMENT_TEXT)
    except Exception as e:
        logger.error(f"Failed to send reengagement message to {telegram_id}: {e}")


def send_registration_video(bot: TeleBot, telegram_id: int):
    """Send tutorial video from Telegram channel post link (Public/Private), direct URL, or local disk."""
    link = config.get_joining_link() or "(link not configured)"
    caption = REGISTRATION_STEPS_CAPTION.format(link=link)

    try:
        _send_upload_action(bot, telegram_id, "upload_video", 1.2)

        # 1. Check if dynamic Telegram post link or URL is configured in Supabase
        setting = database.get_setting("registration_video_source")
        if setting and setting.get("value"):
            video_src = setting["value"].strip()
            from_chat, msg_id = _parse_telegram_post_link(video_src)

            # 1a. If it is a Telegram channel post link -> Copy message directly with custom caption
            if from_chat and msg_id:
                try:
                    bot.copy_message(
                        chat_id=telegram_id,
                        from_chat_id=from_chat,
                        message_id=msg_id,
                        caption=caption
                    )
                    logger.info(f"Copied tutorial video from {from_chat} msg #{msg_id} to {telegram_id}")
                    return
                except Exception as e:
                    logger.error(f"Failed to copy video from channel post ({from_chat}, #{msg_id}): {e}")

            # 1b. If it is a direct video URL or file_id
            elif video_src.startswith("http") or len(video_src) > 20:
                try:
                    bot.send_video(
                        telegram_id,
                        video_src,
                        caption=caption,
                        supports_streaming=True
                    )
                    logger.info(f"Sent tutorial video from URL/file_id to {telegram_id}")
                    return
                except Exception as e:
                    logger.error(f"Failed to send video from URL/file_id: {e}")

        # 2. Fallback to local video file
        video_path = config.get_registration_video_path()
        if video_path and os.path.exists(video_path):
            with open(video_path, "rb") as vf:
                bot.send_video(
                    telegram_id,
                    vf,
                    caption=caption,
                    supports_streaming=True,
                    timeout=120
                )
        else:
            bot.send_message(telegram_id, caption)

    except Exception as e:
        logger.error(f"Failed to send registration video to {telegram_id}: {e}")
        try:
            bot.send_message(telegram_id, caption)
        except Exception:
            pass


def send_registration_steps(bot: TeleBot, telegram_id: int):
    try:
        _send_typing(bot, telegram_id, 1.5)
        bot.send_message(
            telegram_id,
            "Here is the Joining Process\n\n"
            "Serious ga ne Trading Nerchukovadaniki , frst and basic thing oka manchi trading account undali.\n\nHere is the Full Process in Detail 👇"
        )
    except Exception as e:
        logger.error(f"Failed to send joining-process intro to {telegram_id}: {e}")

    send_registration_video(bot, telegram_id)


def send_20s_registration_reminder(bot: TeleBot, telegram_id: int):
    """Send NOTE message followed by dynamic GIF with caption asking for 9-digit Trading ID."""
    try:
        # Message 1: NOTE
        _send_typing(bot, telegram_id, 1.5)
        bot.send_message(telegram_id, FINAL_NOTE)

        # Message 2: Dynamic GIF with Caption
        _send_typing(bot, telegram_id, 1.2)

        # 1. Check if dynamic GIF post link or URL is configured in Supabase
        setting = database.get_setting("account_id_gif_source")
        if setting and setting.get("value"):
            gif_src = setting["value"].strip()
            from_chat, msg_id = _parse_telegram_post_link(gif_src)

            # 1a. If it is a Telegram channel post link -> Copy GIF with caption
            if from_chat and msg_id:
                try:
                    bot.copy_message(
                        chat_id=telegram_id,
                        from_chat_id=from_chat,
                        message_id=msg_id,
                        caption=ACCOUNT_ID_PROMPT_CAPTION
                    )
                    logger.info(f"Copied guidance GIF from {from_chat} msg #{msg_id} to {telegram_id}")
                    return
                except Exception as e:
                    logger.error(f"Failed to copy GIF from channel post ({from_chat}, #{msg_id}): {e}")

            # 1b. If it is a direct GIF URL or file_id
            elif gif_src.startswith("http") or len(gif_src) > 20:
                try:
                    bot.send_animation(
                        telegram_id,
                        gif_src,
                        caption=ACCOUNT_ID_PROMPT_CAPTION
                    )
                    logger.info(f"Sent guidance GIF from URL/file_id to {telegram_id}")
                    return
                except Exception as e:
                    logger.error(f"Failed to send GIF animation from URL: {e}")

        # 2. Fallback to local media/ files
        gif_candidates = [
            os.path.join(config.MEDIA_DIR, "account_id.gif"),
            os.path.join(config.MEDIA_DIR, "id.gif"),
            os.path.join(config.MEDIA_DIR, "trading_id.gif"),
            os.path.join(config.MEDIA_DIR, "account_id.mp4"),
        ]

        sent_gif = False
        for gpath in gif_candidates:
            if os.path.exists(gpath):
                try:
                    with open(gpath, "rb") as gf:
                        bot.send_animation(telegram_id, gf, caption=ACCOUNT_ID_PROMPT_CAPTION)
                    sent_gif = True
                    break
                except Exception:
                    pass

        if not sent_gif:
            bot.send_message(telegram_id, ACCOUNT_ID_PROMPT_CAPTION)

    except Exception as e:
        logger.error(f"Failed to send 20s reminder to {telegram_id}: {e}")


def send_vip_resources(bot: TeleBot, telegram_id: int):
    try:
        msg = config.get_vip_resources_message()
        _send_typing(bot, telegram_id, 1.5)
        bot.send_message(telegram_id, msg)
        logger.info(f"Sent 2-minute VIP resources message to {telegram_id}")
    except Exception as e:
        logger.error(f"Failed to send VIP resources to {telegram_id}: {e}")
