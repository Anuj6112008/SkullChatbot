-- ============================================================
-- SKULL TRADER BOT — FULL DATABASE SETUP
-- Run this ENTIRE script in Supabase SQL Editor (Dashboard > SQL Editor > New query)
-- It is safe to re-run (uses IF NOT EXISTS / OR REPLACE).
-- ============================================================

-- ----------------------------------------------------------
-- 1. Create the execute_sql() RPC function so that the bot's
--    setup_database.py (and any future db.execute() calls) work.
-- ----------------------------------------------------------
CREATE OR REPLACE FUNCTION public.execute_sql(query text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result json;
BEGIN
    EXECUTE query;
    result := json_build_object('success', true);
    RETURN result;
EXCEPTION WHEN OTHERS THEN
    result := json_build_object('success', false, 'error', SQLERRM);
    RETURN result;
END;
$$;

-- ----------------------------------------------------------
-- 2. Tables
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active',
    member_type VARCHAR(50) DEFAULT 'normal',
    registration_status VARCHAR(50) DEFAULT 'not_started',
    verification_status VARCHAR(50) DEFAULT 'pending',
    paid_user BOOLEAN DEFAULT FALSE,
    course_access BOOLEAN DEFAULT FALSE,
    updates_access BOOLEAN DEFAULT FALSE,
    opt_out BOOLEAN DEFAULT FALSE,
    blocked BOOLEAN DEFAULT FALSE,
    followup_stage INTEGER DEFAULT 0,
    onboarding_state VARCHAR(100),
    onboarding_data JSONB DEFAULT '{}'::jsonb,
    last_followup_at TIMESTAMP WITH TIME ZONE,
    hot_lead_active BOOLEAN DEFAULT FALSE,
    hot_lead_day1_sent_count INTEGER DEFAULT 0,
    hot_lead_day1_last_sent_at TIMESTAMP WITH TIME ZONE,
    hot_lead_day2_sent_count INTEGER DEFAULT 0,
    hot_lead_day2_last_sent_date DATE,
    hot_lead_first_seen_date DATE,
    registration_nudge_sent BOOLEAN DEFAULT FALSE,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    registered_at TIMESTAMP WITH TIME ZONE,
    verified_at TIMESTAMP WITH TIME ZONE,
    last_activity TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS registrations (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    registration_data JSONB DEFAULT '{}'::jsonb,
    verification_status VARCHAR(50) DEFAULT 'pending',
    verified_by BIGINT,
    verified_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verification_requests (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    registration_id INTEGER,
    admin_id BIGINT,
    action VARCHAR(50),
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
    FOREIGN KEY (registration_id) REFERENCES registrations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS faq_items (
    id SERIAL PRIMARY KEY,
    intent VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(255),
    description TEXT,
    video_path VARCHAR(500),
    caption TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS media_files (
    id SERIAL PRIMARY KEY,
    intent VARCHAR(100) UNIQUE NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(50) DEFAULT 'video',
    caption TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS followups (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    message_type VARCHAR(50) DEFAULT 'promotional',
    message_content TEXT NOT NULL,
    scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
    sent BOOLEAN DEFAULT FALSE,
    sent_at TIMESTAMP WITH TIME ZONE,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scheduled_messages (
    id SERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    message_content TEXT NOT NULL,
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    sent BOOLEAN DEFAULT FALSE,
    sent_at TIMESTAMP WITH TIME ZONE,
    enabled BOOLEAN DEFAULT TRUE,
    created_by BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id SERIAL PRIMARY KEY,
    message_content TEXT NOT NULL,
    audience VARCHAR(50) NOT NULL,
    total_recipients INTEGER DEFAULT 0,
    successful INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    blocked INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'pending',
    sent_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_by BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    message TEXT NOT NULL,
    intent VARCHAR(100),
    status VARCHAR(50) DEFAULT 'open',
    assigned_to BIGINT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id SERIAL PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    action VARCHAR(255) NOT NULL,
    target_id BIGINT,
    target_type VARCHAR(50),
    details JSONB DEFAULT '{}'::jsonb,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ----------------------------------------------------------
-- 3. Add new columns to users table (if they don't exist yet)
--    This handles databases that already had the old schema.
-- ----------------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS member_type VARCHAR(50) DEFAULT 'normal';
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_state VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_data JSONB DEFAULT '{}'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_followup_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_active BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_day1_sent_count INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_day1_last_sent_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_day2_sent_count INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_day2_last_sent_date DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_first_seen_date DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS registration_nudge_sent BOOLEAN DEFAULT FALSE;

-- ----------------------------------------------------------
-- 4. Indexes
-- ----------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_verification_status ON users(verification_status);
CREATE INDEX IF NOT EXISTS idx_users_onboarding_state ON users(onboarding_state);
CREATE INDEX IF NOT EXISTS idx_users_hot_lead_active ON users(hot_lead_active);
CREATE INDEX IF NOT EXISTS idx_registrations_telegram_id ON registrations(telegram_id);
CREATE INDEX IF NOT EXISTS idx_registrations_verification_status ON registrations(verification_status);
CREATE INDEX IF NOT EXISTS idx_followups_telegram_id ON followups(telegram_id);
CREATE INDEX IF NOT EXISTS idx_followups_scheduled_for ON followups(scheduled_for);
CREATE INDEX IF NOT EXISTS idx_followups_sent ON followups(sent);
CREATE INDEX IF NOT EXISTS idx_scheduled_messages_scheduled_at ON scheduled_messages(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_messages_sent ON scheduled_messages(sent);
CREATE INDEX IF NOT EXISTS idx_broadcasts_audience ON broadcasts(audience);
CREATE INDEX IF NOT EXISTS idx_broadcasts_status ON broadcasts(status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_telegram_id ON support_tickets(telegram_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets(status);
CREATE INDEX IF NOT EXISTS idx_admin_logs_admin_id ON admin_logs(admin_id);
CREATE INDEX IF NOT EXISTS idx_admin_logs_created_at ON admin_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key);

-- ----------------------------------------------------------
-- 5. Default settings
-- ----------------------------------------------------------
INSERT INTO settings (key, value, description) VALUES
    ('welcome_text', 'Welcome to our platform!', 'Default welcome text'),
    ('welcome_video', 'welcome.mp4', 'Welcome video filename'),
    ('registration_cta_text', 'Register Now', 'Registration CTA'),
    ('approval_text', 'Your registration has been approved! You are now a VIP member.', 'Approval message'),
    ('rejection_text', 'Your registration has been rejected.', 'Rejection message'),
    ('support_text', 'Your issue has been forwarded to support.', 'Support message'),
    ('course_access_message', 'Course access granted.', 'Course access message'),
    ('updates_access_message', 'Updates channel access granted.', 'Updates access message'),
    ('followup_enabled', 'true', 'Followup system enabled'),
    ('followup_first_day_count', '4', 'Day-1 followup count'),
    ('followup_first_week_count', '7', 'First-week followup count'),
    ('followup_after_week_count', '15', 'After-week followup count'),
    ('scheduled_posts_enabled', 'true', 'Scheduled posts enabled'),
    ('daily_scheduled_posts_count', '10', 'Daily scheduled posts count'),
    ('broadcast_enabled', 'true', 'Broadcast enabled'),
    ('support_enabled', 'true', 'Support enabled'),
    ('ai_enabled', 'true', 'AI enabled'),
    ('auto_approve_join_requests', 'true', 'Auto-approve join requests')
ON CONFLICT (key) DO NOTHING;

-- ----------------------------------------------------------
-- 6. Default FAQ items
-- ----------------------------------------------------------
INSERT INTO faq_items (intent, display_name, description, enabled) VALUES
    ('REGISTRATION', 'Registration', 'How to register', TRUE),
    ('DEPOSIT', 'Deposit', 'Deposit process', TRUE),
    ('WITHDRAWAL', 'Withdrawal', 'Withdrawal process', TRUE),
    ('PAYMENT', 'Payment', 'Payment information', TRUE),
    ('COURSE', 'Course', 'Course details', TRUE),
    ('ACCESS', 'Access', 'Access issues', TRUE),
    ('LOGIN', 'Login', 'Login help', TRUE),
    ('ACCOUNT', 'Account', 'Account management', TRUE),
    ('GENERAL', 'General', 'General questions', TRUE),
    ('SUPPORT', 'Support', 'Support requests', TRUE)
ON CONFLICT (intent) DO NOTHING;

-- ----------------------------------------------------------
-- DONE. All tables, columns, indexes, settings and FAQ items
-- are now created. The execute_sql() function also exists, so
-- setup_database.py will work without 404 errors on future runs.
-- ----------------------------------------------------------
