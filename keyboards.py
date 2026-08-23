from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_start_keyboard():
    # Main menu removed per client requirement - conversation-driven flow, no button menu.
    return None


def get_back_keyboard(callback_data="back_to_main"):
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn_back = InlineKeyboardButton("🔙 Back", callback_data=callback_data)
    keyboard.add(btn_back)
    return keyboard


def get_end_faq_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn_end = InlineKeyboardButton("✅ End FAQ", callback_data="end_faq")
    keyboard.add(btn_end)
    return keyboard


def get_registration_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn_start = InlineKeyboardButton("✅ Start Registration", callback_data="start_registration")
    btn_cancel = InlineKeyboardButton("❌ Cancel", callback_data="cancel_registration")
    keyboard.add(btn_start, btn_cancel)
    return keyboard


def get_registration_cancel_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn_cancel = InlineKeyboardButton("❌ Cancel", callback_data="cancel_registration")
    keyboard.add(btn_cancel)
    return keyboard


def get_verification_keyboard(registration_id, user_telegram_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_approve = InlineKeyboardButton("✅ Accept", callback_data=f"verify_approve_{registration_id}_{user_telegram_id}")
    btn_reject = InlineKeyboardButton("❌ Decline", callback_data=f"verify_reject_{registration_id}_{user_telegram_id}")
    keyboard.add(btn_approve, btn_reject)
    return keyboard


# ---------------------------------------------------------------------------
# Admin panel — SIMPLIFIED per client.
# Only: VIP Broadcast, Normal Broadcast, All Broadcast, Stats.
# ---------------------------------------------------------------------------
def get_admin_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn_vip_broadcast = InlineKeyboardButton("💎 VIP Broadcast", callback_data="admin_broadcast_vip")
    btn_normal_broadcast = InlineKeyboardButton("👤 Normal Broadcast", callback_data="admin_broadcast_normal")
    btn_all_broadcast = InlineKeyboardButton("📢 All Broadcast", callback_data="admin_broadcast_all")
    btn_stats = InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")
    keyboard.add(btn_vip_broadcast)
    keyboard.add(btn_normal_broadcast)
    keyboard.add(btn_all_broadcast)
    keyboard.add(btn_stats)
    return keyboard


def get_admin_user_actions_keyboard(telegram_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_approve = InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_{telegram_id}")
    btn_reject = InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{telegram_id}")
    btn_paid = InlineKeyboardButton("💎 Mark Paid", callback_data=f"admin_paid_{telegram_id}")
    btn_unpaid = InlineKeyboardButton("🔄 Mark Unpaid", callback_data=f"admin_unpaid_{telegram_id}")
    btn_followup_enable = InlineKeyboardButton("▶️ Enable Followup", callback_data=f"admin_followup_enable_{telegram_id}")
    btn_followup_disable = InlineKeyboardButton("⏹️ Disable Followup", callback_data=f"admin_followup_disable_{telegram_id}")
    btn_course_grant = InlineKeyboardButton("📚 Grant Course", callback_data=f"admin_course_grant_{telegram_id}")
    btn_course_revoke = InlineKeyboardButton("🚫 Revoke Course", callback_data=f"admin_course_revoke_{telegram_id}")
    btn_updates_grant = InlineKeyboardButton("📢 Grant Updates", callback_data=f"admin_updates_grant_{telegram_id}")
    btn_updates_revoke = InlineKeyboardButton("🚫 Revoke Updates", callback_data=f"admin_updates_revoke_{telegram_id}")
    btn_message = InlineKeyboardButton("💬 Send Message", callback_data=f"admin_message_{telegram_id}")
    keyboard.add(btn_approve, btn_reject)
    keyboard.add(btn_paid, btn_unpaid)
    keyboard.add(btn_followup_enable, btn_followup_disable)
    keyboard.add(btn_course_grant, btn_course_revoke)
    keyboard.add(btn_updates_grant, btn_updates_revoke)
    keyboard.add(btn_message)
    return keyboard


def get_confirmation_keyboard(action, data):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_confirm = InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{action}_{data}")
    btn_cancel = InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{action}_{data}")
    keyboard.add(btn_confirm, btn_cancel)
    return keyboard


def get_broadcast_audience_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    audiences = [
        ("VIP", "💎 VIP Members Only"),
        ("NORMAL", "👤 Normal Members Only"),
        ("ALL", "📢 All Members")
    ]
    for value, label in audiences:
        btn = InlineKeyboardButton(label, callback_data=f"broadcast_audience_{value}")
        keyboard.add(btn)
    btn_cancel = InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")
    keyboard.add(btn_cancel)
    return keyboard


def get_screenshot_review_keyboard(registration_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_accept = InlineKeyboardButton("✅ Accept", callback_data=f"ss_accept_{registration_id}")
    btn_reject = InlineKeyboardButton("❌ Reject", callback_data=f"ss_reject_{registration_id}")
    keyboard.add(btn_accept, btn_reject)
    return keyboard


def get_broadcast_preview_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_send = InlineKeyboardButton("✅ Send Broadcast", callback_data="broadcast_send")
    btn_edit = InlineKeyboardButton("✏️ Edit", callback_data="broadcast_edit")
    btn_cancel = InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")
    keyboard.add(btn_send, btn_edit)
    keyboard.add(btn_cancel)
    return keyboard


def get_faq_management_keyboard(faq_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_edit = InlineKeyboardButton("✏️ Edit", callback_data=f"faq_edit_{faq_id}")
    btn_toggle = InlineKeyboardButton("🔄 Toggle Status", callback_data=f"faq_toggle_{faq_id}")
    btn_delete = InlineKeyboardButton("🗑️ Delete", callback_data=f"faq_delete_{faq_id}")
    keyboard.add(btn_edit, btn_toggle)
    keyboard.add(btn_delete)
    return keyboard


def get_scheduled_message_actions_keyboard(message_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_edit = InlineKeyboardButton("✏️ Edit", callback_data=f"schedule_edit_{message_id}")
    btn_toggle = InlineKeyboardButton("🔄 Toggle", callback_data=f"schedule_toggle_{message_id}")
    btn_delete = InlineKeyboardButton("🗑️ Delete", callback_data=f"schedule_delete_{message_id}")
    keyboard.add(btn_edit, btn_toggle)
    keyboard.add(btn_delete)
    return keyboard


def get_support_ticket_actions_keyboard(ticket_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_resolve = InlineKeyboardButton("✅ Resolve", callback_data=f"ticket_resolve_{ticket_id}")
    btn_assign = InlineKeyboardButton("👤 Assign", callback_data=f"ticket_assign_{ticket_id}")
    btn_escalate = InlineKeyboardButton("⬆️ Escalate", callback_data=f"ticket_escalate_{ticket_id}")
    keyboard.add(btn_resolve, btn_assign)
    keyboard.add(btn_escalate)
    return keyboard


def get_cancel_keyboard(callback_prefix="cancel"):
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn_cancel = InlineKeyboardButton("❌ Cancel", callback_data=f"{callback_prefix}")
    keyboard.add(btn_cancel)
    return keyboard


def get_pagination_keyboard(page, total_pages, prefix):
    keyboard = InlineKeyboardMarkup(row_width=3)
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}_prev_{page}"))
    buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}_next_{page}"))
    if buttons:
        keyboard.add(*buttons)
    btn_back = InlineKeyboardButton("🔙 Back", callback_data=f"{prefix}_back")
    keyboard.add(btn_back)
    return keyboard


def get_yes_no_keyboard(action, data):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_yes = InlineKeyboardButton("✅ Yes", callback_data=f"yes_{action}_{data}")
    btn_no = InlineKeyboardButton("❌ No", callback_data=f"no_{action}_{data}")
    keyboard.add(btn_yes, btn_no)
    return keyboard


def get_channel_selection_keyboard(channels, selected=None):
    keyboard = InlineKeyboardMarkup(row_width=1)
    for channel in channels:
        label = f"{'✅ ' if selected == channel else ''}Channel {channel}"
        btn = InlineKeyboardButton(label, callback_data=f"schedule_channel_{channel}")
        keyboard.add(btn)
    btn_back = InlineKeyboardButton("🔙 Back", callback_data="schedule_back")
    keyboard.add(btn_back)
    return keyboard


def get_media_intent_selection_keyboard(intents):
    keyboard = InlineKeyboardMarkup(row_width=2)
    for intent in intents:
        btn = InlineKeyboardButton(intent, callback_data=f"media_intent_{intent}")
        keyboard.add(btn)
    btn_back = InlineKeyboardButton("🔙 Back", callback_data="media_back")
    keyboard.add(btn_back)
    return keyboard


def get_followup_action_keyboard(followup_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_edit = InlineKeyboardButton("✏️ Edit", callback_data=f"followup_edit_{followup_id}")
    btn_toggle = InlineKeyboardButton("🔄 Toggle", callback_data=f"followup_toggle_{followup_id}")
    btn_delete = InlineKeyboardButton("🗑️ Delete", callback_data=f"followup_delete_{followup_id}")
    keyboard.add(btn_edit, btn_toggle)
    keyboard.add(btn_delete)
    return keyboard
