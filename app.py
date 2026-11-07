import discord
from discord.ext import commands
import asyncio
import os
import sys
from datetime import datetime, UTC
import importlib.util
import subprocess
from pathlib import Path

from config import (
    TOKEN,
    PREFIX,
    OWNER_IDS,
    CO_OWNER_IDS,
    OPENAI_API_KEY,
    GOOGLE_API_KEY,
    GOOGLE_SEARCH_ENGINE_ID,
    SERPER_API_KEY,
    COLORS,
    EMOJIS,
    RATE_LIMITS,
    ECONOMY,
    ECONOMY_EMOJIS,
)


def ensure_dashboard_dependencies():
    """Install missing dashboard packages before extensions are imported."""
    required_packages = {
        "fastapi": "fastapi==0.139.2",
        "uvicorn": "uvicorn==0.51.0",
        "socketio": "python-socketio==5.16.3",
        "pymongo": "pymongo==4.17.0",
        "itsdangerous": "itsdangerous==2.2.0",
    }
    missing_modules = [
        module_name
        for module_name in required_packages
        if importlib.util.find_spec(module_name) is None
    ]
    if not missing_modules:
        return True

    print(
        "Installing missing dashboard dependencies "
        f"({', '.join(missing_modules)})..."
    )
    install_command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-cache-dir",
        *(required_packages[module_name] for module_name in missing_modules),
    ]
    try:
        subprocess.run(install_command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Automatic dashboard dependency installation failed: {exc}")
        print(
            "Run manually: "
            + " ".join(
                [sys.executable, "-m", "pip", "install"]
                + [required_packages[module_name] for module_name in missing_modules]
            )
        )
        return False

    importlib.invalidate_caches()
    unresolved_modules = [
        module_name
        for module_name in missing_modules
        if importlib.util.find_spec(module_name) is None
    ]
    if unresolved_modules:
        print(
            "Automatic dashboard dependency installation completed, but "
            f"{', '.join(unresolved_modules)} is still unavailable to "
            f"{sys.executable}."
        )
        return False

    print("Dashboard dependencies installed successfully.")
    return True


ensure_dashboard_dependencies()

# Legacy discord.py 2.3.2 installations predate Discord's XChaCha voice mode.
# Patch only that exact legacy version and only when native support
# is absent. Unsupported environments retain their original advertised modes,
# so negotiation fails closed instead of encrypting with a different cipher.
import discord.voice_client as _vc

_XCHACHA_MODE = 'aead_xchacha20_poly1305_rtpsize'


def _install_legacy_voice_patch():
    if (
        _XCHACHA_MODE in _vc.VoiceClient.supported_modes
        and hasattr(_vc.VoiceClient, '_encrypt_aead_xchacha20_poly1305_rtpsize')
    ):
        return

    if discord.__version__ != '2.3.2':
        print(
            f"⚠️  Voice compatibility patch skipped for discord.py "
            f"{discord.__version__}; install the version pinned in "
            "requirements.txt for native support."
        )
        return

    try:
        from nacl.bindings import crypto_aead_xchacha20poly1305_ietf_encrypt
    except (ImportError, OSError) as exc:
        print(f"⚠️  XChaCha voice support unavailable; voice will fail closed: {exc}")
        return

    def _encrypt_aead_xchacha20_poly1305_rtpsize(self, header, data):
        nonce_int = getattr(self, '_lite_nonce', 0)
        if not 0 <= nonce_int < 0xFFFFFFFF:
            raise OverflowError("XChaCha voice nonce exhausted")
        self._lite_nonce = nonce_int + 1
        nonce4 = nonce_int.to_bytes(4, 'big')
        nonce24 = nonce4 + b'\x00' * 20
        encrypted = crypto_aead_xchacha20poly1305_ietf_encrypt(
            bytes(data),
            bytes(header),
            nonce24,
            bytes(self.secret_key),
        )
        return bytes(header) + encrypted + nonce4

    _vc.VoiceClient._encrypt_aead_xchacha20_poly1305_rtpsize = (
        _encrypt_aead_xchacha20_poly1305_rtpsize
    )
    _vc.VoiceClient.supported_modes = (
        _XCHACHA_MODE,
        *_vc.VoiceClient.supported_modes,
    )
    print("✓ Installed discord.py 2.3.2 XChaCha voice compatibility patch")


_install_legacy_voice_patch()


# Configure Windows output before any startup helper prints Unicode.
if sys.platform == 'win32':
    try:
        os.system('chcp 65001 >nul 2>&1')
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


# Auto-setup database on startup (for Pterodactyl compatibility)
try:
    from setup_database import setup_database
    setup_database()
except Exception as e:
    print(f"⚠️  Database auto-setup skipped: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# BOT SETUP
# ─────────────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True


def get_prefix(bot, message):
    """Get prefix for the guild - checks database for custom prefix"""
    if not message.guild:
        return PREFIX

    if hasattr(bot, 'prefix_cache') and message.guild.id in bot.prefix_cache:
        return bot.prefix_cache[message.guild.id]

    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'database'))
        from models import Database, ServerPrefix

        db = Database()
        session = db.get_session()
        try:
            server_prefix = session.query(ServerPrefix).filter_by(server_id=message.guild.id).first()
            if server_prefix:
                if not hasattr(bot, 'prefix_cache'):
                    bot.prefix_cache = {}
                bot.prefix_cache[message.guild.id] = server_prefix.prefix
                return server_prefix.prefix
        finally:
            session.close()
    except Exception:
        pass

    return PREFIX


