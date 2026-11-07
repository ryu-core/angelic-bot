# MySQL Database Connection Utility for Case Logs
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()

# MySQL Configuration
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', ''),
    'port': int(os.getenv('MYSQL_PORT', 3306)),
    'user': os.getenv('MYSQL_USER', ''),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'database': os.getenv('MYSQL_DATABASE', '')
}

class MySQLCaseLogs:
    """MySQL database handler for moderation case logs"""
    
    def __init__(self):
        self.connection = None
        self.cursor = None
        self.init_database()
    
    def connect(self):
        """Establish MySQL connection"""
        try:
            if not self.connection or not self.connection.is_connected():
                self.connection = mysql.connector.connect(**MYSQL_CONFIG)
                self.cursor = self.connection.cursor(dictionary=True)
            return True
        except Error as e:
            print(f"MySQL Connection Error: {e}")
            return False
    
    def disconnect(self):
        """Close MySQL connection"""
        if self.cursor:
            self.cursor.close()
        if self.connection and self.connection.is_connected():
            self.connection.close()
    
    def init_database(self):
        """Initialize database tables"""
        if not self.connect():
            return
        
        try:
            # Create case_logs table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    case_id INT NOT NULL,
                    case_type ENUM('warn', 'mute', 'kick', 'ban', 'jail', 'unjail', 'unmute', 'unban') NOT NULL,
                    user_id VARCHAR(20) NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    moderator_id VARCHAR(20) NOT NULL,
                    moderator_name VARCHAR(255) NOT NULL,
                    reason TEXT,
                    duration INT DEFAULT NULL,
                    timestamp BIGINT NOT NULL,
                    additional_data JSON DEFAULT NULL,
                    INDEX idx_guild (guild_id),
                    INDEX idx_user (user_id),
                    INDEX idx_moderator (moderator_id),
                    INDEX idx_timestamp (timestamp),
                    UNIQUE KEY unique_case (guild_id, case_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create ban_history table for additional ban tracking
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS ban_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    user_id VARCHAR(20) NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    moderator_id VARCHAR(20) DEFAULT NULL,
                    reason TEXT,
                    timestamp BIGINT NOT NULL,
                    is_manual_ban BOOLEAN DEFAULT FALSE,
                    INDEX idx_guild (guild_id),
                    INDEX idx_user (user_id),
                    INDEX idx_timestamp (timestamp)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            self.connection.commit()
            print("✓ MySQL case logs tables initialized")
            
        except Error as e:
            print(f"Error initializing database: {e}")
        finally:
            self.disconnect()
    
    def log_case(self, guild_id, case_type, user_id, username, moderator_id, moderator_name, reason="No reason provided", duration=None, additional_data=None):
        """Log a moderation case"""
        if not self.connect():
            return None
        
        try:
            # Get next case ID for this guild
            self.cursor.execute(
                "SELECT COALESCE(MAX(case_id), 0) + 1 AS next_case_id FROM case_logs WHERE guild_id = %s",
                (guild_id,)
            )
            result = self.cursor.fetchone()
            case_id = result['next_case_id'] if result else 1
            
            # Insert case log
            self.cursor.execute("""
                INSERT INTO case_logs (guild_id, case_id, case_type, user_id, username, moderator_id, moderator_name, reason, duration, timestamp, additional_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                guild_id,
                case_id,
                case_type,
                user_id,
                username,
                moderator_id,
                moderator_name,
                reason,
                duration,
                int(datetime.now().timestamp()),
                json.dumps(additional_data) if additional_data else None
            ))
            
            self.connection.commit()
            return case_id
            
        except Error as e:
            print(f"Error logging case: {e}")
            return None
        finally:
            self.disconnect()
    
    def log_ban(self, guild_id, user_id, username, moderator_id=None, reason="No reason provided", is_manual=False):
        """Log a ban to ban_history"""
        if not self.connect():
            return
        
        try:
            self.cursor.execute("""
                INSERT INTO ban_history (guild_id, user_id, username, moderator_id, reason, timestamp, is_manual_ban)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                guild_id,
                user_id,
                username,
                moderator_id,
                reason,
                int(datetime.now().timestamp()),
                is_manual
            ))
            
            self.connection.commit()
            
        except Error as e:
            print(f"Error logging ban: {e}")
        finally:
            self.disconnect()
    
    def get_user_cases(self, guild_id, user_id, limit=50):
        """Get all cases for a specific user"""
        if not self.connect():
            return []
        
        try:
            self.cursor.execute("""
                SELECT * FROM case_logs 
                WHERE guild_id = %s AND user_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            """, (guild_id, user_id, limit))
            
            return self.cursor.fetchall()
            
        except Error as e:
            print(f"Error fetching user cases: {e}")
            return []
        finally:
            self.disconnect()
    
    def get_case(self, guild_id, case_id):
        """Get a specific case by ID"""
        if not self.connect():
            return None
        
        try:
            self.cursor.execute("""
                SELECT * FROM case_logs 
                WHERE guild_id = %s AND case_id = %s
            """, (guild_id, case_id))
            
            return self.cursor.fetchone()
            
        except Error as e:
            print(f"Error fetching case: {e}")
            return None
        finally:
            self.disconnect()

# Global instance
mysql_case_logs = MySQLCaseLogs()
