import os
from datetime import datetime, timezone

import discord
from discord.ext import commands
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

from config import COLORS, EMOJIS


load_dotenv()

def _env(name, default=None):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


MYSQL_CONFIG = {
    "host": _env("MYSQL_HOST"),
    "port": int(_env("MYSQL_PORT", "3306")),
    "user": _env("MYSQL_USER"),
    "password": _env("MYSQL_PASSWORD"),
    "database": _env("MYSQL_DATABASE"),
}


def utcnow():
    return datetime.now(timezone.utc)


def _mysql_config_ready():
    return all(MYSQL_CONFIG.get(key) for key in ("host", "user", "password", "database"))


class InviteHistoryView(discord.ui.View):
    def __init__(self, cog, ctx, user, entries, per_page=8):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.user = user
        self.entries = entries
        self.per_page = per_page
        self.page = 0
        self.max_pages = max(1, (len(entries) + per_page - 1) // per_page)
        self._sync_buttons()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command user can use these buttons.", ephemeral=True)
            return False
        return True

    def _sync_buttons(self):
        self.previous_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.max_pages - 1

    def build_embed(self):
        start = self.page * self.per_page
        chunk = self.entries[start:start + self.per_page]
        lines = []

        for index, row in enumerate(chunk, start=start + 1):
            member_id = int(row["member_id"])
            member = self.ctx.guild.get_member(member_id)
            status = "Still in server" if member else "Left server"
            joined_at = row.get("joined_at")
            joined_text = self.cog.format_db_time(joined_at)
            code = row.get("invite_code") or "unknown"
            name = str(member) if member else row.get("member_name") or f"User ID {member_id}"
            lines.append(f"**{index}.** {name} (`{member_id}`)\n{joined_text} | {status} | `{code}`")

        embed = discord.Embed(
            title=f"Invite History - {self.user}",
            description="\n\n".join(lines) if lines else "No invite history found for this user.",
            color=COLORS["secondary"],
            timestamp=utcnow(),
        )
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_pages}  |  {len(self.entries)} total invites")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction, button):
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction, button):
        self.page = min(self.max_pages - 1, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class TopInvitesView(discord.ui.View):
    def __init__(self, cog, ctx, rows, count, per_page=5):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.rows = rows
        self.count = count
        self.per_page = per_page
        self.page = 0
        self.max_pages = max(1, (len(rows) + per_page - 1) // per_page)
        self.top_count = rows[0]["total_invites"] if rows else 0
        self._sync_buttons()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command user can use these buttons.", ephemeral=True)
            return False
        return True

    def _sync_buttons(self):
        self.previous_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.max_pages - 1

    def build_embed(self):
        start = self.page * self.per_page
        chunk = self.rows[start:start + self.per_page]
        lines = []

        for index, row in enumerate(chunk, start=start + 1):
            member = self.ctx.guild.get_member(int(row["user_id"]))
            label = member.mention if member else f"<@{row['user_id']}>"
            total = int(row["total_invites"] or 0)
            goal = max(self.top_count, 1)
            bar = self.cog.make_bar(total, goal, length=12)
            percent = int((total / goal) * 100) if goal else 0
            lines.append(f"**#{index}** {label} - **{total}** invites\n`{bar}` {percent}%")

        embed = discord.Embed(
            title=f"Top {self.count} Inviters",
            description="\n\n".join(lines) if lines else "No invite data found yet.",
            color=COLORS["primary"],
            timestamp=utcnow(),
        )
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_pages}")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction, button):
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction, button):
        self.page = min(self.max_pages - 1, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class InviteDB:
    def __init__(self):
        self.available = _mysql_config_ready()
        self._warned_unavailable = False
        self._init_tables()

    def _connect(self):
        if not self.available:
            raise RuntimeError("InviteDB disabled because MySQL env is missing")
        return mysql.connector.connect(**MYSQL_CONFIG)

    def _warn_missing_mysql(self):
        if not self._warned_unavailable:
            print("InviteDB disabled: missing MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, or MYSQL_DATABASE")
            self._warned_unavailable = True

    def _init_tables(self):
        if not self.available:
            self._warn_missing_mysql()
            return
        try:
            conn = self._connect()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invite_tracker (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    total_invites INT NOT NULL DEFAULT 0,
                    left_count INT NOT NULL DEFAULT 0,
                    fake_count INT NOT NULL DEFAULT 0,
                    bonus_invites INT NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invite_joins (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    member_id BIGINT NOT NULL,
                    member_name VARCHAR(255) DEFAULT NULL,
                    inviter_id BIGINT DEFAULT NULL,
                    invite_code VARCHAR(32) DEFAULT NULL,
                    joined_at DATETIME NOT NULL,
                    left_at DATETIME DEFAULT NULL,
                    is_fake BOOLEAN NOT NULL DEFAULT FALSE,
                    INDEX idx_member (guild_id, member_id),
                    INDEX idx_inviter (guild_id, inviter_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invite_codes (
                    guild_id BIGINT NOT NULL,
                    invite_code VARCHAR(32) NOT NULL,
                    inviter_id BIGINT DEFAULT NULL,
                    uses INT NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT NULL,
                    expires_at DATETIME DEFAULT NULL,
                    PRIMARY KEY (guild_id, invite_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invite_config (
                    guild_id BIGINT PRIMARY KEY,
                    join_log_channel BIGINT DEFAULT NULL,
                    leave_log_channel BIGINT DEFAULT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invite_rewards (
                    guild_id BIGINT NOT NULL,
                    invite_count INT NOT NULL,
                    role_id BIGINT NOT NULL,
                    PRIMARY KEY (guild_id, invite_count)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invite_messages (
                    guild_id BIGINT PRIMARY KEY,
                    join_message TEXT DEFAULT NULL,
                    leave_message TEXT DEFAULT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
            cursor.close()
            conn.close()
        except Error as e:
            print(f"InviteDB init error: {e}")

    def execute(self, query, params=None, fetchone=False, fetchall=False, commit=False):
        if not self.available:
            self._warn_missing_mysql()
            return None if fetchone else []

        try:
            conn = self._connect()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            result = None
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            if commit:
                conn.commit()
            cursor.close()
            conn.close()
            return result
        except Error as e:
            print(f"InviteDB query error: {e}")
            return None if fetchone else []

    def upsert_invite_code(self, guild_id, invite):
        self.execute("""
            INSERT INTO invite_codes (guild_id, invite_code, inviter_id, uses, created_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                inviter_id = VALUES(inviter_id),
                uses = VALUES(uses),
                created_at = VALUES(created_at),
                expires_at = VALUES(expires_at)
        """, (
            guild_id,
            invite.code,
            invite.inviter.id if invite.inviter else None,
            invite.uses or 0,
            invite.created_at.replace(tzinfo=None) if invite.created_at else None,
            invite.expires_at.replace(tzinfo=None) if invite.expires_at else None,
        ), commit=True)

    def get_member_join(self, guild_id, member_id):
        return self.execute("""
            SELECT * FROM invite_joins
            WHERE guild_id = %s AND member_id = %s
            ORDER BY joined_at DESC, id DESC
            LIMIT 1
        """, (guild_id, member_id), fetchone=True)

    def get_inviter_stats(self, guild_id, user_id):
        row = self.execute("""
            SELECT * FROM invite_tracker WHERE guild_id = %s AND user_id = %s
        """, (guild_id, user_id), fetchone=True)
        return row or {
            "guild_id": guild_id,
            "user_id": user_id,
            "total_invites": 0,
            "left_count": 0,
            "fake_count": 0,
            "bonus_invites": 0,
        }

    def record_join(self, guild_id, member, inviter_id, invite_code):
        self.execute("""
            INSERT INTO invite_joins (guild_id, member_id, member_name, inviter_id, invite_code, joined_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            guild_id,
            member.id,
            str(member),
            inviter_id,
            invite_code,
            utcnow().replace(tzinfo=None),
        ), commit=True)

        if inviter_id:
            self.execute("""
                INSERT INTO invite_tracker (guild_id, user_id, total_invites)
                VALUES (%s, %s, 1)
                ON DUPLICATE KEY UPDATE total_invites = total_invites + 1
            """, (guild_id, inviter_id), commit=True)

    def record_leave(self, guild_id, member_id):
        row = self.get_member_join(guild_id, member_id)
        if not row:
            return None

        left_at = utcnow().replace(tzinfo=None)
        joined_at = row["joined_at"]
        fake = bool(joined_at and (left_at - joined_at).total_seconds() <= 86400)
        self.execute("""
            UPDATE invite_joins
            SET left_at = %s, is_fake = %s
            WHERE id = %s
        """, (left_at, fake, row["id"]), commit=True)

        if row.get("inviter_id"):
            self.execute("""
                INSERT INTO invite_tracker (guild_id, user_id, total_invites, left_count, fake_count)
                VALUES (%s, %s, 0, 1, %s)
                ON DUPLICATE KEY UPDATE
                    total_invites = GREATEST(total_invites - 1, 0),
                    left_count = left_count + 1,
                    fake_count = fake_count + VALUES(fake_count)
            """, (guild_id, row["inviter_id"], 1 if fake else 0), commit=True)

        row["left_at"] = left_at
        row["is_fake"] = fake
        return row

    def get_invite_history(self, guild_id, inviter_id):
        return self.execute("""
            SELECT * FROM invite_joins
            WHERE guild_id = %s AND inviter_id = %s
            ORDER BY joined_at DESC, id DESC
        """, (guild_id, inviter_id), fetchall=True)

    def set_reward(self, guild_id, invite_count, role_id):
        self.execute("""
            INSERT INTO invite_rewards (guild_id, invite_count, role_id)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE role_id = VALUES(role_id)
        """, (guild_id, invite_count, role_id), commit=True)

    def get_rewards(self, guild_id):
        return self.execute("""
            SELECT * FROM invite_rewards WHERE guild_id = %s ORDER BY invite_count ASC
        """, (guild_id,), fetchall=True)

    def remove_reward(self, guild_id, invite_count):
        self.execute("""
            DELETE FROM invite_rewards WHERE guild_id = %s AND invite_count = %s
        """, (guild_id, invite_count), commit=True)

    def get_reward_for_count(self, guild_id, invite_count):
        return self.execute("""
            SELECT * FROM invite_rewards WHERE guild_id = %s AND invite_count = %s
        """, (guild_id, invite_count), fetchone=True)

    def set_message(self, guild_id, column, message):
        self.execute(f"""
            INSERT INTO invite_messages (guild_id, {column})
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE {column} = VALUES({column})
        """, (guild_id, message), commit=True)

    def get_messages(self, guild_id):
        return self.execute("""
            SELECT * FROM invite_messages WHERE guild_id = %s
        """, (guild_id,), fetchone=True) or {}

    def get_stats_summary(self, guild_id):
        return {
            "joins": self.execute(
                "SELECT COUNT(*) AS count FROM invite_joins WHERE guild_id = %s",
                (guild_id,),
                fetchone=True,
            ) or {"count": 0},
            "tracker": self.execute("""
                SELECT
                    COALESCE(SUM(total_invites), 0) AS total_invites,
                    COALESCE(SUM(fake_count), 0) AS fake_count
                FROM invite_tracker
                WHERE guild_id = %s
            """, (guild_id,), fetchone=True) or {"total_invites": 0, "fake_count": 0},
            "top": self.execute("""
                SELECT user_id, total_invites
                FROM invite_tracker
                WHERE guild_id = %s
                ORDER BY total_invites DESC
                LIMIT 1
            """, (guild_id,), fetchone=True),
            "rewards": self.execute(
                "SELECT COUNT(*) AS count FROM invite_rewards WHERE guild_id = %s",
                (guild_id,),
                fetchone=True,
            ) or {"count": 0},
        }

    def top_inviters(self, guild_id, limit):
        return self.execute("""
            SELECT * FROM invite_tracker
            WHERE guild_id = %s
            ORDER BY total_invites DESC, user_id ASC
            LIMIT %s
        """, (guild_id, limit), fetchall=True)

    def get_config(self, guild_id):
        return self.execute("""
            SELECT * FROM invite_config WHERE guild_id = %s
        """, (guild_id,), fetchone=True) or {}

    def set_log_channel(self, guild_id, column, channel_id):
        self.execute(f"""
            INSERT INTO invite_config (guild_id, {column})
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE {column} = VALUES({column})
        """, (guild_id, channel_id), commit=True)


class InviteManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = InviteDB()
        self.invite_cache = {}
        self.invite_cache_ready = set()
        self.invite_permission_warnings = set()
        self.invite_goals = {}

    def make_bar(self, current, goal, length=16):
        if goal <= 0:
            return "░" * length
        filled = min(length, int((current / goal) * length))
        return "█" * filled + "░" * (length - filled)

    async def db_call(self, fn, *args):
        try:
            return await self.bot.loop.run_in_executor(None, lambda: fn(*args))
        except Exception as e:
            print(f"InviteDB executor error: {e}")
            return None

    def base_embed(self, title, description=None, color=None):
        embed = discord.Embed(
            title=title,
            description=description,
            color=color if color is not None else COLORS["primary"],
            timestamp=utcnow(),
        )
        embed.set_footer(text="Invite Manager")
        return embed

    def error_embed(self, message):
        return self.base_embed("Invite Error", message, COLORS["error"])

    def success_embed(self, title, message):
        return self.base_embed(title, message, COLORS["success"])

    def format_db_time(self, value, style="R"):
        if not value:
            return "Unknown"
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return discord.utils.format_dt(value, style)

    @staticmethod
    def can_read_guild_invites(guild):
        member = guild.me
        if member is None:
            return False
        permissions = member.guild_permissions
        return permissions.administrator or permissions.manage_guild

    def mark_invite_cache_unavailable(self, guild, *, announce=True, error=None):
        self.invite_cache.pop(guild.id, None)
        self.invite_cache_ready.discard(guild.id)
        if not announce or guild.id in self.invite_permission_warnings:
            return
        self.invite_permission_warnings.add(guild.id)
        error_code = getattr(error, "code", None)
        if error_code == 50001:
            detail = "Discord reports Missing Access; confirm xiel still belongs to and can access this server."
        else:
            detail = "Grant xiel the Manage Server permission to enable invite tracking."
        print(f"Invite tracking unavailable for {guild.id}: {detail}")

    async def cache_guild_invites(self, guild, *, announce=True):
        if not self.can_read_guild_invites(guild):
            self.mark_invite_cache_unavailable(guild, announce=announce)
            return False
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {invite.code: invite.uses or 0 for invite in invites}
            self.invite_cache_ready.add(guild.id)
            self.invite_permission_warnings.discard(guild.id)
            for invite in invites:
                await self.db_call(self.db.upsert_invite_code, guild.id, invite)
            return True
        except discord.Forbidden as error:
            self.mark_invite_cache_unavailable(guild, announce=announce, error=error)
            return False
        except discord.HTTPException as error:
            self.invite_cache.pop(guild.id, None)
            self.invite_cache_ready.discard(guild.id)
            print(f"Invite cache request failed for {guild.id}: HTTP {error.status} (code {error.code})")
            return False
        except Exception as error:
            self.invite_cache.pop(guild.id, None)
            self.invite_cache_ready.discard(guild.id)
            print(f"Invite cache error for {guild.id}: {error}")
            return False

    async def detect_used_invite(self, guild):
        if not self.can_read_guild_invites(guild):
            self.mark_invite_cache_unavailable(guild)
            return None
        if guild.id not in self.invite_cache_ready:
            await self.cache_guild_invites(guild)
            return None

        before = self.invite_cache.get(guild.id, {})
        try:
            invites = await guild.invites()
        except discord.Forbidden as error:
            self.mark_invite_cache_unavailable(guild, error=error)
            return None
        except discord.HTTPException as error:
            self.invite_cache.pop(guild.id, None)
            self.invite_cache_ready.discard(guild.id)
            print(f"Invite fetch failed for {guild.id}: HTTP {error.status} (code {error.code})")
            return None
        except Exception as error:
            self.invite_cache.pop(guild.id, None)
            self.invite_cache_ready.discard(guild.id)
            print(f"Invite fetch error for {guild.id}: {error}")
            return None

        used = None
        for invite in invites:
            old_uses = before.get(invite.code, 0)
            if (invite.uses or 0) > old_uses:
                used = invite
                break

        self.invite_cache[guild.id] = {invite.code: invite.uses or 0 for invite in invites}
        self.invite_cache_ready.add(guild.id)
        for invite in invites:
            await self.db_call(self.db.upsert_invite_code, guild.id, invite)
        return used

    def format_message(self, template, member, inviter, invite_count):
        return template.format(
            member=member.mention,
            member_name=str(member),
            server=member.guild.name,
            inviter=inviter.mention if inviter else "Unknown",
            invite_count=invite_count,
            member_count=member.guild.member_count,
        )

    async def get_log_channel(self, guild, key):
        config = await self.db_call(self.db.get_config, guild.id) or {}
        channel_id = config.get(key)
        if channel_id:
            channel = guild.get_channel(int(channel_id))
            if channel:
                return channel
        return None

    async def maybe_give_reward(self, guild, inviter_id, total_invites):
        reward = await self.db_call(self.db.get_reward_for_count, guild.id, total_invites)
        if not reward:
            return

        role = guild.get_role(int(reward["role_id"]))
        member = guild.get_member(int(inviter_id))
        if not role or not member:
            return

        try:
            await member.add_roles(role, reason=f"Reached {total_invites} invites")
            try:
                await member.send(
                    f"🎉 You've reached {total_invites} invites in {guild.name} and earned the {role.mention} role!"
                )
            except discord.HTTPException:
                pass
        except Exception as e:
            print(f"Invite reward role error: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        tracked = 0
        for guild in self.bot.guilds:
            if await self.cache_guild_invites(guild, announce=False):
                tracked += 1
        skipped = len(self.bot.guilds) - tracked
        summary = f"{tracked}/{len(self.bot.guilds)} servers"
        if skipped:
            summary += f"; {skipped} skipped without Manage Server"
        print(f"InviteManager invite cache ready ({summary}).")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        if invite.guild:
            await self.cache_guild_invites(invite.guild)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if invite.guild:
            await self.cache_guild_invites(invite.guild)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        used_invite = await self.detect_used_invite(member.guild)
        inviter = used_invite.inviter if used_invite else None
        invite_code = used_invite.code if used_invite else None

        await self.db_call(self.db.record_join, member.guild.id, member, inviter.id if inviter else None, invite_code)
        stats = await self.db_call(self.db.get_inviter_stats, member.guild.id, inviter.id) if inviter else None
        total_invites = int(stats["total_invites"]) if stats else 0

        if inviter:
            await self.maybe_give_reward(member.guild, inviter.id, total_invites)

        # Invite data is recorded silently; use ,inviter [member] to show it on demand.

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        row = await self.db_call(self.db.record_leave, member.guild.id, member.id)
        # Leave data is recorded silently; no automatic invite messages are posted.

    @commands.command(name="inviter")
    async def inviter(self, ctx, member: discord.Member = None):
        """Show who invited you or a specific member."""
        member = member or ctx.author
        row = await self.db_call(self.db.get_member_join, ctx.guild.id, member.id)
        if not row:
            return await ctx.reply(embed=self.error_embed("No invite data found for this member."))

        inviter = ctx.guild.get_member(int(row["inviter_id"])) if row.get("inviter_id") else None
        stats = await self.db_call(self.db.get_inviter_stats, ctx.guild.id, row["inviter_id"]) if row.get("inviter_id") else None
        stats_text = "0 total invites | 0 left | 0 fake"
        if stats:
            stats_text = f"{stats['total_invites']} total invites | {stats['left_count']} left | {stats['fake_count']} fake"

        embed = discord.Embed(title="Invite Information", color=COLORS["primary"], timestamp=utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Member",
            value=f"{member.mention} - joined {discord.utils.format_dt(member.joined_at, 'R') if member.joined_at else 'Unknown'}",
            inline=False,
        )
        embed.add_field(name="Invited by", value=inviter.mention if inviter else "Unknown / Vanity URL / Widget", inline=False)
        embed.add_field(name="Invite code", value=f"`{row.get('invite_code') or 'unknown'}`", inline=True)
        embed.add_field(name="Inviter stats", value=stats_text, inline=True)
        embed.add_field(name="Account age", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.set_footer(text=f"User ID: {member.id}")
        await ctx.reply(embed=embed)

    @commands.command(name="invitehistory")
    async def invitehistory(self, ctx, user: discord.Member = None):
        """Show every person a user has invited to this server."""
        user = user or ctx.author
        rows = await self.db_call(self.db.get_invite_history, ctx.guild.id, user.id) or []
        view = InviteHistoryView(self, ctx, user, rows)
        await ctx.reply(embed=view.build_embed(), view=view)

    @commands.command(name="setreward")
    @commands.has_permissions(manage_guild=True)
    async def setreward(self, ctx, invite_count: int, role: discord.Role):
        """Configure a role reward for a specific invite count."""
        if invite_count <= 0:
            return await ctx.reply(embed=self.error_embed("Invite count must be greater than 0."))
        await self.db_call(self.db.set_reward, ctx.guild.id, invite_count, role.id)
        await ctx.reply(embed=self.success_embed("Invite Reward Set", f"Role {role.mention} will be given at {invite_count} invites."))

    @commands.command(name="listrewards")
    async def listrewards(self, ctx):
        """List all configured invite reward roles for this server."""
        rows = await self.db_call(self.db.get_rewards, ctx.guild.id) or []
        if not rows:
            return await ctx.reply(embed=self.base_embed("Invite Rewards", "No invite rewards configured.", COLORS["secondary"]))

        lines = ["**Invites Needed**  |  **Role**"]
        for row in rows:
            role = ctx.guild.get_role(int(row["role_id"]))
            role_text = role.mention if role else f"<@&{row['role_id']}>"
            lines.append(f"{row['invite_count']}  |  {role_text}")

        await ctx.reply(embed=self.base_embed("Invite Rewards", "\n".join(lines), COLORS["secondary"]))

    @commands.command(name="removereward")
    @commands.has_permissions(manage_guild=True)
    async def removereward(self, ctx, invite_count: int):
        """Remove an invite reward threshold."""
        await self.db_call(self.db.remove_reward, ctx.guild.id, invite_count)
        await ctx.reply(embed=self.success_embed("Invite Reward Removed", f"Removed reward configured at {invite_count} invites."))

    @commands.command(name="setjoinmessage")
    @commands.has_permissions(manage_guild=True)
    async def setjoinmessage(self, ctx, *, message: str):
        """Set a custom text message for invite join logs."""
        await self.db_call(self.db.set_message, ctx.guild.id, "join_message", message)
        preview = self.format_message(message, ctx.author, ctx.author, 0)
        await ctx.reply(embed=self.success_embed("Join Message Set", f"Preview:\n{preview}"))

    @commands.command(name="setleavemessage")
    @commands.has_permissions(manage_guild=True)
    async def setleavemessage(self, ctx, *, message: str):
        """Set a custom text message for invite leave logs."""
        await self.db_call(self.db.set_message, ctx.guild.id, "leave_message", message)
        preview = self.format_message(message, ctx.author, ctx.author, 0)
        await ctx.reply(embed=self.success_embed("Leave Message Set", f"Preview:\n{preview}"))

    @commands.command(name="invitestats")
    async def invitestats(self, ctx):
        """Show server-wide invite statistics."""
        summary = await self.db_call(self.db.get_stats_summary, ctx.guild.id) or {}
        tracker = summary.get("tracker", {})
        joins = int(summary.get("joins", {}).get("count", 0))
        total = int(tracker.get("total_invites", 0) or 0)
        fake = int(tracker.get("fake_count", 0) or 0)
        fake_rate = (fake / total * 100) if total else 0
        top = summary.get("top")
        top_text = "No data"
        if top:
            member = ctx.guild.get_member(int(top["user_id"]))
            member_text = member.mention if member else f"<@{top['user_id']}>"
            top_text = f"{member_text} - {top['total_invites']} invites"

        active_invites = "Unavailable (grant Manage Server)"
        if self.can_read_guild_invites(ctx.guild):
            try:
                active_invites = str(len(await ctx.guild.invites()))
            except discord.Forbidden as error:
                self.mark_invite_cache_unavailable(ctx.guild, error=error)
            except discord.HTTPException as error:
                print(
                    f"Active invite fetch failed for {ctx.guild.id}: "
                    f"HTTP {error.status} (code {error.code})"
                )

        embed = self.base_embed("Server Invite Stats", color=COLORS["primary"])
        embed.add_field(name="Total joins tracked", value=str(joins), inline=True)
        embed.add_field(name="Total invites given out", value=str(total), inline=True)
        embed.add_field(name="Fake invite rate", value=f"{fake_rate:.1f}%", inline=True)
        embed.add_field(name="Top inviter", value=top_text, inline=False)
        embed.add_field(name="Reward roles configured", value=str(summary.get("rewards", {}).get("count", 0)), inline=True)
        embed.add_field(name="Active invite links", value=active_invites, inline=True)
        embed.set_footer(text=f"Last updated {discord.utils.format_dt(utcnow(), 'R')}")
        await ctx.reply(embed=embed)

    @commands.command(name="invitegoal")
    async def invitegoal(self, ctx, goal: int):
        """Set and show your personal invite goal."""
        if goal <= 0:
            return await ctx.reply(embed=self.error_embed("Goal must be greater than 0."))

        self.invite_goals[(ctx.guild.id, ctx.author.id)] = goal
        stats = await self.db_call(self.db.get_inviter_stats, ctx.guild.id, ctx.author.id) or {}
        current = int(stats.get("total_invites", 0))
        percent = min(100, int((current / goal) * 100))
        bar = self.make_bar(current, goal)

        embed = self.base_embed("Invite Goal", color=COLORS["secondary"])
        embed.description = f"`{bar}`  {current}/{goal} invites ({percent}%)"
        await ctx.reply(embed=embed)

    @commands.command(name="topinvites")
    async def topinvites(self, ctx, count: int = 10):
        """Show the top N inviters with percentage bars."""
        count = max(1, min(count, 25))
        rows = await self.db_call(self.db.top_inviters, ctx.guild.id, count) or []
        view = TopInvitesView(self, ctx, rows, count)
        await ctx.reply(embed=view.build_embed(), view=view)

    @commands.command(name="setinvitelog")
    @commands.has_permissions(manage_guild=True)
    async def setinvitelog(self, ctx, log_type: str, channel: discord.TextChannel = None):
        """Set join or leave invite log channel."""
        channel = channel or ctx.channel
        log_type = log_type.lower()
        if log_type not in {"join", "leave"}:
            return await ctx.reply(embed=self.error_embed("Use `join` or `leave` as the log type."))

        column = "join_log_channel" if log_type == "join" else "leave_log_channel"
        await self.db_call(self.db.set_log_channel, ctx.guild.id, column, channel.id)
        await ctx.reply(embed=self.success_embed("Invite Log Updated", f"{log_type.title()} invite logs will be sent to {channel.mention}."))

    @commands.command(name="invites")
    async def invites(self, ctx, user: discord.Member = None):
        """Show invite totals for a user."""
        user = user or ctx.author
        stats = await self.db_call(self.db.get_inviter_stats, ctx.guild.id, user.id) or {}
        total = int(stats.get("total_invites", 0))
        left = int(stats.get("left_count", 0))
        fake = int(stats.get("fake_count", 0))
        embed = self.base_embed(f"Invites - {user}", color=COLORS["primary"])
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Total Invites", value=str(total), inline=True)
        embed.add_field(name="Left", value=str(left), inline=True)
        embed.add_field(name="Fake", value=str(fake), inline=True)
        await ctx.reply(embed=embed)

    @commands.command(name="inviteleaderboard", aliases=["invitelb", "invlb"])
    async def inviteleaderboard(self, ctx):
        """Show the top 10 invite leaderboard."""
        rows = await self.db_call(self.db.top_inviters, ctx.guild.id, 10) or []
        view = TopInvitesView(self, ctx, rows, 10)
        await ctx.reply(embed=view.build_embed(), view=view)

    @setreward.error
    @removereward.error
    @setjoinmessage.error
    @setleavemessage.error
    @setinvitelog.error
    async def admin_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            return await ctx.reply(embed=self.error_embed("You need Manage Server permission to use this command."))
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.reply(embed=self.error_embed(f"Missing argument: `{error.param.name}`"))
        if isinstance(error, commands.BadArgument):
            return await ctx.reply(embed=self.error_embed("Invalid argument provided."))
        print(f"Invite admin command error: {error}")
        await ctx.reply(embed=self.error_embed("Something went wrong while running that command."))

    @inviter.error
    @invitehistory.error
    @invitegoal.error
    @topinvites.error
    @invites.error
    async def command_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.reply(embed=self.error_embed(f"Missing argument: `{error.param.name}`"))
        if isinstance(error, commands.BadArgument):
            return await ctx.reply(embed=self.error_embed("I could not parse that member, role, or number."))
        print(f"Invite command error: {error}")
        await ctx.reply(embed=self.error_embed("Something went wrong while running that command."))


async def setup(bot):
    await bot.add_cog(InviteManager(bot))