class AngelicBot(commands.Bot):
    """Bot lifecycle with one-time setup and deterministic shutdown."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._presence_task = None
        self._stats_save_task = None
        self._command_sync_lock = None
        self._global_commands_synced = False
        self._guild_commands_reconciled = False
        self._shutdown_saved = False

    async def setup_hook(self):
        """Load extensions and publish the global command source once per run."""
        await load_cogs()
        self._command_sync_lock = asyncio.Lock()
        await self.sync_global_commands()

    async def sync_global_commands(self):
        """Publish global commands once, retrying safely after transient errors."""
        if self._global_commands_synced:
            return True
        if self._command_sync_lock is None:
            self._command_sync_lock = asyncio.Lock()

        async with self._command_sync_lock:
            if self._global_commands_synced:
                return True
            try:
                synced = await self.tree.sync()
            except Exception as exc:
                print(f'⚠️  Failed to sync global slash commands: {exc}')
                return False

            self._global_commands_synced = True
            print(f'✓ Synced {len(synced)} global slash command(s)')
            return True

    async def close(self):
        """Cancel owned tasks and persist stats on every shutdown path."""
        tasks = [
            task
            for task in (self._presence_task, self._stats_save_task)
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if not self._shutdown_saved:
            self._shutdown_saved = True
            print('\n💾 Saving persistent stats before shutdown...')
            save_persistent_stats()

        await super().close()


bot = AngelicBot(
    command_prefix=get_prefix,
    intents=intents,
    help_command=None  # Custom help in cogs/help.py
)

# Storage for snipes
bot.snipes = {}
bot.edit_snipes = {}

# Persistent stats tracking
bot.start_time = datetime.now(UTC)
bot.commands_executed = 0


# ─────────────────────────────────────────────────────────────────────────────
# PERSISTENT STATS
# ─────────────────────────────────────────────────────────────────────────────
def load_persistent_stats():
    """Load stats from MySQL persistent_stats table"""
    try:
        from utils.mysql_settings import settings_db as _stats_db
        bot.commands_executed = _stats_db.get_persistent_stat('total_commands_used', 0)
        print(f'📊 Loaded persistent stats: {bot.commands_executed} commands')
    except Exception as e:
        print(f'⚠️  Failed to load persistent stats: {e}')


def save_persistent_stats():
    """Save stats to MySQL persistent_stats table"""
    try:
        from utils.mysql_settings import settings_db as _stats_db
        total_members = sum(guild.member_count or 0 for guild in bot.guilds)
        _stats_db.set_persistent_stats({
            'total_members': total_members,
            'total_commands_used': bot.commands_executed,
            'last_updated': datetime.now(UTC).isoformat(),
        })
        print(f'💾 Saved persistent stats: {bot.commands_executed} commands, {total_members} members')
    except Exception as e:
        print(f'⚠️  Failed to save persistent stats: {e}')


load_persistent_stats()


# ─────────────────────────────────────────────────────────────────────────────
# BANNER & BOT EVENTS
# ─────────────────────────────────────────────────────────────────────────────
def print_banner():
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           XIEL - Premium Edition                      ║
║                                                           ║
║   ● Moderation  ● Utilities  ● Games  ● AI Chat          ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
""")


