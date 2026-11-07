import asyncio
import os
import time
from datetime import datetime, UTC

import discord
from discord.ext import commands, tasks
import mysql.connector

import config
from utils.embeds import error_embed, info_embed, success_embed


PERIODS = ("daily", "weekly", "monthly", "total")


def _get_mysql_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", ""),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", ""),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", ""),
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
    )


def _period_keys(now=None):
    now = now or datetime.now(UTC)
    iso = now.isocalendar()
    return {
        "daily": now.strftime("%Y-%m-%d"),
        "weekly": f"{iso.year}-W{iso.week:02d}",
        "monthly": now.strftime("%Y-%m"),
        "total": "all",
    }


class MessageStats(commands.Cog):
    """Giveaway Boat-style message counting and leaderboards."""

    def __init__(self, bot):
        self.bot = bot
        self.enabled_cache = {}
        self.pending = {}
        self.pending_lock = asyncio.Lock()
        self.db_ready = asyncio.Event()
        asyncio.create_task(self.init_db())
        self.flush_message_counts.start()

    def cog_unload(self):
        self.flush_message_counts.cancel()

    async def init_db(self):
        def _init():
            conn = _get_mysql_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_message_counter_settings (
                        guild_id BIGINT PRIMARY KEY,
                        enabled TINYINT DEFAULT 0,
                        updated_at BIGINT
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_message_counts (
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        period_type VARCHAR(16) NOT NULL,
                        period_key VARCHAR(16) NOT NULL,
                        count INT DEFAULT 0,
                        updated_at BIGINT,
                        PRIMARY KEY (guild_id, user_id, period_type, period_key),
                        INDEX idx_message_counts_leaderboard (guild_id, period_type, period_key, count)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                conn.commit()
            finally:
                cursor.close()
                conn.close()

        try:
            await asyncio.to_thread(_init)
        except Exception as e:
            print(f"Message counter DB init failed: {e}")
        finally:
            self.db_ready.set()

    def _sync_execute(self, query, params=None, fetchone=False, fetchall=False):
        conn = _get_mysql_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params)
            result = None
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            conn.commit()
            return result
        finally:
            cursor.close()
            conn.close()

    async def _execute(self, query, params=None, fetchone=False, fetchall=False):
        await self.db_ready.wait()
        return await asyncio.to_thread(self._sync_execute, query, params, fetchone, fetchall)

    def _sync_bulk_increment(self, rows):
        conn = _get_mysql_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT INTO bot_message_counts
                    (guild_id, user_id, period_type, period_key, count, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    count = count + VALUES(count),
                    updated_at = VALUES(updated_at)
            """, rows)
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    async def _get_prefix(self, message):
        if message.guild and hasattr(self.bot, "prefix_cache"):
            return self.bot.prefix_cache.get(message.guild.id, config.PREFIX)
        return config.PREFIX

    async def _is_enabled(self, guild_id):
        guild_id = int(guild_id)
        if guild_id in self.enabled_cache:
            return self.enabled_cache[guild_id]

        row = await self._execute(
            "SELECT enabled FROM bot_message_counter_settings WHERE guild_id = %s",
            (guild_id,),
            fetchone=True,
        )
        enabled = bool(row and row.get("enabled"))
        self.enabled_cache[guild_id] = enabled
        return enabled

    async def _set_enabled(self, guild_id, enabled):
        guild_id = int(guild_id)
        await self._execute("""
            INSERT INTO bot_message_counter_settings (guild_id, enabled, updated_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE enabled = VALUES(enabled), updated_at = VALUES(updated_at)
        """, (guild_id, 1 if enabled else 0, int(time.time())))
        self.enabled_cache[guild_id] = bool(enabled)

    async def _queue_increment(self, guild_id, user_id):
        keys = _period_keys()
        async with self.pending_lock:
            for period, period_key in keys.items():
                key = (int(guild_id), int(user_id), period, period_key)
                self.pending[key] = self.pending.get(key, 0) + 1

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        if not await self._is_enabled(message.guild.id):
            return

        prefix = await self._get_prefix(message)
        if prefix and message.content.startswith(prefix):
            return

        await self._queue_increment(message.guild.id, message.author.id)

    @tasks.loop(seconds=30)
    async def flush_message_counts(self):
        await self.db_ready.wait()
        async with self.pending_lock:
            if not self.pending:
                return
            batch = self.pending
            self.pending = {}

        now = int(time.time())
        rows = [
            (guild_id, user_id, period, period_key, count, now)
            for (guild_id, user_id, period, period_key), count in batch.items()
        ]
        try:
            await asyncio.to_thread(self._sync_bulk_increment, rows)
        except Exception as e:
            print(f"Message counter flush failed: {e}")
            async with self.pending_lock:
                for key, count in batch.items():
                    self.pending[key] = self.pending.get(key, 0) + count

    @flush_message_counts.before_loop
    async def before_flush_message_counts(self):
        await self.bot.wait_until_ready()

    async def get_counts_for_users(self, guild_id, user_ids):
        user_ids = [int(user_id) for user_id in user_ids]
        result = {user_id: {period: 0 for period in PERIODS} for user_id in user_ids}
        if not user_ids:
            return result

        keys = _period_keys()
        placeholders = ",".join(["%s"] * len(user_ids))
        params = [int(guild_id), *user_ids]
        for period, period_key in keys.items():
            params.extend([period, period_key])

        period_clause = " OR ".join(["(period_type = %s AND period_key = %s)" for _ in PERIODS])
        rows = await self._execute(
            f"""
            SELECT user_id, period_type, count
            FROM bot_message_counts
            WHERE guild_id = %s
              AND user_id IN ({placeholders})
              AND ({period_clause})
            """,
            tuple(params),
            fetchall=True,
        )
        for row in rows or []:
            user_id = int(row["user_id"])
            period = row["period_type"]
            if user_id in result and period in result[user_id]:
                result[user_id][period] += int(row.get("count") or 0)

        async with self.pending_lock:
            for (pending_guild, user_id, period, period_key), count in self.pending.items():
                if pending_guild == int(guild_id) and user_id in result and keys.get(period) == period_key:
                    result[user_id][period] += int(count)

        return result

    async def _get_user_counts(self, guild_id, user_id):
        return (await self.get_counts_for_users(guild_id, [user_id])).get(int(user_id), {period: 0 for period in PERIODS})

    async def _get_leaderboard(self, guild_id, period, limit):
        keys = _period_keys()
        rows = await self._execute(
            """
            SELECT user_id, count
            FROM bot_message_counts
            WHERE guild_id = %s AND period_type = %s AND period_key = %s
            ORDER BY count DESC
            LIMIT %s
            """,
            (int(guild_id), period, keys[period], int(limit)),
            fetchall=True,
        )
        leaderboard = {int(row["user_id"]): int(row.get("count") or 0) for row in rows or []}
        async with self.pending_lock:
            for (pending_guild, user_id, pending_period, period_key), count in self.pending.items():
                if pending_guild == int(guild_id) and pending_period == period and keys[period] == period_key:
                    leaderboard[user_id] = leaderboard.get(user_id, 0) + int(count)
        return sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)[:limit]

    @commands.group(name="messagecounter", aliases=["msgcounter"], invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def messagecounter(self, ctx):
        enabled = await self._is_enabled(ctx.guild.id)
        state = "enabled" if enabled else "disabled"
        await ctx.reply(embed=info_embed("Message Counter", f"Message counting is currently **{state}**."))

    @messagecounter.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def messagecounter_enable(self, ctx):
        await self._set_enabled(ctx.guild.id, True)
        await ctx.reply(embed=success_embed("Message Counter Enabled", "Human non-command messages will now be counted."))

    @messagecounter.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def messagecounter_disable(self, ctx):
        await self._set_enabled(ctx.guild.id, False)
        await ctx.reply(embed=success_embed("Message Counter Disabled", "Message counting is now disabled."))

    @messagecounter.command(name="status")
    @commands.has_permissions(manage_guild=True)
    async def messagecounter_status(self, ctx):
        enabled = await self._is_enabled(ctx.guild.id)
        state = "enabled" if enabled else "disabled"
        await ctx.reply(embed=info_embed("Message Counter", f"Message counting is currently **{state}**."))

    @commands.command(name="messages", aliases=["msgcount", "messagecount"])
    @commands.guild_only()
    async def messages(self, ctx, *args):
        member = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
        period = "total"
        for arg in args:
            lowered = arg.lower()
            if lowered in PERIODS:
                period = lowered
            elif not ctx.message.mentions:
                return await ctx.reply(embed=error_embed("Invalid User", "Mention a user or use `daily`, `weekly`, `monthly`, or `total`."))
        if period not in PERIODS:
            return await ctx.reply(embed=error_embed("Invalid Period", "Use `daily`, `weekly`, `monthly`, or `total`."))

        counts = await self._get_user_counts(ctx.guild.id, member.id)
        embed = discord.Embed(
            title=f"{member.display_name}'s Messages",
            color=config.COLORS["primary"],
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name=period.title(), value=f"`{counts[period]:,}` messages", inline=False)
        embed.add_field(
            name="All Periods",
            value=(
                f"Daily: `{counts['daily']:,}`\n"
                f"Weekly: `{counts['weekly']:,}`\n"
                f"Monthly: `{counts['monthly']:,}`\n"
                f"Total: `{counts['total']:,}`"
            ),
            inline=False,
        )
        await ctx.reply(embed=embed)

    @commands.command(name="messagelb", aliases=["messageleaderboard", "msglb"])
    @commands.guild_only()
    async def messagelb(self, ctx, period: str = "total", limit: int = 10):
        period = period.lower()
        if period not in PERIODS:
            return await ctx.reply(embed=error_embed("Invalid Period", "Use `daily`, `weekly`, `monthly`, or `total`."))
        limit = max(1, min(int(limit), 25))

        rows = await self._get_leaderboard(ctx.guild.id, period, limit)
        if not rows:
            return await ctx.reply(embed=info_embed("Message Leaderboard", "No counted messages for that period yet."))

        lines = []
        for index, (user_id, count) in enumerate(rows, start=1):
            rank = f"`#{index}`"
            lines.append(f"{rank} <@{user_id}> - `{count:,}`")

        embed = discord.Embed(
            title=f"Message Leaderboard - {period.title()}",
            description="\n".join(lines),
            color=config.COLORS["primary"],
        )
        await ctx.reply(embed=embed)

    @commands.command(name="messagereset")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def messagereset(self, ctx, target: str = None):
        if not target:
            return await ctx.reply(embed=error_embed("Missing Target", "Use `,messagereset @user` or `,messagereset all`."))

        async with self.pending_lock:
            if target.lower() == "all":
                self.pending = {key: value for key, value in self.pending.items() if key[0] != ctx.guild.id}
            elif ctx.message.mentions:
                user_id = ctx.message.mentions[0].id
                self.pending = {key: value for key, value in self.pending.items() if not (key[0] == ctx.guild.id and key[1] == user_id)}
            else:
                return await ctx.reply(embed=error_embed("Invalid Target", "Use `,messagereset @user` or `,messagereset all`."))

        if target.lower() == "all":
            await self._execute("DELETE FROM bot_message_counts WHERE guild_id = %s", (ctx.guild.id,))
            return await ctx.reply(embed=success_embed("Message Counts Reset", "All message counts were reset for this server."))

        member = ctx.message.mentions[0]
        await self._execute(
            "DELETE FROM bot_message_counts WHERE guild_id = %s AND user_id = %s",
            (ctx.guild.id, member.id),
        )
        await ctx.reply(embed=success_embed("Message Counts Reset", f"Message counts reset for {member.mention}."))


async def setup(bot):
    await bot.add_cog(MessageStats(bot))
