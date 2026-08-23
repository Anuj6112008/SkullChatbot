import logging
import httpx
from config import config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.url = config.SUPABASE_URL
        self.key = config.SUPABASE_KEY
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        self.client = httpx.Client(timeout=30.0)

    def _get_url(self, table_name):
        return f"{self.url}/rest/v1/{table_name}"

    def _handle_response(self, response):
        try:
            response.raise_for_status()
            if response.text:
                return response.json()
            return []
        except Exception as e:
            logger.error(f"Supabase API error: {e}, Response: {response.text}")
            return []

    def select(self, table_name, match_conditions=None, order_by=None, limit=None, offset=None, columns="*"):
        url = self._get_url(table_name)
        params = {"select": columns}
        if match_conditions:
            for key, value in match_conditions.items():
                if isinstance(value, dict):
                    for op, val in value.items():
                        if op == "eq":
                            params[key] = f"eq.{val}"
                        elif op == "gt":
                            params[key] = f"gt.{val}"
                        elif op == "gte":
                            params[key] = f"gte.{val}"
                        elif op == "lt":
                            params[key] = f"lt.{val}"
                        elif op == "lte":
                            params[key] = f"lte.{val}"
                        elif op == "neq":
                            params[key] = f"neq.{val}"
                        elif op == "like":
                            params[key] = f"like.{val}"
                        elif op == "ilike":
                            params[key] = f"ilike.{val}"
                else:
                    params[key] = f"eq.{value}"
        if order_by:
            order_str = ",".join([f"{field}.{direction}" for field, direction in order_by.items()])
            params["order"] = order_str
        if limit:
            params["limit"] = str(limit)
        if offset:
            params["offset"] = str(offset)
        response = self.client.get(url, headers=self.headers, params=params)
        return self._handle_response(response)

    def insert(self, table_name, data):
        url = self._get_url(table_name)
        response = self.client.post(url, headers=self.headers, json=data)
        return self._handle_response(response)

    def update(self, table_name, data, match_conditions):
        url = self._get_url(table_name)
        params = {}
        for key, value in match_conditions.items():
            params[key] = f"eq.{value}"
        response = self.client.patch(url, headers=self.headers, json=data, params=params)
        return self._handle_response(response)

    def delete(self, table_name, match_conditions):
        url = self._get_url(table_name)
        params = {}
        for key, value in match_conditions.items():
            params[key] = f"eq.{value}"
        response = self.client.delete(url, headers=self.headers, params=params)
        return self._handle_response(response)

    def count(self, table_name, match_conditions=None):
        result = self.select(table_name, match_conditions=match_conditions, limit=1000)
        return len(result) if result else 0

    def execute(self, query):
        url = f"{self.url}/rest/v1/rpc/execute_sql"
        try:
            response = self.client.post(url, headers=self.headers, json={"query": query})
            return self._handle_response(response)
        except Exception as e:
            logger.error(f"Execute SQL failed: {e}")
            return []

    def get_user(self, telegram_id):
        result = self.select("users", match_conditions={"telegram_id": telegram_id})
        if result:
            return result[0]
        return None

    def create_user(self, user_data):
        existing = self.get_user(user_data.get("telegram_id"))
        if existing:
            return existing
        result = self.insert("users", user_data)
        if result:
            return result[0]
        return None

    def update_user(self, telegram_id, update_data):
        result = self.update("users", update_data, {"telegram_id": telegram_id})
        if result:
            return result[0]
        return None

    def get_registration(self, registration_id):
        result = self.select("registrations", match_conditions={"id": registration_id})
        if result:
            return result[0]
        return None

    def get_registration_by_user(self, telegram_id):
        result = self.select("registrations", match_conditions={"telegram_id": telegram_id}, order_by={"created_at": "desc"}, limit=1)
        if result:
            return result[0]
        return None

    def create_registration(self, registration_data):
        result = self.insert("registrations", registration_data)
        if result:
            return result[0]
        return None

    def update_registration(self, registration_id, update_data):
        result = self.update("registrations", update_data, {"id": registration_id})
        if result:
            return result[0]
        return None

    def get_pending_verifications(self):
        return self.select("registrations", match_conditions={"verification_status": "pending"})

    def create_verification_request(self, data):
        result = self.insert("verification_requests", data)
        if result:
            return result[0]
        return None

    def get_support_ticket(self, ticket_id):
        result = self.select("support_tickets", match_conditions={"id": ticket_id})
        if result:
            return result[0]
        return None

    def create_support_ticket(self, data):
        result = self.insert("support_tickets", data)
        if result:
            return result[0]
        return None

    def update_support_ticket(self, ticket_id, update_data):
        result = self.update("support_tickets", update_data, {"id": ticket_id})
        if result:
            return result[0]
        return None

    def get_faq_item(self, intent):
        result = self.select("faq_items", match_conditions={"intent": intent, "enabled": True})
        if result:
            return result[0]
        return None

    def get_all_faq_items(self, enabled_only=True):
        conditions = {"enabled": True} if enabled_only else {}
        return self.select("faq_items", match_conditions=conditions)

    def create_faq_item(self, data):
        result = self.insert("faq_items", data)
        if result:
            return result[0]
        return None

    def update_faq_item(self, faq_id, update_data):
        result = self.update("faq_items", update_data, {"id": faq_id})
        if result:
            return result[0]
        return None

    def get_media_file(self, media_id):
        result = self.select("media_files", match_conditions={"id": media_id})
        if result:
            return result[0]
        return None

    def get_media_by_intent(self, intent):
        result = self.select("media_files", match_conditions={"intent": intent, "enabled": True})
        if result:
            return result[0]
        return None

    def create_media_file(self, data):
        result = self.insert("media_files", data)
        if result:
            return result[0]
        return None

    def get_scheduled_message(self, message_id):
        result = self.select("scheduled_messages", match_conditions={"id": message_id})
        if result:
            return result[0]
        return None

    def get_all_scheduled_messages(self, enabled_only=True):
        conditions = {"enabled": True} if enabled_only else {}
        return self.select("scheduled_messages", match_conditions=conditions, order_by={"scheduled_at": "asc"})

    def create_scheduled_message(self, data):
        result = self.insert("scheduled_messages", data)
        if result:
            return result[0]
        return None

    def update_scheduled_message(self, message_id, update_data):
        result = self.update("scheduled_messages", update_data, {"id": message_id})
        if result:
            return result[0]
        return None

    def delete_scheduled_message(self, message_id):
        return self.delete("scheduled_messages", {"id": message_id})

    def get_broadcast(self, broadcast_id):
        result = self.select("broadcasts", match_conditions={"id": broadcast_id})
        if result:
            return result[0]
        return None

    def create_broadcast(self, data):
        result = self.insert("broadcasts", data)
        if result:
            return result[0]
        return None

    def update_broadcast(self, broadcast_id, update_data):
        result = self.update("broadcasts", update_data, {"id": broadcast_id})
        if result:
            return result[0]
        return None

    def get_admin_logs(self, limit=100, offset=0):
        return self.select("admin_logs", order_by={"created_at": "desc"}, limit=limit, offset=offset)

    def create_admin_log(self, data):
        result = self.insert("admin_logs", data)
        if result:
            return result[0]
        return None

    def get_setting(self, key):
        result = self.select("settings", match_conditions={"key": key})
        if result:
            return result[0]
        return None

    def get_all_settings(self):
        return self.select("settings")

    def set_setting(self, key, value, description=None):
        data = {"key": key, "value": value}
        if description:
            data["description"] = description
        existing = self.get_setting(key)
        if existing:
            result = self.update("settings", data, {"key": key})
        else:
            result = self.insert("settings", data)
        if result:
            return result[0]
        return None

    def get_user_followups(self, telegram_id):
        return self.select("followups", match_conditions={"telegram_id": telegram_id}, order_by={"created_at": "desc"})

    def create_followup(self, data):
        result = self.insert("followups", data)
        if result:
            return result[0]
        return None

    def update_followup(self, followup_id, update_data):
        result = self.update("followups", update_data, {"id": followup_id})
        if result:
            return result[0]
        return None

    def get_due_followups(self):
        result = self.select("followups", match_conditions={"sent": False, "enabled": True})
        return result if result else []

    def get_due_scheduled_messages(self):
        import datetime
        now = datetime.datetime.now().isoformat()
        result = self.select("scheduled_messages", match_conditions={"sent": False, "enabled": True})
        due = []
        if result:
            for msg in result:
                if msg.get("scheduled_at") and msg["scheduled_at"] <= now:
                    due.append(msg)
        return due

    def get_user_counts(self):
        total = self.count("users")
        approved = self.count("users", match_conditions={"verification_status": "approved"})
        pending = self.count("registrations", match_conditions={"verification_status": "pending"})
        paid = self.count("users", match_conditions={"paid_user": True})
        free = self.count("users", match_conditions={"paid_user": False})
        vip = self.count("users", match_conditions={"member_type": "vip"})
        normal = self.count("users", match_conditions={"member_type": "normal"})
        return {
            "total": total,
            "approved": approved,
            "pending_verification": pending,
            "paid": paid,
            "free": free,
            "vip": vip,
            "normal": normal
        }

database = Database()