@bot.event
async def on_ready():
    print(f'\n✓ Bot is online!')
    print(f'├─ Logged in as: {bot.user.name}')
    print(f'├─ Serving: {len(bot.guilds)} servers')
    print(f'├─ Prefix: {PREFIX} (default)')
    print(f'└─ User ID: {bot.user.id}\n')

    bot.prefix_cache = {}

    if not bot._global_commands_synced:
        await bot.sync_global_commands()

    # Older releases copied global commands into every guild. Reconcile each
    # guild once so those stale copies are removed without mutating the global
    # source tree. Global commands automatically apply to newly joined guilds.
    if bot._global_commands_synced and not bot._guild_commands_reconciled:
        reconciled = 0
        for guild in bot.guilds:
            try:
                await bot.tree.sync(guild=guild)
                reconciled += 1
            except Exception as exc:
                print(f'⚠️  Failed to reconcile slash commands in {guild.name}: {exc}')
        bot._guild_commands_reconciled = reconciled == len(bot.guilds)
        print(f'✓ Reconciled guild slash commands in {reconciled} guild(s)')

    if bot._presence_task is None or bot._presence_task.done():
        bot._presence_task = asyncio.create_task(
            presence_loop(),
            name='presence-loop',
        )
    if bot._stats_save_task is None or bot._stats_save_task.done():
        bot._stats_save_task = asyncio.create_task(
            stats_save_loop(),
            name='stats-save-loop',
        )


async def presence_loop():
    """Update bot presence every 30 seconds"""
    await bot.wait_until_ready()
    activities = [
        discord.Activity(type=discord.ActivityType.playing, name=f"{PREFIX}help"),
        discord.Activity(type=discord.ActivityType.watching, name=f"{len(bot.guilds)} servers"),
    ]

    activity_index = 0
    while not bot.is_closed():
        try:
            await bot.change_presence(activity=activities[activity_index])
            activity_index = (activity_index + 1) % len(activities)
        except Exception:
            pass
        await asyncio.sleep(30)


