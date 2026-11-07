"""
Premium Access System for xiel
Handles paid command access checks, granting, and revoking
"""
import discord
from discord.ext import commands
import config
import os
import sys

# Add database directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'database'))
from models import Database, PremiumAccess, BotProfileAccess

# Global DB instance
_db = Database()

# Support server invite link
SUPPORT_SERVER = os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.gg/fQKAjaNKzV')

# All premium command names
PREMIUM_COMMANDS = ['mimic', 'roastvc', 'ghost-ping-detector', 'grant', 'add-trigger', 'corrupt', 'snapshot-server', 'restore-server']

PREMIUM_COMMAND_ALIASES = {
    'all': 'all',
    '*': 'all',
    'mimic': 'mimic',
    'roastvc': 'roastvc',
    'roast-vc': 'roastvc',
    'ghost-ping-detector': 'ghost-ping-detector',
    'ghostpingdetector': 'ghost-ping-detector',
    'ghostping': 'ghost-ping-detector',
    'gpd': 'ghost-ping-detector',
    'grant': 'grant',
    'temp-role': 'grant',
    'temprole': 'grant',
    'add-trigger': 'add-trigger',
    'addtrigger': 'add-trigger',
    'autoreply': 'add-trigger',
    'corrupt': 'corrupt',
    'snapshot-server': 'snapshot-server',
    'snapshot': 'snapshot-server',
    'backup-server': 'snapshot-server',
    'restore-server': 'restore-server',
    'restore': 'restore-server',
}

# Bot profile commands — separate permission, NOT premium
BOT_PROFILE_COMMANDS = ['botavatar', 'botreset']


def normalize_premium_command(command_name: str) -> str | None:
    """Return the canonical premium command name, or None if invalid."""
    if command_name is None:
        return None

    normalized = str(command_name).strip().lower()
    if not normalized:
        return None
    normalized = normalized.lstrip(',.!?/')
    normalized = normalized.replace('_', '-').replace(' ', '-')
    return PREMIUM_COMMAND_ALIASES.get(normalized)


def check_premium(user_id: int, server_id: int, command_name: str) -> bool:
    """Check if a user has premium access for a command in a server"""
    command_name = normalize_premium_command(command_name)
    if not command_name:
        return False

    # Bot owners and co-owners always have access
    if user_id in config.OWNER_IDS or user_id in config.CO_OWNER_IDS:
        return True
    
    session = _db.get_session()
    try:
        # Check for specific command access or 'all' wildcard
        access = session.query(PremiumAccess).filter(
            PremiumAccess.user_id == user_id,
            PremiumAccess.server_id == server_id,
            PremiumAccess.command_name.in_([command_name, 'all'])
        ).first()
        return access is not None
    except Exception as e:
        print(f"Error checking premium: {e}")
        return False
    finally:
        session.close()


def grant_premium(user_id: int, server_id: int, command_name: str, granted_by: int) -> bool:
    """Grant premium access to a user for a command in a server"""
    command_name = normalize_premium_command(command_name)
    if not command_name:
        return False

    session = _db.get_session()
    try:
        # Check if already exists
        existing = session.query(PremiumAccess).filter(
            PremiumAccess.user_id == user_id,
            PremiumAccess.server_id == server_id,
            PremiumAccess.command_name == command_name
        ).first()
        
        if existing:
            return False  # Already granted
        
        access = PremiumAccess(
            user_id=user_id,
            server_id=server_id,
            command_name=command_name,
            granted_by=granted_by
        )
        session.add(access)
        session.commit()
        return True
    except Exception as e:
        print(f"Error granting premium: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def revoke_premium(user_id: int, server_id: int, command_name: str) -> bool:
    """Revoke premium access from a user"""
    command_name = normalize_premium_command(command_name)
    if not command_name:
        return False

    session = _db.get_session()
    try:
        deleted = session.query(PremiumAccess).filter(
            PremiumAccess.user_id == user_id,
            PremiumAccess.server_id == server_id,
            PremiumAccess.command_name == command_name
        ).delete()
        session.commit()
        return deleted > 0
    except Exception as e:
        print(f"Error revoking premium: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_all_premium(server_id: int = None):
    """Get all premium access records, optionally filtered by server"""
    session = _db.get_session()
    try:
        query = session.query(PremiumAccess)
        if server_id:
            query = query.filter(PremiumAccess.server_id == server_id)
        results = query.all()
        return [r.to_dict() for r in results]
    except Exception as e:
        print(f"Error getting premium list: {e}")
        return []
    finally:
        session.close()


def premium_required(command_name: str):
    """Decorator that checks premium access. Shows locked embed if no access."""
    async def predicate(ctx):
        if check_premium(ctx.author.id, ctx.guild.id, command_name):
            return True
        
        # Send locked embed
        embed = discord.Embed(
            title="🔒 Premium Command",
            description=(
                f"**`{config.PREFIX}{command_name}`** is a premium command!\n\n"
                f"To unlock this command, open a ticket in our support server "
                f"and purchase access from the bot owner.\n\n"
                f"**[🎫 Open Ticket in Support Server]({SUPPORT_SERVER})**"
            ),
            color=0xfbbf24  # Gold
        )
        embed.set_footer(text="xiel Premium • Contact the bot owner to purchase")
        await ctx.reply(embed=embed)
        return False
    
    return commands.check(predicate)


def check_bot_profile_access(user_id: int, server_id: int) -> bool:
    """Check if a user has bot profile access (separate from premium)"""
    # Bot owners and co-owners always have access
    if user_id in config.OWNER_IDS or user_id in config.CO_OWNER_IDS:
        return True
    
    session = _db.get_session()
    try:
        access = session.query(BotProfileAccess).filter(
            BotProfileAccess.user_id == user_id,
            BotProfileAccess.server_id == server_id
        ).first()
        return access is not None
    except Exception as e:
        print(f"Error checking bot profile access: {e}")
        return False
    finally:
        session.close()


def bot_profile_required(command_name: str = 'botavatar'):
    """Decorator that checks bot profile access. Shows locked embed if no access."""
    async def predicate(ctx):
        if check_bot_profile_access(ctx.author.id, ctx.guild.id):
            return True
        
        # Send locked embed — different from premium
        embed = discord.Embed(
            title="🔒 Bot Profile Command",
            description=(
                f"**`{config.PREFIX}{command_name}`** requires **Bot Profile Access**!\n\n"
                f"This is a separate permission from premium.\n"
                f"Contact the bot owner to get access granted for your server.\n\n"
                f"**[🎫 Open Ticket in Support Server]({SUPPORT_SERVER})**"
            ),
            color=0xf97316  # Orange
        )
        embed.set_footer(text="xiel • Bot Profile Access required")
        await ctx.reply(embed=embed)
        return False
    
    return commands.check(predicate)
