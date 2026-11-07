"""
MySQL Database Manager for Bot Settings
Replaces JSON/SQLite files with persistent MySQL storage
"""
import mysql.connector
from mysql.connector import Error
import os
from typing import Optional, Dict, List, Any

class MySQLSettingsDB:
    """Centralized MySQL database for all bot settings"""
    
    def __init__(self):
        # Credentials must be provided through environment variables.
        self.config = {
            'host': os.getenv('MYSQL_HOST', ''),
            'port': int(os.getenv('MYSQL_PORT', '3306')),
            'user': os.getenv('MYSQL_USER', ''),
            'password': os.getenv('MYSQL_PASSWORD', ''),
            'database': os.getenv('MYSQL_DATABASE', ''),
            'autocommit': False,
            'charset': 'utf8mb4'
        }
        self._config_ready = all(
            self.config.get(key)
            for key in ('host', 'user', 'password', 'database')
        )
        self.connection = None
        if not self._config_ready:
            print(
                "MySQL settings database disabled: set MYSQL_HOST, MYSQL_USER, "
                "MYSQL_PASSWORD, and MYSQL_DATABASE"
            )
            return
        try:
            self.init_tables()
            print("✓ MySQL settings database initialized")
        except Exception as e:
            print(f"⚠️ MySQL settings database initialization failed: {e}")
            print("Settings will not persist! Check MySQL credentials.")
    
    def get_connection(self):
        """Get or create database connection"""
        if not self._config_ready:
            return None
        try:
            if self.connection is None or not self.connection.is_connected():
                self.connection = mysql.connector.connect(**self.config)
            return self.connection
        except Error as e:
            print(f"❌ MySQL connection error: {e}")
            print(f"Config: host={self.config['host']}, user={self.config['user']}, db={self.config['database']}")
            return None
    
    def init_tables(self):
        """Initialize tables used by the active welcome-system integration."""
        try:
            conn = self.get_connection()
            if not conn:
                return

            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS welcome_config (
                    guild_id VARCHAR(32) PRIMARY KEY,
                    channel_id VARCHAR(32) NOT NULL,
                    message TEXT DEFAULT NULL,
                    custom_image_url TEXT DEFAULT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
            cursor.close()
            print("MySQL welcome settings table initialized")
        except Error as e:
            print(f"Error initializing tables: {e}")
    # ===== GUILD CONFIG =====
    def set_guild_config(self, guild_id: str, key: str, value: str) -> bool:
        """Set guild configuration value"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"""
                INSERT INTO guild_config (guild_id, {key})
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE {key} = %s
            """, (guild_id, value, value))
            
            conn.commit()
            cursor.close()
            return True
        except Error as e:
            print(f"Error setting guild config: {e}")
            return False
    
    def get_guild_config(self, guild_id: str) -> Optional[Dict]:
        """Get guild configuration"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM guild_config WHERE guild_id = %s", (guild_id,))
            result = cursor.fetchone()
            cursor.close()
            return result
        except Error as e:
            print(f"Error getting guild config: {e}")
            return None
    
    # ===== WELCOME SYSTEM =====
    def set_welcome_channel(self, guild_id: str, channel_id: str, message: str = None) -> bool:
        """Set welcome channel"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO welcome_config (guild_id, channel_id, message)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE channel_id = %s, message = COALESCE(%s, message)
            """, (guild_id, channel_id, message, channel_id, message))
            
            conn.commit()
            cursor.close()
            return True
        except Error as e:
            print(f"Error setting welcome channel: {e}")
            return False
    
    def get_welcome_config(self, guild_id: str) -> Optional[Dict]:
        """Get welcome configuration"""
        try:
            conn = self.get_connection()
            if not conn:
                return None
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM welcome_config WHERE guild_id = %s", (guild_id,))
            result = cursor.fetchone()
            cursor.close()
            return result
        except Error as e:
            print(f"Error getting welcome config: {e}")
            return None
    
    def update_welcome_message(self, guild_id: str, message: str) -> bool:
        """Update welcome message"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE welcome_config SET message = %s WHERE guild_id = %s
            """, (message, guild_id))
            
            conn.commit()
            cursor.close()
            return True
        except Error as e:
            print(f"Error updating welcome message: {e}")
            return False
    
    def update_welcome_image(self, guild_id: str, image_url: str) -> bool:
        """Update custom welcome image"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE welcome_config SET custom_image_url = %s WHERE guild_id = %s
            """, (image_url, guild_id))
            
            conn.commit()
            cursor.close()
            return True
        except Error as e:
            print(f"Error updating welcome image: {e}")
            return False
    
    def remove_welcome_channel(self, guild_id: str) -> bool:
        """Remove welcome channel"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM welcome_config WHERE guild_id = %s", (guild_id,))
            
            conn.commit()
            cursor.close()
            return True
        except Error as e:
            print(f"Error removing welcome channel: {e}")
            return False
    
    # ===== JAIL SYSTEM =====
    def add_jail(self, guild_id: str, user_id: str, moderator_id: str, reason: str = None, expires_at = None) -> bool:
        """Add user to jail"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO active_jails (guild_id, user_id, moderator_id, reason, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE moderator_id = %s, reason = %s, expires_at = %s
            """, (guild_id, user_id, moderator_id, reason, expires_at, moderator_id, reason, expires_at))
            
            conn.commit()
            cursor.close()
            return True
        except Error as e:
            print(f"Error adding jail: {e}")
            return False
    
    def remove_jail(self, guild_id: str, user_id: str) -> bool:
        """Remove user from jail"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM active_jails WHERE guild_id = %s AND user_id = %s", (guild_id, user_id))
            
            conn.commit()
            cursor.close()
            return True
        except Error as e:
            print(f"Error removing jail: {e}")
            return False
    
    def get_jailed_users(self, guild_id: str) -> List[Dict]:
        """Get all jailed users in guild"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM active_jails WHERE guild_id = %s", (guild_id,))
            results = cursor.fetchall()
            cursor.close()
            return results
        except Error as e:
            print(f"Error getting jailed users: {e}")
            return []
    
    # ===== WARNINGS =====
    def add_warning(self, guild_id: str, user_id: str, moderator_id: str, reason: str) -> bool:
        """Add warning to user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO warnings (guild_id, user_id, moderator_id, reason)
                VALUES (%s, %s, %s, %s)
            """, (guild_id, user_id, moderator_id, reason))
            
            conn.commit()
            cursor.close()
            return True
        except Error as e:
            print(f"Error adding warning: {e}")
            return False
    
    def get_warnings(self, guild_id: str, user_id: str) -> List[Dict]:
        """Get user warnings"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM warnings WHERE guild_id = %s AND user_id = %s ORDER BY warned_at DESC", (guild_id, user_id))
            results = cursor.fetchall()
            cursor.close()
            return results
        except Error as e:
            print(f"Error getting warnings: {e}")
            return []
    
    # ===== STICKY MESSAGES =====
    def set_sticky_message(self, channel_id: str, guild_id: str, message: str) -> bool:
        """Set sticky message for channel"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO sticky_messages (channel_id, guild_id, message)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE message = %s
            """, (channel_id, guild_id, message, message))
            
            conn.commit()
            cursor.close()
            return True
        except Error as e:
            print(f"Error setting sticky message: {e}")
            return False
    
    def get_sticky_message(self, channel_id: str) -> Optional[Dict]:
        """Get sticky message for channel"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM sticky_messages WHERE channel_id = %s", (channel_id,))
            result = cursor.fetchone()
            cursor.close()
            return result
        except Error as e:
            print(f"Error getting sticky message: {e}")
            return None

# Global instance
settings_db = MySQLSettingsDB()