async def stats_save_loop():
    """Save persistent stats in one periodic batch."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(300)
        save_persistent_stats()


# ─────────────────────────────────────────────────────────────────────────────
# SNIPE TRACKING
# ─────────────────────────────────────────────────────────────────────────────
def track_deleted_message(message):
    """Track deleted message for snipe command"""
    if message.author.bot:
        return

    if message.channel.id not in bot.snipes:
        bot.snipes[message.channel.id] = []

    bot.snipes[message.channel.id].insert(0, {
        'content': message.content,
        'author': message.author,
        'created_at': message.created_at,
        'attachments': [att.url for att in message.attachments]
    })
    bot.snipes[message.channel.id] = bot.snipes[message.channel.id][:10]


def track_edited_message(before, after):
    """Track edited message for editsnipe command"""
    if before.author.bot or before.content == after.content:
        return

    if before.channel.id not in bot.edit_snipes:
        bot.edit_snipes[before.channel.id] = []

    bot.edit_snipes[before.channel.id].insert(0, {
        'before': before.content,
        'after': after.content,
        'author': before.author,
        'edited_at': after.edited_at or discord.utils.utcnow()
    })
    bot.edit_snipes[before.channel.id] = bot.edit_snipes[before.channel.id][:5]


bot.track_snipe = track_deleted_message
bot.track_editsnipe = track_edited_message


# ─────────────────────────────────────────────────────────────────────────────
# COMMAND & MESSAGE EVENTS
# ─────────────────────────────────────────────────────────────────────────────
@bot.event
async def on_command_completion(ctx):
    """Track successful command executions"""
    bot.commands_executed += 1


def _strip_prefix(value, prefix):
    value = (value or "").strip()
    if prefix and value.startswith(prefix):
        value = value[len(prefix):].lstrip()
    elif PREFIX and value.startswith(PREFIX):
        value = value[len(PREFIX):].lstrip()
    return value


async def process_prefix_commands(message):
    """Run prefix commands after applying saved guild aliases."""
    if message.author.bot or not message.guild:
        return

    prefix = get_prefix(bot, message)
    if not prefix or not message.content.startswith(prefix):
        return

    without_prefix = message.content[len(prefix):]
    if not without_prefix.strip():
        return

    cmd_name = without_prefix.split(maxsplit=1)[0].lower()
    rest = without_prefix[len(cmd_name):]

    try:
        from utils.database import settings_db
        alias_cmd = settings_db.get_alias(message.guild.id, cmd_name) if settings_db else None
    except Exception:
        alias_cmd = None

    if alias_cmd:
        target = _strip_prefix(alias_cmd, prefix)
        if target:
            message.content = f"{prefix}{target}{rest}"

    await bot.process_commands(message)


@bot.event
async def on_message(message):
    """Handle sticky messages"""
    if message.author.bot:
        return

    await process_prefix_commands(message)

    from utils.database import sticky_db
    channel_id = str(message.channel.id)

    if sticky_db.has(channel_id):
        sticky_data = sticky_db.get(channel_id)

        try:
            old_msg = await message.channel.fetch_message(int(sticky_data['message_id']))
            await old_msg.delete()
        except Exception:
            pass

        try:
            embed = discord.Embed(
                description=sticky_data['message'],
                color=COLORS['primary']
            )
            embed.set_footer(text='📌 Sticky Message')
            new_msg = await message.channel.send(embed=embed)
            sticky_data['message_id'] = str(new_msg.id)
            sticky_db.set(channel_id, sticky_data)
        except Exception:
            pass


@bot.event
async def on_message_edit(before, after):
    """Process commands edited into messages."""
    if after.author.bot or not after.guild or before.content == after.content:
        return

    await process_prefix_commands(after)


@bot.event
async def on_guild_join(guild):
    """Log new guilds; global application commands apply automatically."""
    print(f'📥 Joined server: {guild.name} ({guild.id})')


# ─────────────────────────────────────────────────────────────────────────────
# COG LOADING & ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
async def load_cogs():
    """Load all cog files"""
    cogs_dir = Path(__file__).resolve().parent / 'cogs'
    if not cogs_dir.is_dir():
        print("⚠️  No cogs directory found")
        return

    for cog_path in sorted(cogs_dir.glob('*.py')):
        if cog_path.name != '__init__.py':
            try:
                await bot.load_extension(f'cogs.{cog_path.stem}')
                print(f'✓ Loaded cog: {cog_path.stem}')
            except Exception as e:
                print(f'❌ Failed to load {cog_path.name}: {e}')


async def main():
    """Main function for Pterodactyl compatibility"""
    if not TOKEN or not TOKEN.strip():
        print("\nERROR: DISCORD_TOKEN is missing or blank. Set a fresh bot token in Pterodactyl Variables or your private .env file.")
        return

    print_banner()

    async with bot:
        print('\n⏳ Connecting to Discord...\n')
        await bot.start(TOKEN)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\n\n🛑 Bot stopped by user')
    except Exception as e:
        print(f'\n\n❌ Fatal error: {e}')
