import os
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

from config import COLORS, OWNER_IDS


load_dotenv()

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", ""),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", ""),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", ""),
}

CONFESSION_COLOR = 0x2B2D31
INVITE_RE = re.compile(r"(discord\.gg/|discord(?:app)?\.com/invite/)", re.IGNORECASE)


def utcnow():
    return datetime.now(timezone.utc)


class ConfessionDB:
    def __init__(self):
        self._init_tables()

    def _connect(self):
        return mysql.connector.connect(**MYSQL_CONFIG)

    def _init_tables(self):
        try:
            conn = self._connect()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS confessions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id VARCHAR(32) NOT NULL,
                    channel_id VARCHAR(32) NOT NULL,
                    message TEXT NOT NULL,
                    embed_message_id VARCHAR(32) DEFAULT NULL,
                    created_at BIGINT NOT NULL,
                    INDEX idx_confession_guild (guild_id),
                    INDEX idx_confession_message (guild_id, embed_message_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS confession_senders (
                    confession_id INT PRIMARY KEY,
                    guild_id VARCHAR(32) NOT NULL,
                    sender_id VARCHAR(32) NOT NULL,
                    INDEX idx_sender_guild (guild_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS confession_config (
                    guild_id VARCHAR(32) PRIMARY KEY,
                    channel_id VARCHAR(32) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS confession_bans (
                    guild_id VARCHAR(32) NOT NULL,
                    user_id VARCHAR(32) NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS word_filters (
                    guild_id VARCHAR(32) NOT NULL,
                    word VARCHAR(255) NOT NULL,
                    PRIMARY KEY (guild_id, word)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS confession_reactions (
                    confession_id INT PRIMARY KEY,
                    support_count INT NOT NULL DEFAULT 0,
                    relate_count INT NOT NULL DEFAULT 0,
                    strength_count INT NOT NULL DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
            cursor.close()
            conn.close()
        except Error as e:
            print(f"ConfessionDB init error: {e}")

    def execute(self, query, params=None, fetchone=False, fetchall=False, commit=False, lastrowid=False):
        try:
            conn = self._connect()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            result = None
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            elif lastrowid:
                result = cursor.lastrowid
            if commit:
                conn.commit()
            cursor.close()
            conn.close()
            return result
        except Error as e:
            print(f"ConfessionDB query error: {e} | Query: {query}")
            return None if fetchone or lastrowid else []

    def set_config(self, guild_id, channel_id):
        self.execute("""
            INSERT INTO confession_config (guild_id, channel_id)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE channel_id = VALUES(channel_id)
        """, (str(guild_id), str(channel_id)), commit=True)

    def get_config(self, guild_id):
        return self.execute(
            "SELECT * FROM confession_config WHERE guild_id = %s",
            (str(guild_id),),
            fetchone=True,
        )

    def create_confession(self, guild_id, channel_id, sender_id, message):
        created_at = int(datetime.now(timezone.utc).timestamp())
        confession_id = self.execute("""
            INSERT INTO confessions (guild_id, channel_id, message, created_at)
            VALUES (%s, %s, %s, %s)
        """, (str(guild_id), str(channel_id), message, created_at), commit=True, lastrowid=True)
        self.execute("""
            INSERT INTO confession_senders (confession_id, guild_id, sender_id)
            VALUES (%s, %s, %s)
        """, (confession_id, str(guild_id), str(sender_id)), commit=True)
        self.execute(
            "INSERT INTO confession_reactions (confession_id) VALUES (%s)",
            (confession_id,),
            commit=True,
        )
        return {
            "id": confession_id,
            "guild_id": str(guild_id),
            "channel_id": str(channel_id),
            "message": message,
            "created_at": created_at,
            "embed_message_id": None,
        }

    def set_embed_message_id(self, confession_id, message_id):
        self.execute(
            "UPDATE confessions SET embed_message_id = %s WHERE id = %s",
            (str(message_id), confession_id),
            commit=True,
        )

    def get_confession(self, guild_id, confession_id):
        return self.execute("""
            SELECT c.*, s.sender_id
            FROM confessions c
            LEFT JOIN confession_senders s ON s.confession_id = c.id
            WHERE c.guild_id = %s AND c.id = %s
        """, (str(guild_id), confession_id), fetchone=True)

    def get_confession_by_message(self, guild_id, message_id):
        return self.execute("""
            SELECT * FROM confessions
            WHERE guild_id = %s AND embed_message_id = %s
        """, (str(guild_id), str(message_id)), fetchone=True)

    def delete_confession(self, guild_id, confession_id):
        self.execute("DELETE FROM confession_reactions WHERE confession_id = %s", (confession_id,), commit=True)
        self.execute("DELETE FROM confession_senders WHERE confession_id = %s", (confession_id,), commit=True)
        self.execute(
            "DELETE FROM confessions WHERE guild_id = %s AND id = %s",
            (str(guild_id), confession_id),
            commit=True,
        )

    def is_banned(self, guild_id, user_id):
        row = self.execute(
            "SELECT 1 FROM confession_bans WHERE guild_id = %s AND user_id = %s",
            (str(guild_id), str(user_id)),
            fetchone=True,
        )
        return bool(row)

    def ban_user(self, guild_id, user_id):
        self.execute("""
            INSERT IGNORE INTO confession_bans (guild_id, user_id)
            VALUES (%s, %s)
        """, (str(guild_id), str(user_id)), commit=True)

    def unban_user(self, guild_id, user_id):
        self.execute(
            "DELETE FROM confession_bans WHERE guild_id = %s AND user_id = %s",
            (str(guild_id), str(user_id)),
            commit=True,
        )

    def add_filter(self, guild_id, word):
        self.execute("""
            INSERT IGNORE INTO word_filters (guild_id, word)
            VALUES (%s, %s)
        """, (str(guild_id), word.lower()), commit=True)

    def remove_filter(self, guild_id, word):
        self.execute(
            "DELETE FROM word_filters WHERE guild_id = %s AND word = %s",
            (str(guild_id), word.lower()),
            commit=True,
        )

    def get_filters(self, guild_id):
        rows = self.execute(
            "SELECT word FROM word_filters WHERE guild_id = %s",
            (str(guild_id),),
            fetchall=True,
        )
        return [row["word"] for row in rows]

    def get_reactions(self, confession_id):
        self.execute(
            "INSERT IGNORE INTO confession_reactions (confession_id) VALUES (%s)",
            (confession_id,),
            commit=True,
        )
        return self.execute(
            "SELECT * FROM confession_reactions WHERE confession_id = %s",
            (confession_id,),
            fetchone=True,
        ) or {"support_count": 0, "relate_count": 0, "strength_count": 0}

    def increment_reaction(self, confession_id, reaction_type):
        columns = {
            "support": "support_count",
            "relate": "relate_count",
            "strength": "strength_count",
        }
        column = columns.get(reaction_type)
        if not column:
            return self.get_reactions(confession_id)
        self.execute(
            f"UPDATE confession_reactions SET {column} = {column} + 1 WHERE confession_id = %s",
            (confession_id,),
            commit=True,
        )
        return self.get_reactions(confession_id)

    def adjust_support_reaction(self, confession_id, delta):
        self.execute(
            """
            UPDATE confession_reactions
            SET support_count = GREATEST(support_count + %s, 0)
            WHERE confession_id = %s
            """,
            (delta, confession_id),
            commit=True,
        )
        return self.get_reactions(confession_id)

    def stats(self, guild_id):
        total = self.execute(
            "SELECT COUNT(*) AS total FROM confessions WHERE guild_id = %s",
            (str(guild_id),),
            fetchone=True,
        ) or {"total": 0}
        day = self.execute("""
            SELECT FROM_UNIXTIME(created_at, '%Y-%m-%d') AS day, COUNT(*) AS count
            FROM confessions
            WHERE guild_id = %s
            GROUP BY day
            ORDER BY count DESC, day DESC
            LIMIT 1
        """, (str(guild_id),), fetchone=True) or {"day": "No data", "count": 0}
        reactions = self.execute("""
            SELECT COALESCE(SUM(r.support_count + r.relate_count + r.strength_count), 0) AS total
            FROM confessions c
            LEFT JOIN confession_reactions r ON r.confession_id = c.id
            WHERE c.guild_id = %s
        """, (str(guild_id),), fetchone=True) or {"total": 0}
        return {
            "total": total["total"],
            "day": day["day"] or "No data",
            "day_count": day["count"] or 0,
            "reactions": reactions["total"] or 0,
        }


class ConfessionManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = ConfessionDB()

    async def db_call(self, fn, *args):
        try:
            return await self.bot.loop.run_in_executor(None, lambda: fn(*args))
        except Exception as e:
            print(f"ConfessionDB executor error: {e}")
            return None

    def base_embed(self, title, description=None, color=None):
        embed = discord.Embed(
            title=title,
            description=description,
            color=color if color is not None else COLORS["primary"],
            timestamp=utcnow(),
        )
        return embed

    def build_confession_embed(self, row):
        embed = discord.Embed(
            title=f"🔒 Anonymous Confession #{int(row['id']):03d}",
            description=row["message"],
            color=CONFESSION_COLOR,
            timestamp=datetime.fromtimestamp(int(row["created_at"]), timezone.utc),
        )
        embed.set_footer(text="Your identity is protected • React with ❤️ to support")
        return embed

    def sanitize_message(self, content):
        return content.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere").strip()

    async def safe_dm(self, user, content=None, embed=None):
        try:
            await user.send(content=content, embed=embed)
        except Exception:
            pass

    async def get_confession_channel_id(self, guild_id):
        config = await self.db_call(self.db.get_config, guild_id)
        return int(config["channel_id"]) if config and config.get("channel_id") else None

    async def is_blocked_by_filter(self, guild_id, content):
        if INVITE_RE.search(content):
            return "silent"
        filters = await self.db_call(self.db.get_filters, guild_id) or []
        lowered = content.lower()
        if any(word and word in lowered for word in filters):
            return "dm"
        return None

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return

        channel_id = await self.get_confession_channel_id(message.guild.id)
        if not channel_id or message.channel.id != channel_id:
            return

        perms = message.channel.permissions_for(message.guild.me)
        if not perms.manage_messages:
            await self.safe_dm(
                message.author,
                "The confession channel is not configured correctly. I need Manage Messages permission so your identity can stay protected.",
            )
            owner = message.guild.owner or await message.guild.fetch_member(message.guild.owner_id)
            if owner:
                await self.safe_dm(
                    owner,
                    f"Confession privacy warning in **{message.guild.name}**: I cannot delete messages in {message.channel.mention}. Please grant Manage Messages.",
                )
            return

        await message.delete()
        if not message.content or not message.content.strip():
            return

        # Owner bypass — bot owners can always submit confessions
        if message.author.id not in OWNER_IDS:
            if await self.db_call(self.db.is_banned, message.guild.id, message.author.id):
                await self.safe_dm(message.author, "You are not allowed to submit confessions in this server.")
                return

        filter_result = await self.is_blocked_by_filter(message.guild.id, message.content)
        if filter_result == "silent":
            return
        if filter_result == "dm":
            await self.safe_dm(message.author, "Your confession was blocked by the server filter.")
            return

        clean_message = self.sanitize_message(message.content)
        if not clean_message:
            return

        row = await self.db_call(
            self.db.create_confession,
            message.guild.id,
            message.channel.id,
            message.author.id,
            clean_message,
        )
        sent = await message.channel.send(
            embed=self.build_confession_embed(row),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await self.db_call(self.db.set_embed_message_id, row["id"], sent.id)
        try:
            await sent.add_reaction("❤️")
        except Exception as e:
            print(f"Confession support reaction error: {e}")

    async def handle_support_reaction(self, payload, delta):
        if str(payload.emoji) != "❤️" or self.bot.user and payload.user_id == self.bot.user.id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        row = await self.db_call(self.db.get_confession_by_message, payload.guild_id, payload.message_id)
        if not row:
            return
        await self.db_call(self.db.adjust_support_reaction, row["id"], delta)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.handle_support_reaction(payload, 1)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.handle_support_reaction(payload, -1)

    @commands.command(name="setconfession")
    @commands.has_permissions(manage_guild=True)
    async def setconfession(self, ctx, channel: discord.TextChannel):
        """Set the anonymous confession channel."""
        await self.db_call(self.db.set_config, ctx.guild.id, channel.id)
        await ctx.reply(embed=self.base_embed("Confession Channel Set", f"{channel.mention} is now the anonymous confession channel.", COLORS["success"]))

    @commands.command(name="confesslog")
    @commands.has_permissions(manage_guild=True)
    async def confesslog(self, ctx, confession_id: int):
        """Privately reveal who sent a confession ID."""
        row = await self.db_call(self.db.get_confession, ctx.guild.id, confession_id)
        if not row:
            return await ctx.reply(embed=self.base_embed("Not Found", f"No confession found for #{confession_id:03d}.", COLORS["error"]))

        user = await self.bot.fetch_user(int(row["sender_id"]))
        embed = self.base_embed(
            f"Private Confession Log #{confession_id:03d}",
            f"Sender: {user} (`{user.id}`)\nChannel: <#{row['channel_id']}>\nCreated: <t:{row['created_at']}:F>\n\n**Message:**\n{row['message']}",
            COLORS["warning"],
        )
        await self.safe_dm(ctx.author, embed=embed)
        await ctx.reply(embed=self.base_embed("Log Sent Privately", "I sent the confession sender details to your DMs.", COLORS["success"]))

    @commands.command(name="deleteconfession")
    @commands.has_permissions(manage_guild=True)
    async def deleteconfession(self, ctx, confession_id: int):
        """Delete a confession embed and remove it from the database."""
        row = await self.db_call(self.db.get_confession, ctx.guild.id, confession_id)
        if not row:
            return await ctx.reply(embed=self.base_embed("Not Found", f"No confession found for #{confession_id:03d}.", COLORS["error"]))

        channel = ctx.guild.get_channel(int(row["channel_id"]))
        if channel and row.get("embed_message_id"):
            try:
                msg = await channel.fetch_message(int(row["embed_message_id"]))
                await msg.delete()
            except Exception as e:
                print(f"deleteconfession message delete error: {e}")

        await self.db_call(self.db.delete_confession, ctx.guild.id, confession_id)
        await ctx.reply(embed=self.base_embed("Confession Deleted", f"Confession #{confession_id:03d} was deleted.", COLORS["success"]))

    @commands.command(name="banconfess")
    @commands.has_permissions(manage_guild=True)
    async def banconfess(self, ctx, member: discord.Member):
        """Block a user from submitting confessions."""
        await self.db_call(self.db.ban_user, ctx.guild.id, member.id)
        await ctx.reply(embed=self.base_embed("User Confession-Banned", f"{member.mention} can no longer submit confessions.", COLORS["warning"]))

    @commands.command(name="unbanconfess")
    @commands.has_permissions(manage_guild=True)
    async def unbanconfess(self, ctx, member: discord.Member):
        """Remove a user's confession ban."""
        await self.db_call(self.db.unban_user, ctx.guild.id, member.id)
        await ctx.reply(embed=self.base_embed("User Confession-Unbanned", f"{member.mention} can submit confessions again.", COLORS["success"]))

    @commands.command(name="reply")
    async def reply(self, ctx, confession_id: int, *, message: str):
        """Reply anonymously in a thread on a confession."""
        row = await self.db_call(self.db.get_confession, ctx.guild.id, confession_id)
        if not row:
            return await ctx.reply(embed=self.base_embed("Not Found", f"No confession found for #{confession_id:03d}.", COLORS["error"]))

        if ctx.author.id not in OWNER_IDS:
            if await self.db_call(self.db.is_banned, ctx.guild.id, ctx.author.id):
                return await ctx.reply("You are not allowed to submit confessions.", delete_after=8)

        filter_result = await self.is_blocked_by_filter(ctx.guild.id, message)
        if filter_result:
            await self.safe_dm(ctx.author, "Your confession was blocked by the server filter.")
            try:
                await ctx.message.delete()
            except Exception:
                pass
            return

        channel = ctx.guild.get_channel(int(row["channel_id"]))
        if not channel or not row.get("embed_message_id"):
            return await ctx.reply(embed=self.base_embed("Missing Message", "I cannot find the original confession embed.", COLORS["error"]))

        confession_message = await channel.fetch_message(int(row["embed_message_id"]))
        thread = confession_message.thread
        if thread is None:
            thread = await confession_message.create_thread(name=f"Confession #{confession_id:03d} replies")

        embed = self.base_embed(
            f"Anonymous Reply to #{confession_id:03d}",
            self.sanitize_message(message),
            CONFESSION_COLOR,
        )
        embed.set_footer(text="Anonymous reply • Identity protected")
        await thread.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await ctx.reply(embed=self.base_embed("Reply Posted", "Your anonymous reply was posted in the confession thread.", COLORS["success"]))

    @commands.command(name="confessionstats")
    async def confessionstats(self, ctx):
        """Show total confessions, most active day, and total reactions."""
        stats = await self.db_call(self.db.stats, ctx.guild.id) or {}
        embed = self.base_embed("Confession Stats", color=COLORS["primary"])
        embed.add_field(name="Total Confessions", value=str(stats.get("total", 0)), inline=True)
        embed.add_field(name="Most Active Day", value=f"{stats.get('day', 'No data')} ({stats.get('day_count', 0)})", inline=True)
        embed.add_field(name="Total Reactions", value=str(stats.get("reactions", 0)), inline=True)
        await ctx.reply(embed=embed)

    @commands.command(name="addfilter")
    @commands.has_permissions(manage_guild=True)
    async def addfilter(self, ctx, *, word: str):
        """Add a blocked confession word or phrase."""
        await self.db_call(self.db.add_filter, ctx.guild.id, word.strip())
        await ctx.reply(embed=self.base_embed("Filter Added", f"`{word.strip()}` was added to the confession blacklist.", COLORS["warning"]))

    @commands.command(name="removefilter")
    @commands.has_permissions(manage_guild=True)
    async def removefilter(self, ctx, *, word: str):
        """Remove a blocked confession word or phrase."""
        await self.db_call(self.db.remove_filter, ctx.guild.id, word.strip())
        await ctx.reply(embed=self.base_embed("Filter Removed", f"`{word.strip()}` was removed from the confession blacklist.", COLORS["success"]))

    @setconfession.error
    @confesslog.error
    @deleteconfession.error
    @banconfess.error
    @unbanconfess.error
    @addfilter.error
    @removefilter.error
    async def admin_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            return await ctx.reply(embed=self.base_embed("Missing Permission", "You need Manage Server permission.", COLORS["error"]))
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.reply(embed=self.base_embed("Missing Argument", f"Missing `{error.param.name}`.", COLORS["error"]))
        if isinstance(error, commands.BadArgument):
            return await ctx.reply(embed=self.base_embed("Invalid Argument", "I could not parse that argument.", COLORS["error"]))
        print(f"Confession admin command error: {error}")
        await ctx.reply(embed=self.base_embed("Command Error", "Something went wrong.", COLORS["error"]))

    @reply.error
    @confessionstats.error
    async def command_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.reply(embed=self.base_embed("Missing Argument", f"Missing `{error.param.name}`.", COLORS["error"]))
        if isinstance(error, commands.BadArgument):
            return await ctx.reply(embed=self.base_embed("Invalid Argument", "I could not parse that argument.", COLORS["error"]))
        print(f"Confession command error: {error}")
        await ctx.reply(embed=self.base_embed("Command Error", "Something went wrong.", COLORS["error"]))


async def setup(bot):
    await bot.add_cog(ConfessionManager(bot))
