import logging
from database import database

logger = logging.getLogger(__name__)

class DatabaseSetup:
    def __init__(self):
        self.db = database

    def run(self):
        self.create_users_table()
        self.create_registrations_table()
        self.create_verification_requests_table()
        self.create_faq_items_table()
        self.create_media_files_table()
        self.create_followups_table()
        self.create_scheduled_messages_table()
        self.create_broadcasts_table()
        self.create_support_tickets_table()
        self.create_admin_logs_table()
        self.create_settings_table()
        self.create_indexes()
        self.alter_users_table_for_flow()
        self.insert_default_settings()
        self.insert_default_faq_items()
        logger.info("Database setup completed successfully")

    def create_users_table(self):
        query = """
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
            joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            registered_at TIMESTAMP WITH TIME ZONE,
            verified_at TIMESTAMP WITH TIME ZONE,
            last_activity TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """
        self.db.execute(query)
        logger.info("Users table created or verified")

    def alter_users_table_for_flow(self):
        """Add columns needed by the new conversation flow and hot-lead system.
        These run as ALTER TABLE ... ADD COLUMN IF NOT EXISTS so they are safe
        to re-run on an existing database."""
        alters = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS member_type VARCHAR(50) DEFAULT 'normal';",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_state VARCHAR(100);",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_data JSONB DEFAULT '{}'::jsonb;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_followup_at TIMESTAMP WITH TIME ZONE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_active BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_day1_sent_count INTEGER DEFAULT 0;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_day1_last_sent_at TIMESTAMP WITH TIME ZONE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_day2_sent_count INTEGER DEFAULT 0;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_day2_last_sent_date DATE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS hot_lead_first_seen_date DATE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS registration_nudge_sent BOOLEAN DEFAULT FALSE;",
        ]
        for stmt in alters:
            try:
                self.db.execute(stmt)
            except Exception as e:
                logger.warning(f"Alter users warning: {e}")
        logger.info("Users table altered for new flow columns")

    def create_registrations_table(self):
        query = """
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
        """
        self.db.execute(query)
        logger.info("Registrations table created or verified")

    def create_verification_requests_table(self):
        query = """
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
        """
        self.db.execute(query)
        logger.info("Verification requests table created or verified")

    def create_faq_items_table(self):
        query = """
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
        """
        self.db.execute(query)
        logger.info("FAQ items table created or verified")

    def create_media_files_table(self):
        query = """
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
        """
        self.db.execute(query)
        logger.info("Media files table created or verified")

    def create_followups_table(self):
        query = """
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
        """
        self.db.execute(query)
        logger.info("Followups table created or verified")

    def create_scheduled_messages_table(self):
        query = """
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
        """
        self.db.execute(query)
        logger.info("Scheduled messages table created or verified")

    def create_broadcasts_table(self):
        query = """
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
        """
        self.db.execute(query)
        logger.info("Broadcasts table created or verified")

    def create_support_tickets_table(self):
        query = """
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
        """
        self.db.execute(query)
        logger.info("Support tickets table created or verified")

    def create_admin_logs_table(self):
        query = """
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
        """
        self.db.execute(query)
        logger.info("Admin logs table created or verified")

    def create_settings_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS settings (
            id SERIAL PRIMARY KEY,
            key VARCHAR(100) UNIQUE NOT NULL,
            value TEXT,
            description TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """
        self.db.execute(query)
        logger.info("Settings table created or verified")

    def create_indexes(self):
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);",
            "CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);",
            "CREATE INDEX IF NOT EXISTS idx_users_verification_status ON users(verification_status);",
            "CREATE INDEX IF NOT EXISTS idx_users_onboarding_state ON users(onboarding_state);",
            "CREATE INDEX IF NOT EXISTS idx_users_hot_lead_active ON users(hot_lead_active);",
            "CREATE INDEX IF NOT EXISTS idx_registrations_telegram_id ON registrations(telegram_id);",
            "CREATE INDEX IF NOT EXISTS idx_registrations_verification_status ON registrations(verification_status);",
            "CREATE INDEX IF NOT EXISTS idx_followups_telegram_id ON followups(telegram_id);",
            "CREATE INDEX IF NOT EXISTS idx_followups_scheduled_for ON followups(scheduled_for);",
            "CREATE INDEX IF NOT EXISTS idx_followups_sent ON followups(sent);",
            "CREATE INDEX IF NOT EXISTS idx_scheduled_messages_scheduled_at ON scheduled_messages(scheduled_at);",
            "CREATE INDEX IF NOT EXISTS idx_scheduled_messages_sent ON scheduled_messages(sent);",
            "CREATE INDEX IF NOT EXISTS idx_broadcasts_audience ON broadcasts(audience);",
            "CREATE INDEX IF NOT EXISTS idx_broadcasts_status ON broadcasts(status);",
            "CREATE INDEX IF NOT EXISTS idx_support_tickets_telegram_id ON support_tickets(telegram_id);",
            "CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets(status);",
            "CREATE INDEX IF NOT EXISTS idx_admin_logs_admin_id ON admin_logs(admin_id);",
            "CREATE INDEX IF NOT EXISTS idx_admin_logs_created_at ON admin_logs(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key);"
        ]
        for index in indexes:
            try:
                self.db.execute(index)
            except Exception as e:
                logger.warning(f"Index creation warning: {e}")
        logger.info("Indexes created or verified")

    def insert_default_settings(self):
        defaults = {
            "welcome_text": "Welcome to our platform!",
            "welcome_video": "welcome.mp4",
            "registration_cta_text": "Register Now",
            "approval_text": "Your registration has been approved! You are now a VIP member.",
            "rejection_text": "Your registration has been rejected.",
            "support_text": "Your issue has been forwarded to support.",
            "course_access_message": "Course access granted.",
            "updates_access_message": "Updates channel access granted.",
            "followup_enabled": "true",
            "followup_first_day_count": "4",
            "followup_first_week_count": "7",
            "followup_after_week_count": "15",
            "scheduled_posts_enabled": "true",
            "daily_scheduled_posts_count": "10",
            "broadcast_enabled": "true",
            "support_enabled": "true",
            "ai_enabled": "true",
            "auto_approve_join_requests": "true"
        }
        for key, value in defaults.items():
            try:
                existing = self.db.get_setting(key)
                if not existing:
                    self.db.set_setting(key, value)
            except Exception as e:
                logger.warning(f"Failed to insert setting {key}: {e}")
        logger.info("Default settings inserted")

    def insert_default_faq_items(self):
        defaults = [
            {"intent": "REGISTRATION", "display_name": "Registration", "description": "How to register"},
            {"intent": "DEPOSIT", "display_name": "Deposit", "description": "Deposit process"},
            {"intent": "WITHDRAWAL", "display_name": "Withdrawal", "description": "Withdrawal process"},
            {"intent": "PAYMENT", "display_name": "Payment", "description": "Payment information"},
            {"intent": "COURSE", "display_name": "Course", "description": "Course details"},
            {"intent": "ACCESS", "display_name": "Access", "description": "Access issues"},
            {"intent": "LOGIN", "display_name": "Login", "description": "Login help"},
            {"intent": "ACCOUNT", "display_name": "Account", "description": "Account management"},
            {"intent": "GENERAL", "display_name": "General", "description": "General questions"},
            {"intent": "SUPPORT", "display_name": "Support", "description": "Support requests"}
        ]
        for item in defaults:
            try:
                existing = self.db.get_faq_item(item["intent"])
                if not existing:
                    self.db.create_faq_item(item)
            except Exception as e:
                logger.warning(f"Failed to insert FAQ item {item['intent']}: {e}")
        logger.info("Default FAQ items inserted")

def main():
    logging.basicConfig(level=logging.INFO)
    setup = DatabaseSetup()
    try:
        setup.run()
        logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

if __name__ == "__main__":
    main()
