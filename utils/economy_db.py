# MySQL Database Handler for Economy System — UNIVERSAL (global balances)
import mysql.connector
from mysql.connector import Error, pooling
import os
import time
from contextlib import contextmanager
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

def _env(name, default=None):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


MYSQL_CONFIG = {
    'host': _env('MYSQL_HOST'),
    'port': int(_env('MYSQL_PORT', '3306')),
    'user': _env('MYSQL_USER'),
    'password': _env('MYSQL_PASSWORD'),
    'database': _env('MYSQL_DATABASE')
}


def _mysql_config_ready():
    return all(MYSQL_CONFIG.get(key) for key in ('host', 'user', 'password', 'database'))

class EconomyDatabase:
    """Universal MySQL economy — balances/cooldowns/loans shared across all servers."""

    def __init__(self):
        self._pool = None
        self._init_pool()
        self.init_database()

    def _init_pool(self, retries=5, delay=1.0):
        """Create the connection pool (retries on transient startup failures)."""
        if not _mysql_config_ready():
            print("Economy MySQL env missing; economy DB features disabled")
            return

        for attempt in range(retries):
            try:
                self._pool = pooling.MySQLConnectionPool(
                    pool_name="economy_pool",
                    pool_size=10,
                    pool_reset_session=True,
                    **MYSQL_CONFIG
                )
                print("✓ Economy MySQL connection pool created (size=10)")
                return
            except Error as e:
                print(f"Economy pool init error (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
        print("❌ Could not create economy MySQL pool — DB features disabled")

    @contextmanager
    def _get_conn(self):
        """Yield an isolated (connection, cursor) pair from the pool.
        Each caller gets its own connection — no shared state, no race conditions.
        """
        conn = None
        cursor = None
        try:
            if self._pool is None:
                raise RuntimeError("Economy database is unavailable because MySQL is not configured")
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            yield conn, cursor
        except Error as e:
            print(f"Economy DB connection error: {e}")
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass
            # Re-yield None,None so methods can handle gracefully
            # This is a generator so we need a different approach
            raise
        # Note: cleanup done in finally blocks inside each method

    def init_database(self):
        """Initialize / migrate all economy tables to universal schema."""
        conn = None
        cursor = None
        try:
            if self._pool is None:
                print("Skipping economy database initialization; MySQL is not configured")
                return
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)

            # ── Economy Users (global) ──────────────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS economy_users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(20) NOT NULL UNIQUE,
                    wallet BIGINT DEFAULT 1000,
                    bank BIGINT DEFAULT 0,
                    total_earned BIGINT DEFAULT 0,
                    total_spent BIGINT DEFAULT 0,
                    daily_streak INT DEFAULT 0,
                    last_daily BIGINT DEFAULT 0,
                    last_weekly BIGINT DEFAULT 0,
                    last_work BIGINT DEFAULT 0,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    INDEX idx_user (user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # ── Economy Shop (per-guild) ─────────────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS economy_shop (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(20) NOT NULL,
                    item_id VARCHAR(50) NOT NULL,
                    item_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    price BIGINT NOT NULL,
                    emoji VARCHAR(50) DEFAULT '💎',
                    item_type ENUM('collectible','booster','consumable','cosmetic','gamble') DEFAULT 'collectible',
                    stock INT DEFAULT -1,
                    required_role VARCHAR(20) DEFAULT NULL,
                    created_at BIGINT NOT NULL,
                    INDEX idx_guild (guild_id),
                    UNIQUE KEY unique_item (guild_id, item_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # ── Economy Inventory (global) ───────────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS economy_inventory (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(20) NOT NULL,
                    item_id VARCHAR(50) NOT NULL,
                    quantity INT DEFAULT 1,
                    purchased_at BIGINT NOT NULL,
                    INDEX idx_user (user_id),
                    UNIQUE KEY unique_user_item (user_id, item_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # ── Economy Transactions (global) ────────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS economy_transactions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(20) NOT NULL,
                    transaction_type ENUM('earn','spend','transfer_send','transfer_receive','game_win','game_loss','shop_buy','shop_sell','admin_add','admin_remove','item_use') NOT NULL,
                    amount BIGINT NOT NULL,
                    description TEXT,
                    timestamp BIGINT NOT NULL,
                    INDEX idx_user (user_id),
                    INDEX idx_timestamp (timestamp)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # ── Economy Cooldowns (global) ───────────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS economy_cooldowns (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(20) NOT NULL,
                    cooldown_type ENUM('daily','weekly','work','crime','rob','slots','coinflip','blackjack','dice','roulette') NOT NULL,
                    expires_at BIGINT NOT NULL,
                    INDEX idx_user (user_id),
                    UNIQUE KEY unique_cooldown (user_id, cooldown_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # ── Economy Loans (global) ───────────────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS economy_loans (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(20) NOT NULL,
                    amount BIGINT NOT NULL,
                    total_with_tax BIGINT NOT NULL,
                    daily_payment BIGINT NOT NULL,
                    total_remaining BIGINT NOT NULL,
                    taken_at BIGINT NOT NULL,
                    next_due_at BIGINT NOT NULL,
                    last_payment_at BIGINT DEFAULT 0,
                    ping_count INT DEFAULT 0,
                    last_ping_at BIGINT DEFAULT 0,
                    status ENUM('active','paid','defaulted') DEFAULT 'active',
                    INDEX idx_user (user_id),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Migration: drop stale guild_id column if present (old per-guild schema)
            # This covers ALL tables that were migrated from per-guild to universal
            _tables_to_migrate = [
                'economy_users', 'economy_loans', 'economy_transactions', 'economy_cooldowns',
                'economy_inventory', 'economy_active_effects'
            ]
            for _table in _tables_to_migrate:
                try:
                    cursor.execute(f"""
                        SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = '{_table}'
                        AND COLUMN_NAME = 'guild_id'
                    """)
                    row = cursor.fetchone()
                    if row and (row.get('cnt') or 0) > 0:
                        # First drop any UNIQUE/INDEX constraints that include guild_id
                        try:
                            cursor.execute(f"""
                                SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
                                WHERE TABLE_SCHEMA = DATABASE()
                                AND TABLE_NAME = '{_table}'
                                AND COLUMN_NAME = 'guild_id'
                                AND CONSTRAINT_NAME != 'PRIMARY'
                            """)
                            constraints = cursor.fetchall()
                            for c in constraints:
                                cname = c['CONSTRAINT_NAME']
                                try:
                                    cursor.execute(f"ALTER TABLE {_table} DROP INDEX `{cname}`")
                                    conn.commit()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        # Now drop the column
                        cursor.execute(f"ALTER TABLE {_table} DROP COLUMN guild_id")
                        conn.commit()
                        print(f"✓ Dropped guild_id column from {_table} (migration)")
                except Exception:
                    pass

            # Migration: drop UNIQUE constraint on user_id if it exists (old schema)
            try:
                cursor.execute("""
                    SELECT COUNT(*) AS cnt FROM information_schema.TABLE_CONSTRAINTS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'economy_loans'
                    AND CONSTRAINT_TYPE = 'UNIQUE'
                    AND CONSTRAINT_NAME = 'user_id'
                """)
                row = cursor.fetchone()
                if row and (row.get('cnt') or 0) > 0:
                    cursor.execute("ALTER TABLE economy_loans DROP INDEX user_id")
                    conn.commit()
                    print("✓ Dropped UNIQUE constraint on economy_loans.user_id (migration)")
            except Exception:
                pass

            # Migration: expand transaction_type ENUM to include new types
            try:
                cursor.execute("""
                    ALTER TABLE economy_transactions
                    MODIFY COLUMN transaction_type ENUM('earn','spend','transfer_send','transfer_receive','game_win','game_loss','shop_buy','shop_sell','admin_add','admin_remove','admin_set','item_use') NOT NULL
                """)
                conn.commit()
            except Exception:
                pass

            # Migration: expand cooldown_type ENUM to include 'slots' and future types
            try:
                cursor.execute("""
                    ALTER TABLE economy_cooldowns
                    MODIFY COLUMN cooldown_type ENUM('daily','weekly','work','crime','rob','slots','coinflip','blackjack','dice','roulette') NOT NULL
                """)
                conn.commit()
            except Exception:
                pass


            # ── Economy Active Effects (global) ──────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS economy_active_effects (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(20) NOT NULL,
                    effect_type VARCHAR(50) NOT NULL,
                    effect_value DECIMAL(10,2) NOT NULL,
                    uses_remaining INT DEFAULT -1,
                    expires_at BIGINT DEFAULT -1,
                    item_id VARCHAR(50),
                    created_at BIGINT NOT NULL,
                    INDEX idx_user (user_id),
                    INDEX idx_effect_type (effect_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            conn.commit()
            print("✓ MySQL economy tables initialized (universal)")

        except Error as e:
            print(f"Error initializing economy database: {e}")
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def _exec(self, sql, params=(), fetchone=False, fetchall=False, commit=False):
        """Helper: run a single query on its own pooled connection."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute(sql, params)
            result = None
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            if commit:
                conn.commit()
            return result
        except Error as e:
            print(f"DB exec error: {e}")
            return None
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    # ==================== USER BALANCE METHODS ====================

    def get_user(self, user_id):
        """Get global user economy data, create if doesn't exist."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute("SELECT * FROM economy_users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                ts = int(datetime.now().timestamp())
                try:
                    cursor.execute("""
                        INSERT IGNORE INTO economy_users (user_id, wallet, bank, created_at, updated_at)
                        VALUES (%s, 1000, 0, %s, %s)
                    """, (user_id, ts, ts))
                    conn.commit()
                except Error:
                    pass
                cursor.execute("SELECT * FROM economy_users WHERE user_id = %s", (user_id,))
                user = cursor.fetchone()
            return user
        except Error as e:
            print(f"Error getting user: {e}")
            return None
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def update_balance(self, user_id, wallet_change=0, bank_change=0):
        """Update user balance (wallet and/or bank).
        Uses GREATEST to prevent negative wallets/banks.
        Auto-creates user if UPDATE affects 0 rows."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            ts = int(datetime.now().timestamp())
            cursor.execute("""
                UPDATE economy_users
                SET wallet = GREATEST(wallet + %s, 0),
                    bank = GREATEST(bank + %s, 0),
                    updated_at = %s
                WHERE user_id = %s
            """, (wallet_change, bank_change, ts, user_id))
            rows_affected = cursor.rowcount
            conn.commit()
            
            if rows_affected == 0:
                # User doesn't exist yet — create them first, then apply change
                print(f"[Balance Warning] User {user_id} not found during update_balance, auto-creating...")
                cursor.execute("""
                    INSERT IGNORE INTO economy_users (user_id, wallet, bank, created_at, updated_at)
                    VALUES (%s, GREATEST(1000 + %s, 0), GREATEST(%s, 0), %s, %s)
                """, (user_id, wallet_change, bank_change, ts, ts))
                conn.commit()
            
            return True
        except Error as e:
            print(f"Error updating balance for {user_id}: {e}")
            return False
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def transfer_wallet(self, sender_id, receiver_id, amount,
                        sender_description="", receiver_description=""):
        """Atomically transfer wallet funds between two global users.

        Both account rows are created (if needed), locked in a stable order,
        and updated on one connection. Transaction history is committed with
        the balance changes so callers can never observe a partial transfer.

        Returns ``(True, "success")`` or ``(False, reason)`` where reason is
        ``invalid_transfer``, ``insufficient_funds``, or ``database_error``.
        """
        sender_id = str(sender_id)
        receiver_id = str(receiver_id)
        if sender_id == receiver_id or not isinstance(amount, int) or amount <= 0:
            return False, "invalid_transfer"

        conn = None
        cursor = None
        try:
            if self._pool is None:
                return False, "database_error"

            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            conn.start_transaction()
            ts = int(datetime.now().timestamp())
            account_ids = sorted((sender_id, receiver_id))

            # Ensure both rows exist before locking. INSERT IGNORE is safe when
            # another transaction creates either account concurrently.
            cursor.executemany("""
                INSERT IGNORE INTO economy_users
                    (user_id, wallet, bank, created_at, updated_at)
                VALUES (%s, 1000, 0, %s, %s)
            """, [
                (account_ids[0], ts, ts),
                (account_ids[1], ts, ts),
            ])

            # Stable ordering prevents two opposite-direction transfers from
            # taking the account locks in different orders.
            cursor.execute("""
                SELECT user_id, wallet
                FROM economy_users
                WHERE user_id IN (%s, %s)
                ORDER BY user_id
                FOR UPDATE
            """, (sender_id, receiver_id))
            locked_users = cursor.fetchall()
            if len(locked_users) != 2:
                raise RuntimeError("Could not lock both economy accounts")

            # Keep the sufficiency check in the debit itself. Even if this
            # method is changed later, the sender can never go negative.
            cursor.execute("""
                UPDATE economy_users
                SET wallet = wallet - %s, updated_at = %s
                WHERE user_id = %s AND wallet >= %s
            """, (amount, ts, sender_id, amount))
            if cursor.rowcount != 1:
                conn.rollback()
                return False, "insufficient_funds"

            cursor.execute("""
                UPDATE economy_users
                SET wallet = wallet + %s, updated_at = %s
                WHERE user_id = %s
            """, (amount, ts, receiver_id))
            if cursor.rowcount != 1:
                raise RuntimeError("Could not credit payment receiver")

            cursor.executemany("""
                INSERT INTO economy_transactions
                    (user_id, transaction_type, amount, description, timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, [
                (sender_id, 'transfer_send', amount, sender_description, ts),
                (receiver_id, 'transfer_receive', amount, receiver_description, ts),
            ])
            conn.commit()
            return True, "success"
        except Exception as e:
            if conn:
                try: conn.rollback()
                except Exception: pass
            print(f"Error transferring wallet funds: {e}")
            return False, "database_error"
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def add_earnings(self, user_id, amount):
        """Add earnings to wallet and track total_earned.
        Uses GREATEST to prevent negative wallet. Auto-creates user if missing."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            ts = int(datetime.now().timestamp())
            cursor.execute("""
                UPDATE economy_users
                SET wallet = GREATEST(wallet + %s, 0),
                    total_earned = total_earned + %s,
                    updated_at = %s
                WHERE user_id = %s
            """, (amount, amount, ts, user_id))
            rows_affected = cursor.rowcount
            conn.commit()
            
            if rows_affected == 0:
                print(f"[Earnings Warning] User {user_id} not found during add_earnings, auto-creating...")
                cursor.execute("""
                    INSERT IGNORE INTO economy_users (user_id, wallet, bank, total_earned, created_at, updated_at)
                    VALUES (%s, GREATEST(1000 + %s, 0), 0, %s, %s, %s)
                """, (user_id, amount, amount, ts, ts))
                conn.commit()
            
            return True
        except Error as e:
            print(f"Error adding earnings for {user_id}: {e}")
            return False
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def set_balance(self, user_id, wallet, bank, reset_stats=False):
        """Set user balance directly (admin commands).
        If reset_stats=True also resets total_earned, total_spent, daily_streak."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            ts = int(datetime.now().timestamp())
            if reset_stats:
                cursor.execute("""
                    INSERT INTO economy_users (user_id, wallet, bank, total_earned, total_spent, daily_streak, created_at, updated_at)
                    VALUES (%s, %s, %s, 0, 0, 0, %s, %s)
                    ON DUPLICATE KEY UPDATE wallet = %s, bank = %s, total_earned = 0, total_spent = 0, daily_streak = 0, updated_at = %s
                """, (user_id, wallet, bank, ts, ts, wallet, bank, ts))
            else:
                cursor.execute("""
                    INSERT INTO economy_users (user_id, wallet, bank, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE wallet = %s, bank = %s, updated_at = %s
                """, (user_id, wallet, bank, ts, ts, wallet, bank, ts))
            conn.commit()
            return True
        except Error as e:
            print(f"Error setting balance: {e}")
            return False
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    # ==================== TRANSACTION METHODS ====================

    def log_transaction(self, user_id, transaction_type, amount, description=""):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            ts = int(datetime.now().timestamp())
            cursor.execute("""
                INSERT INTO economy_transactions (user_id, transaction_type, amount, description, timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, transaction_type, amount, description, ts))
            conn.commit()
        except Error as e:
            print(f"Error logging transaction: {e}")
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    # ==================== INVENTORY METHODS ====================

    def add_item(self, user_id, item_id, quantity=1):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            ts = int(datetime.now().timestamp())
            cursor.execute("""
                INSERT INTO economy_inventory (user_id, item_id, quantity, purchased_at)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE quantity = quantity + %s
            """, (user_id, item_id, quantity, ts, quantity))
            conn.commit()
            return True
        except Error as e:
            print(f"Error adding item: {e}")
            return False
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def remove_item(self, user_id, item_id, quantity=1):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute("""
                UPDATE economy_inventory SET quantity = quantity - %s
                WHERE user_id = %s AND item_id = %s
            """, (quantity, user_id, item_id))
            cursor.execute("""
                DELETE FROM economy_inventory WHERE user_id = %s AND item_id = %s AND quantity <= 0
            """, (user_id, item_id))
            conn.commit()
            return True
        except Error as e:
            print(f"Error removing item: {e}")
            return False
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def get_inventory(self, user_id, guild_id):
        """Get user inventory; joins with guild's shop for item info."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute("""
                SELECT i.*, s.item_name, s.description, s.emoji, s.item_type, s.price
                FROM economy_inventory i
                LEFT JOIN economy_shop s ON i.item_id = s.item_id AND s.guild_id = %s
                WHERE i.user_id = %s
                ORDER BY i.purchased_at DESC
            """, (guild_id, user_id))
            return cursor.fetchall()
        except Error as e:
            print(f"Error getting inventory: {e}")
            return []
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    # ==================== SHOP METHODS (per-guild) ====================

    def get_shop_items(self, guild_id, item_type=None):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            if item_type:
                cursor.execute("""
                    SELECT * FROM economy_shop WHERE guild_id = %s AND item_type = %s ORDER BY price ASC
                """, (guild_id, item_type))
            else:
                cursor.execute("""
                    SELECT * FROM economy_shop WHERE guild_id = %s ORDER BY item_type, price ASC
                """, (guild_id,))
            return cursor.fetchall()
        except Error as e:
            print(f"Error getting shop items: {e}")
            return []
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def get_shop_item(self, guild_id, item_id):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute(
                "SELECT * FROM economy_shop WHERE guild_id = %s AND item_id = %s",
                (guild_id, item_id))
            return cursor.fetchone()
        except Error as e:
            print(f"Error getting shop item: {e}")
            return None
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    # ==================== COOLDOWN METHODS ====================

    def check_cooldown(self, user_id, cooldown_type):
        """Returns remaining seconds or 0 if not on cooldown."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            now = int(datetime.now().timestamp())
            cursor.execute("""
                SELECT expires_at FROM economy_cooldowns
                WHERE user_id = %s AND cooldown_type = %s
            """, (user_id, cooldown_type))
            row = cursor.fetchone()
            if row:
                if row['expires_at'] > now:
                    return row['expires_at'] - now
                cursor.execute("""
                    DELETE FROM economy_cooldowns WHERE user_id = %s AND cooldown_type = %s
                """, (user_id, cooldown_type))
                conn.commit()
            return 0
        except Error as e:
            print(f"Error checking cooldown: {e}")
            return 0
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def set_cooldown(self, user_id, cooldown_type, duration_seconds):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            expires_at = int(datetime.now().timestamp()) + duration_seconds
            cursor.execute("""
                INSERT INTO economy_cooldowns (user_id, cooldown_type, expires_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE expires_at = %s
            """, (user_id, cooldown_type, expires_at, expires_at))
            conn.commit()
            return True
        except Error as e:
            print(f"Error setting cooldown: {e}")
            return False
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    # ==================== ACTIVE EFFECTS METHODS ====================

    def add_effect(self, user_id, effect_type, effect_value, uses_remaining=-1, duration_seconds=-1, item_id=None):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            ts = int(datetime.now().timestamp())
            expires_at = ts + duration_seconds if duration_seconds > 0 else -1
            cursor.execute("""
                INSERT INTO economy_active_effects
                (user_id, effect_type, effect_value, uses_remaining, expires_at, item_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (user_id, effect_type, effect_value, uses_remaining, expires_at, item_id, ts))
            conn.commit()
            return True
        except Error as e:
            print(f"Error adding effect: {e}")
            return False
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def get_active_effects(self, user_id, effect_type=None):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            now = int(datetime.now().timestamp())
            if effect_type:
                cursor.execute("""
                    SELECT * FROM economy_active_effects
                    WHERE user_id = %s AND effect_type = %s
                    AND (expires_at = -1 OR expires_at > %s)
                    AND (uses_remaining = -1 OR uses_remaining > 0)
                """, (user_id, effect_type, now))
            else:
                cursor.execute("""
                    SELECT * FROM economy_active_effects
                    WHERE user_id = %s
                    AND (expires_at = -1 OR expires_at > %s)
                    AND (uses_remaining = -1 OR uses_remaining > 0)
                """, (user_id, now))
            return cursor.fetchall()
        except Error as e:
            print(f"Error getting active effects: {e}")
            return []
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def consume_effect_use(self, effect_id):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute("""
                UPDATE economy_active_effects SET uses_remaining = uses_remaining - 1
                WHERE id = %s AND uses_remaining > 0
            """, (effect_id,))
            conn.commit()
            return True
        except Error as e:
            print(f"Error consuming effect: {e}")
            return False
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def remove_expired_effects(self, user_id):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            now = int(datetime.now().timestamp())
            cursor.execute("""
                DELETE FROM economy_active_effects
                WHERE user_id = %s
                AND ((expires_at != -1 AND expires_at <= %s) OR (uses_remaining != -1 AND uses_remaining <= 0))
            """, (user_id, now))
            conn.commit()
            return True
        except Error as e:
            print(f"Error removing expired effects: {e}")
            return False
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def has_rob_protection(self, user_id):
        return len(self.get_active_effects(user_id, 'rob_protection')) > 0

    # ==================== LEADERBOARD ====================

    def get_leaderboard(self, limit=10):
        """Global leaderboard — top users by total balance."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute("""
                SELECT user_id, wallet, bank, (wallet + bank) AS total
                FROM economy_users
                ORDER BY total DESC
                LIMIT %s
            """, (limit,))
            return cursor.fetchall()
        except Error as e:
            print(f"Error getting leaderboard: {e}")
            return []
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    # ==================== LOAN METHODS ====================

    def take_loan(self, user_id, amount):
        """Create a new loan and add money to wallet."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            ts = int(datetime.now().timestamp())
            tax = int(amount * 0.10)
            total_with_tax = amount + tax
            daily_payment = max(1, total_with_tax // 30)
            next_due_at = ts + 86400

            cursor.execute("""
                SELECT id FROM economy_loans WHERE user_id = %s AND status = 'active'
            """, (user_id,))
            existing = cursor.fetchone()
            # Consume any remaining rows to avoid 'Unread result found'
            cursor.fetchall()
            if existing:
                return False, "You already have an active loan!"

            cursor.execute("""
                INSERT INTO economy_loans
                (user_id, amount, total_with_tax, daily_payment, total_remaining,
                 taken_at, next_due_at, last_payment_at, ping_count, last_ping_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, 0, 'active')
                ON DUPLICATE KEY UPDATE
                    amount = VALUES(amount),
                    total_with_tax = VALUES(total_with_tax),
                    daily_payment = VALUES(daily_payment),
                    total_remaining = VALUES(total_remaining),
                    taken_at = VALUES(taken_at),
                    next_due_at = VALUES(next_due_at),
                    last_payment_at = 0,
                    ping_count = 0,
                    last_ping_at = 0,
                    status = 'active'
            """, (user_id, amount, total_with_tax, daily_payment, total_with_tax, ts, next_due_at))

            cursor.execute("""
                UPDATE economy_users SET wallet = wallet + %s, updated_at = %s WHERE user_id = %s
            """, (amount, ts, user_id))

            conn.commit()
            return True, {'amount': amount, 'total_with_tax': total_with_tax,
                          'daily_payment': daily_payment, 'tax': tax}
        except Error as e:
            print(f"Error taking loan: {e}")
            return False, str(e)
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def get_active_loan(self, user_id):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute("""
                SELECT * FROM economy_loans WHERE user_id = %s AND status = 'active'
                ORDER BY taken_at DESC LIMIT 1
            """, (user_id,))
            return cursor.fetchone()
        except Error as e:
            print(f"Error getting loan: {e}")
            return None
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def pay_loan(self, user_id, payment_amount):
        """Pay toward active loan. Returns (success, message, data)."""
        conn = None
        cursor = None
        result = (False, "Unknown error", None)
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            ts = int(datetime.now().timestamp())

            cursor.execute("""
                SELECT * FROM economy_loans WHERE user_id = %s AND status = 'active'
            """, (user_id,))
            loan = cursor.fetchone()
            # Consume remaining rows to avoid 'Unread result found'
            cursor.fetchall()

            if not loan:
                result = (False, "You don't have an active loan!", None)
            else:
                cursor.execute(
                    "SELECT wallet FROM economy_users WHERE user_id = %s", (user_id,))
                user = cursor.fetchone()
                cursor.fetchall()

                if not user or user['wallet'] < payment_amount:
                    result = (False, "Not enough money in your wallet!", None)
                else:
                    actual_payment = min(payment_amount, loan['total_remaining'])
                    new_remaining = loan['total_remaining'] - actual_payment
                    next_due = ts + 86400

                    if new_remaining <= 0:
                        cursor.execute("""
                            UPDATE economy_loans SET total_remaining = 0, status = 'paid',
                            last_payment_at = %s, next_due_at = %s WHERE id = %s
                        """, (ts, next_due, loan['id']))
                        cursor.execute("""
                            UPDATE economy_users SET wallet = wallet - %s, updated_at = %s WHERE user_id = %s
                        """, (actual_payment, ts, user_id))
                        conn.commit()
                        result = (True, "paid_off", {'paid': actual_payment, 'remaining': 0})
                    else:
                        cursor.execute("""
                            UPDATE economy_loans SET total_remaining = %s, last_payment_at = %s,
                            next_due_at = %s, ping_count = 0 WHERE id = %s
                        """, (new_remaining, ts, next_due, loan['id']))
                        cursor.execute("""
                            UPDATE economy_users SET wallet = wallet - %s, updated_at = %s WHERE user_id = %s
                        """, (actual_payment, ts, user_id))
                        conn.commit()
                        result = (True, "partial", {'paid': actual_payment, 'remaining': new_remaining})
        except Error as e:
            print(f"Error paying loan: {e}")
            result = (False, str(e), None)
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass
        return result

    def get_all_overdue_loans(self):
        """Get all active loans overdue 7+ days (for background task)."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            now = int(datetime.now().timestamp())
            week_ago = now - (7 * 86400)
            cursor.execute("""
                SELECT l.*, u.wallet, u.bank FROM economy_loans l
                LEFT JOIN economy_users u ON l.user_id = u.user_id
                WHERE l.status = 'active'
                AND l.next_due_at < %s
                AND (l.last_payment_at = 0 OR l.last_payment_at < %s)
                AND l.taken_at <= %s
            """, (now, now, week_ago))
            return cursor.fetchall()
        except Error as e:
            print(f"Error getting overdue loans: {e}")
            return []
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def update_loan_ping(self, loan_id, ping_count):
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            now = int(datetime.now().timestamp())
            cursor.execute("""
                UPDATE economy_loans SET ping_count = %s, last_ping_at = %s WHERE id = %s
            """, (ping_count, now, loan_id))
            conn.commit()
        except Error as e:
            print(f"Error updating loan ping: {e}")
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def apply_loan_penalty(self, loan_id, penalty_amount):
        """Deduct penalty from bank. Returns (deducted, bank_remaining)."""
        conn = None
        cursor = None
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            now = int(datetime.now().timestamp())
            cursor.execute("SELECT * FROM economy_loans WHERE id = %s", (loan_id,))
            loan = cursor.fetchone()
            if not loan:
                return 0, 0

            cursor.execute(
                "SELECT bank FROM economy_users WHERE user_id = %s", (loan['user_id'],))
            user = cursor.fetchone()
            bank = user['bank'] if user else 0

            actual_deduct = min(penalty_amount, bank)
            new_bank = bank - actual_deduct
            new_remaining = max(0, loan['total_remaining'] - actual_deduct)

            cursor.execute("""
                UPDATE economy_users SET bank = bank - %s, updated_at = %s WHERE user_id = %s
            """, (actual_deduct, now, loan['user_id']))

            if new_remaining <= 0:
                cursor.execute("""
                    UPDATE economy_loans SET total_remaining = 0, status = 'paid',
                    last_payment_at = %s WHERE id = %s
                """, (now, loan_id))
            else:
                cursor.execute("""
                    UPDATE economy_loans SET total_remaining = %s, last_payment_at = %s,
                    next_due_at = %s WHERE id = %s
                """, (new_remaining, now, now + 86400, loan_id))

            conn.commit()
            return actual_deduct, new_bank
        except Error as e:
            print(f"Error applying loan penalty: {e}")
            return 0, 0
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass


# Global instance
economy_db = EconomyDatabase()
