import re
import json
import logging
import datetime
from typing import Any, Dict, List, Optional
from config import config

logger = logging.getLogger(__name__)

def validate_telegram_id(telegram_id):
    try:
        return int(telegram_id)
    except (ValueError, TypeError):
        return None

def validate_phone_number(phone):
    pattern = re.compile(r'^\+?[1-9]\d{1,14}$')
    return bool(pattern.match(str(phone)))

def validate_email(email):
    pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    return bool(pattern.match(str(email)))

def format_telegram_username(username):
    if username:
        username = username.strip()
        if not username.startswith('@'):
            return f'@{username}'
        return username
    return None

def sanitize_text(text):
    if not text:
        return ""
    text = str(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def truncate_text(text, max_length=1000):
    if not text:
        return ""
    text = str(text)
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

def parse_json_safely(json_string):
    try:
        return json.loads(json_string)
    except (json.JSONDecodeError, TypeError):
        return {}

def to_json_safely(data):
    try:
        return json.dumps(data, default=str)
    except (TypeError, ValueError):
        return "{}"

def get_current_timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def get_current_datetime():
    return datetime.datetime.now(datetime.timezone.utc)

def format_datetime(dt):
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return str(dt)
    if isinstance(dt, datetime.datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return str(dt)

def add_days_to_date(days):
    return get_current_datetime() + datetime.timedelta(days=days)

def add_hours_to_date(hours):
    return get_current_datetime() + datetime.timedelta(hours=hours)

def is_within_time_range(check_time, start_time, end_time):
    if not check_time or not start_time or not end_time:
        return False
    check = datetime.datetime.strptime(check_time, '%H:%M').time()
    start = datetime.datetime.strptime(start_time, '%H:%M').time()
    end = datetime.datetime.strptime(end_time, '%H:%M').time()
    if start <= end:
        return start <= check <= end
    return check >= start or check <= end

def generate_followup_schedule(start_date, message_count):
    schedule = []
    current = start_date
    for i in range(message_count):
        schedule.append(current)
        if i < 24:
            current = add_hours_to_date(current, 1)
        else:
            current = add_days_to_date(current, 1)
    return schedule

def calculate_followup_stage(days_since_join):
    if days_since_join <= 1:
        return "first_day"
    elif days_since_join <= 7:
        return "first_week"
    else:
        return "after_week"

def should_send_followup(user_data, followup_config):
    if user_data.get("paid_user", False):
        return False
    if user_data.get("opt_out", False):
        return False
    if user_data.get("blocked", False):
        return False
    if user_data.get("verification_status") != "approved":
        return False
    followup_stage = user_data.get("followup_stage", 0)
    max_followup_days = followup_config.get("max_followup_days", config.MAX_FOLLOWUP_DAYS)
    joined_at = user_data.get("joined_at")
    if joined_at:
        try:
            if isinstance(joined_at, str):
                joined_at = datetime.datetime.fromisoformat(joined_at.replace('Z', '+00:00'))
            days_since = (get_current_datetime() - joined_at).days
            if days_since > max_followup_days:
                return False
        except:
            pass
    return True

def extract_keywords(text):
    text = str(text).lower()
    keywords = re.findall(r'\b[a-z0-9]+\b', text)
    return keywords

def detect_intent_from_keywords(text, intent_mapping):
    text = str(text).lower()
    detected_intents = {}
    for intent, keywords in intent_mapping.items():
        score = 0
        for keyword in keywords:
            if keyword.lower() in text:
                score += 1
        if score > 0:
            detected_intents[intent] = score
    if detected_intents:
        return max(detected_intents, key=detected_intents.get)
    return "GENERAL"

def is_admin(telegram_id):
    return config.is_admin(telegram_id)

def get_user_full_name(user_data):
    first = user_data.get("first_name", "")
    last = user_data.get("last_name", "")
    if first and last:
        return f"{first} {last}"
    return first or last or "Unknown User"

def format_user_display(user_data):
    name = get_user_full_name(user_data)
    username = user_data.get("username")
    if username:
        username = format_telegram_username(username)
        return f"{name} ({username})"
    return name

def create_user_summary(user_data):
    summary = []
    summary.append(f"ID: {user_data.get('telegram_id', 'N/A')}")
    summary.append(f"Name: {get_user_full_name(user_data)}")
    username = user_data.get("username")
    if username:
        summary.append(f"Username: @{username}")
    summary.append(f"Status: {user_data.get('status', 'unknown')}")
    summary.append(f"Paid: {'Yes' if user_data.get('paid_user') else 'No'}")
    summary.append(f"Verified: {user_data.get('verification_status', 'pending')}")
    summary.append(f"Course Access: {'Yes' if user_data.get('course_access') else 'No'}")
    summary.append(f"Updates Access: {'Yes' if user_data.get('updates_access') else 'No'}")
    return "\n".join(summary)

def create_registration_summary(registration_data):
    summary = []
    data = registration_data.get("registration_data", {})
    summary.append(f"Registration ID: {registration_data.get('id', 'N/A')}")
    summary.append(f"Telegram ID: {registration_data.get('telegram_id', 'N/A')}")
    summary.append(f"Status: {registration_data.get('verification_status', 'pending')}")
    if isinstance(data, dict):
        for key, value in data.items():
            summary.append(f"{key.title()}: {value}")
    else:
        summary.append(f"Data: {str(data)}")
    return "\n".join(summary)

def get_media_path(filename):
    return config.get_media_path(filename)

def get_prompt_path(filename=None):
    return config.get_prompt_path(filename)

def validate_video_file(filename):
    if not filename:
        return False
    import os
    ext = os.path.splitext(filename)[1].lower()
    return ext in config.ALLOWED_VIDEO_EXTENSIONS

def get_file_size_mb(filepath):
    import os
    try:
        size_bytes = os.path.getsize(filepath)
        return size_bytes / (1024 * 1024)
    except:
        return 0

def is_video_within_size_limit(filepath):
    size_mb = get_file_size_mb(filepath)
    return size_mb <= config.MAX_VIDEO_SIZE_MB

def escape_markdown(text):
    if not text:
        return ""
    text = str(text)
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def safe_split_string(text, delimiter=","):
    if not text:
        return []
    return [item.strip() for item in str(text).split(delimiter) if item.strip()]

def convert_to_boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on', 'y')
    return bool(value)

def get_nested_value(data, path, default=None):
    if not data or not path:
        return default
    keys = path.split('.')
    current = data
    for key in keys:
        try:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    index = int(key)
                    current = current[index]
                except (ValueError, IndexError):
                    return default
            else:
                return default
        except:
            return default
        if current is None:
            return default
    return current

def chunk_list(items, chunk_size):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]

def retry_operation(func, *args, max_attempts=None, delay=None, **kwargs):
    if max_attempts is None:
        max_attempts = config.RETRY_ATTEMPTS
    if delay is None:
        delay = config.RETRY_DELAY_SECONDS
    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            logger.warning(f"Retry {attempt+1}/{max_attempts} failed: {e}")
            import time
            time.sleep(delay)
    return None