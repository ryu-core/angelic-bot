"""
SQLAlchemy Database Models for Discord Bot Dashboard
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
from pathlib import Path

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(BigInteger, primary_key=True)  # Discord user ID
    username = Column(String(255), nullable=False)
    discriminator = Column(String(4))
    avatar = Column(String(255))
    access_token = Column(Text)  # Should be encrypted
    refresh_token = Column(Text)  # Should be encrypted
    token_expires_at = Column(DateTime)
    is_owner = Column(Boolean, default=False)
    is_coowner = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sessions = relationship('Session', back_populates='user', cascade='all, delete-orphan')
    audit_logs = relationship('AuditLog', back_populates='user')
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'username': self.username,
            'discriminator': self.discriminator,
            'avatar': self.avatar,
            'is_owner': self.is_owner,
            'is_coowner': self.is_coowner,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }


class Server(Base):
    __tablename__ = 'servers'
    
    id = Column(BigInteger, primary_key=True)  # Discord guild ID
    name = Column(String(255), nullable=False)
    icon = Column(String(255))
    owner_id = Column(BigInteger)
    member_count = Column(Integer, default=0)
    bot_joined_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    stats = relationship('BotStats', back_populates='server', cascade='all, delete-orphan')
    command_usage = relationship('CommandUsage', back_populates='server')
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'icon': self.icon,
            'owner_id': str(self.owner_id) if self.owner_id else None,
            'members': self.member_count,
            'bot_joined_at': self.bot_joined_at.isoformat() if self.bot_joined_at else None,
            'is_active': self.is_active,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None
        }


class BotStats(Base):
    __tablename__ = 'bot_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.id', ondelete='CASCADE'))
    commands_executed = Column(Integer, default=0)
    messages_processed = Column(Integer, default=0)
    active_users = Column(Integer, default=0)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    server = relationship('Server', back_populates='stats')


class GlobalStats(Base):
    __tablename__ = 'global_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    total_guilds = Column(Integer, default=0)
    total_users = Column(Integer, default=0)
    total_commands = Column(Integer, default=0)
    uptime_seconds = Column(Integer, default=0)
    recorded_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = 'sessions'
    
    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'))
    session_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    
    # Relationships
    user = relationship('User', back_populates='sessions')


class CommandUsage(Base):
    __tablename__ = 'command_usage'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    command_name = Column(String(255), nullable=False)
    user_id = Column(BigInteger)
    server_id = Column(BigInteger, ForeignKey('servers.id', ondelete='SET NULL'))
    executed_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    # Relationships
    server = relationship('Server', back_populates='command_usage')


class AuditLog(Base):
    __tablename__ = 'audit_log'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'))
    action = Column(String(255), nullable=False)
    target_type = Column(String(50))
    target_id = Column(String(255))
    details = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship('User', back_populates='audit_logs')


class GlobalBan(Base):
    """Cross-server ban records — bans a user from ALL servers the bot is in"""
    __tablename__ = 'global_bans'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, unique=True)  # Banned user's Discord ID
    username = Column(String(255))  # Cached username at ban time
    reason = Column(Text)
    banned_by = Column(BigInteger, nullable=False)  # Owner who issued the ban
    banned_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': str(self.user_id),
            'username': self.username,
            'reason': self.reason,
            'banned_by': str(self.banned_by),
            'banned_at': self.banned_at.isoformat() if self.banned_at else None
        }


class PremiumAccess(Base):
    """Tracks paid command access per user per server"""
    __tablename__ = 'premium_access'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    server_id = Column(BigInteger, nullable=False)
    command_name = Column(String(255), nullable=False)  # e.g. 'mimic', 'roastvc', 'ghost-ping-detector', 'botavatar', 'all'
    granted_by = Column(BigInteger, nullable=False)  # Owner who granted access
    granted_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': str(self.user_id),
            'server_id': str(self.server_id),
            'command_name': self.command_name,
            'granted_by': str(self.granted_by),
            'granted_at': self.granted_at.isoformat() if self.granted_at else None
        }


class BotToggle(Base):
    """Per-server bot activation/deactivation"""
    __tablename__ = 'bot_toggles'
    
    server_id = Column(BigInteger, primary_key=True)
    is_enabled = Column(Boolean, default=True)
    toggled_by = Column(BigInteger)  # Owner who toggled
    toggled_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'server_id': str(self.server_id),
            'is_enabled': self.is_enabled,
            'toggled_by': str(self.toggled_by) if self.toggled_by else None,
            'toggled_at': self.toggled_at.isoformat() if self.toggled_at else None
        }


class GhostPingConfig(Base):
    """Per-server ghost ping detector toggle"""
    __tablename__ = 'ghost_ping_config'
    
    server_id = Column(BigInteger, primary_key=True)
    enabled = Column(Boolean, default=False)
    toggled_by = Column(BigInteger)  # User who toggled (must have premium)
    toggled_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'server_id': str(self.server_id),
            'enabled': self.enabled,
            'toggled_by': str(self.toggled_by) if self.toggled_by else None,
            'toggled_at': self.toggled_at.isoformat() if self.toggled_at else None
        }


class ServerWebhook(Base):
    """Legacy per-server profile metadata.

    Webhook columns remain mapped for schema compatibility with existing
    databases, but new application startup no longer creates or stores
    credential-bearing webhook records.
    """
    __tablename__ = 'server_webhooks'
    
    server_id = Column(BigInteger, primary_key=True)
    channel_id = Column(BigInteger, nullable=False)
    webhook_id = Column(BigInteger, nullable=False)
    webhook_url = Column(Text, nullable=False)
    webhook_token = Column(String(255))
    avatar_url = Column(Text)    # Cached bot avatar URL for this server
    banner_url = Column(Text)    # Cached bot banner URL for this server
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        # Never expose webhook_url or webhook_token: both can authorize webhook
        # operations and must be treated as credentials.
        return {
            'server_id': str(self.server_id),
            'channel_id': str(self.channel_id),
            'webhook_id': str(self.webhook_id),
            'avatar_url': self.avatar_url,
            'banner_url': self.banner_url,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class BotProfileAccess(Base):
    """Separate permission for botavatar — NOT tied to premium"""
    __tablename__ = 'bot_profile_access'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    server_id = Column(BigInteger, nullable=False)
    granted_by = Column(BigInteger, nullable=False)  # Owner who granted
    granted_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': str(self.user_id),
            'server_id': str(self.server_id),
            'granted_by': str(self.granted_by),
            'granted_at': self.granted_at.isoformat() if self.granted_at else None
        }



class TempRole(Base):
    """Temporary role assignments that auto-expire"""
    __tablename__ = 'temp_roles'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    role_id = Column(BigInteger, nullable=False)
    granted_by = Column(BigInteger, nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'server_id': str(self.server_id),
            'user_id': str(self.user_id),
            'role_id': str(self.role_id),
            'granted_by': str(self.granted_by),
            'granted_at': self.granted_at.isoformat() if self.granted_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }


class ServerPrefix(Base):
    """Custom prefix per server"""
    __tablename__ = 'server_prefixes'
    
    server_id = Column(BigInteger, primary_key=True)
    prefix = Column(String(10), nullable=False)
    set_by = Column(BigInteger, nullable=False)
    set_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'server_id': str(self.server_id),
            'prefix': self.prefix,
            'set_by': str(self.set_by),
            'set_at': self.set_at.isoformat() if self.set_at else None
        }


class AutoTrigger(Base):
    """Auto-reply triggers — keyword-based auto-responses per server"""
    __tablename__ = 'auto_triggers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, nullable=False)
    phrase = Column(String(255), nullable=False)
    response = Column(Text, nullable=False)
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'server_id': str(self.server_id),
            'phrase': self.phrase,
            'response': self.response,
            'created_by': str(self.created_by),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class CaughtPokemon(Base):
    """Pokemon catch data - replaces JSON file storage"""
    __tablename__ = 'caught_pokemon'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(BigInteger, nullable=False, index=True)  # User who caught this Pokemon
    caught_id = Column(BigInteger, nullable=False, index=True)  # User who was caught
    name = Column(String(255), nullable=False)
    rarity = Column(String(50), nullable=False)  # Common, Rare, Epic, Legendary, Mythic, Divine
    rarity_score = Column(Integer, default=0)
    pokemon_type = Column(String(50), nullable=False)  # Fire, Water, etc.
    level = Column(Integer, default=1)
    
    # Stats
    hp = Column(Integer, nullable=False)
    attack = Column(Integer, nullable=False)
    defense = Column(Integer, nullable=False)
    speed = Column(Integer, nullable=False)
    exp = Column(Integer, default=0)
    
    # Moves (stored as JSON array)
    moves = Column(JSON, nullable=False)
    
    # Metadata
    caught_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'owner_id': str(self.owner_id),
            'caught_id': str(self.caught_id),
            'name': self.name,
            'rarity': self.rarity,
            'rarity_score': self.rarity_score,
            'type': self.pokemon_type,
            'level': self.level,
            'stats': {
                'hp': self.hp,
                'attack': self.attack,
                'defense': self.defense,
                'speed': self.speed
            },
            'exp': self.exp,
            'moves': self.moves,
            'caught_at': self.caught_at.isoformat() if self.caught_at else None
        }


class BattleTeam(Base):
    """User's 3v3 battle team"""
    __tablename__ = 'battle_teams'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, unique=True, index=True)
    
    # Team slots (Pokemon IDs from caught_pokemon table)
    slot1_id = Column(Integer, ForeignKey('caught_pokemon.id', ondelete='SET NULL'))
    slot2_id = Column(Integer, ForeignKey('caught_pokemon.id', ondelete='SET NULL'))
    slot3_id = Column(Integer, ForeignKey('caught_pokemon.id', ondelete='SET NULL'))
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'user_id': str(self.user_id),
            'slot1_id': self.slot1_id,
            'slot2_id': self.slot2_id,
            'slot3_id': self.slot3_id,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# Database connection and session management
