import os
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

SCREENSHOT_REQUEST_NOTE = (
    "𝐌𝐞 𝟗 𝐃𝐢𝐠𝐢𝐭 𝐓𝐫𝐚𝐝𝐢𝐧𝐠 𝐀𝐜𝐜𝐨𝐮𝐧𝐭 𝐈𝐝 🪪 send chesthe ne, Verify avthundi."
)


def get_capital_response(amount: int) -> str:
    if amount < 5000:
        return CAPITAL_RESP_LOW
    elif 5000 <= amount <= 9999:
        return CAPITAL_RESP_MID
    else:
        return CAPITAL_RESP_HIGH


def send_testimonials(bot: TeleBot, telegram_id: int):
    
    try:
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
                    logger.warning(f"Failed to send cached media group: {e}")

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
        bot.send_message(telegram_id, NO_FEE_TEXT)
    except Exception as e:
        logger.error(f"Failed to send no-fee message to {telegram_id}: {e}")


def send_vip_benefits(bot: TeleBot, telegram_id: int):
    try:
        bot.send_message(telegram_id, VIP_BENEFITS_TEXT)
    except Exception as e:
        logger.error(f"Failed to send VIP benefits to {telegram_id}: {e}")


def send_ask_to_join(bot: TeleBot, telegram_id: int):
    try:
        bot.send_message(telegram_id, ASK_TO_JOIN_TEXT)
    except Exception as e:
        logger.error(f"Failed to send ask-to-join message to {telegram_id}: {e}")


def send_reengagement_message(bot: TeleBot, telegram_id: int):
    try:
        bot.send_message(telegram_id, REENGAGEMENT_TEXT)
    except Exception as e:
        logger.error(f"Failed to send reengagement message to {telegram_id}: {e}")


def send_registration_video(bot: TeleBot, telegram_id: int):
    try:
        cached = database.get_setting("cached_registration_video_file_id")
        if cached and cached.get("value"):
            try:
                bot.send_video(
                    telegram_id,
                    cached["value"],
                    caption=REGISTRATION_STEPS_CAPTION,
                    supports_streaming=True
                )
                return
            except Exception as e:
                logger.warning(f"Cached video send failed: {e}")

        video_path = config.get_registration_video_path()
        if video_path and os.path.exists(video_path):
            with open(video_path, "rb") as vf:
                sent_msg = bot.send_video(
                    telegram_id,
                    vf,
                    caption=REGISTRATION_STEPS_CAPTION,
                    supports_streaming=True,
                    timeout=120
                )
                if sent_msg and sent_msg.video:
                    database.set_setting("cached_registration_video_file_id", sent_msg.video.file_id)
        else:
            bot.send_message(telegram_id, REGISTRATION_STEPS_CAPTION)

    except Exception as e:
        logger.error(f"Failed to send registration video to {telegram_id}: {e}")
        try:
            bot.send_message(telegram_id, REGISTRATION_STEPS_CAPTION)
        except Exception:
            pass


def send_registration_steps(bot: TeleBot, telegram_id: int):
    try:
        bot.send_message(
            telegram_id,
            "Here is the Joining Process\n\n"
            "Serious ga ne Trading Nerchukovadaniki , frst and basic thing oka manchi trading account undali.\n\nHere is the Full Process in Detail 👇"
        )
    except Exception as e:
        logger.error(f"Failed to send joining-process intro to {telegram_id}: {e}")

    link = config.get_joining_link() or "(link not configured)"

    send_registration_video(bot, telegram_id)


def send_20s_registration_reminder(bot: TeleBot, telegram_id: int):
    try:
        bot.send_message(telegram_id, FINAL_NOTE)
    except Exception as e:
        logger.error(f"Failed to send final note to {telegram_id}: {e}")
    try:
        bot.send_message(telegram_id, SCREENSHOT_REQUEST_NOTE)
    except Exception as e:
        logger.error(f"Failed to send screenshot note to {telegram_id}: {e}")


def send_vip_resources(bot: TeleBot, telegram_id: int):
    try:
        msg = config.get_vip_resources_message()
        bot.send_message(telegram_id, msg)
        logger.info(f"Sent 2-minute VIP resources message to {telegram_id}")
    except Exception as e:
        logger.error(f"Failed to send VIP resources to {telegram_id}: {e}")