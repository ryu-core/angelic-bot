"""
Staff Supervision — SQLite Database Module
Manages message_tracker, loa_tracker, and supervision_config tables in data/staff_data.db
"""

import sqlite3
import os
import json
from datetime import date


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'staff_data.db')


class StaffDatabase:
    """Lightweight SQLite wrapper for staff supervision data."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._create_tables()

    # ── connection helper ────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    # ── table creation ───────────────────────────────────────────────────
    def _create_tables(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS message_tracker (
                    user_id       INTEGER PRIMARY KEY,
                    daily_count   INTEGER NOT NULL DEFAULT 0,
                    weekly_count  INTEGER NOT NULL DEFAULT 0
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS loa_tracker (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id         INTEGER NOT NULL,
                    reason          TEXT    NOT NULL,
                    end_date        TEXT    NOT NULL,
                    original_roles  TEXT    NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS supervision_config (
                    guild_id  INTEGER NOT NULL,
                    key       TEXT    NOT NULL,
                    value     TEXT    NOT NULL,
                    PRIMARY KEY (guild_id, key)
                );
            """)
            conn.commit()

    # ══════════════════════════════════════════════════════════════════════
    #  CONFIGURATION (per-guild, stored in DB)
    # ══════════════════════════════════════════════════════════════════════

    def set_config(self, guild_id: int, key: str, value) -> None:
        """Set a config value (auto-serializes lists/dicts to JSON)."""
        if isinstance(value, (list, dict)):
            val_str = json.dumps(value)
        else:
            val_str = str(value)
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO supervision_config (guild_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value;
            """, (guild_id, key, val_str))
            conn.commit()

    def get_config(self, guild_id: int, key: str, default=None):
        """Get a config value. Returns default if not set."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM supervision_config WHERE guild_id = ? AND key = ?;",
                (guild_id, key)
            ).fetchone()
        if row is None:
            return default
        return row['value']

    def get_config_int(self, guild_id: int, key: str, default: int = 0) -> int:
        val = self.get_config(guild_id, key)
        if val is None:
            return default
        try:
            return int(val)
        except ValueError:
            return default

    def get_config_list(self, guild_id: int, key: str) -> list[int]:
        """Get a config value that's stored as a JSON list of ints."""
        val = self.get_config(guild_id, key)
        if val is None:
            return []
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []

    def add_to_config_list(self, guild_id: int, key: str, item: int) -> bool:
        """Add an int to a JSON list config. Returns False if already present."""
        current = self.get_config_list(guild_id, key)
        if item in current:
            return False
        current.append(item)
        self.set_config(guild_id, key, current)
        return True

    def remove_from_config_list(self, guild_id: int, key: str, item: int) -> bool:
        """Remove an int from a JSON list config. Returns False if not found."""
        current = self.get_config_list(guild_id, key)
        if item not in current:
            return False
        current.remove(item)
        self.set_config(guild_id, key, current)
        return True

    def get_all_config(self, guild_id: int) -> dict:
        """Return all config key-value pairs for a guild."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value FROM supervision_config WHERE guild_id = ?;",
                (guild_id,)
            ).fetchall()
        return {r['key']: r['value'] for r in rows}

    # ══════════════════════════════════════════════════════════════════════
    #  MESSAGE TRACKING
    # ══════════════════════════════════════════════════════════════════════

    def increment_message(self, user_id: int) -> None:
        """Upsert: create row if missing, then +1 daily & weekly."""
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO message_tracker (user_id, daily_count, weekly_count)
                VALUES (?, 1, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    daily_count  = daily_count  + 1,
                    weekly_count = weekly_count  + 1;
            """, (user_id,))
            conn.commit()

    def get_counts(self, user_id: int) -> tuple[int, int]:
        """Return (daily_count, weekly_count) for a user. (0, 0) if absent."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT daily_count, weekly_count FROM message_tracker WHERE user_id = ?;",
                (user_id,)
            ).fetchone()
        if row:
            return row['daily_count'], row['weekly_count']
        return 0, 0

    def get_all_counts(self) -> list[dict]:
        """Return all rows as list of dicts for the weekly report."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, daily_count, weekly_count FROM message_tracker ORDER BY weekly_count DESC;"
            ).fetchall()
        return [dict(r) for r in rows]

    def reset_daily(self) -> None:
        """Zero every user's daily_count."""
        with self._connect() as conn:
            conn.execute("UPDATE message_tracker SET daily_count = 0;")
            conn.commit()

    def reset_weekly(self) -> None:
        """Zero every user's weekly_count."""
        with self._connect() as conn:
            conn.execute("UPDATE message_tracker SET weekly_count = 0;")
            conn.commit()

    # ══════════════════════════════════════════════════════════════════════
    #  LOA TRACKING
    # ══════════════════════════════════════════════════════════════════════

    def add_loa(self, user_id: int, reason: str, end_date: str, role_ids: list[int]) -> int:
        """Insert a new LOA row. Returns the row id."""
        roles_str = ','.join(str(r) for r in role_ids)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO loa_tracker (user_id, reason, end_date, original_roles) VALUES (?, ?, ?, ?);",
                (user_id, reason, end_date, roles_str)
            )
            conn.commit()
            return cursor.lastrowid

    def get_active_loa(self, user_id: int) -> dict | None:
        """Return the latest active LOA for a user (end_date > today), or None."""
        today = date.today().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM loa_tracker WHERE user_id = ? AND end_date > ? ORDER BY end_date DESC LIMIT 1;",
                (user_id, today)
            ).fetchone()
        return dict(row) if row else None

    def get_all_active_loas(self) -> list[dict]:
        """Return all active LOA rows."""
        today = date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM loa_tracker WHERE end_date > ? ORDER BY end_date ASC;",
                (today,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_expired_loas(self) -> list[dict]:
        """Return all LOA rows where end_date <= today (ready for auto-removal)."""
        today = date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM loa_tracker WHERE end_date <= ?;",
                (today,)
            ).fetchall()
        return [dict(r) for r in rows]

    def remove_loa(self, loa_id: int) -> None:
        """Delete a specific LOA row by its id."""
        with self._connect() as conn:
            conn.execute("DELETE FROM loa_tracker WHERE id = ?;", (loa_id,))
            conn.commit()

    def remove_loa_by_user(self, user_id: int) -> None:
        """Delete all LOA rows for a user (used by owner /loa-remove)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM loa_tracker WHERE user_id = ?;", (user_id,))
            conn.commit()

    def update_loa(self, user_id: int, new_end_date: str = None, new_reason: str = None) -> bool:
        """Update the latest active LOA for a user. Returns True if a row was updated."""
        today = date.today().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM loa_tracker WHERE user_id = ? AND end_date > ? ORDER BY end_date DESC LIMIT 1;",
                (user_id, today)
            ).fetchone()
            if not row:
                return False

            loa_id = row['id']
            if new_end_date and new_reason:
                conn.execute(
                    "UPDATE loa_tracker SET end_date = ?, reason = ? WHERE id = ?;",
                    (new_end_date, new_reason, loa_id)
                )
            elif new_end_date:
                conn.execute(
                    "UPDATE loa_tracker SET end_date = ? WHERE id = ?;",
                    (new_end_date, loa_id)
                )
            elif new_reason:
                conn.execute(
                    "UPDATE loa_tracker SET reason = ? WHERE id = ?;",
                    (new_reason, loa_id)
                )
            conn.commit()
            return True

    def get_loa_roles(self, user_id: int) -> list[int]:
        """Return stored original role IDs for the user's active LOA."""
        today = date.today().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT original_roles FROM loa_tracker WHERE user_id = ? AND end_date > ? ORDER BY end_date DESC LIMIT 1;",
                (user_id, today)
            ).fetchone()
        if row and row['original_roles']:
            return [int(r) for r in row['original_roles'].split(',') if r.strip()]
        return []

    def is_on_loa(self, user_id: int) -> bool:
        """Quick check: is this user currently on LOA?"""
        return self.get_active_loa(user_id) is not None


# Module-level singleton
staff_db = StaffDatabase()