def _env(name, default=None):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _build_mysql_url():
    """Build MySQL connection URL from environment variables."""
    from urllib.parse import quote_plus

    user = _env('MYSQL_USER')
    password = _env('MYSQL_PASSWORD')
    host = _env('MYSQL_HOST')
    port = _env('MYSQL_PORT', '3306')
    database = _env('MYSQL_DATABASE')
    if not all([user, password, host, port, database]):
        return None
    return f"mysql+mysqlconnector://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}"


class Database:
    def __init__(self, database_url=None):
        if database_url is None:
            database_url = _env('DATABASE_URL') or _build_mysql_url()
        if not database_url:
            data_dir = Path(__file__).resolve().parent.parent / 'data'
            data_dir.mkdir(exist_ok=True)
            database_url = f"sqlite:///{data_dir / 'dashboard.db'}"
            print(f"⚠️  DATABASE_URL/MySQL env missing; using local SQLite dashboard DB: {data_dir / 'dashboard.db'}")

        if database_url.startswith('sqlite'):
            self.engine = create_engine(
                database_url,
                connect_args={'check_same_thread': False}
            )
        else:
            self.engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                pool_recycle=3600
            )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def create_tables(self):
        """Create all tables"""
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self):
        """Get a new database session"""
        return self.SessionLocal()
    
    def close(self):
        """Close database connection"""
        self.engine.dispose()


# Global database instance — connects to MySQL
db = Database()
db.create_tables()  # Ensure all tables (including caught_pokemon, battle_teams) exist
