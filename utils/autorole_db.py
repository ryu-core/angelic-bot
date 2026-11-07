import mysql.connector
from mysql.connector import Error
from datetime import datetime
import os

def _env(name, default=None):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _mysql_config_ready(config):
    return all(config.get(key) for key in ('host', 'user', 'password', 'database'))


class AutoRoleDatabase:
    """Database handler for auto-role system"""
    
    def __init__(self):
        self.connection = None
        self.cursor = None
        self.db_config = {
            'host': _env('MYSQL_HOST'),
            'port': int(_env('MYSQL_PORT', '3306')),
            'user': _env('MYSQL_USER'),
            'password': _env('MYSQL_PASSWORD'),
            'database': _env('MYSQL_DATABASE')
        }
        self.available = _mysql_config_ready(self.db_config)
        self._warned_unavailable = False

    def _warn_missing_mysql(self):
        if not self._warned_unavailable:
            print("AutoRole DB disabled: missing MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, or MYSQL_DATABASE")
            self._warned_unavailable = True
    
    def connect(self):
        """Connect to MySQL database"""
        if not self.available:
            self._warn_missing_mysql()
            return False

        try:
            self.connection = mysql.connector.connect(**self.db_config)
            self.cursor = self.connection.cursor(dictionary=True)
            return True
        except Error as e:
            print(f"❌ AutoRole DB connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MySQL database"""
        if self.cursor:
            self.cursor.close()
        if self.connection and self.connection.is_connected():
            self.connection.close()
    
    def init_database(self):
        """Initialize auto-role tables"""
        if not self.connect():
            return False
        
        try:
            # Auto-role configuration table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS autorole_config (
                    guild_id VARCHAR(20) PRIMARY KEY,
                    tag_role_id VARCHAR(20) DEFAULT NULL,
                    tag_enabled BOOLEAN DEFAULT FALSE,
                    vanity_text VARCHAR(255) DEFAULT NULL,
                    vanity_role_id VARCHAR(20) DEFAULT NULL,
                    vanity_enabled BOOLEAN DEFAULT FALSE,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    INDEX idx_tag_enabled (tag_enabled),
                    INDEX idx_vanity_enabled (vanity_enabled)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            self.connection.commit()
            print("✓ MySQL auto-role tables initialized")
            return True
            
        except Error as e:
            print(f"Error initializing auto-role tables: {e}")
            return False
        finally:
            self.disconnect()
    
    def get_config(self, guild_id):
        """Get auto-role configuration for a guild"""
        if not self.connect():
            return None
        
        try:
            self.cursor.execute("""
                SELECT * FROM autorole_config
                WHERE guild_id = %s
            """, (guild_id,))
            
            return self.cursor.fetchone()
            
        except Error as e:
            print(f"Error getting auto-role config: {e}")
            return None
        finally:
            self.disconnect()
    
    def get_all_configs(self):
        """Get all auto-role configurations"""
        if not self.connect():
            return []
        
        try:
            self.cursor.execute("""
                SELECT * FROM autorole_config
                WHERE tag_enabled = TRUE OR vanity_enabled = TRUE
            """)
            
            return self.cursor.fetchall()
            
        except Error as e:
            print(f"Error getting all configs: {e}")
            return []
        finally:
            self.disconnect()
    
    def set_tag_role(self, guild_id, role_id):
        """Set server tag role for a guild"""
        if not self.connect():
            return False
        
        try:
            timestamp = int(datetime.now().timestamp())
            
            # Check if config exists
            self.cursor.execute("""
                SELECT guild_id FROM autorole_config
                WHERE guild_id = %s
            """, (guild_id,))
            
            if self.cursor.fetchone():
                # Update existing
                self.cursor.execute("""
                    UPDATE autorole_config
                    SET tag_role_id = %s,
                        tag_enabled = TRUE,
                        updated_at = %s
                    WHERE guild_id = %s
                """, (role_id, timestamp, guild_id))
            else:
                # Insert new
                self.cursor.execute("""
                    INSERT INTO autorole_config
                    (guild_id, tag_role_id, tag_enabled, created_at, updated_at)
                    VALUES (%s, %s, TRUE, %s, %s)
                """, (guild_id, role_id, timestamp, timestamp))
            
            self.connection.commit()
            return True
            
        except Error as e:
            print(f"Error setting tag role: {e}")
            return False
        finally:
            self.disconnect()
    
    def set_vanity_role(self, guild_id, vanity_text, role_id):
        """Set vanity URL role for a guild"""
        if not self.connect():
            return False
        
        try:
            timestamp = int(datetime.now().timestamp())
            
            # Check if config exists
            self.cursor.execute("""
                SELECT guild_id FROM autorole_config
                WHERE guild_id = %s
            """, (guild_id,))
            
            if self.cursor.fetchone():
                # Update existing
                self.cursor.execute("""
                    UPDATE autorole_config
                    SET vanity_text = %s,
                        vanity_role_id = %s,
                        vanity_enabled = TRUE,
                        updated_at = %s
                    WHERE guild_id = %s
                """, (vanity_text, role_id, timestamp, guild_id))
            else:
                # Insert new
                self.cursor.execute("""
                    INSERT INTO autorole_config
                    (guild_id, vanity_text, vanity_role_id, vanity_enabled, created_at, updated_at)
                    VALUES (%s, %s, %s, TRUE, %s, %s)
                """, (guild_id, vanity_text, role_id, timestamp, timestamp))
            
            self.connection.commit()
            return True
            
        except Error as e:
            print(f"Error setting vanity role: {e}")
            return False
        finally:
            self.disconnect()
    
    def disable_tag(self, guild_id):
        """Disable server tag detection for a guild"""
        if not self.connect():
            return False
        
        try:
            self.cursor.execute("""
                UPDATE autorole_config
                SET tag_enabled = FALSE,
                    updated_at = %s
                WHERE guild_id = %s
            """, (int(datetime.now().timestamp()), guild_id))
            
            self.connection.commit()
            return True
            
        except Error as e:
            print(f"Error disabling tag: {e}")
            return False
        finally:
            self.disconnect()
    
    def disable_vanity(self, guild_id):
        """Disable vanity URL detection for a guild"""
        if not self.connect():
            return False
        
        try:
            self.cursor.execute("""
                UPDATE autorole_config
                SET vanity_enabled = FALSE,
                    updated_at = %s
                WHERE guild_id = %s
            """, (int(datetime.now().timestamp()), guild_id))
            
            self.connection.commit()
            return True
            
        except Error as e:
            print(f"Error disabling vanity: {e}")
            return False
        finally:
            self.disconnect()

# Global instance
autorole_db = AutoRoleDatabase()
