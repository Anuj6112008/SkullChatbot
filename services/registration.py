import logging
from telebot import TeleBot
from config import config
from database import database
from utils import get_current_timestamp, sanitize_text

logger = logging.getLogger(__name__)

class RegistrationService:
    def __init__(self, bot: TeleBot = None):
        self.bot = bot
        self.registration_states = {}

    def set_registration_state(self, telegram_id: int, state: str):
        self.registration_states[telegram_id] = state

    def get_registration_state(self, telegram_id: int):
        return self.registration_states.get(telegram_id)

    def clear_registration_state(self, telegram_id: int):
        if telegram_id in self.registration_states:
            del self.registration_states[telegram_id]

    def is_awaiting_account_id(self, telegram_id: int) -> bool:
        return self.registration_states.get(telegram_id) == "awaiting_account_id"

    def is_in_registration(self, telegram_id: int) -> bool:
        state = self.registration_states.get(telegram_id)
        return state == "in_registration" or state == "awaiting_account_id"