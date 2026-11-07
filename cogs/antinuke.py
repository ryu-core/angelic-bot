"""antinuke.py — Full rewrite of AntiNuke cog.

Key fixes over original:
 1. Recovery runs AFTER the nuker is stopped (ban bot → punish human → recover)
    so the guild is still in a sane state when we restore channels/roles.
 2. Audit dedup is skipped when filtering by target_id, so every channel/role
    in a mass nuke gets its own audit lookup instead of being silently skipped.
 3. Cache refresh in on_guild_channel_create is done BEFORE the audit handler
    so subsequent delete events still find the original snapshots.
 4. Nuke bot AND inviter are both stopped immediately before recovery runs.
 5. Retry window increased to 6 × 1.5 s to survive Discord's audit-log lag.
 6. Channel/role recovery uses asyncio.gather so nothing blocks the event loop
    during a mass nuke.
 7. Owner DM notification with a rich embed when antinuke triggers.
 8. antinuke config / antinuke list show whitelist, admins, and trusted users.
"""

import asyncio
import time
from collections import defaultdict
from datetime import timedelta

import discord
from discord.ext import commands, tasks

from app import COLORS, OWNER_IDS
from utils.antinuke_core import (
    COMMAND_MODULE_MAP,
    DEFAULT_MODULES,
    VALID_PUNISHMENTS,
    default_config,
    get_module_config,
    merge_config,
    normalize_module,
    parse_bool,
    parse_module_flags,
)
from utils.database import settings_db


# ─── tunables ────────────────────────────────────────────────────────────────
CONFIG_NAMESPACE        = "antinuke_v3"
LEGACY_CONFIG_NAMESPACE = "antinuke_v2"
CONFIG_KEY              = "config"
TRACK_WINDOW            = 10        # rolling window in seconds
TRACK_CLEANUP_SECONDS   = 30        # how often the in-memory tracker is pruned
CACHE_REFRESH_SECONDS   = 300       # how often guild snapshots are refreshed
AUDIT_RETRY_ATTEMPTS    = 6         # was 4 — extra headroom for Discord lag
AUDIT_RETRY_DELAY       = 1.5       # was 0.8
AUDIT_DEDUPE_SECONDS    = 60        # how long a processed-audit key is remembered
# ─────────────────────────────────────────────────────────────────────────────


class AntiNuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # nuke_tracker[guild_id][user_id][module] = [timestamp, ...]
        if not hasattr(self.bot, "nuke_tracker"):
            self.bot.nuke_tracker = {}
        # guild_cache[guild_id] = {channels: {id: snapshot}, roles: {id: snapshot}}
        if not hasattr(self.bot, "guild_cache"):
            self.bot.guild_cache = {}
        # bot_adder_cache[guild_id][bot_id] = {user_id, time}
        if not hasattr(self.bot, "bot_adder_cache"):
            self.bot.bot_adder_cache = {}

        # recovery_tracker[guild_id][user_id][module] = [{time, payload}, ...]
        self.recovery_tracker: dict = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )
        self.last_owner_warning: dict = {}
        # processed_audits[(guild_id, action, entry_id_or_hash)] = timestamp
        self.processed_audits: dict = {}

        self.cleanup_tracker.start()
        self.refresh_guild_cache.start()

    @property
    def qualified_name(self):
        return "Security"

    def cog_unload(self):
        for loop in (self.cleanup_tracker, self.refresh_guild_cache):
            try:
                loop.cancel()
            except Exception as exc:
                print(f"antinuke unload loop error: {exc}")

    # =========================================================================
    # Config helpers
    # =========================================================================

    def _get_config(self, guild_id: int) -> dict:
        try:
            raw = None
            if settings_db:
                raw = settings_db.get_setting(CONFIG_NAMESPACE, guild_id, CONFIG_KEY, None)
                if raw is None:
                    raw = settings_db.get_setting(LEGACY_CONFIG_NAMESPACE, guild_id, CONFIG_KEY, None)
            return merge_config(raw)
        except Exception as exc:
            print(f"antinuke get_config error: {exc}")
            return default_config()

    def _save_config(self, guild_id: int, config: dict):
        try:
            if settings_db:
                settings_db.set_setting(CONFIG_NAMESPACE, guild_id, CONFIG_KEY, merge_config(config))
        except Exception as exc:
            print(f"antinuke save_config error: {exc}")

    def _reset_config(self, guild_id: int):
        try:
            if settings_db:
                settings_db.delete_setting(CONFIG_NAMESPACE, guild_id, CONFIG_KEY)
                settings_db.delete_setting(LEGACY_CONFIG_NAMESPACE, guild_id, CONFIG_KEY)
        except Exception as exc:
            print(f"antinuke reset_config error: {exc}")

    # =========================================================================
    # Access / whitelist helpers
    # =========================================================================

    def _is_owner(self, guild: discord.Guild, user_id: int) -> bool:
        return bool(guild and user_id and (user_id == guild.owner_id or user_id in OWNER_IDS))

    def _whitelist_role(self, guild_id: int, user_id: int):
        try:
            if not settings_db or not user_id:
                return None
            return settings_db.get_antinuke_whitelist_role(guild_id, user_id)
        except Exception as exc:
            print(f"antinuke whitelist lookup error: {exc}")
            return None

    def _is_antinuke_admin(self, guild_id: int, user_id: int) -> bool:
        return self._whitelist_role(guild_id, user_id) == "admin"

    def _is_whitelisted(self, guild_id: int, user_id: int) -> bool:
        return self._whitelist_role(guild_id, user_id) in {"whitelisted", "admin"}

    def _is_trusted(self, guild_id: int, user_id: int) -> bool:
        return self._whitelist_role(guild_id, user_id) == "trusted"

    def _is_exempt(self, guild: discord.Guild, user_id: int, module: str = None) -> bool:
        try:
            if not guild or not user_id:
                return True
            if self.bot.user and user_id == self.bot.user.id:
                return True
            if self._is_owner(guild, user_id):
                return True
            if self._is_whitelisted(guild.id, user_id):
                return True
            if normalize_module(module) == "botadd" and self._is_trusted(guild.id, user_id):
                return True
            return False
        except Exception as exc:
            print(f"antinuke exempt check error: {exc}")
            return True

    async def _ensure_command_access(self, ctx: commands.Context) -> bool:
        try:
            if self._is_owner(ctx.guild, ctx.author.id) or self._is_antinuke_admin(ctx.guild.id, ctx.author.id):
                return True
            await ctx.reply("only the server owner, bot owners, or antinuke admins can use this.", mention_author=False)
            return False
        except Exception as exc:
            print(f"antinuke access check error: {exc}")
            return False

    async def _ensure_owner_access(self, ctx: commands.Context) -> bool:
        try:
            if self._is_owner(ctx.guild, ctx.author.id):
                return True
            await ctx.reply("only the server owner or bot owners can manage antinuke admins.", mention_author=False)
            return False
        except Exception as exc:
            print(f"antinuke owner access error: {exc}")
            return False

    async def _ensure_db(self, ctx: commands.Context) -> bool:
        if settings_db:
            return True
        await ctx.reply("the antinuke database is not available right now.", mention_author=False)
        return False

    # =========================================================================
    # Embed / send helpers
    # =========================================================================

    def _embed(self, title: str, description: str, color: int = None) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color or COLORS.get("primary", 0x3498DB),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="AntiNuke")
        return embed

    async def _safe_send(self, destination, *, content=None, embed=None):
        try:
            if destination:
                await destination.send(content=content, embed=embed)
        except Exception as exc:
            print(f"antinuke safe_send error: {exc}")

    async def _warn_owner(self, guild: discord.Guild, message: str):
        """Plain-text DM to the owner for permission/config warnings."""
        try:
            now = time.time()
            key = (guild.id, message)
            if now - self.last_owner_warning.get(key, 0) < 60:
                return
            self.last_owner_warning[key] = now
            owner = guild.owner or await self.bot.fetch_user(guild.owner_id)
            if owner:
                await owner.send(f"**{guild.name}:** {message}")
        except Exception as exc:
            print(f"antinuke warn_owner error: {exc}")

    async def _notify_owner_trigger(
        self, guild: discord.Guild, user, module: str, count: int, punishment: str
    ):
        """Rich embed DM to the guild owner when antinuke punishes someone."""
        try:
            now = time.time()
            key = (guild.id, "trigger", getattr(user, "id", 0), module)
            if now - self.last_owner_warning.get(key, 0) < 30:
                return
            self.last_owner_warning[key] = now
            owner = guild.owner or await self.bot.fetch_user(guild.owner_id)
            if not owner:
                return
            desc = (
                f"**Guild:** {guild.name} (`{guild.id}`)\n"
                f"**User:** {self._target_name(user)} (`{getattr(user, 'id', '?')}`)\n"
                f"**Module:** `{module}`\n"
                f"**Actions in {TRACK_WINDOW}s:** `{count}`\n"
                f"**Punishment:** `{punishment}`"
            )
            embed = discord.Embed(
                title="⚠️ AntiNuke Triggered",
                color=COLORS.get("error", 0xe74c3c),
                description=desc,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text="AntiNuke")
            await owner.send(embed=embed)
        except Exception as exc:
            print(f"antinuke notify_owner_trigger error: {exc}")

    async def _log_action(self, guild: discord.Guild, title: str, description: str, color: int = None):
        try:
            config     = self._get_config(guild.id)
            channel_id = config.get("log_channel_id")
            channel    = guild.get_channel(int(channel_id)) if channel_id else None
            if not channel:
                channel = guild.system_channel
            if not channel:
                me = guild.me
                for tc in guild.text_channels:
                    perms = tc.permissions_for(me)
                    if perms.view_channel and perms.send_messages:
                        channel = tc
                        break
            embed = self._embed(title, description, color)
            if channel:
                await self._safe_send(channel, embed=embed)
            else:
                print(f"antinuke log fallback missing in guild {guild.id}: {title} - {description}")
        except Exception as exc:
            print(f"antinuke log_action error: {exc}")

    def _target_name(self, user) -> str:
        return (
            getattr(user, "mention", None)
            or getattr(user, "name", None)
            or f"user {getattr(user, 'id', 'unknown')}"
        )

    async def _resolve_user_id(self, ctx: commands.Context, target: str):
        if not target:
            return None, None
        cleaned = str(target).strip().removeprefix("<@").removeprefix("!").removesuffix(">")
        if not cleaned.isdigit():
            return None, None
        user_id = int(cleaned)
        member  = ctx.guild.get_member(user_id)
        if member:
            return user_id, member.mention
        user = self.bot.get_user(user_id)
        if not user:
            try:
                user = await self.bot.fetch_user(user_id)
            except Exception:
                user = None
        return user_id, (user.mention if user else str(user_id))

    # =========================================================================
    # Audit log helpers
    # =========================================================================

    def _audit_key(self, guild_id: int, action, entry) -> tuple:
        entry_id = getattr(entry, "id", None)
        if entry_id:
            return (guild_id, str(action), entry_id)
        target_id  = getattr(getattr(entry, "target", None), "id", None)
        user_id    = getattr(getattr(entry, "user",   None), "id", None)
        created_ts = int(getattr(entry, "created_at", discord.utils.utcnow()).timestamp())
        return (guild_id, str(action), target_id, user_id, created_ts)

    def _audit_is_processed(self, guild_id: int, action, entry) -> bool:
        return self._audit_key(guild_id, action, entry) in self.processed_audits

    def _mark_audit_processed(self, guild_id: int, action, entry):
        self.processed_audits[self._audit_key(guild_id, action, entry)] = time.time()

    async def _audit_entry(
        self,
        guild: discord.Guild,
        action,
        target_id: int = None,
        newer_than: float = 20,
        limit: int = 15,
    ):
        """
        Fetch the most recent audit-log entry for *action*.

        KEY FIX vs original:
        - When target_id is given we skip the processed-entry dedup check.
          Every channel/role has a unique target_id so deduplication by entry
          would cause all but the first to return None during a mass nuke.
        - Retry count raised to AUDIT_RETRY_ATTEMPTS (6) × AUDIT_RETRY_DELAY (1.5 s).
        """
        if not action:
            return None

        for attempt in range(AUDIT_RETRY_ATTEMPTS):
            if attempt:
                await asyncio.sleep(AUDIT_RETRY_DELAY)
            try:
                entries = [e async for e in guild.audit_logs(limit=limit, action=action)]
            except discord.Forbidden:
                await self._warn_owner(
                    guild,
                    "I cannot read audit logs for antinuke. Please give me the **View Audit Log** permission.",
                )
                return None
            except Exception as exc:
                print(f"antinuke audit fetch error (attempt {attempt + 1}): {exc}")
                continue

            now = time.time()
            for entry in entries:
                try:
                    if now - entry.created_at.timestamp() > newer_than:
                        continue

                    # Only apply dedup when NOT filtering by target_id.
                    # If we ARE filtering by target_id each lookup is for a
                    # distinct object so the same executor-entry must NOT be
                    # suppressed across multiple events (e.g. mass channel delete).
                    if target_id is None and self._audit_is_processed(guild.id, action, entry):
                        continue

                    entry_target_id = getattr(getattr(entry, "target", None), "id", None)
                    if target_id is not None and entry_target_id != target_id:
                        continue

                    return entry
                except Exception as exc:
                    print(f"antinuke audit entry parse error: {exc}")

        print(f"antinuke audit miss: guild={guild.id} action={action} target={target_id}")
        return None

    def _remember_bot_adder(self, guild_id: int, bot_id: int, user_id: int):
        try:
            self.bot.bot_adder_cache.setdefault(guild_id, {})[bot_id] = {
                "user_id": user_id,
                "time":    time.time(),
            }
        except Exception as exc:
            print(f"antinuke remember_bot_adder error: {exc}")

    def _get_bot_adder(self, guild_id: int, bot_id: int):
        try:
            payload = self.bot.bot_adder_cache.get(guild_id, {}).get(bot_id)
            if not payload or time.time() - payload.get("time", 0) > 31_536_000:
                return None
            return payload.get("user_id")
        except Exception as exc:
            print(f"antinuke get_bot_adder error: {exc}")
            return None

    async def _resolve_executor(self, guild: discord.Guild, entry):
        """
        If the executor in an audit entry is itself a bot, walk back through
        bot_add audit logs to find the human who invited it.
        """
        try:
            executor = getattr(entry, "user", None)
            if not executor:
                return None
            if self.bot.user and executor.id == self.bot.user.id:
                return executor
            if not getattr(executor, "bot", False):
                return executor

            cached_adder_id = self._get_bot_adder(guild.id, executor.id)
            if cached_adder_id:
                return guild.get_member(cached_adder_id) or await self.bot.fetch_user(cached_adder_id)

            bot_add_entry = await self._audit_entry(
                guild,
                discord.AuditLogAction.bot_add,
                target_id=executor.id,
                newer_than=31_536_000,
                limit=50,
            )
            if bot_add_entry and getattr(bot_add_entry, "user", None) and not bot_add_entry.user.bot:
                self._remember_bot_adder(guild.id, executor.id, bot_add_entry.user.id)
                return bot_add_entry.user
            return executor
        except Exception as exc:
            print(f"antinuke resolve_executor error: {exc}")
            return None

    async def _resolve_audit_actor(self, guild: discord.Guild, entry):
        """Returns (human_executor, [linked_bots_to_also_ban])."""
        try:
            actor       = getattr(entry, "user", None)
            executor    = await self._resolve_executor(guild, entry)
            linked_bots = []
            if actor and getattr(actor, "bot", False) and (not self.bot.user or actor.id != self.bot.user.id):
                linked_bots.append(actor)
            return executor, linked_bots
        except Exception as exc:
            print(f"antinuke resolve_audit_actor error: {exc}")
            return None, []

    # =========================================================================
    # Snapshot helpers (for recovery)
    # =========================================================================

    def _overwrites_to_payload(self, channel: discord.abc.GuildChannel) -> list:
        payload = []
        try:
            for target, overwrite in channel.overwrites.items():
                allow, deny = overwrite.pair()
                payload.append({
                    "target_id":   target.id,
                    "target_type": "role" if isinstance(target, discord.Role) else "member",
                    "allow":       allow.value,
                    "deny":        deny.value,
                })
        except Exception as exc:
            print(f"antinuke overwrite snapshot error: {exc}")
        return payload

    def _snapshot_channel(self, channel: discord.abc.GuildChannel) -> dict | None:
        try:
            base = {
                "recovery_type": "channel_delete",
                "id":            channel.id,
                "name":          channel.name,
                "type":          str(channel.type),
                "position":      channel.position,
                "category_id":   getattr(channel.category, "id", None),
                "overwrites":    self._overwrites_to_payload(channel),
            }
            if isinstance(channel, discord.TextChannel):
                base.update(topic=channel.topic, nsfw=channel.nsfw, slowmode_delay=channel.slowmode_delay)
            elif isinstance(channel, discord.VoiceChannel):
                base.update(bitrate=channel.bitrate, user_limit=channel.user_limit, nsfw=channel.nsfw)
            elif isinstance(channel, discord.StageChannel):
                base.update(bitrate=channel.bitrate, user_limit=channel.user_limit, topic=channel.topic)
            elif isinstance(channel, discord.ForumChannel):
                base.update(
                    topic=channel.topic,
                    nsfw=channel.nsfw,
                    slowmode_delay=channel.slowmode_delay,
                    default_auto_archive_duration=channel.default_auto_archive_duration,
                )
            return base
        except Exception as exc:
            print(f"antinuke channel snapshot error: {exc}")
            return None

    def _snapshot_role(self, role: discord.Role) -> dict | None:
        try:
            return {
                "recovery_type": "role_delete",
                "id":          role.id,
                "name":        role.name,
                "permissions": role.permissions.value,
                "color":       role.color.value,
                "hoist":       role.hoist,
                "mentionable": role.mentionable,
                "position":    role.position,
            }
        except Exception as exc:
            print(f"antinuke role snapshot error: {exc}")
            return None

    async def _snapshot_emoji(self, emoji: discord.Emoji) -> dict | None:
        try:
            image = None
            try:
                image = await emoji.read()
            except Exception as exc:
                print(f"antinuke emoji image snapshot warning: {exc}")
            return {
                "recovery_type": "emoji_delete",
                "id":       emoji.id,
                "name":     emoji.name,
                "image":    image,
                "role_ids": [r.id for r in getattr(emoji, "roles", [])],
            }
        except Exception as exc:
            print(f"antinuke emoji snapshot error: {exc}")
            return None

    # =========================================================================
    # Guild cache management
    # =========================================================================

    def _refresh_single_guild_cache(self, guild: discord.Guild):
        try:
            self.bot.guild_cache[guild.id] = {
                "updated_at": time.time(),
                "channels": {
                    ch.id: snap
                    for ch in guild.channels
                    if (snap := self._snapshot_channel(ch))
                },
                "roles": {
                    role.id: snap
                    for role in guild.roles
                    if role != guild.default_role and (snap := self._snapshot_role(role))
                },
            }
        except Exception as exc:
            print(f"antinuke refresh guild cache error: {exc}")

    def _channel_snapshot_from_cache(self, guild_id: int, channel_id: int) -> dict | None:
        return self.bot.guild_cache.get(guild_id, {}).get("channels", {}).get(channel_id)

    def _role_snapshot_from_cache(self, guild_id: int, role_id: int) -> dict | None:
        return self.bot.guild_cache.get(guild_id, {}).get("roles", {}).get(role_id)

    # =========================================================================
    # Recovery helpers
    # =========================================================================

    def _build_overwrites(self, guild: discord.Guild, payloads: list) -> dict:
        overwrites = {}
        try:
            for item in payloads or []:
                target = (
                    guild.get_role(item["target_id"])
                    if item["target_type"] == "role"
                    else guild.get_member(item["target_id"])
                )
                if not target:
                    continue
                allow = discord.Permissions(item["allow"])
                deny  = discord.Permissions(item["deny"])
                overwrites[target] = discord.PermissionOverwrite.from_pair(allow, deny)
        except Exception as exc:
            print(f"antinuke overwrite rebuild error: {exc}")
        return overwrites

    async def _restore_channel(self, guild: discord.Guild, snapshot: dict) -> discord.abc.GuildChannel | None:
        try:
            category   = guild.get_channel(snapshot.get("category_id"))
            overwrites = self._build_overwrites(guild, snapshot.get("overwrites", []))
            kwargs = {
                "name":       snapshot.get("name", "restored-channel"),
                "overwrites": overwrites,
                "position":   snapshot.get("position", 0),
                "reason":     "AntiNuke recovery",
            }
            if isinstance(category, discord.CategoryChannel):
                kwargs["category"] = category

            ch_type = snapshot.get("type")
            if ch_type == "category":
                kwargs.pop("category", None)
                return await guild.create_category(**kwargs)
            if ch_type == "voice":
                kwargs.update(bitrate=snapshot.get("bitrate"), user_limit=snapshot.get("user_limit", 0))
                return await guild.create_voice_channel(**kwargs)
            if ch_type == "stage_voice":
                kwargs.update(bitrate=snapshot.get("bitrate"), user_limit=snapshot.get("user_limit", 0))
                return await guild.create_stage_channel(**kwargs)
            if ch_type == "forum":
                creator = getattr(guild, "create_forum", None) or getattr(guild, "create_forum_channel", None)
                if not creator:
                    return None
                kwargs.update(topic=snapshot.get("topic"), nsfw=snapshot.get("nsfw", False))
                if snapshot.get("default_auto_archive_duration"):
                    kwargs["default_auto_archive_duration"] = snapshot["default_auto_archive_duration"]
                return await creator(**kwargs)
            # Default: text channel
            kwargs.update(
                topic=snapshot.get("topic"),
                nsfw=snapshot.get("nsfw", False),
                slowmode_delay=snapshot.get("slowmode_delay", 0),
            )
            return await guild.create_text_channel(**kwargs)
        except Exception as exc:
            print(f"antinuke restore_channel error: {exc}")
            return None

    async def _restore_role(self, guild: discord.Guild, snapshot: dict) -> discord.Role | None:
        try:
            role = await guild.create_role(
                name=snapshot.get("name", "restored-role"),
                permissions=discord.Permissions(snapshot.get("permissions", 0)),
                color=discord.Color(snapshot.get("color", 0)),
                hoist=snapshot.get("hoist", False),
                mentionable=snapshot.get("mentionable", False),
                reason="AntiNuke recovery",
            )
            try:
                await role.edit(position=snapshot.get("position", role.position), reason="AntiNuke recovery")
            except Exception as exc:
                print(f"antinuke restore_role position error: {exc}")
            return role
        except Exception as exc:
            print(f"antinuke restore_role error: {exc}")
            return None

    async def _restore_emoji(self, guild: discord.Guild, snapshot: dict) -> discord.Emoji | None:
        try:
            image = snapshot.get("image")
            if not image:
                return None
            roles = [r for rid in snapshot.get("role_ids", []) if (r := guild.get_role(rid))]
            return await guild.create_custom_emoji(
                name=snapshot.get("name", "restored_emoji"),
                image=image,
                roles=roles,
                reason="AntiNuke recovery",
            )
        except Exception as exc:
            print(f"antinuke restore_emoji error: {exc}")
            return None

    async def _restore_bans(self, guild: discord.Guild, user_ids: list[int]) -> list[str]:
        restored = []
        for uid in dict.fromkeys(user_ids):
            try:
                user = guild.get_member(uid) or await self.bot.fetch_user(uid)
                await guild.unban(user, reason="AntiNuke recovery")
                restored.append(getattr(user, "name", str(uid)))
            except Exception as exc:
                print(f"antinuke unban recovery error: {exc}")
        return restored

    async def _remove_granted_admin_roles(self, guild: discord.Guild, payloads: list[dict]) -> list[str]:
        removed = []
        for payload in payloads:
            member = guild.get_member(payload.get("target_id"))
            if not member:
                continue
            roles = [
                r for rid in payload.get("role_ids", [])
                if (r := guild.get_role(rid))
                and r in member.roles
                and r < guild.me.top_role
                and not r.managed
            ]
            if roles:
                try:
                    await member.remove_roles(*roles, reason="AntiNuke recovery")
                    removed.extend(r.name for r in roles)
                except Exception as exc:
                    print(f"antinuke admin role recovery error: {exc}")
        return removed

    # =========================================================================
    # Recovery tracker
    # =========================================================================

    def _store_recovery(self, guild_id: int, user_id: int, module: str, payload):
        if payload is None:
            return
        self.recovery_tracker[guild_id][user_id][module].append(
            {"time": time.time(), "payload": payload}
        )

    def _recent_recovery(self, guild_id: int, user_id: int, module: str) -> list:
        now    = time.time()
        items  = self.recovery_tracker[guild_id][user_id].get(module, [])
        recent = [i["payload"] for i in items if now - i["time"] <= TRACK_WINDOW]
        self.recovery_tracker[guild_id][user_id][module] = [
            i for i in items if now - i["time"] <= TRACK_WINDOW
        ]
        return recent

    async def _recover_module(self, guild: discord.Guild, user_id: int, module: str):
        """
        Restore everything the nuker destroyed / undo what they created.
        Called AFTER the nuker has been banned so they can't keep destroying
        things while recovery is in progress.
        Channel and role payloads are processed in parallel via asyncio.gather.
        """
        payloads = self._recent_recovery(guild.id, user_id, module)
        if not payloads:
            return

        # ── channels ──────────────────────────────────────────────────────
        if module == "channel":
            restored, deleted = [], []

            async def _handle_channel(payload):
                if payload.get("recovery_type") == "channel_create":
                    ch = guild.get_channel(payload.get("id"))
                    if ch:
                        try:
                            name = getattr(ch, "name", str(ch.id))
                            await ch.delete(reason="AntiNuke recovery")
                            deleted.append(f"#{name}")
                        except Exception as exc:
                            print(f"antinuke delete created channel error: {exc}")
                elif payload.get("recovery_type") == "channel_delete":
                    ch = await self._restore_channel(guild, payload)
                    if ch:
                        restored.append(f"#{ch.name}")

            await asyncio.gather(*[_handle_channel(p) for p in payloads])
            if restored:
                await self._log_action(guild, "AntiNuke Recovery", f"Restored channels: {', '.join(restored)}", COLORS.get("success"))
            if deleted:
                await self._log_action(guild, "AntiNuke Recovery", f"Deleted nuke-created channels: {', '.join(deleted)}", COLORS.get("success"))
            return

        # ── roles ─────────────────────────────────────────────────────────
        if module == "role":
            restored, deleted = [], []

            async def _handle_role(payload):
                if payload.get("recovery_type") == "role_create":
                    role = guild.get_role(payload.get("id"))
                    if role and role < guild.me.top_role and not role.managed:
                        try:
                            await role.delete(reason="AntiNuke recovery")
                            deleted.append(role.name)
                        except Exception as exc:
                            print(f"antinuke delete created role error: {exc}")
                elif payload.get("recovery_type") == "role_delete":
                    role = await self._restore_role(guild, payload)
                    if role:
                        restored.append(role.name)

            await asyncio.gather(*[_handle_role(p) for p in payloads])
            if restored:
                await self._log_action(guild, "AntiNuke Recovery", f"Restored roles: {', '.join(restored)}", COLORS.get("success"))
            if deleted:
                await self._log_action(guild, "AntiNuke Recovery", f"Deleted nuke-created roles: {', '.join(deleted)}", COLORS.get("success"))
            return

        # ── bans ──────────────────────────────────────────────────────────
        if module == "ban":
            user_ids = [p for p in payloads if isinstance(p, int)]
            restored = await self._restore_bans(guild, user_ids)
            if restored:
                await self._log_action(guild, "AntiNuke Recovery", f"Unbanned: {', '.join(restored)}", COLORS.get("success"))
            return

        # ── emojis ────────────────────────────────────────────────────────
        if module == "emoji":
            restored = []
            for payload in payloads:
                if payload.get("recovery_type") != "emoji_delete":
                    continue
                emoji = await self._restore_emoji(guild, payload)
                if emoji:
                    restored.append(str(emoji))
            if restored:
                await self._log_action(guild, "AntiNuke Recovery", f"Restored emojis: {', '.join(restored)}", COLORS.get("success"))
            elif payloads:
                await self._log_action(
                    guild, "AntiNuke Recovery",
                    "Emoji deletions detected but Discord did not provide enough image data to restore them.",
                    COLORS.get("warning"),
                )
            return

        # ── admin role grants ──────────────────────────────────────────────
        if module == "adminrole":
            dicts   = [p for p in payloads if isinstance(p, dict)]
            removed = await self._remove_granted_admin_roles(guild, dicts)
            if removed:
                await self._log_action(guild, "AntiNuke Recovery", f"Removed granted admin roles: {', '.join(removed)}", COLORS.get("success"))

    # =========================================================================
    # Action tracking
    # =========================================================================

    def _push_action(self, guild_id: int, user_id: int, module: str, amount: int = 1) -> tuple[int, list]:
        now          = time.time()
        guild_bucket = self.bot.nuke_tracker.setdefault(guild_id, {})
        user_bucket  = guild_bucket.setdefault(user_id, {})
        timestamps   = user_bucket.setdefault(module, [])
        timestamps.extend([now] * max(1, amount))
        user_bucket[module] = [ts for ts in timestamps if now - ts <= TRACK_WINDOW]
        return len(user_bucket[module]), user_bucket[module]

    def _clear_actions(self, guild_id: int, user_id: int, module: str):
        try:
            self.bot.nuke_tracker.get(guild_id, {}).get(user_id, {}).pop(module, None)
        except Exception:
            pass

    # =========================================================================
    # Punishment
    # =========================================================================

    async def _apply_punishment(
        self, guild: discord.Guild, user, punishment: str, reason: str
    ) -> tuple[bool, str]:
        try:
            punishment = "strip" if punishment == "stripstaff" else punishment
            member     = guild.get_member(user.id)

            if self._is_exempt(guild, user.id):
                return False, f"refusing to punish protected user {self._target_name(user)}."
            if member and member.top_role >= guild.me.top_role:
                return False, f"missing role hierarchy to punish {self._target_name(user)}."

            if punishment == "warn":
                return True, f"{self._target_name(user)} triggered antinuke for {reason}."
            if punishment == "ban":
                await guild.ban(discord.Object(id=user.id), reason=reason, delete_message_days=0)
                return True, f"{self._target_name(user)} has been **banned** for {reason}."
            if punishment == "kick":
                if not member:
                    return False, f"cannot kick {self._target_name(user)} — no longer in server."
                await member.kick(reason=reason)
                return True, f"{self._target_name(user)} has been **kicked** for {reason}."
            if punishment == "strip":
                if not member:
                    return False, f"cannot strip {self._target_name(user)} — no longer in server."
                removable = [
                    r for r in member.roles
                    if r != guild.default_role and not r.managed and r < guild.me.top_role
                ]
                if removable:
                    await member.remove_roles(*removable, reason=reason)
                return True, f"{self._target_name(user)} had roles **stripped** for {reason}."
            if punishment == "timeout":
                if not member:
                    return False, f"cannot timeout {self._target_name(user)} — no longer in server."
                await member.timeout(discord.utils.utcnow() + timedelta(days=28), reason=reason)
                return True, f"{self._target_name(user)} has been **timed out** for {reason}."
            return False, f"unknown punishment type: {punishment}"
        except discord.Forbidden:
            return False, (
                f"missing permissions to punish {self._target_name(user)}. "
                "Move my role higher and grant moderation permissions."
            )
        except Exception as exc:
            print(f"antinuke punishment error: {exc}")
            return False, f"failed to punish {self._target_name(user)} — internal error."

    async def _ban_linked_bots(self, guild: discord.Guild, users, reason: str) -> list[str]:
        """Immediately ban all bots that performed nuking actions."""
        messages = []
        seen     = set()
        for user in users or []:
            try:
                if not user or user.id in seen:
                    continue
                seen.add(user.id)
                if self.bot.user and user.id == self.bot.user.id:
                    continue
                if not getattr(user, "bot", False):
                    continue
                if self._is_exempt(guild, user.id):
                    messages.append(f"refusing to ban protected bot {self._target_name(user)}.")
                    continue
                member = guild.get_member(user.id)
                if member and member.top_role >= guild.me.top_role:
                    messages.append(f"missing hierarchy to ban bot {self._target_name(user)}.")
                    continue
                await guild.ban(discord.Object(id=user.id), reason=reason, delete_message_days=0)
                messages.append(f"bot {self._target_name(user)} has been **banned** for {reason}.")
            except discord.NotFound:
                messages.append(f"bot {self._target_name(user)} was already gone.")
            except discord.Forbidden:
                messages.append(f"missing permissions to ban bot {self._target_name(user)}.")
            except Exception as exc:
                print(f"antinuke linked bot ban error: {exc}")
                messages.append(f"failed to ban bot {self._target_name(user)} — internal error.")
        return messages

    # =========================================================================
    # Core threshold handler
    # =========================================================================

    async def _handle_threshold(
        self,
        guild: discord.Guild,
        user,
        module: str,
        readable_action: str,
        config: dict,
        *,
        amount: int = 1,
        extra_note: str = "",
        dry_run: bool = False,
        linked_bots=None,
    ):
        """
        Central detection → punishment → recovery pipeline.

        Execution order (critical for correctness):
          1. Check threshold   — bail early if not exceeded.
          2. Ban linked bots   — nuke bot is removed from the server immediately.
          3. Punish the human  — human executor is stopped.
          4. Recover           — restore destroyed channels/roles now that the
                                 nuker can no longer interfere.
          5. Log               — emit a single embed with everything that happened.
          6. Clear tracker     — reset so we don't double-trigger.
          7. DM owner          — rich embed notification.
        """
        try:
            module = normalize_module(module)
            if not module or not user:
                return

            # Safety: never punish a missing executor or the bot itself
            if not user or user.id == self.bot.user.id:
                return

            module_config = get_module_config(config, module)
            if not module_config:
                return
            if not dry_run and not module_config.get("enabled"):
                return
            if self._is_exempt(guild, user.id, module):
                return

            count, timestamps = self._push_action(guild.id, user.id, module, amount=amount)
            threshold = module_config.get("threshold", 1)
            print(f"antinuke track: guild={guild.id} user={user.id} module={module} count={count}/{threshold}")
            if count < threshold:
                return

            window_span  = int(max(1, round(timestamps[-1] - timestamps[0]))) if len(timestamps) > 1 else 1
            reason       = f"{readable_action} ({count} in {window_span}s)"
            trigger_text = f"{self._target_name(user)} triggered antinuke for {readable_action}. ({count} in {window_span}s)"
            if extra_note:
                trigger_text = f"{trigger_text}\n{extra_note}".strip()

            # ── dry-run (test mode) ───────────────────────────────────────
            if dry_run:
                await self._log_action(guild, "AntiNuke Test", trigger_text, COLORS.get("warning"))
                self._clear_actions(guild.id, user.id, module)
                return

            # STEP 1: ban the nuke bot(s) immediately — stop them first
            linked_messages = await self._ban_linked_bots(guild, linked_bots, reason)

            # STEP 2: punish the human inviter/executor
            # Bots always get banned regardless of the configured punishment.
            config_punishment  = module_config.get("punishment", "ban")
            actual_punishment  = "ban" if getattr(user, "bot", False) else config_punishment
            success, punish_message = await self._apply_punishment(
                guild,
                user,
                actual_punishment,
                reason,
            )

            # STEP 3: recover AFTER nuker is stopped
            await self._recover_module(guild, user.id, module)

            # STEP 4: log everything in one embed
            punish_lines = [punish_message, *linked_messages]
            await self._log_action(
                guild,
                "AntiNuke Triggered",
                f"{trigger_text}\n\n" + "\n".join(punish_lines),
                COLORS.get("error") if success else COLORS.get("warning"),
            )

            # STEP 5: clear tracker for this module
            self._clear_actions(guild.id, user.id, module)

            if not success:
                await self._warn_owner(guild, punish_message)

            # STEP 6: DM the guild owner with a rich embed
            await self._notify_owner_trigger(guild, user, module, count, actual_punishment)

        except Exception as exc:
            print(f"antinuke threshold handler error: {exc}")

    # =========================================================================
    # Audit event handler
    # =========================================================================

    async def _handle_audit_event(
        self,
        guild: discord.Guild,
        module: str,
        audit_action,
        readable_action: str,
        *,
        target_id: int = None,
        recovery_payload=None,
        extra_note: str = "",
        newer_than: float = 20,
    ):
        try:
            config        = self._get_config(guild.id)
            module_config = get_module_config(config, module)
            if not module_config or not module_config.get("enabled"):
                return

            entry = await self._audit_entry(guild, audit_action, target_id=target_id, newer_than=newer_than)
            if not entry:
                return
            self._mark_audit_processed(guild.id, audit_action, entry)

            executor, linked_bots = await self._resolve_audit_actor(guild, entry)
            if not executor or self._is_exempt(guild, executor.id, module):
                return

            self._store_recovery(guild.id, executor.id, normalize_module(module), recovery_payload)
            await self._handle_threshold(
                guild,
                executor,
                module,
                readable_action,
                config,
                extra_note=extra_note,
                linked_bots=linked_bots,
            )
        except Exception as exc:
            print(f"antinuke audit event handler error: {exc}")

    # =========================================================================
    # Commands — helpers
    # =========================================================================

    def _module_status_line(self, module: str, module_config: dict) -> str:
        cmd_text = "command on" if module_config.get("command_detection") else "command off"
        return (
            f"`{module}`: {'✅ on' if module_config.get('enabled') else '❌ off'} | "
            f"threshold `{module_config.get('threshold')}` | "
            f"do `{module_config.get('punishment')}` | {cmd_text}"
        )

    def _config_embed(self, guild: discord.Guild) -> discord.Embed:
        config      = self._get_config(guild.id)
        log_channel = guild.get_channel(int(config["log_channel_id"])) if config.get("log_channel_id") else None
        lines       = [self._module_status_line(m, config["modules"][m]) for m in DEFAULT_MODULES]
        embed       = self._embed("AntiNuke Config", "\n".join(lines))
        embed.add_field(name="Log Channel", value=log_channel.mention if log_channel else "not set", inline=False)
        return embed

    async def _build_full_config_embed(self, guild: discord.Guild) -> discord.Embed:
        """Config embed that also shows whitelist, admins, and trusted users."""
        embed = self._config_embed(guild)
        if settings_db:
            try:
                entries     = settings_db.get_all_antinuke_whitelisted(guild.id)
                whitelisted = [e for e in entries if e.get("role") == "whitelisted"]
                admins      = [e for e in entries if e.get("role") == "admin"]
                trusted     = [e for e in entries if e.get("role") == "trusted"]
                wl_str = ", ".join(f"<@{int(e['user_id'])}>" for e in whitelisted) or "none"
                ad_str = ", ".join(f"<@{int(e['user_id'])}>" for e in admins) or "none"
                tr_str = ", ".join(f"<@{int(e['user_id'])}>" for e in trusted) or "none"
                embed.add_field(name="Whitelist",        value=wl_str, inline=False)
                embed.add_field(name="Admins",           value=ad_str, inline=False)
                embed.add_field(name="Trusted (botadd)", value=tr_str, inline=False)
            except Exception as exc:
                print(f"antinuke full config embed error: {exc}")
        return embed

    async def _module_command(self, ctx: commands.Context, module: str, state: str = None, flags=()):
        if not await self._ensure_command_access(ctx):
            return
        module = normalize_module(module)
        if not module:
            return await ctx.reply("unknown antinuke module.", mention_author=False)

        config        = self._get_config(ctx.guild.id)
        module_config = config["modules"][module]
        desired_state = parse_bool(state)

        if desired_state is None:
            return await ctx.reply(
                embed=self._embed(
                    f"AntiNuke — {module}",
                    f"{self._module_status_line(module, module_config)}\n\n"
                    f"usage: `antinuke {module} <on/off> [--threshold 1-20] "
                    f"[--do ban/kick/strip/timeout/warn] [--command on/off]`",
                ),
                mention_author=False,
            )

        updates, errors = parse_module_flags(flags)
        if errors:
            return await ctx.reply("\n".join(errors), mention_author=False)

        module_config["enabled"] = desired_state
        module_config.update(updates)
        config["modules"][module] = module_config
        self._save_config(ctx.guild.id, config)
        await ctx.reply(
            embed=self._embed(
                "AntiNuke Updated",
                self._module_status_line(module, module_config),
                COLORS.get("success"),
            ),
            mention_author=False,
        )

    # ── main group ────────────────────────────────────────────────────────────
    @commands.group(name="antinuke", aliases=["an"], invoke_without_command=True)
    @commands.guild_only()
    async def antinuke(self, ctx: commands.Context):
        if not await self._ensure_command_access(ctx):
            return
        await ctx.reply(embed=await self._build_full_config_embed(ctx.guild), mention_author=False)

    # ── info ─────────────────────────────────────────────────────────────────
    @antinuke.command(name="config", aliases=["status", "settings"])
    async def antinuke_config(self, ctx: commands.Context):
        if not await self._ensure_command_access(ctx):
            return
        await ctx.reply(embed=await self._build_full_config_embed(ctx.guild), mention_author=False)

    @antinuke.command(name="list")
    async def antinuke_list(self, ctx: commands.Context):
        if not await self._ensure_command_access(ctx):
            return
        config          = self._get_config(ctx.guild.id)
        all_modules_str = ", ".join(f"`{name}`" for name in DEFAULT_MODULES)
        enabled         = [name for name, mc in config["modules"].items() if mc.get("enabled")]
        enabled_str     = "\n".join(f"✅ `{m}`" for m in enabled) if enabled else "none enabled"
        wl_str          = "none"
        if settings_db:
            try:
                entries  = settings_db.get_all_antinuke_whitelisted(ctx.guild.id)
                wl_lines = [f"<@{int(e['user_id'])}> (`{e['role']}`)" for e in entries]
                wl_str   = "\n".join(wl_lines) or "none"
            except Exception:
                pass
        embed = self._embed("AntiNuke Modules & Access List", f"**All modules:** {all_modules_str}")
        embed.add_field(name="Enabled Modules", value=enabled_str, inline=True)
        embed.add_field(name="Access List",     value=wl_str,      inline=True)
        await ctx.reply(embed=embed, mention_author=False)

    # ── bulk on/off ───────────────────────────────────────────────────────────
    @antinuke.command(name="enable")
    async def antinuke_enable(self, ctx: commands.Context):
        if not await self._ensure_command_access(ctx):
            return
        config = self._get_config(ctx.guild.id)
        for module in config["modules"].values():
            module["enabled"] = True
        self._save_config(ctx.guild.id, config)
        await ctx.reply(embed=self._embed("AntiNuke Enabled", "All antinuke modules are now ✅ on.", COLORS.get("success")), mention_author=False)

    @antinuke.command(name="disable")
    async def antinuke_disable(self, ctx: commands.Context):
        if not await self._ensure_command_access(ctx):
            return
        config = self._get_config(ctx.guild.id)
        for module in config["modules"].values():
            module["enabled"] = False
        self._save_config(ctx.guild.id, config)
        await ctx.reply(embed=self._embed("AntiNuke Disabled", "All antinuke modules are now ❌ off.", COLORS.get("warning")), mention_author=False)

    # ── global setters ────────────────────────────────────────────────────────
    @antinuke.command(name="punishment")
    async def antinuke_punishment(self, ctx: commands.Context, punishment: str = None):
        if not await self._ensure_command_access(ctx):
            return
        punishment = punishment.lower() if punishment else None
        if punishment not in VALID_PUNISHMENTS:
            return await ctx.reply(
                f"usage: `antinuke punishment <{'|'.join(VALID_PUNISHMENTS)}>`",
                mention_author=False,
            )
        config = self._get_config(ctx.guild.id)
        for module in config["modules"].values():
            module["punishment"] = punishment
        self._save_config(ctx.guild.id, config)
        await ctx.reply(embed=self._embed("AntiNuke Updated", f"All module punishments set to `{punishment}`.", COLORS.get("success")), mention_author=False)

    @antinuke.command(name="threshold")
    async def antinuke_threshold(self, ctx: commands.Context, action: str = None, number: int = None):
        if not await self._ensure_command_access(ctx):
            return
        module = normalize_module(action)
        if not module or number is None or number < 1 or number > 20:
            return await ctx.reply("usage: `antinuke threshold <module> <1-20>`", mention_author=False)
        config = self._get_config(ctx.guild.id)
        config["modules"][module]["threshold"] = number
        self._save_config(ctx.guild.id, config)
        await ctx.reply(embed=self._embed("AntiNuke Updated", f"`{module}` threshold set to `{number}`.", COLORS.get("success")), mention_author=False)

    @antinuke.command(name="reset")
    async def antinuke_reset(self, ctx: commands.Context):
        if not await self._ensure_command_access(ctx):
            return
        self._reset_config(ctx.guild.id)
        if settings_db:
            for entry in settings_db.get_all_antinuke_whitelisted(ctx.guild.id):
                settings_db.remove_antinuke_whitelist(ctx.guild.id, entry["user_id"])
        await ctx.reply(embed=self._embed("AntiNuke Reset", "Settings and antinuke whitelist/admin entries were reset.", COLORS.get("warning")), mention_author=False)

    @antinuke.command(name="logchannel", aliases=["log"])
    async def antinuke_logchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        if not await self._ensure_command_access(ctx):
            return
        config = self._get_config(ctx.guild.id)
        config["log_channel_id"] = channel.id if channel else None
        self._save_config(ctx.guild.id, config)
        await ctx.reply(
            embed=self._embed(
                "AntiNuke Log Channel",
                f"Logs will go to {channel.mention}." if channel else "Antinuke log channel cleared.",
                COLORS.get("success"),
            ),
            mention_author=False,
        )

    @antinuke.command(name="test")
    async def antinuke_test(self, ctx: commands.Context):
        if ctx.author.id not in OWNER_IDS:
            return await ctx.reply("this test command is only for bot owners.", mention_author=False)
        await self._handle_threshold(
            ctx.guild, ctx.author, "channel", "test trigger",
            self._get_config(ctx.guild.id), dry_run=True,
        )
        await ctx.reply("antinuke test ran. check the log channel if one is set.", mention_author=False)

    # ── per-module toggles ────────────────────────────────────────────────────
    @antinuke.command(name="ban")
    async def antinuke_ban(self, ctx: commands.Context, state: str = None, *flags):
        await self._module_command(ctx, "ban", state, flags)

    @antinuke.command(name="kick")
    async def antinuke_kick(self, ctx: commands.Context, state: str = None, *flags):
        await self._module_command(ctx, "kick", state, flags)

    @antinuke.command(name="channel", aliases=["channels"])
    async def antinuke_channel(self, ctx: commands.Context, state: str = None, *flags):
        await self._module_command(ctx, "channel", state, flags)

    @antinuke.command(name="role", aliases=["roles"])
    async def antinuke_role(self, ctx: commands.Context, state: str = None, *flags):
        await self._module_command(ctx, "role", state, flags)

    @antinuke.command(name="webhook", aliases=["webhooks"])
    async def antinuke_webhook(self, ctx: commands.Context, state: str = None, *flags):
        await self._module_command(ctx, "webhook", state, flags)

    @antinuke.command(name="botadd", aliases=["bot", "bots", "bot_add"])
    async def antinuke_botadd(self, ctx: commands.Context, state: str = None, *flags):
        await self._module_command(ctx, "botadd", state, flags)

    @antinuke.command(name="emoji", aliases=["emojis"])
    async def antinuke_emoji(self, ctx: commands.Context, state: str = None, *flags):
        await self._module_command(ctx, "emoji", state, flags)

    @antinuke.command(name="vanity")
    async def antinuke_vanity(self, ctx: commands.Context, state: str = None, *flags):
        await self._module_command(ctx, "vanity", state, flags)

    @antinuke.command(name="server", aliases=["guild"])
    async def antinuke_server(self, ctx: commands.Context, state: str = None, *flags):
        await self._module_command(ctx, "guild", state, flags)

    @antinuke.command(name="adminrole", aliases=["adminroles"])
    async def antinuke_adminrole(self, ctx: commands.Context, state: str = None, *flags):
        await self._module_command(ctx, "adminrole", state, flags)

    # ── access management helpers ─────────────────────────────────────────────
    async def _add_access_entry(self, ctx: commands.Context, target: str, role: str):
        if not await self._ensure_db(ctx):
            return
        user_id, label = await self._resolve_user_id(ctx, target)
        if not user_id:
            return await ctx.reply("please provide a valid user mention or ID.", mention_author=False)
        settings_db.add_antinuke_whitelist(ctx.guild.id, user_id, role=role)
        await ctx.reply(embed=self._embed("AntiNuke Updated", f"{label} added as `{role}`.", COLORS.get("success")), mention_author=False)

    async def _remove_access_entry(self, ctx: commands.Context, target: str):
        if not await self._ensure_db(ctx):
            return
        user_id, label = await self._resolve_user_id(ctx, target)
        if not user_id:
            return await ctx.reply("please provide a valid user mention or ID.", mention_author=False)
        settings_db.remove_antinuke_whitelist(ctx.guild.id, user_id)
        await ctx.reply(embed=self._embed("AntiNuke Updated", f"{label} removed from antinuke access.", COLORS.get("success")), mention_author=False)

    async def _list_access_entries(self, ctx: commands.Context, role: str, title: str):
        if not await self._ensure_db(ctx):
            return
        entries = settings_db.get_all_antinuke_whitelisted(ctx.guild.id)
        users   = []
        for entry in entries:
            if entry["role"] != role:
                continue
            user_id = int(entry["user_id"])
            member  = ctx.guild.get_member(user_id)
            users.append(member.mention if member else str(user_id))
        await ctx.reply(embed=self._embed(title, ", ".join(users) if users else "none"), mention_author=False)

    # ── admin management ──────────────────────────────────────────────────────
    @antinuke.group(name="admin", invoke_without_command=True)
    async def antinuke_admin(self, ctx: commands.Context, target: str = None):
        if not await self._ensure_owner_access(ctx):
            return
        if target:
            await self._add_access_entry(ctx, target, "admin")
            return
        await self._list_access_entries(ctx, "admin", "AntiNuke Admins")

    @antinuke_admin.command(name="add")
    async def antinuke_admin_add(self, ctx: commands.Context, target: str = None):
        if not await self._ensure_owner_access(ctx):
            return
        await self._add_access_entry(ctx, target, "admin")

    @antinuke_admin.command(name="remove", aliases=["delete"])
    async def antinuke_admin_remove(self, ctx: commands.Context, target: str = None):
        if not await self._ensure_owner_access(ctx):
            return
        await self._remove_access_entry(ctx, target)

    @antinuke_admin.command(name="list")
    async def antinuke_admin_list(self, ctx: commands.Context):
        if not await self._ensure_command_access(ctx):
            return
        await self._list_access_entries(ctx, "admin", "AntiNuke Admins")

    @antinuke.command(name="admins")
    async def antinuke_admins(self, ctx: commands.Context):
        if not await self._ensure_command_access(ctx):
            return
        await self._list_access_entries(ctx, "admin", "AntiNuke Admins")

    # ── whitelist management ──────────────────────────────────────────────────
    @antinuke.group(name="whitelist", aliases=["wl"], invoke_without_command=True)
    async def antinuke_whitelist(self, ctx: commands.Context, target: str = None):
        if not await self._ensure_command_access(ctx):
            return
        if target:
            await self._add_access_entry(ctx, target, "whitelisted")
            return
        await self._list_access_entries(ctx, "whitelisted", "AntiNuke Whitelist")

    @antinuke_whitelist.command(name="add")
    async def antinuke_whitelist_add(self, ctx: commands.Context, target: str = None):
        if not await self._ensure_command_access(ctx):
            return
        await self._add_access_entry(ctx, target, "whitelisted")

    @antinuke_whitelist.command(name="remove", aliases=["delete"])
    async def antinuke_whitelist_remove(self, ctx: commands.Context, target: str = None):
        if not await self._ensure_command_access(ctx):
            return
        await self._remove_access_entry(ctx, target)

    @antinuke_whitelist.command(name="list")
    async def antinuke_whitelist_list(self, ctx: commands.Context):
        if not await self._ensure_command_access(ctx):
            return
        await self._list_access_entries(ctx, "whitelisted", "AntiNuke Whitelist")

    # ── trusted management ────────────────────────────────────────────────────
    @antinuke.group(name="trust", invoke_without_command=True)
    async def antinuke_trust(self, ctx: commands.Context, target: str = None):
        if not await self._ensure_command_access(ctx):
            return
        if target:
            await self._add_access_entry(ctx, target, "trusted")
            return
        await self._list_access_entries(ctx, "trusted", "Trusted Bot Add Users")

    @antinuke_trust.command(name="add")
    async def antinuke_trust_add(self, ctx: commands.Context, target: str = None):
        if not await self._ensure_command_access(ctx):
            return
        await self._add_access_entry(ctx, target, "trusted")

    @antinuke_trust.command(name="remove", aliases=["delete"])
    async def antinuke_trust_remove(self, ctx: commands.Context, target: str = None):
        if not await self._ensure_command_access(ctx):
            return
        await self._remove_access_entry(ctx, target)

    @antinuke_trust.command(name="list")
    async def antinuke_trust_list(self, ctx: commands.Context):
        if not await self._ensure_command_access(ctx):
            return
        await self._list_access_entries(ctx, "trusted", "Trusted Bot Add Users")

    # =========================================================================
    # Loops
    # =========================================================================

    @tasks.loop(seconds=TRACK_CLEANUP_SECONDS)
    async def cleanup_tracker(self):
        try:
            now = time.time()
            for guild_id, users in list(self.bot.nuke_tracker.items()):
                for user_id, actions in list(users.items()):
                    for module, timestamps in list(actions.items()):
                        actions[module] = [ts for ts in timestamps if now - ts <= TRACK_WINDOW]
                        if not actions[module]:
                            actions.pop(module, None)
                    if not actions:
                        users.pop(user_id, None)
                if not users:
                    self.bot.nuke_tracker.pop(guild_id, None)

            for guild_id, users in list(self.recovery_tracker.items()):
                for user_id, actions in list(users.items()):
                    for module, items in list(actions.items()):
                        actions[module] = [i for i in items if now - i["time"] <= TRACK_WINDOW]
                        if not actions[module]:
                            actions.pop(module, None)
                    if not actions:
                        users.pop(user_id, None)
                if not users:
                    self.recovery_tracker.pop(guild_id, None)

            for key, created_at in list(self.processed_audits.items()):
                if now - created_at > AUDIT_DEDUPE_SECONDS:
                    self.processed_audits.pop(key, None)

            for guild_id, bots in list(self.bot.bot_adder_cache.items()):
                for bot_id, payload in list(bots.items()):
                    if now - payload.get("time", 0) > 31_536_000:
                        bots.pop(bot_id, None)
                if not bots:
                    self.bot.bot_adder_cache.pop(guild_id, None)
        except Exception as exc:
            print(f"antinuke cleanup loop error: {exc}")

    @cleanup_tracker.before_loop
    async def before_cleanup_tracker(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=CACHE_REFRESH_SECONDS)
    async def refresh_guild_cache(self):
        try:
            for guild in self.bot.guilds:
                self._refresh_single_guild_cache(guild)
        except Exception as exc:
            print(f"antinuke cache loop error: {exc}")

    @refresh_guild_cache.before_loop
    async def before_refresh_guild_cache(self):
        await self.bot.wait_until_ready()

    # =========================================================================
    # Listeners
    # =========================================================================

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            for guild in self.bot.guilds:
                self._refresh_single_guild_cache(guild)
        except Exception as exc:
            print(f"antinuke on_ready error: {exc}")

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        try:
            if not ctx.guild or not ctx.command:
                return
            command_name = (ctx.invoked_with or ctx.command.name).lower()
            module = COMMAND_MODULE_MAP.get(command_name) or COMMAND_MODULE_MAP.get(ctx.command.name.lower())
            if not module:
                return
            config        = self._get_config(ctx.guild.id)
            module_config = get_module_config(config, module)
            if not module_config or not module_config.get("enabled") or not module_config.get("command_detection"):
                return
            if self._is_exempt(ctx.guild, ctx.author.id, module):
                return
            amount = 1
            if command_name == "massban":
                amount = max(1, len([arg for arg in ctx.args[2:] if isinstance(arg, discord.Member)]))
            await self._handle_threshold(
                ctx.guild,
                ctx.author,
                module,
                f"dangerous command `{ctx.invoked_with or ctx.command.name}`",
                config,
                amount=amount,
                extra_note="command detection is enabled for this module.",
            )
        except Exception as exc:
            print(f"antinuke command detection error: {exc}")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        try:
            # KEY FIX: refresh cache BEFORE audit handler so subsequent delete
            # events for this channel can still find its snapshot in the cache.
            self._refresh_single_guild_cache(channel.guild)
            await self._handle_audit_event(
                channel.guild,
                "channel",
                discord.AuditLogAction.channel_create,
                "channel creation",
                target_id=channel.id,
                recovery_payload={"recovery_type": "channel_create", "id": channel.id},
            )
        except Exception as exc:
            print(f"antinuke channel create listener error: {exc}")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        try:
            self._refresh_single_guild_cache(after.guild)
            me_before = before.permissions_for(before.guild.me)
            me_after  = after.permissions_for(after.guild.me)
            if me_before.view_channel and not me_after.view_channel:
                await self._warn_owner(after.guild, f"I lost access to #{after.name}. Please check my permissions.")
            elif me_before.send_messages and not me_after.send_messages:
                await self._warn_owner(after.guild, f"I lost send message permissions in #{after.name}.")
        except Exception as exc:
            print(f"antinuke channel update listener error: {exc}")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        try:
            snapshot = self._channel_snapshot_from_cache(channel.guild.id, channel.id) or self._snapshot_channel(channel)
            await self._handle_audit_event(
                channel.guild,
                "channel",
                discord.AuditLogAction.channel_delete,
                "channel deletion",
                target_id=channel.id,
                recovery_payload=snapshot,
            )
            self._refresh_single_guild_cache(channel.guild)
        except Exception as exc:
            print(f"antinuke channel delete listener error: {exc}")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        try:
            await self._handle_audit_event(
                role.guild,
                "role",
                discord.AuditLogAction.role_create,
                "role creation",
                target_id=role.id,
                recovery_payload={"recovery_type": "role_create", "id": role.id},
            )
            self._refresh_single_guild_cache(role.guild)
        except Exception as exc:
            print(f"antinuke role create listener error: {exc}")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        try:
            self._refresh_single_guild_cache(after.guild)
        except Exception as exc:
            print(f"antinuke role update listener error: {exc}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        try:
            snapshot = self._role_snapshot_from_cache(role.guild.id, role.id) or self._snapshot_role(role)
            await self._handle_audit_event(
                role.guild,
                "role",
                discord.AuditLogAction.role_delete,
                "role deletion",
                target_id=role.id,
                recovery_payload=snapshot,
            )
            self._refresh_single_guild_cache(role.guild)
        except Exception as exc:
            print(f"antinuke role delete listener error: {exc}")

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        try:
            await self._handle_audit_event(
                guild,
                "ban",
                discord.AuditLogAction.ban,
                "member bans",
                target_id=user.id,
                recovery_payload=user.id,
            )
        except Exception as exc:
            print(f"antinuke member ban listener error: {exc}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        try:
            await self._handle_audit_event(
                member.guild,
                "kick",
                discord.AuditLogAction.kick,
                "member kicks",
                target_id=member.id,
            )
        except Exception as exc:
            print(f"antinuke member remove listener error: {exc}")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        try:
            await self._handle_audit_event(
                channel.guild,
                "webhook",
                discord.AuditLogAction.webhook_create,
                "webhook creation",
                newer_than=15,
            )
        except Exception as exc:
            print(f"antinuke webhook update listener error: {exc}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            if not member.bot:
                return
            entry = await self._audit_entry(member.guild, discord.AuditLogAction.bot_add, target_id=member.id)
            if entry and getattr(entry, "user", None) and not entry.user.bot:
                self._remember_bot_adder(member.guild.id, member.id, entry.user.id)
            if entry:
                self._mark_audit_processed(member.guild.id, discord.AuditLogAction.bot_add, entry)
                executor = await self._resolve_executor(member.guild, entry)
            else:
                executor = None
            config        = self._get_config(member.guild.id)
            module_config = get_module_config(config, "botadd")
            if not module_config or not module_config.get("enabled") or not executor:
                return
            await self._handle_threshold(
                member.guild,
                executor,
                "botadd",
                "bot additions",
                config,
                linked_bots=[member],
            )
        except Exception as exc:
            print(f"antinuke member join listener error: {exc}")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        try:
            if self.bot.user and after.id == self.bot.user.id and before.roles != after.roles:
                await self._warn_owner(after.guild, "my roles or guild permissions changed. Please double-check my access.")

            added_roles = [role for role in after.roles if role not in before.roles]
            removed_roles = [role for role in before.roles if role not in after.roles]
            changed_roles = added_roles + removed_roles
            if not changed_roles:
                return

            config = self._get_config(after.guild.id)
            role_module = get_module_config(config, "role")
            if role_module and role_module.get("enabled"):
                entry = await self._audit_entry(
                    after.guild,
                    discord.AuditLogAction.member_role_update,
                    target_id=after.id,
                )
                if entry:
                    self._mark_audit_processed(after.guild.id, discord.AuditLogAction.member_role_update, entry)
                    executor, linked_bots = await self._resolve_audit_actor(after.guild, entry)
                    if executor and not self._is_exempt(after.guild, executor.id, "role"):
                        added_names = ", ".join(role.name for role in added_roles) or "none"
                        removed_names = ", ".join(role.name for role in removed_roles) or "none"
                        role_guard_config = merge_config(config)
                        role_guard_config["modules"]["role"]["threshold"] = 1
                        role_guard_config["modules"]["role"]["punishment"] = "ban"
                        await self._handle_threshold(
                            after.guild,
                            executor,
                            "role",
                            "member role changes",
                            role_guard_config,
                            extra_note=f"target: {after.mention} | added: {added_names} | removed: {removed_names}",
                            linked_bots=linked_bots,
                        )

            admin_roles = [role for role in added_roles if role.permissions.administrator]
            if not admin_roles:
                return

            payload = {
                "recovery_type": "admin_role_grant",
                "target_id":     after.id,
                "role_ids":      [role.id for role in admin_roles],
            }
            await self._handle_audit_event(
                after.guild,
                "adminrole",
                discord.AuditLogAction.member_role_update,
                "admin role grants",
                target_id=after.id,
                recovery_payload=payload,
                extra_note=f"roles: {', '.join(role.name for role in admin_roles)}",
            )
        except Exception as exc:
            print(f"antinuke member update listener error: {exc}")

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        try:
            changed = []
            if before.name != after.name:
                changed.append("name")
            if before.icon != after.icon:
                changed.append("icon")
            if before.afk_timeout != after.afk_timeout:
                changed.append("afk timeout")
            if before.verification_level != after.verification_level:
                changed.append("verification level")
            if before.default_notifications != after.default_notifications:
                changed.append("default notifications")
            if before.explicit_content_filter != after.explicit_content_filter:
                changed.append("content filter")

            vanity_changed = getattr(before, "vanity_url_code", None) != getattr(after, "vanity_url_code", None)
            if vanity_changed:
                changed.append("vanity")
            if not changed:
                return

            config = self._get_config(after.id)
            entry  = await self._audit_entry(after, discord.AuditLogAction.guild_update, target_id=after.id)
            if not entry:
                return
            self._mark_audit_processed(after.id, discord.AuditLogAction.guild_update, entry)
            executor, linked_bots = await self._resolve_audit_actor(after, entry)
            if not executor:
                return

            note = f"changed: {', '.join(changed)}"
            if vanity_changed and get_module_config(config, "vanity").get("enabled"):
                await self._handle_threshold(
                    after, executor, "vanity", "vanity changes", config,
                    extra_note=note, linked_bots=linked_bots,
                )
                return
            await self._handle_threshold(
                after, executor, "guild", "server updates", config,
                extra_note=note, linked_bots=linked_bots,
            )
        except Exception as exc:
            print(f"antinuke guild update listener error: {exc}")

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        try:
            before_by_id = {emoji.id: emoji for emoji in before}
            after_ids    = {emoji.id for emoji in after}
            deleted      = [emoji for emoji_id, emoji in before_by_id.items() if emoji_id not in after_ids]
            if not deleted:
                return
            action = getattr(discord.AuditLogAction, "emoji_delete", None)
            for emoji in deleted:
                snapshot = await self._snapshot_emoji(emoji)
                await self._handle_audit_event(
                    guild, "emoji", action, "emoji deletion",
                    target_id=emoji.id,
                    recovery_payload=snapshot,
                    extra_note=f"emoji: {emoji.name}",
                )
        except Exception as exc:
            print(f"antinuke emoji update listener error: {exc}")


async def setup(bot):
    try:
        await bot.add_cog(AntiNuke(bot))
    except Exception as exc:
        print(f"antinuke setup error: {exc}")
