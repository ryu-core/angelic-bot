"""
Database module — MySQL only.
Provides a unified Database class used by all cogs.
"""
import json
import os

# MySQL backend (required)
_settings_db = None

try:
    from utils.mysql_settings import settings_db as _mysql_db
    # Quick connection test
    if _mysql_db._connect():
        _mysql_db._disconnect()
        _settings_db = _mysql_db
        print("[OK] Database backend: MySQL")
except Exception as e:
    print(f"[!!] CRITICAL: MySQL database connection failed! {e}")
    print("[!!] Bot settings will NOT persist. Check MySQL credentials.")

# Export the active backend for direct use
settings_db = _settings_db


class Database:
    """Unified key-value store backed by MySQL.
    
    Each 'namespace' maps to a separate logical table in MySQL.
    """

    def __init__(self, filename):
        self.namespace = filename.replace('.json', '')
        self._db = _settings_db

    def load(self):
        """No-op (data is always fresh from DB)."""
        return {}

    def save(self):
        """No-op (data is saved on each set/delete)."""
        pass

    def get(self, key, default=None):
        if not self._db:
            return default
        return self._db.get_setting(self.namespace, '0', str(key), default)

    def set(self, key, value):
        if not self._db:
            return
        self._db.set_setting(self.namespace, '0', str(key), value)

    def delete(self, key):
        if not self._db:
            return
        self._db.delete_setting(self.namespace, '0', str(key))

    def has(self, key):
        if not self._db:
            return False
        return self._db.has_setting(self.namespace, '0', str(key))

    def all(self):
        if not self._db:
            return {}
        return self._db.get_all_settings(self.namespace, '0')

    def clear(self):
        all_data = self.all()
        for key in all_data:
            self.delete(key)


# Create database instances — same names, auto-backed by MySQL
warnings_db = Database('warnings')
blacklist_db = Database('blacklist')
config_db = Database('config')
jail_db = Database('jail')
modstats_db = Database('modstats')
sticky_db = Database('sticky')
timezone_db = Database('timezone')
logs_db = Database('logs')
