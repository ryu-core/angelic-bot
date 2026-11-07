# MySQL Database Handler for Bot Settings & Persistent Data
# Replaces JSON file-based database.py to survive restarts
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()


def _env(name, default=None):
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


# MySQL Configuration (same as economy_db / mysql_logs)
MYSQL_CONFIG = {
    'host': _env('MYSQL_HOST'),
    'port': int(_env('MYSQL_PORT', 3306)),
    'user': _env('MYSQL_USER'),
    'password': _env('MYSQL_PASSWORD'),
    'database': _env('MYSQL_DATABASE')
}


class MySQLSettingsDB:
    """MySQL-backed key-value store that replaces the JSON Database class.
    
    Provides the same API: get, set, delete, has, all
    Each 'namespace' (warnings, jail, config, etc.) maps to a separate table.
    """

    def __init__(self):
        self.connection = None
        self.cursor = None
        self._init_tables()

    def _connect(self):
        try:
            if not self.connection or not self.connection.is_connected():
                self.connection = mysql.connector.connect(**MYSQL_CONFIG)
                self.cursor = self.connection.cursor(dictionary=True)
            return True
        except Error as e:
            print(f"MySQL Settings Connection Error: {e}")
            return False

    def _disconnect(self):
        try:
            if self.cursor:
                self.cursor.close()
            if self.connection and self.connection.is_connected():
                self.connection.close()
        except:
            pass
        self.connection = None
        self.cursor = None

    def _init_tables(self):
        """Create all settings tables."""
        if not self._connect():
            print("WARNING: Could not connect to MySQL for settings.")
            return
        try:
            # Generic key-value settings table (for config, logs, blacklist, sticky, timezone)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    namespace VARCHAR(50) NOT NULL,
                    guild_id VARCHAR(20) NOT NULL DEFAULT '0',
                    setting_key VARCHAR(255) NOT NULL,
                    setting_value LONGTEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_setting (namespace, guild_id, setting_key),
                    INDEX idx_namespace (namespace),
                    INDEX idx_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Warnings table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_warnings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    user_id VARCHAR(20) NOT NULL,
                    reason TEXT NOT NULL,
                    moderator_id VARCHAR(20) NOT NULL,
                    moderator_name VARCHAR(255),
                    created_at BIGINT NOT NULL,
                    INDEX idx_guild_user (guild_id, user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Jail table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_jail (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    user_id VARCHAR(20) NOT NULL,
                    stored_roles JSON,
                    reason TEXT,
                    moderator_id VARCHAR(20),
                    jailed_at BIGINT NOT NULL,
                    duration_seconds INT DEFAULT NULL,
                    duration_text VARCHAR(50) DEFAULT 'Permanent',
                    UNIQUE KEY unique_jail (guild_id, user_id),
                    INDEX idx_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Modstats table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_modstats (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    moderator_id VARCHAR(20) NOT NULL,
                    warns INT DEFAULT 0,
                    kicks INT DEFAULT 0,
                    bans INT DEFAULT 0,
                    jails INT DEFAULT 0,
                    mutes INT DEFAULT 0,
                    UNIQUE KEY unique_modstat (guild_id, moderator_id),
                    INDEX idx_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Catch cards table (no avatar_url — fetched live from Discord to save storage)
            # Max collection size enforced in save_catch() to keep DB under 60GB
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS catch_cards (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    owner_id VARCHAR(20) NOT NULL,
                    caught_user_id VARCHAR(20) NOT NULL,
                    caught_username VARCHAR(100),
                    caught_display_name VARCHAR(100),
                    rarity VARCHAR(20) DEFAULT 'Common',
                    catch_type VARCHAR(20) DEFAULT 'Normal',
                    hp SMALLINT DEFAULT 100,
                    attack SMALLINT DEFAULT 50,
                    defense SMALLINT DEFAULT 50,
                    speed SMALLINT DEFAULT 50,
                    level SMALLINT DEFAULT 1,
                    exp INT DEFAULT 0,
                    caught_at BIGINT NOT NULL,
                    INDEX idx_owner (owner_id),
                    UNIQUE KEY unique_catch (owner_id, caught_user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Battle teams table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS battle_teams (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    owner_id VARCHAR(20) NOT NULL,
                    slot1_user_id VARCHAR(20),
                    slot2_user_id VARCHAR(20),
                    slot3_user_id VARCHAR(20),
                    UNIQUE KEY unique_team (owner_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Reminders table (for new remind command)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_reminders (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(20) NOT NULL,
                    channel_id VARCHAR(20) NOT NULL,
                    guild_id VARCHAR(20) NOT NULL,
                    message TEXT NOT NULL,
                    remind_at BIGINT NOT NULL,
                    created_at BIGINT NOT NULL,
                    INDEX idx_remind_at (remind_at),
                    INDEX idx_user (user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Aliases table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_aliases (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    alias_name VARCHAR(100) NOT NULL,
                    command_string VARCHAR(500) NOT NULL,
                    created_by VARCHAR(20),
                    UNIQUE KEY unique_alias (guild_id, alias_name),
                    INDEX idx_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Goodbye/Boost messages table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_system_messages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    message_type ENUM('goodbye', 'boost') NOT NULL,
                    channel_id VARCHAR(20) NOT NULL,
                    message_template TEXT NOT NULL,
                    image_url TEXT DEFAULT NULL,
                    self_destruct_seconds INT DEFAULT NULL,
                    UNIQUE KEY unique_msg (guild_id, message_type, channel_id),
                    INDEX idx_guild_type (guild_id, message_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            self.cursor.execute("SHOW COLUMNS FROM bot_system_messages LIKE 'image_url'")
            if not self.cursor.fetchone():
                self.cursor.execute("""
                    ALTER TABLE bot_system_messages
                    ADD COLUMN image_url TEXT DEFAULT NULL AFTER message_template
                """)

            # Per-booster custom roles
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_booster_roles (
                    guild_id VARCHAR(20) NOT NULL,
                    user_id VARCHAR(20) NOT NULL,
                    role_id VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id),
                    UNIQUE KEY unique_booster_role (guild_id, role_id),
                    INDEX idx_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Therapy session configuration and active session tracking
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_therapy_config (
                    guild_id VARCHAR(20) PRIMARY KEY,
                    panel_channel_id VARCHAR(20) DEFAULT NULL,
                    category_id VARCHAR(20) DEFAULT NULL,
                    therapist_role_id VARCHAR(20) DEFAULT NULL,
                    recommend_role_id VARCHAR(20) DEFAULT NULL,
                    log_channel_id VARCHAR(20) DEFAULT NULL,
                    panel_message_id VARCHAR(20) DEFAULT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            self.cursor.execute("SHOW COLUMNS FROM bot_therapy_config LIKE 'recommend_role_id'")
            if not self.cursor.fetchone():
                self.cursor.execute("""
                    ALTER TABLE bot_therapy_config
                    ADD COLUMN recommend_role_id VARCHAR(20) DEFAULT NULL AFTER therapist_role_id
                """)

            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_therapy_therapists (
                    guild_id VARCHAR(20) NOT NULL,
                    user_id VARCHAR(20) NOT NULL,
                    added_by VARCHAR(20),
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id),
                    INDEX idx_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_therapy_sessions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    requester_id VARCHAR(20) NOT NULL,
                    therapist_id VARCHAR(20) NOT NULL,
                    channel_id VARCHAR(20) NOT NULL,
                    status ENUM('open', 'closed') NOT NULL DEFAULT 'open',
                    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP NULL DEFAULT NULL,
                    closed_by VARCHAR(20) DEFAULT NULL,
                    close_reason TEXT,
                    INDEX idx_guild_status (guild_id, status),
                    INDEX idx_requester_status (guild_id, requester_id, status),
                    INDEX idx_channel (guild_id, channel_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Antinuke config table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_antinuke (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    enabled BOOLEAN DEFAULT FALSE,
                    ban_threshold INT DEFAULT 3,
                    kick_threshold INT DEFAULT 3,
                    channel_threshold INT DEFAULT 3,
                    role_threshold INT DEFAULT 3,
                    punishment VARCHAR(20) DEFAULT 'ban',
                    UNIQUE KEY unique_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Antinuke whitelist
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_antinuke_whitelist (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    user_id VARCHAR(20) NOT NULL,
                    role VARCHAR(20) DEFAULT 'whitelisted',
                    UNIQUE KEY unique_entry (guild_id, user_id),
                    INDEX idx_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Auto-react config
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_autoreact (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    channel_id VARCHAR(20) NOT NULL,
                    emoji VARCHAR(100) NOT NULL,
                    UNIQUE KEY unique_react (guild_id, channel_id, emoji),
                    INDEX idx_guild_channel (guild_id, channel_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Counter channels
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_counters (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    channel_id VARCHAR(20) NOT NULL,
                    counter_type VARCHAR(50) NOT NULL,
                    name_template VARCHAR(255) DEFAULT '{count}',
                    UNIQUE KEY unique_counter (guild_id, counter_type),
                    INDEX idx_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Join DM config
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_joindm (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    message_template TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    UNIQUE KEY unique_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Persistent stats table (replaces data/persistent_stats.json)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS persistent_stats (
                    key_name VARCHAR(100) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Ticket sorting rules
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_ticket_sort (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    keyword VARCHAR(100) NOT NULL,
                    category_id VARCHAR(20) NOT NULL,
                    match_mode VARCHAR(10) DEFAULT 'startswith',
                    UNIQUE KEY unique_rule (guild_id, keyword),
                    INDEX idx_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            self.connection.commit()
            print("✓ MySQL settings tables initialized")

        except Error as e:
            print(f"Error initializing settings tables: {e}")
        finally:
            self._disconnect()

    # ─── Generic Key-Value API (replaces Database class) ───

    def get_setting(self, namespace, guild_id, key, default=None):
        """Get a setting value."""
        if not self._connect():
            return default
        try:
            self.cursor.execute(
                "SELECT setting_value FROM bot_settings WHERE namespace=%s AND guild_id=%s AND setting_key=%s",
                (namespace, str(guild_id), key)
            )
            row = self.cursor.fetchone()
            if row and row['setting_value'] is not None:
                try:
                    return json.loads(row['setting_value'])
                except (json.JSONDecodeError, TypeError):
                    return row['setting_value']
            return default
        except Error as e:
            print(f"Error getting setting: {e}")
            return default
        finally:
            self._disconnect()

    def set_setting(self, namespace, guild_id, key, value):
        """Set a setting value."""
        if not self._connect():
            return
        try:
            val_str = json.dumps(value) if not isinstance(value, str) else value
            self.cursor.execute("""
                INSERT INTO bot_settings (namespace, guild_id, setting_key, setting_value)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
            """, (namespace, str(guild_id), key, val_str))
            self.connection.commit()
        except Error as e:
            print(f"Error setting value: {e}")
        finally:
            self._disconnect()

    def delete_setting(self, namespace, guild_id, key):
        """Delete a setting."""
        if not self._connect():
            return
        try:
            self.cursor.execute(
                "DELETE FROM bot_settings WHERE namespace=%s AND guild_id=%s AND setting_key=%s",
                (namespace, str(guild_id), key)
            )
            self.connection.commit()
        except Error as e:
            print(f"Error deleting setting: {e}")
        finally:
            self._disconnect()

    def has_setting(self, namespace, guild_id, key):
        """Check if setting exists."""
        if not self._connect():
            return False
        try:
            self.cursor.execute(
                "SELECT 1 FROM bot_settings WHERE namespace=%s AND guild_id=%s AND setting_key=%s",
                (namespace, str(guild_id), key)
            )
            return self.cursor.fetchone() is not None
        except Error:
            return False
        finally:
            self._disconnect()

    def get_all_settings(self, namespace, guild_id):
        """Get all settings for a namespace+guild."""
        if not self._connect():
            return {}
        try:
            self.cursor.execute(
                "SELECT setting_key, setting_value FROM bot_settings WHERE namespace=%s AND guild_id=%s",
                (namespace, str(guild_id))
            )
            result = {}
            for row in self.cursor.fetchall():
                try:
                    result[row['setting_key']] = json.loads(row['setting_value'])
                except (json.JSONDecodeError, TypeError):
                    result[row['setting_key']] = row['setting_value']
            return result
        except Error as e:
            print(f"Error getting all settings: {e}")
            return {}
        finally:
            self._disconnect()

    # ─── Warnings API ───

    def add_warning(self, guild_id, user_id, reason, moderator_id, moderator_name):
        """Add a warning."""
        if not self._connect():
            return 0
        try:
            import time
            self.cursor.execute("""
                INSERT INTO bot_warnings (guild_id, user_id, reason, moderator_id, moderator_name, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (str(guild_id), str(user_id), reason, str(moderator_id), moderator_name, int(time.time())))
            self.connection.commit()
            # Return total warnings for this user
            self.cursor.execute(
                "SELECT COUNT(*) as cnt FROM bot_warnings WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            row = self.cursor.fetchone()
            return row['cnt'] if row else 1
        except Error as e:
            print(f"Error adding warning: {e}")
            return 0
        finally:
            self._disconnect()

    def get_warnings(self, guild_id, user_id):
        """Get all warnings for a user in a guild."""
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT * FROM bot_warnings WHERE guild_id=%s AND user_id=%s ORDER BY created_at DESC",
                (str(guild_id), str(user_id))
            )
            return self.cursor.fetchall()
        except Error as e:
            print(f"Error getting warnings: {e}")
            return []
        finally:
            self._disconnect()

    def get_all_warnings_count(self, guild_id):
        """Get total warning count for a guild."""
        if not self._connect():
            return 0
        try:
            self.cursor.execute(
                "SELECT COUNT(*) as cnt FROM bot_warnings WHERE guild_id=%s",
                (str(guild_id),)
            )
            row = self.cursor.fetchone()
            return row['cnt'] if row else 0
        except Error as e:
            return 0
        finally:
            self._disconnect()

    def clear_warnings(self, guild_id, user_id):
        """Clear all warnings for a user."""
        if not self._connect():
            return
        try:
            self.cursor.execute(
                "DELETE FROM bot_warnings WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            self.connection.commit()
        except Error as e:
            print(f"Error clearing warnings: {e}")
        finally:
            self._disconnect()

    # ─── Jail API ───

    def jail_user(self, guild_id, user_id, role_ids, reason, moderator_id, duration_seconds=None, duration_text="Permanent"):
        """Jail a user (store roles, reason, etc.)."""
        if not self._connect():
            return
        try:
            import time
            self.cursor.execute("""
                INSERT INTO bot_jail (guild_id, user_id, stored_roles, reason, moderator_id, jailed_at, duration_seconds, duration_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE stored_roles=VALUES(stored_roles), reason=VALUES(reason),
                    moderator_id=VALUES(moderator_id), jailed_at=VALUES(jailed_at),
                    duration_seconds=VALUES(duration_seconds), duration_text=VALUES(duration_text)
            """, (str(guild_id), str(user_id), json.dumps(role_ids), reason,
                  str(moderator_id), int(time.time()), duration_seconds, duration_text))
            self.connection.commit()
        except Error as e:
            print(f"Error jailing user: {e}")
        finally:
            self._disconnect()

    def unjail_user(self, guild_id, user_id):
        """Remove jail record, return stored role IDs."""
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT stored_roles FROM bot_jail WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            row = self.cursor.fetchone()
            role_ids = json.loads(row['stored_roles']) if row and row['stored_roles'] else []
            self.cursor.execute(
                "DELETE FROM bot_jail WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            self.connection.commit()
            return role_ids
        except Error as e:
            print(f"Error unjailing user: {e}")
            return []
        finally:
            self._disconnect()

    def is_jailed(self, guild_id, user_id):
        """Check if a user is jailed."""
        if not self._connect():
            return False
        try:
            self.cursor.execute(
                "SELECT 1 FROM bot_jail WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            return self.cursor.fetchone() is not None
        except Error:
            return False
        finally:
            self._disconnect()

    def get_jail_data(self, guild_id, user_id):
        """Get jail data for a user."""
        if not self._connect():
            return None
        try:
            self.cursor.execute(
                "SELECT * FROM bot_jail WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            row = self.cursor.fetchone()
            if row and row.get('stored_roles'):
                row['stored_roles'] = json.loads(row['stored_roles'])
            return row
        except Error:
            return None
        finally:
            self._disconnect()

    def get_all_jailed(self, guild_id):
        """Get all jailed users in a guild."""
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT * FROM bot_jail WHERE guild_id=%s",
                (str(guild_id),)
            )
            rows = self.cursor.fetchall()
            for row in rows:
                if row.get('stored_roles'):
                    row['stored_roles'] = json.loads(row['stored_roles'])
            return rows
        except Error:
            return []
        finally:
            self._disconnect()

    # ─── Modstats API ───

    def increment_modstat(self, guild_id, moderator_id, action_type):
        """Increment a moderation stat counter."""
        if not self._connect():
            return
        try:
            self.cursor.execute(f"""
                INSERT INTO bot_modstats (guild_id, moderator_id, {action_type})
                VALUES (%s, %s, 1)
                ON DUPLICATE KEY UPDATE {action_type} = {action_type} + 1
            """, (str(guild_id), str(moderator_id)))
            self.connection.commit()
        except Error as e:
            print(f"Error incrementing modstat: {e}")
        finally:
            self._disconnect()

    def get_modstats(self, guild_id, moderator_id=None):
        """Get moderation stats."""
        if not self._connect():
            return {} if moderator_id else []
        try:
            if moderator_id:
                self.cursor.execute(
                    "SELECT * FROM bot_modstats WHERE guild_id=%s AND moderator_id=%s",
                    (str(guild_id), str(moderator_id))
                )
                return self.cursor.fetchone() or {'warns': 0, 'kicks': 0, 'bans': 0, 'jails': 0, 'mutes': 0}
            else:
                self.cursor.execute(
                    "SELECT * FROM bot_modstats WHERE guild_id=%s",
                    (str(guild_id),)
                )
                return self.cursor.fetchall()
        except Error:
            return {} if moderator_id else []
        finally:
            self._disconnect()

    def get_guild_modstats_totals(self, guild_id):
        """Get server-wide totals."""
        if not self._connect():
            return {'warns': 0, 'kicks': 0, 'bans': 0, 'jails': 0, 'mutes': 0}
        try:
            self.cursor.execute("""
                SELECT COALESCE(SUM(warns),0) as warns, COALESCE(SUM(kicks),0) as kicks,
                       COALESCE(SUM(bans),0) as bans, COALESCE(SUM(jails),0) as jails,
                       COALESCE(SUM(mutes),0) as mutes
                FROM bot_modstats WHERE guild_id=%s
            """, (str(guild_id),))
            row = self.cursor.fetchone()
            return row if row else {'warns': 0, 'kicks': 0, 'bans': 0, 'jails': 0, 'mutes': 0}
        except Error:
            return {'warns': 0, 'kicks': 0, 'bans': 0, 'jails': 0, 'mutes': 0}
        finally:
            self._disconnect()

    # ─── Catch Cards API ───

    def save_catch(self, owner_id, caught_user_id, username, display_name, rarity, catch_type, stats, avatar_url=None):
        """Save a caught user card. Max 500 per owner to conserve storage."""
        if not self._connect():
            return False
        try:
            import time
            # Enforce 500-card collection cap
            self.cursor.execute(
                "SELECT COUNT(*) as cnt FROM catch_cards WHERE owner_id=%s",
                (str(owner_id),)
            )
            row = self.cursor.fetchone()
            if row and row['cnt'] >= 500:
                return False  # Collection full

            self.cursor.execute("""
                INSERT INTO catch_cards (owner_id, caught_user_id, caught_username, caught_display_name,
                    rarity, catch_type, hp, attack, defense, speed, level, exp, caught_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE caught_username=VALUES(caught_username),
                    caught_display_name=VALUES(caught_display_name)
            """, (str(owner_id), str(caught_user_id), username, display_name,
                  rarity, catch_type,
                  stats.get('hp', 100), stats.get('attack', 50), stats.get('defense', 50),
                  stats.get('speed', 50), stats.get('level', 1), stats.get('exp', 0),
                  int(time.time())))
            self.connection.commit()
            return True
        except Error as e:
            print(f"Error saving catch: {e}")
            return False
        finally:
            self._disconnect()

    def get_collection(self, owner_id):
        """Get all caught users for an owner."""
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT * FROM catch_cards WHERE owner_id=%s ORDER BY caught_at DESC",
                (str(owner_id),)
            )
            return self.cursor.fetchall()
        except Error:
            return []
        finally:
            self._disconnect()

    def get_catch(self, owner_id, caught_user_id):
        """Get a specific caught user."""
        if not self._connect():
            return None
        try:
            self.cursor.execute(
                "SELECT * FROM catch_cards WHERE owner_id=%s AND caught_user_id=%s",
                (str(owner_id), str(caught_user_id))
            )
            return self.cursor.fetchone()
        except Error:
            return None
        finally:
            self._disconnect()

    def remove_catch(self, owner_id, caught_user_id):
        """Remove a caught user from collection."""
        if not self._connect():
            return False
        try:
            self.cursor.execute(
                "DELETE FROM catch_cards WHERE owner_id=%s AND caught_user_id=%s",
                (str(owner_id), str(caught_user_id))
            )
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Error:
            return False
        finally:
            self._disconnect()

    def transfer_catch(self, from_owner_id, to_owner_id, caught_user_id):
        """Transfer a catch from one owner to another."""
        if not self._connect():
            return False
        try:
            self.cursor.execute(
                "UPDATE catch_cards SET owner_id=%s WHERE owner_id=%s AND caught_user_id=%s",
                (str(to_owner_id), str(from_owner_id), str(caught_user_id))
            )
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Error:
            return False
        finally:
            self._disconnect()

    def update_catch_stats(self, owner_id, caught_user_id, **kwargs):
        """Update caught user stats (hp, attack, defense, speed, level, exp)."""
        if not self._connect():
            return
        try:
            set_parts = []
            values = []
            for key, val in kwargs.items():
                if key in ('hp', 'attack', 'defense', 'speed', 'level', 'exp'):
                    set_parts.append(f"{key}=%s")
                    values.append(val)
            if not set_parts:
                return
            values.extend([str(owner_id), str(caught_user_id)])
            self.cursor.execute(
                f"UPDATE catch_cards SET {', '.join(set_parts)} WHERE owner_id=%s AND caught_user_id=%s",
                values
            )
            self.connection.commit()
        except Error as e:
            print(f"Error updating catch stats: {e}")
        finally:
            self._disconnect()

    # ─── Battle Teams API ───

    def save_team(self, owner_id, slot1, slot2, slot3):
        """Save battle team."""
        if not self._connect():
            return
        try:
            self.cursor.execute("""
                INSERT INTO battle_teams (owner_id, slot1_user_id, slot2_user_id, slot3_user_id)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE slot1_user_id=VALUES(slot1_user_id),
                    slot2_user_id=VALUES(slot2_user_id), slot3_user_id=VALUES(slot3_user_id)
            """, (str(owner_id), str(slot1), str(slot2), str(slot3)))
            self.connection.commit()
        except Error as e:
            print(f"Error saving team: {e}")
        finally:
            self._disconnect()

    def get_team(self, owner_id):
        """Get battle team."""
        if not self._connect():
            return None
        try:
            self.cursor.execute(
                "SELECT * FROM battle_teams WHERE owner_id=%s",
                (str(owner_id),)
            )
            return self.cursor.fetchone()
        except Error:
            return None
        finally:
            self._disconnect()

    # ─── Reminders API ───

    def add_reminder(self, user_id, channel_id, guild_id, message, remind_at):
        """Add a reminder."""
        if not self._connect():
            return None
        try:
            import time
            self.cursor.execute("""
                INSERT INTO bot_reminders (user_id, channel_id, guild_id, message, remind_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (str(user_id), str(channel_id), str(guild_id), message, remind_at, int(time.time())))
            self.connection.commit()
            return self.cursor.lastrowid
        except Error as e:
            print(f"Error adding reminder: {e}")
            return None
        finally:
            self._disconnect()

    def get_due_reminders(self):
        """Get all reminders that are due."""
        if not self._connect():
            return []
        try:
            import time
            self.cursor.execute(
                "SELECT * FROM bot_reminders WHERE remind_at <= %s",
                (int(time.time()),)
            )
            return self.cursor.fetchall()
        except Error:
            return []
        finally:
            self._disconnect()

    def delete_reminder(self, reminder_id):
        """Delete a reminder."""
        if not self._connect():
            return
        try:
            self.cursor.execute("DELETE FROM bot_reminders WHERE id=%s", (reminder_id,))
            self.connection.commit()
        except Error:
            pass
        finally:
            self._disconnect()

    # ─── Aliases API ───

    def add_alias(self, guild_id, alias_name, command_string, created_by):
        if not self._connect():
            return False
        try:
            self.cursor.execute("""
                INSERT INTO bot_aliases (guild_id, alias_name, command_string, created_by)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE command_string=VALUES(command_string)
            """, (str(guild_id), alias_name.lower(), command_string, str(created_by)))
            self.connection.commit()
            return True
        except Error:
            return False
        finally:
            self._disconnect()

    def remove_alias(self, guild_id, alias_name):
        if not self._connect():
            return False
        try:
            self.cursor.execute(
                "DELETE FROM bot_aliases WHERE guild_id=%s AND alias_name=%s",
                (str(guild_id), alias_name.lower())
            )
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Error:
            return False
        finally:
            self._disconnect()

    def get_alias(self, guild_id, alias_name):
        if not self._connect():
            return None
        try:
            self.cursor.execute(
                "SELECT command_string FROM bot_aliases WHERE guild_id=%s AND alias_name=%s",
                (str(guild_id), alias_name.lower())
            )
            row = self.cursor.fetchone()
            return row['command_string'] if row else None
        except Error:
            return None
        finally:
            self._disconnect()

    def get_all_aliases(self, guild_id):
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT * FROM bot_aliases WHERE guild_id=%s ORDER BY alias_name",
                (str(guild_id),)
            )
            return self.cursor.fetchall()
        except Error:
            return []
        finally:
            self._disconnect()

    # ─── System Messages (goodbye/boost) API ───

    def add_system_message(self, guild_id, msg_type, channel_id, template, self_destruct=None, image_url=None):
        if not self._connect():
            return False
        try:
            self.cursor.execute("""
                INSERT INTO bot_system_messages (guild_id, message_type, channel_id, message_template, image_url, self_destruct_seconds)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    message_template=VALUES(message_template),
                    image_url=VALUES(image_url),
                    self_destruct_seconds=VALUES(self_destruct_seconds)
            """, (str(guild_id), msg_type, str(channel_id), template, image_url, self_destruct))
            self.connection.commit()
            return True
        except Error:
            return False
        finally:
            self._disconnect()

    def remove_system_message(self, guild_id, msg_type, channel_id):
        if not self._connect():
            return False
        try:
            self.cursor.execute(
                "DELETE FROM bot_system_messages WHERE guild_id=%s AND message_type=%s AND channel_id=%s",
                (str(guild_id), msg_type, str(channel_id))
            )
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Error:
            return False
        finally:
            self._disconnect()

    def get_system_messages(self, guild_id, msg_type):
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT * FROM bot_system_messages WHERE guild_id=%s AND message_type=%s",
                (str(guild_id), msg_type)
            )
            return self.cursor.fetchall()
        except Error:
            return []
        finally:
            self._disconnect()

    def clear_system_messages(self, guild_id, msg_type):
        if not self._connect():
            return 0
        try:
            self.cursor.execute(
                "DELETE FROM bot_system_messages WHERE guild_id=%s AND message_type=%s",
                (str(guild_id), msg_type)
            )
            self.connection.commit()
            return self.cursor.rowcount
        except Error:
            return 0
        finally:
            self._disconnect()

    # ─── Booster Role API ───

    def set_booster_role(self, guild_id, user_id, role_id):
        if not self._connect():
            return False
        try:
            self.cursor.execute("""
                INSERT INTO bot_booster_roles (guild_id, user_id, role_id)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE role_id=VALUES(role_id)
            """, (str(guild_id), str(user_id), str(role_id)))
            self.connection.commit()
            return True
        except Error as e:
            print(f"Booster role save error: {e}")
            return False
        finally:
            self._disconnect()

    def get_booster_role(self, guild_id, user_id):
        if not self._connect():
            return None
        try:
            self.cursor.execute(
                "SELECT * FROM bot_booster_roles WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            return self.cursor.fetchone()
        except Error:
            return None
        finally:
            self._disconnect()

    def get_all_booster_roles(self, guild_id):
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT * FROM bot_booster_roles WHERE guild_id=%s",
                (str(guild_id),)
            )
            return self.cursor.fetchall()
        except Error:
            return []
        finally:
            self._disconnect()

    def remove_booster_role(self, guild_id, user_id):
        if not self._connect():
            return False
        try:
            self.cursor.execute(
                "DELETE FROM bot_booster_roles WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Error:
            return False
        finally:
            self._disconnect()

    def transfer_therapy_session(self, guild_id, channel_id, therapist_id):
        if not self._connect():
            return False
        try:
            self.cursor.execute("""
                UPDATE bot_therapy_sessions
                SET therapist_id=%s
                WHERE guild_id=%s AND channel_id=%s AND status='open'
            """, (
                str(therapist_id),
                str(guild_id),
                str(channel_id),
            ))
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Error:
            return False
        finally:
            self._disconnect()

    # ─── Therapy Session API ───

    def get_therapy_config(self, guild_id):
        if not self._connect():
            return None
        try:
            self.cursor.execute(
                "SELECT * FROM bot_therapy_config WHERE guild_id=%s",
                (str(guild_id),)
            )
            return self.cursor.fetchone()
        except Error:
            return None
        finally:
            self._disconnect()

    def set_therapy_config(self, guild_id, **kwargs):
        allowed = {
            "panel_channel_id",
            "category_id",
            "therapist_role_id",
            "recommend_role_id",
            "log_channel_id",
            "panel_message_id",
        }
        updates = {k: (None if v is None else str(v)) for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        if not self._connect():
            return False
        try:
            columns = ["guild_id"] + list(updates.keys())
            values = [str(guild_id)] + list(updates.values())
            placeholders = ", ".join(["%s"] * len(columns))
            update_sql = ", ".join(f"{column}=VALUES({column})" for column in updates)
            self.cursor.execute(
                f"INSERT INTO bot_therapy_config ({', '.join(columns)}) VALUES ({placeholders}) "
                f"ON DUPLICATE KEY UPDATE {update_sql}",
                tuple(values)
            )
            self.connection.commit()
            return True
        except Error as e:
            print(f"Therapy config save error: {e}")
            return False
        finally:
            self._disconnect()

    def add_therapy_therapist(self, guild_id, user_id, added_by=None):
        if not self._connect():
            return False
        try:
            self.cursor.execute("""
                INSERT IGNORE INTO bot_therapy_therapists (guild_id, user_id, added_by)
                VALUES (%s, %s, %s)
            """, (str(guild_id), str(user_id), None if added_by is None else str(added_by)))
            self.connection.commit()
            return True
        except Error:
            return False
        finally:
            self._disconnect()

    def remove_therapy_therapist(self, guild_id, user_id):
        if not self._connect():
            return False
        try:
            self.cursor.execute(
                "DELETE FROM bot_therapy_therapists WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Error:
            return False
        finally:
            self._disconnect()

    def get_therapy_therapists(self, guild_id):
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT user_id FROM bot_therapy_therapists WHERE guild_id=%s ORDER BY added_at",
                (str(guild_id),)
            )
            return self.cursor.fetchall()
        except Error:
            return []
        finally:
            self._disconnect()

    def create_therapy_session(self, guild_id, requester_id, therapist_id, channel_id):
        if not self._connect():
            return None
        try:
            self.cursor.execute("""
                INSERT INTO bot_therapy_sessions (guild_id, requester_id, therapist_id, channel_id)
                VALUES (%s, %s, %s, %s)
            """, (str(guild_id), str(requester_id), str(therapist_id), str(channel_id)))
            self.connection.commit()
            return self.cursor.lastrowid
        except Error as e:
            print(f"Therapy session create error: {e}")
            return None
        finally:
            self._disconnect()

    def get_open_therapy_session_for_user(self, guild_id, user_id):
        if not self._connect():
            return None
        try:
            self.cursor.execute("""
                SELECT * FROM bot_therapy_sessions
                WHERE guild_id=%s AND requester_id=%s AND status='open'
                ORDER BY opened_at DESC LIMIT 1
            """, (str(guild_id), str(user_id)))
            return self.cursor.fetchone()
        except Error:
            return None
        finally:
            self._disconnect()

    def get_open_therapy_session_by_channel(self, guild_id, channel_id):
        if not self._connect():
            return None
        try:
            self.cursor.execute("""
                SELECT * FROM bot_therapy_sessions
                WHERE guild_id=%s AND channel_id=%s AND status='open'
                ORDER BY opened_at DESC LIMIT 1
            """, (str(guild_id), str(channel_id)))
            return self.cursor.fetchone()
        except Error:
            return None
        finally:
            self._disconnect()

    def get_open_therapy_sessions(self, guild_id):
        if not self._connect():
            return []
        try:
            self.cursor.execute("""
                SELECT * FROM bot_therapy_sessions
                WHERE guild_id=%s AND status='open'
                ORDER BY opened_at DESC
            """, (str(guild_id),))
            return self.cursor.fetchall()
        except Error:
            return []
        finally:
            self._disconnect()

    def close_therapy_session(self, guild_id, channel_id, closed_by=None, reason=None):
        if not self._connect():
            return False
        try:
            self.cursor.execute("""
                UPDATE bot_therapy_sessions
                SET status='closed', closed_at=NOW(), closed_by=%s, close_reason=%s
                WHERE guild_id=%s AND channel_id=%s AND status='open'
            """, (
                None if closed_by is None else str(closed_by),
                reason,
                str(guild_id),
                str(channel_id),
            ))
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Error:
            return False
        finally:
            self._disconnect()

    # ─── Antinuke API ───

    def get_antinuke_config(self, guild_id):
        if not self._connect():
            return None
        try:
            self.cursor.execute("SELECT * FROM bot_antinuke WHERE guild_id=%s", (str(guild_id),))
            return self.cursor.fetchone()
        except Error:
            return None
        finally:
            self._disconnect()

    def set_antinuke_config(self, guild_id, **kwargs):
        if not self._connect():
            return
        try:
            self.cursor.execute("""
                INSERT INTO bot_antinuke (guild_id, enabled, ban_threshold, kick_threshold, channel_threshold, role_threshold, punishment)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE enabled=VALUES(enabled), ban_threshold=VALUES(ban_threshold),
                    kick_threshold=VALUES(kick_threshold), channel_threshold=VALUES(channel_threshold),
                    role_threshold=VALUES(role_threshold), punishment=VALUES(punishment)
            """, (str(guild_id), kwargs.get('enabled', False), kwargs.get('ban_threshold', 3),
                  kwargs.get('kick_threshold', 3), kwargs.get('channel_threshold', 3),
                  kwargs.get('role_threshold', 3), kwargs.get('punishment', 'ban')))
            self.connection.commit()
        except Error as e:
            print(f"Error setting antinuke config: {e}")
        finally:
            self._disconnect()

    def is_antinuke_whitelisted(self, guild_id, user_id):
        if not self._connect():
            return False
        try:
            self.cursor.execute(
                "SELECT 1 FROM bot_antinuke_whitelist WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            return self.cursor.fetchone() is not None
        except Error:
            return False
        finally:
            self._disconnect()

    def add_antinuke_whitelist(self, guild_id, user_id, role='whitelisted'):
        if not self._connect():
            return
        try:
            self.cursor.execute("""
                INSERT INTO bot_antinuke_whitelist (guild_id, user_id, role) VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE role=VALUES(role)
            """, (str(guild_id), str(user_id), role))
            self.connection.commit()
        except Error:
            pass
        finally:
            self._disconnect()

    def remove_antinuke_whitelist(self, guild_id, user_id):
        if not self._connect():
            return
        try:
            self.cursor.execute(
                "DELETE FROM bot_antinuke_whitelist WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            self.connection.commit()
        except Error:
            pass
        finally:
            self._disconnect()

    def get_antinuke_whitelist_role(self, guild_id, user_id):
        """Get the role of a whitelisted user ('admin' or 'whitelisted'). Returns None if not found."""
        if not self._connect():
            return None
        try:
            self.cursor.execute(
                "SELECT role FROM bot_antinuke_whitelist WHERE guild_id=%s AND user_id=%s",
                (str(guild_id), str(user_id))
            )
            row = self.cursor.fetchone()
            return row['role'] if row else None
        except Error:
            return None
        finally:
            self._disconnect()

    def is_antinuke_admin(self, guild_id, user_id):
        """Check if a user is an antinuke admin."""
        return self.get_antinuke_whitelist_role(guild_id, user_id) == 'admin'

    def get_all_antinuke_whitelisted(self, guild_id):
        """Get all whitelisted users for a guild."""
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT user_id, role FROM bot_antinuke_whitelist WHERE guild_id=%s ORDER BY role, user_id",
                (str(guild_id),)
            )
            return self.cursor.fetchall()
        except Error:
            return []
        finally:
            self._disconnect()

    # ─── Auto-react API ───

    def add_autoreact(self, guild_id, channel_id, emoji):
        if not self._connect():
            return False
        try:
            self.cursor.execute("""
                INSERT INTO bot_autoreact (guild_id, channel_id, emoji) VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE emoji=VALUES(emoji)
            """, (str(guild_id), str(channel_id), emoji))
            self.connection.commit()
            return True
        except Error:
            return False
        finally:
            self._disconnect()

    def remove_autoreact(self, guild_id, channel_id, emoji=None):
        if not self._connect():
            return
        try:
            if emoji:
                self.cursor.execute(
                    "DELETE FROM bot_autoreact WHERE guild_id=%s AND channel_id=%s AND emoji=%s",
                    (str(guild_id), str(channel_id), emoji)
                )
            else:
                self.cursor.execute(
                    "DELETE FROM bot_autoreact WHERE guild_id=%s AND channel_id=%s",
                    (str(guild_id), str(channel_id))
                )
            self.connection.commit()
        except Error:
            pass
        finally:
            self._disconnect()

    def get_autoreacts(self, guild_id, channel_id):
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT emoji FROM bot_autoreact WHERE guild_id=%s AND channel_id=%s",
                (str(guild_id), str(channel_id))
            )
            return [r['emoji'] for r in self.cursor.fetchall()]
        except Error:
            return []
        finally:
            self._disconnect()

    # ─── Join DM API ───

    def set_joindm(self, guild_id, message_template):
        if not self._connect():
            return
        try:
            self.cursor.execute("""
                INSERT INTO bot_joindm (guild_id, message_template, enabled) VALUES (%s, %s, TRUE)
                ON DUPLICATE KEY UPDATE message_template=VALUES(message_template), enabled=TRUE
            """, (str(guild_id), message_template))
            self.connection.commit()
        except Error:
            pass
        finally:
            self._disconnect()

    def remove_joindm(self, guild_id):
        if not self._connect():
            return
        try:
            self.cursor.execute(
                "UPDATE bot_joindm SET enabled=FALSE WHERE guild_id=%s",
                (str(guild_id),)
            )
            self.connection.commit()
        except Error:
            pass
        finally:
            self._disconnect()

    def get_joindm(self, guild_id):
        if not self._connect():
            return None
        try:
            self.cursor.execute(
                "SELECT * FROM bot_joindm WHERE guild_id=%s AND enabled=TRUE",
                (str(guild_id),)
            )
            return self.cursor.fetchone()
        except Error:
            return None
        finally:
            self._disconnect()

    # ─── Persistent Stats API (replaces JSON file) ───

    def get_persistent_stat(self, key, default=None):
        """Get a persistent stat value."""
        if not self._connect():
            return default
        try:
            self.cursor.execute(
                "SELECT value FROM persistent_stats WHERE key_name=%s",
                (key,)
            )
            row = self.cursor.fetchone()
            if row:
                try:
                    return json.loads(row['value'])
                except (json.JSONDecodeError, TypeError):
                    return row['value']
            return default
        except Error:
            return default
        finally:
            self._disconnect()

    def set_persistent_stat(self, key, value):
        """Set a persistent stat value."""
        if not self._connect():
            return
        try:
            val_str = json.dumps(value) if not isinstance(value, str) else value
            self.cursor.execute("""
                INSERT INTO persistent_stats (key_name, value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE value = VALUES(value)
            """, (key, val_str))
            self.connection.commit()
        except Error as e:
            print(f"Error setting persistent stat: {e}")
        finally:
            self._disconnect()

    # ─── Ticket Sort API ───

    def set_persistent_stats(self, stats):
        """Set multiple persistent stat values in one database transaction."""
        if not stats or not self._connect():
            return
        try:
            rows = [
                (str(key), json.dumps(value) if not isinstance(value, str) else value)
                for key, value in stats.items()
            ]
            self.cursor.executemany("""
                INSERT INTO persistent_stats (key_name, value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE value = VALUES(value)
            """, rows)
            self.connection.commit()
        except Error as e:
            print(f"Error setting persistent stats: {e}")
        finally:
            self._disconnect()

    def add_ticket_sort_rule(self, guild_id, keyword, category_id, match_mode='startswith'):
        """Add a ticket sort rule."""
        if not self._connect():
            return False
        try:
            self.cursor.execute("""
                INSERT INTO bot_ticket_sort (guild_id, keyword, category_id, match_mode)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE category_id = VALUES(category_id), match_mode = VALUES(match_mode)
            """, (str(guild_id), keyword.lower(), str(category_id), match_mode))
            self.connection.commit()
            return True
        except Error:
            return False
        finally:
            self._disconnect()

    def remove_ticket_sort_rule(self, guild_id, keyword):
        """Remove a ticket sort rule."""
        if not self._connect():
            return False
        try:
            self.cursor.execute(
                "DELETE FROM bot_ticket_sort WHERE guild_id=%s AND keyword=%s",
                (str(guild_id), keyword.lower())
            )
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Error:
            return False
        finally:
            self._disconnect()

    def get_ticket_sort_rules(self, guild_id):
        """Get all ticket sort rules for a guild."""
        if not self._connect():
            return []
        try:
            self.cursor.execute(
                "SELECT keyword, category_id, match_mode FROM bot_ticket_sort WHERE guild_id=%s ORDER BY keyword",
                (str(guild_id),)
            )
            return self.cursor.fetchall()
        except Error:
            return []
        finally:
            self._disconnect()

    def clear_ticket_sort_rules(self, guild_id):
        """Clear all ticket sort rules for a guild."""
        if not self._connect():
            return 0
        try:
            self.cursor.execute(
                "DELETE FROM bot_ticket_sort WHERE guild_id=%s",
                (str(guild_id),)
            )
            self.connection.commit()
            return self.cursor.rowcount
        except Error:
            return 0
        finally:
            self._disconnect()


# Global singleton
settings_db = MySQLSettingsDB()
