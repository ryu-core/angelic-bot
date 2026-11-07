import asyncio
import io
import os
import time

import aiohttp
import discord
from discord.ext import commands
import mysql.connector
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

import config
from utils.embeds import error_embed, info_embed, success_embed
from utils.permissions import is_owner


GLOBAL_RELATIONSHIP_SCOPE_ID = 0


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


def _now() -> int:
    return int(time.time())


def _duration_words(start_ts: int) -> str:
    days = max(0, int((_now() - int(start_ts)) // 86400))
    years, rem = divmod(days, 365)
    months, days = divmod(rem, 30)
    parts = []
    if years:
        parts.append(f"{years}y")
    if months:
        parts.append(f"{months}mo")
    if days or not parts:
        parts.append(f"{days}d")
    return " ".join(parts)


def _font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "web/static/fonts/share-tech-mono.ttf",
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    text = text.strip()
    while text and draw.textlength(text + "...", font=font) > max_width:
        text = text[:-1]
    return (text + "...") if text else "..."


class MarriageDB:
    def __init__(self):
        self.ready = asyncio.Event()
        self.available = False
        asyncio.create_task(self.init_db())

    async def init_db(self):
        def _init():
            conn = _get_mysql_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_marriages (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user1_id BIGINT NOT NULL,
                        user2_id BIGINT NOT NULL,
                        proposer_id BIGINT NOT NULL,
                        created_at BIGINT NOT NULL,
                        updated_at BIGINT NOT NULL,
                        INDEX idx_marriage_guild_users (guild_id, user1_id, user2_id),
                        INDEX idx_marriage_created (guild_id, created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_marriage_stats (
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        proposals_sent INT DEFAULT 0,
                        proposals_received INT DEFAULT 0,
                        proposals_accepted INT DEFAULT 0,
                        proposals_declined INT DEFAULT 0,
                        divorces INT DEFAULT 0,
                        PRIMARY KEY (guild_id, user_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_adoptions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        parent_id BIGINT NOT NULL,
                        child_id BIGINT NOT NULL,
                        created_at BIGINT NOT NULL,
                        updated_at BIGINT NOT NULL,
                        UNIQUE KEY uniq_adoption_pair (guild_id, parent_id, child_id),
                        INDEX idx_adoption_parent (guild_id, parent_id),
                        INDEX idx_adoption_child (guild_id, child_id),
                        INDEX idx_adoption_created (guild_id, created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                self._migrate_existing_relationships(cursor)
                conn.commit()
            finally:
                cursor.close()
                conn.close()

        try:
            await asyncio.to_thread(_init)
            self.available = True
        except Exception as e:
            self.available = False
            print(f"Marriage DB init failed: {e}")
        finally:
            self.ready.set()

    def _migrate_existing_relationships(self, cursor):
        """Copy older per-server relationship rows into the global scope when safe."""
        scope_id = self.scope_id()
        cursor.execute(
            """
            SELECT *
            FROM bot_marriages
            WHERE guild_id <> %s
            ORDER BY created_at ASC
            """,
            (scope_id,),
        )
        for row in cursor.fetchall() or []:
            user1 = int(row["user1_id"])
            user2 = int(row["user2_id"])
            cursor.execute(
                """
                SELECT id
                FROM bot_marriages
                WHERE guild_id = %s AND (user1_id IN (%s, %s) OR user2_id IN (%s, %s))
                LIMIT 1
                """,
                (scope_id, user1, user2, user1, user2),
            )
            if cursor.fetchone():
                continue
            cursor.execute(
                """
                INSERT INTO bot_marriages (guild_id, user1_id, user2_id, proposer_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    scope_id,
                    user1,
                    user2,
                    int(row["proposer_id"]),
                    int(row["created_at"]),
                    int(row["updated_at"]),
                ),
            )

        cursor.execute(
            """
            SELECT *
            FROM bot_adoptions
            WHERE guild_id <> %s
            ORDER BY created_at ASC
            """,
            (scope_id,),
        )
        for row in cursor.fetchall() or []:
            parent_id = int(row["parent_id"])
            child_id = int(row["child_id"])
            cursor.execute(
                """
                SELECT id
                FROM bot_adoptions
                WHERE guild_id = %s AND child_id = %s
                LIMIT 1
                """,
                (scope_id, child_id),
            )
            if cursor.fetchone():
                continue
            cursor.execute(
                """
                INSERT INTO bot_adoptions (guild_id, parent_id, child_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (scope_id, parent_id, child_id, int(row["created_at"]), int(row["updated_at"])),
            )

    def _execute_sync(self, query, params=None, fetchone=False, fetchall=False):
        conn = _get_mysql_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
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

    async def execute(self, query, params=None, fetchone=False, fetchall=False):
        await self.ready.wait()
        if not self.available:
            raise RuntimeError("Marriage database is not available.")
        return await asyncio.to_thread(self._execute_sync, query, params, fetchone, fetchall)

    def scope_id(self, _guild_id: int | None = None) -> int:
        return GLOBAL_RELATIONSHIP_SCOPE_ID

    async def get_marriage(self, guild_id: int, user_id: int):
        scope_id = self.scope_id(guild_id)
        return await self.execute(
            """
            SELECT *
            FROM bot_marriages
            WHERE guild_id = %s AND (user1_id = %s OR user2_id = %s)
            LIMIT 1
            """,
            (scope_id, int(user_id), int(user_id)),
            fetchone=True,
        )

    async def create_marriage(self, guild_id: int, proposer_id: int, partner_id: int):
        scope_id = self.scope_id(guild_id)
        user1, user2 = sorted((int(proposer_id), int(partner_id)))
        now = _now()
        existing = await self.execute(
            """
            SELECT id
            FROM bot_marriages
            WHERE guild_id = %s
              AND (user1_id IN (%s, %s) OR user2_id IN (%s, %s))
            LIMIT 1
            """,
            (scope_id, user1, user2, user1, user2),
            fetchone=True,
        )
        if existing:
            return False
        await self.execute(
            """
            INSERT INTO bot_marriages (guild_id, user1_id, user2_id, proposer_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (scope_id, user1, user2, int(proposer_id), now, now),
        )
        return True

    async def delete_marriage(self, guild_id: int, user_id: int):
        row = await self.get_marriage(guild_id, user_id)
        if not row:
            return None
        await self.execute("DELETE FROM bot_marriages WHERE id = %s", (int(row["id"]),))
        return row

    async def increment_stat(self, guild_id: int, user_id: int, field: str, amount: int = 1):
        scope_id = self.scope_id(guild_id)
        allowed = {
            "proposals_sent",
            "proposals_received",
            "proposals_accepted",
            "proposals_declined",
            "divorces",
        }
        if field not in allowed:
            return
        await self.execute(
            f"""
            INSERT INTO bot_marriage_stats (guild_id, user_id, {field})
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE {field} = {field} + VALUES({field})
            """,
            (scope_id, int(user_id), int(amount)),
        )

    async def get_stats(self, guild_id: int, user_id: int):
        scope_id = self.scope_id(guild_id)
        row = await self.execute(
            "SELECT * FROM bot_marriage_stats WHERE guild_id = %s AND user_id = %s",
            (scope_id, int(user_id)),
            fetchone=True,
        )
        return row or {
            "proposals_sent": 0,
            "proposals_received": 0,
            "proposals_accepted": 0,
            "proposals_declined": 0,
            "divorces": 0,
        }

    async def leaderboard(self, guild_id: int, limit: int = 10):
        scope_id = self.scope_id(guild_id)
        return await self.execute(
            """
            SELECT *
            FROM bot_marriages
            WHERE guild_id = %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (scope_id, int(limit)),
            fetchall=True,
        ) or []

    async def count_marriages(self, guild_id: int):
        scope_id = self.scope_id(guild_id)
        row = await self.execute(
            "SELECT COUNT(*) AS total FROM bot_marriages WHERE guild_id = %s",
            (scope_id,),
            fetchone=True,
        )
        return int((row or {}).get("total") or 0)

    async def get_adoption(self, guild_id: int, parent_id: int, child_id: int):
        scope_id = self.scope_id(guild_id)
        return await self.execute(
            """
            SELECT *
            FROM bot_adoptions
            WHERE guild_id = %s AND parent_id = %s AND child_id = %s
            LIMIT 1
            """,
            (scope_id, int(parent_id), int(child_id)),
            fetchone=True,
        )

    async def get_any_parent(self, guild_id: int, child_id: int):
        scope_id = self.scope_id(guild_id)
        return await self.execute(
            """
            SELECT *
            FROM bot_adoptions
            WHERE guild_id = %s AND child_id = %s
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (scope_id, int(child_id)),
            fetchone=True,
        )

    async def create_adoption(self, guild_id: int, parent_id: int, child_id: int):
        scope_id = self.scope_id(guild_id)
        if int(parent_id) == int(child_id):
            return (False, None)
        existing_parent = await self.get_any_parent(guild_id, child_id)
        if existing_parent:
            return (False, existing_parent)
        existing = await self.get_adoption(guild_id, parent_id, child_id)
        if existing:
            return (False, existing)
        now = _now()
        await self.execute(
            """
            INSERT INTO bot_adoptions (guild_id, parent_id, child_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (scope_id, int(parent_id), int(child_id), now, now),
        )
        return (True, None)

    async def delete_adoption(self, guild_id: int, parent_id: int, child_id: int):
        row = await self.get_adoption(guild_id, parent_id, child_id)
        if not row:
            return None
        await self.execute("DELETE FROM bot_adoptions WHERE id = %s", (int(row["id"]),))
        return row

    async def clear_adoptions_for_user(self, guild_id: int, user_id: int):
        scope_id = self.scope_id(guild_id)
        rows = await self.execute(
            """
            SELECT *
            FROM bot_adoptions
            WHERE guild_id = %s AND (parent_id = %s OR child_id = %s)
            """,
            (scope_id, int(user_id), int(user_id)),
            fetchall=True,
        ) or []
        await self.execute(
            "DELETE FROM bot_adoptions WHERE guild_id = %s AND (parent_id = %s OR child_id = %s)",
            (scope_id, int(user_id), int(user_id)),
        )
        return rows

    async def get_children(self, guild_id: int, parent_id: int):
        scope_id = self.scope_id(guild_id)
        return await self.execute(
            """
            SELECT *
            FROM bot_adoptions
            WHERE guild_id = %s AND parent_id = %s
            ORDER BY created_at ASC
            """,
            (scope_id, int(parent_id)),
            fetchall=True,
        ) or []

    async def get_parents(self, guild_id: int, child_id: int):
        scope_id = self.scope_id(guild_id)
        return await self.execute(
            """
            SELECT *
            FROM bot_adoptions
            WHERE guild_id = %s AND child_id = %s
            ORDER BY created_at ASC
            """,
            (scope_id, int(child_id)),
            fetchall=True,
        ) or []

    async def adoption_leaderboard(self, guild_id: int, limit: int = 10):
        scope_id = self.scope_id(guild_id)
        return await self.execute(
            """
            SELECT parent_id, COUNT(*) AS total, MIN(created_at) AS first_adoption
            FROM bot_adoptions
            WHERE guild_id = %s
            GROUP BY parent_id
            ORDER BY total DESC, first_adoption ASC
            LIMIT %s
            """,
            (scope_id, int(limit)),
            fetchall=True,
        ) or []


class ProposalView(discord.ui.View):
    def __init__(self, cog, ctx, proposer: discord.Member, target: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.proposer = proposer
        self.target = target
        self.message = None
        self.finished = False

    async def _reject_wrong_user(self, interaction: discord.Interaction):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Only the proposed partner can answer this.", ephemeral=True)
            return True
        return False

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._reject_wrong_user(interaction):
            return
        if self.finished:
            return await interaction.response.send_message("This proposal has already been answered.", ephemeral=True)

        self.finished = True
        try:
            if await self.cog.db.get_marriage(self.ctx.guild.id, self.proposer.id):
                return await interaction.response.edit_message(
                    embed=error_embed("Already Married", f"{self.proposer.mention} is already married."),
                    view=None,
                )
            if await self.cog.db.get_marriage(self.ctx.guild.id, self.target.id):
                return await interaction.response.edit_message(
                    embed=error_embed("Already Married", f"{self.target.mention} is already married."),
                    view=None,
                )
            created = await self.cog.db.create_marriage(self.ctx.guild.id, self.proposer.id, self.target.id)
            if not created:
                return await interaction.response.edit_message(
                    embed=error_embed("Already Married", "One of you got married before this proposal was accepted."),
                    view=None,
                )
            await self.cog.db.increment_stat(self.ctx.guild.id, self.proposer.id, "proposals_accepted")
            await self.cog.db.increment_stat(self.ctx.guild.id, self.target.id, "proposals_accepted")
        except Exception as e:
            return await interaction.response.edit_message(
                embed=error_embed("Marriage Failed", f"Could not save this marriage: `{e}`"),
                view=None,
            )

        embed = discord.Embed(
            title="Marriage Accepted",
            description=(
                f"{self.proposer.mention} and {self.target.mention} are now married.\n"
                "Use the tree command to view the family."
            ),
            color=config.COLORS["success"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=self.target.display_avatar.url)
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._reject_wrong_user(interaction):
            return
        if self.finished:
            return await interaction.response.send_message("This proposal has already been answered.", ephemeral=True)
        self.finished = True
        try:
            await self.cog.db.increment_stat(self.ctx.guild.id, self.target.id, "proposals_declined")
        except Exception:
            pass
        await interaction.response.edit_message(
            embed=info_embed("Proposal Declined", f"{self.target.mention} declined {self.proposer.mention}'s proposal."),
            view=None,
        )

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    embed=info_embed("Proposal Expired", f"{self.target.mention} did not answer in time."),
                    view=self,
                )
            except Exception:
                pass


class DivorceView(discord.ui.View):
    def __init__(self, cog, ctx, marriage):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.marriage = marriage
        self.message = None

    @discord.ui.button(label="Confirm Divorce", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This confirmation is not yours.", ephemeral=True)
        try:
            row = await self.cog.db.delete_marriage(self.ctx.guild.id, self.ctx.author.id)
            await self.cog.db.increment_stat(self.ctx.guild.id, int(self.ctx.author.id), "divorces")
        except Exception as e:
            return await interaction.response.edit_message(
                embed=error_embed("Divorce Failed", f"Could not update marriage data: `{e}`"),
                view=None,
            )
        if not row:
            return await interaction.response.edit_message(embed=error_embed("Not Married", "You are not married."), view=None)

        partner_id = int(row["user2_id"] if int(row["user1_id"]) == self.ctx.author.id else row["user1_id"])
        embed = discord.Embed(
            title="Divorce Complete",
            description=f"{self.ctx.author.mention} divorced <@{partner_id}> after **{_duration_words(row['created_at'])}**.",
            color=config.COLORS["error"],
            timestamp=discord.utils.utcnow(),
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This confirmation is not yours.", ephemeral=True)
        await interaction.response.edit_message(embed=info_embed("Divorce Cancelled", "Nothing changed."), view=None)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class AdoptionView(discord.ui.View):
    def __init__(self, cog, ctx, parent: discord.Member, child: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.parent = parent
        self.child = child
        self.message = None
        self.finished = False

    async def _reject_wrong_user(self, interaction: discord.Interaction):
        if interaction.user.id != self.child.id:
            await interaction.response.send_message("Only the adoptee can answer this.", ephemeral=True)
            return True
        return False

    @discord.ui.button(label="Accept Adoption", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._reject_wrong_user(interaction):
            return
        if self.finished:
            return await interaction.response.send_message("This adoption request has already been answered.", ephemeral=True)
        self.finished = True
        try:
            created, blocker = await self.cog.db.create_adoption(self.ctx.guild.id, self.parent.id, self.child.id)
        except Exception as e:
            return await interaction.response.edit_message(
                embed=error_embed("Adoption Failed", f"Could not save this adoption: `{e}`"),
                view=None,
            )
        if not created:
            parent_id = int(blocker["parent_id"]) if blocker and blocker.get("parent_id") else self.parent.id
            return await interaction.response.edit_message(
                embed=error_embed("Already Adopted", f"{self.child.mention} already has parent <@{parent_id}>."),
                view=None,
            )

        embed = discord.Embed(
            title="Adoption Accepted",
            description=f"{self.parent.mention} adopted {self.child.mention}.",
            color=config.COLORS["success"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=self.child.display_avatar.url)
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._reject_wrong_user(interaction):
            return
        if self.finished:
            return await interaction.response.send_message("This adoption request has already been answered.", ephemeral=True)
        self.finished = True
        await interaction.response.edit_message(
            embed=info_embed("Adoption Declined", f"{self.child.mention} declined {self.parent.mention}'s adoption request."),
            view=None,
        )

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    embed=info_embed("Adoption Expired", f"{self.child.mention} did not answer in time."),
                    view=self,
                )
            except Exception:
                pass


class Marriage(commands.Cog):
    """Prefix-only marriage commands with adoption, family trees, and server graphs."""

    def __init__(self, bot):
        self.bot = bot
        self.db = MarriageDB()

    def _prefix(self, ctx):
        return getattr(ctx, "prefix", None) or config.PREFIX

    async def _ensure_db(self, ctx) -> bool:
        await self.db.ready.wait()
        if self.db.available:
            return True
        await ctx.reply(embed=error_embed("Marriage Database Offline", "Marriage commands need the MySQL database to be reachable."))
        return False

    async def _avatar(self, user, size: int):
        url = str(user.display_avatar.with_size(256).url)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    response.raise_for_status()
                    raw = await response.read()
            avatar = Image.open(io.BytesIO(raw)).convert("RGBA").resize((size, size), Image.LANCZOS)
        except Exception:
            avatar = Image.new("RGBA", (size, size), (90, 95, 120, 255))
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        return ImageOps.fit(avatar, (size, size)), mask

    async def _make_graph_card(self, guild: discord.Guild, rows):
        width = 1350
        row_h = 92
        height = 230 + max(1, len(rows)) * row_h
        img = Image.new("RGB", (width, height), (17, 19, 29))
        draw = ImageDraw.Draw(img)

        for x in range(width):
            ratio = x / width
            draw.line((x, 0, x, height), fill=(int(21 + 33 * ratio), int(25 + 14 * ratio), int(43 + 37 * ratio)))

        title_font = _font(50, True)
        row_font = _font(28, True)
        small_font = _font(19)
        draw.text((65, 50), "Marriage Graph", font=title_font, fill=(255, 245, 250))
        draw.text((67, 112), f"{guild.name[:55]} • longest active couples", font=small_font, fill=(185, 195, 220))

        if not rows:
            draw.rounded_rectangle((65, 180, width - 65, 290), radius=20, fill=(27, 31, 48), outline=(90, 98, 130), width=2)
            draw.text((95, 218), "No marriages yet. Someone has to make the first brave prefix command.", font=row_font, fill=(240, 245, 255))
        else:
            max_days = max(1, max(int((_now() - int(row["created_at"])) // 86400) for row in rows))
            top_y = 180
            for index, row in enumerate(rows, start=1):
                y = top_y + (index - 1) * row_h
                days = max(0, int((_now() - int(row["created_at"])) // 86400))
                pct = days / max_days
                fill = (28, 32, 49) if index % 2 else (24, 28, 44)
                draw.rounded_rectangle((65, y, width - 65, y + 68), radius=18, fill=fill, outline=(61, 69, 96), width=1)
                rank_color = (255, 215, 110) if index == 1 else (210, 220, 240)
                draw.text((88, y + 17), f"#{index}", font=row_font, fill=rank_color)

                left = guild.get_member(int(row["user1_id"]))
                right = guild.get_member(int(row["user2_id"]))
                left_name = left.display_name if left else f"User {row['user1_id']}"
                right_name = right.display_name if right else f"User {row['user2_id']}"
                names = _truncate(draw, f"{left_name} ♥ {right_name}", row_font, 540)
                draw.text((165, y + 17), names, font=row_font, fill=(255, 255, 255))

                bar_x, bar_y, bar_w = 745, y + 24, 385
                draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + 20), radius=10, fill=(43, 49, 70))
                draw.rounded_rectangle((bar_x, bar_y, bar_x + int(bar_w * pct), bar_y + 20), radius=10, fill=(255, 105, 160))
                draw.text((1160, y + 17), f"{days:,}d", font=row_font, fill=(220, 230, 246))

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow = ImageDraw.Draw(overlay)
        glow.ellipse((width - 330, -170, width + 160, 310), fill=(255, 105, 160, 32))
        glow.ellipse((-180, height - 250, 280, height + 160), fill=(91, 192, 255, 26))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB").filter(ImageFilter.UnsharpMask(radius=1, percent=115))

        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return output

    async def _resolve_user(self, guild: discord.Guild, user_id: int):
        member = guild.get_member(int(user_id))
        if member:
            return member
        try:
            return await self.bot.fetch_user(int(user_id))
        except Exception:
            return None

    def _user_label(self, user, fallback_id: int) -> str:
        if user:
            return getattr(user, "display_name", None) or getattr(user, "name", None) or f"User {fallback_id}"
        return f"User {fallback_id}"

    async def _family_size(self, guild_id: int, user_id: int, limit: int = 500):
        seen = {int(user_id)}
        queue = [int(user_id)]
        while queue and len(seen) < limit:
            current = queue.pop(0)
            related = set()
            marriage = await self.db.get_marriage(guild_id, current)
            if marriage:
                related.add(int(marriage["user2_id"] if int(marriage["user1_id"]) == current else marriage["user1_id"]))
            related.update(int(row["parent_id"]) for row in await self.db.get_parents(guild_id, current))
            related.update(int(row["child_id"]) for row in await self.db.get_children(guild_id, current))

            for related_id in related:
                if related_id not in seen:
                    seen.add(related_id)
                    queue.append(related_id)
        return seen

    async def _make_family_tree_card(self, guild: discord.Guild, member: discord.Member):
        marriage = await self.db.get_marriage(guild.id, member.id)
        partner_id = None
        if marriage:
            partner_id = int(marriage["user2_id"] if int(marriage["user1_id"]) == member.id else marriage["user1_id"])

        center_ids = [int(member.id)] + ([partner_id] if partner_id else [])
        parent_edges = []
        parent_ids = []
        child_edges = []
        child_ids = []

        for center_id in center_ids:
            for row in await self.db.get_parents(guild.id, center_id):
                parent_id = int(row["parent_id"])
                parent_edges.append((parent_id, center_id))
                if parent_id not in parent_ids:
                    parent_ids.append(parent_id)

            for row in await self.db.get_children(guild.id, center_id):
                child_id = int(row["child_id"])
                child_edges.append((center_id, child_id))
                if child_id not in child_ids:
                    child_ids.append(child_id)

        node_w, node_h = 220, 92
        gap_x, row_gap = 32, 66
        max_cols = 5
        width = 120 + (max_cols * node_w) + ((max_cols - 1) * gap_x)
        title_y = 54
        first_row_y = 186

        def chunks(values, size):
            return [values[index:index + size] for index in range(0, len(values), size)]

        rows = []
        if parent_ids:
            for index, group in enumerate(chunks(parent_ids, max_cols)):
                rows.append({"label": "Parents" if index == 0 else "", "nodes": [(uid, "parent", (168, 185, 214)) for uid in group]})
        else:
            rows.append({"label": "Parents", "nodes": [], "note": "No parents listed"})

        rows.append({
            "label": "Marriage" if partner_id else "Member",
            "nodes": [(uid, "you" if uid == member.id else "spouse", (192, 141, 172)) for uid in center_ids],
        })

        visible_child_ids = child_ids[:50]
        overflow = len(child_ids) > len(visible_child_ids)
        if visible_child_ids:
            for index, group in enumerate(chunks(visible_child_ids, max_cols)):
                rows.append({"label": "Children" if index == 0 else "", "nodes": [(uid, "child", (169, 196, 182)) for uid in group]})
        else:
            rows.append({"label": "Children", "nodes": [], "note": "No children listed"})

        row_height = node_h + row_gap
        height = first_row_y + (len(rows) * row_height) + 110
        img = Image.new("RGB", (width, height), (246, 247, 250))
        draw = ImageDraw.Draw(img)

        title_font = _font(42, True)
        node_font = _font(23, True)
        small_font = _font(18)
        label_font = _font(20, True)
        line = (112, 122, 145)
        ink = (35, 40, 54)
        muted = (102, 112, 135)
        accent = (154, 75, 118)

        draw.rounded_rectangle((32, 28, width - 32, height - 28), radius=18, fill=(255, 255, 255), outline=(215, 219, 229), width=2)
        draw.text((64, title_y), "Family Tree", font=title_font, fill=ink)
        draw.text((66, title_y + 52), f"Direct family view - centered on {member.display_name}", font=small_font, fill=muted)

        positions = {}
        row_positions = []
        for row_index, row in enumerate(rows):
            y = first_row_y + row_index * row_height
            if row["label"]:
                draw.text((64, y - 34), row["label"], font=label_font, fill=accent)
            nodes = row["nodes"]
            if not nodes:
                draw.text((width // 2 - 88, y + 32), row.get("note", "No entries"), font=small_font, fill=muted)
                row_positions.append([])
                continue
            total_width = len(nodes) * node_w + (len(nodes) - 1) * gap_x
            start_x = (width - total_width) // 2
            current_positions = []
            for index, (user_id, subtitle, outline) in enumerate(nodes):
                x = start_x + index * (node_w + gap_x)
                positions[int(user_id)] = (x, y, subtitle, outline)
                current_positions.append((int(user_id), x, y))
            row_positions.append(current_positions)

        def node_top(user_id):
            x, y, _subtitle, _outline = positions[int(user_id)]
            return (x + node_w // 2, y)

        def node_bottom(user_id):
            x, y, _subtitle, _outline = positions[int(user_id)]
            return (x + node_w // 2, y + node_h)

        def connect(parent_id, child_id):
            if int(parent_id) not in positions or int(child_id) not in positions:
                return
            px, py = node_bottom(parent_id)
            cx, cy = node_top(child_id)
            mid_y = (py + cy) // 2
            draw.line((px, py, px, mid_y), fill=line, width=3)
            draw.line((px, mid_y, cx, mid_y), fill=line, width=3)
            draw.line((cx, mid_y, cx, cy), fill=line, width=3)

        for parent_id, child_id in parent_edges:
            connect(parent_id, child_id)
        if partner_id and member.id in positions and partner_id in positions:
            left_x, y, _subtitle, _outline = positions[member.id]
            right_x, _right_y, _subtitle2, _outline2 = positions[partner_id]
            y_mid = y + node_h // 2
            left_edge = left_x + node_w
            right_edge = right_x
            draw.line((left_edge, y_mid, right_edge, y_mid), fill=accent, width=4)
        for parent_id, child_id in child_edges:
            if child_id in visible_child_ids:
                connect(parent_id, child_id)

        async def draw_node(user_id: int, x: int, y: int, subtitle: str, outline=(198, 204, 218)):
            user = await self._resolve_user(guild, user_id)
            draw.rounded_rectangle((x, y, x + node_w, y + node_h), radius=14, fill=(252, 253, 255), outline=outline, width=2)
            if user:
                avatar, mask = await self._avatar(user, 54)
                img.paste(avatar, (x + 14, y + 18), mask)
                draw.ellipse((x + 12, y + 16, x + 70, y + 74), outline=outline, width=2)
            name = _truncate(draw, self._user_label(user, user_id), node_font, node_w - 86)
            draw.text((x + 82, y + 18), name, font=node_font, fill=ink)
            draw.text((x + 82, y + 52), subtitle, font=small_font, fill=muted)

        for user_id, (x, y, subtitle, outline) in positions.items():
            await draw_node(user_id, x, y, subtitle, outline)

        family_size = len(await self._family_size(guild.id, member.id))
        footer = f"Family size: {family_size:,} - {len(parent_ids)} parent(s) - {len(child_ids)} child/children"
        if partner_id:
            footer += " - married"
        if overflow:
            footer += " - showing first 50 children"
        draw.text((64, height - 74), footer, font=small_font, fill=muted)

        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return output

    async def _make_connected_family_tree_card(self, guild: discord.Guild, member: discord.Member):
        limit = 90
        seen = {int(member.id)}
        order = [int(member.id)]
        queue = [int(member.id)]
        levels = {int(member.id): 0}
        parent_edges = set()
        spouse_edges = set()
        overflow = False

        def add_relative(user_id: int, level: int):
            nonlocal overflow
            user_id = int(user_id)
            if user_id not in levels:
                levels[user_id] = level
            if user_id in seen:
                return
            if len(seen) >= limit:
                overflow = True
                return
            seen.add(user_id)
            order.append(user_id)
            queue.append(user_id)

        while queue:
            current = queue.pop(0)
            current_level = levels.get(current, 0)

            marriage = await self.db.get_marriage(guild.id, current)
            if marriage:
                spouse_id = int(marriage["user2_id"] if int(marriage["user1_id"]) == current else marriage["user1_id"])
                spouse_edges.add(tuple(sorted((current, spouse_id))))
                add_relative(spouse_id, current_level)

            for row in await self.db.get_parents(guild.id, current):
                parent_id = int(row["parent_id"])
                parent_edges.add((parent_id, current))
                add_relative(parent_id, current_level - 1)

            for row in await self.db.get_children(guild.id, current):
                child_id = int(row["child_id"])
                parent_edges.add((current, child_id))
                add_relative(child_id, current_level + 1)

            if overflow:
                break

        order_index = {user_id: index for index, user_id in enumerate(order)}
        node_w, node_h = 230, 94
        gap_x, row_gap = 34, 74
        max_cols = 5
        width = 140 + (max_cols * node_w) + ((max_cols - 1) * gap_x)
        title_y = 54
        first_row_y = 192

        def chunks(values, size):
            return [values[index:index + size] for index in range(0, len(values), size)]

        def level_label(level: int) -> str:
            if level < -1:
                return f"Ancestors {abs(level)} levels up"
            if level == -1:
                return "Parents"
            if level == 0:
                return "Center"
            if level == 1:
                return "Children"
            return f"Generation +{level}"

        def subtitle(user_id: int, level: int) -> str:
            if user_id == member.id:
                return "you"
            if tuple(sorted((member.id, user_id))) in spouse_edges:
                return "spouse"
            if level < 0:
                return "ancestor" if level < -1 else "parent"
            if level > 0:
                return "descendant" if level > 1 else "child"
            return "family"

        def outline_for(user_id: int, level: int):
            if user_id == member.id:
                return (154, 75, 118)
            if tuple(sorted((member.id, user_id))) in spouse_edges:
                return (192, 141, 172)
            if level < 0:
                return (168, 185, 214)
            if level > 0:
                return (169, 196, 182)
            return (198, 204, 218)

        rows = []
        for level in sorted(set(levels.values())):
            nodes_at_level = sorted(
                [user_id for user_id in seen if levels.get(user_id) == level],
                key=lambda user_id: order_index.get(user_id, 9999),
            )
            for index, group in enumerate(chunks(nodes_at_level, max_cols)):
                rows.append({
                    "label": level_label(level) if index == 0 else "",
                    "nodes": [(uid, subtitle(uid, level), outline_for(uid, level)) for uid in group],
                })

        row_height = node_h + row_gap
        height = first_row_y + (max(1, len(rows)) * row_height) + 116
        img = Image.new("RGB", (width, height), (246, 247, 250))
        draw = ImageDraw.Draw(img)

        title_font = _font(42, True)
        node_font = _font(23, True)
        small_font = _font(18)
        label_font = _font(20, True)
        line = (112, 122, 145)
        ink = (35, 40, 54)
        muted = (102, 112, 135)
        accent = (154, 75, 118)

        draw.rounded_rectangle((32, 28, width - 32, height - 28), radius=18, fill=(255, 255, 255), outline=(215, 219, 229), width=2)
        draw.text((64, title_y), "Family Tree", font=title_font, fill=ink)
        draw.text((66, title_y + 52), f"Cross-server connected family centered on {member.display_name}", font=small_font, fill=muted)

        positions = {}
        for row_index, row in enumerate(rows):
            y = first_row_y + row_index * row_height
            if row["label"]:
                draw.text((64, y - 34), row["label"], font=label_font, fill=accent)
            nodes = row["nodes"]
            total_width = len(nodes) * node_w + (len(nodes) - 1) * gap_x
            start_x = (width - total_width) // 2
            for index, (user_id, node_subtitle, outline) in enumerate(nodes):
                x = start_x + index * (node_w + gap_x)
                positions[int(user_id)] = (x, y, node_subtitle, outline)

        def node_top(user_id):
            x, y, _subtitle, _outline = positions[int(user_id)]
            return (x + node_w // 2, y)

        def node_bottom(user_id):
            x, y, _subtitle, _outline = positions[int(user_id)]
            return (x + node_w // 2, y + node_h)

        def connect_parent(parent_id, child_id):
            if int(parent_id) not in positions or int(child_id) not in positions:
                return
            px, py = node_bottom(parent_id)
            cx, cy = node_top(child_id)
            mid_y = (py + cy) // 2
            draw.line((px, py, px, mid_y), fill=line, width=3)
            draw.line((px, mid_y, cx, mid_y), fill=line, width=3)
            draw.line((cx, mid_y, cx, cy), fill=line, width=3)

        def connect_spouses(left_id, right_id):
            if int(left_id) not in positions or int(right_id) not in positions:
                return
            lx, ly, _subtitle, _outline = positions[int(left_id)]
            rx, ry, _subtitle2, _outline2 = positions[int(right_id)]
            if (rx, ry) < (lx, ly):
                lx, ly, rx, ry = rx, ry, lx, ly
            left_mid = (lx + node_w, ly + node_h // 2)
            right_mid = (rx, ry + node_h // 2)
            if ly == ry:
                draw.line((left_mid[0], left_mid[1], right_mid[0], right_mid[1]), fill=accent, width=4)
                mid_x = (left_mid[0] + right_mid[0]) // 2
                draw.text((mid_x - 30, left_mid[1] - 24), "married", font=_font(14, True), fill=accent)
                return
            elbow_x = (left_mid[0] + right_mid[0]) // 2
            draw.line((left_mid[0], left_mid[1], elbow_x, left_mid[1]), fill=accent, width=4)
            draw.line((elbow_x, left_mid[1], elbow_x, right_mid[1]), fill=accent, width=4)
            draw.line((elbow_x, right_mid[1], right_mid[0], right_mid[1]), fill=accent, width=4)

        for parent_id, child_id in parent_edges:
            connect_parent(parent_id, child_id)
        for left_id, right_id in spouse_edges:
            connect_spouses(left_id, right_id)

        async def draw_node(user_id: int, x: int, y: int, node_subtitle: str, outline=(198, 204, 218)):
            user = await self._resolve_user(guild, user_id)
            draw.rounded_rectangle((x, y, x + node_w, y + node_h), radius=14, fill=(252, 253, 255), outline=outline, width=2)
            if user:
                avatar, mask = await self._avatar(user, 54)
                img.paste(avatar, (x + 14, y + 19), mask)
                draw.ellipse((x + 12, y + 17, x + 70, y + 75), outline=outline, width=2)
            name = _truncate(draw, self._user_label(user, user_id), node_font, node_w - 88)
            draw.text((x + 82, y + 18), name, font=node_font, fill=ink)
            draw.text((x + 82, y + 53), node_subtitle, font=small_font, fill=muted)

        for user_id, (x, y, node_subtitle, outline) in positions.items():
            await draw_node(user_id, x, y, node_subtitle, outline)

        family_size = len(await self._family_size(guild.id, member.id))
        footer = f"Visible: {len(seen):,} of {family_size:,} linked member(s) - {len(parent_edges)} parent link(s) - {len(spouse_edges)} marriage link(s)"
        if overflow:
            footer += f" - capped at {limit}"
        draw.text((64, height - 74), footer, font=small_font, fill=muted)

        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return output

    async def _send_partner_embed(self, ctx, member: discord.Member):
        marriage = await self.db.get_marriage(ctx.guild.id, member.id)
        if not marriage:
            return await ctx.reply(embed=info_embed("Not Married", f"{member.mention} is not married yet."))
        partner_id = int(marriage["user2_id"] if int(marriage["user1_id"]) == member.id else marriage["user1_id"])
        partner = ctx.guild.get_member(partner_id)
        embed = discord.Embed(
            title=f"{member.display_name}'s Partner",
            description=f"{member.mention} is married to {partner.mention if partner else f'<@{partner_id}>'}.",
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Together", value=_duration_words(marriage["created_at"]), inline=True)
        embed.add_field(name="Since", value=f"<t:{int(marriage['created_at'])}:D>", inline=True)
        embed.set_thumbnail(url=(partner or member).display_avatar.url)
        await ctx.reply(embed=embed)

    async def _send_leaderboard(self, ctx, limit: int = 10):
        limit = max(1, min(int(limit), 20))
        rows = await self.db.leaderboard(ctx.guild.id, limit)
        if not rows:
            return await ctx.reply(embed=info_embed("Marriage Leaderboard", "No active marriages yet."))
        lines = []
        for index, row in enumerate(rows, start=1):
            lines.append(
                f"`#{index}` <@{int(row['user1_id'])}> ♥ <@{int(row['user2_id'])}> - **{_duration_words(row['created_at'])}**"
            )
        embed = discord.Embed(
            title="Marriage Leaderboard",
            description="\n".join(lines),
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        await ctx.reply(embed=embed)

    async def _send_graph(self, ctx, limit: int = 10):
        limit = max(1, min(int(limit), 12))
        rows = await self.db.leaderboard(ctx.guild.id, limit)
        async with ctx.typing():
            image = await self._make_graph_card(ctx.guild, rows)
        await ctx.reply(file=discord.File(image, filename="marriage_graph.png"))

    def _mention_list(self, ids, empty: str = "None"):
        if not ids:
            return empty
        return "\n".join(f"`#{index}` <@{int(user_id)}>" for index, user_id in enumerate(ids, start=1))

    async def _send_family_embed(self, ctx, member: discord.Member):
        marriage = await self.db.get_marriage(ctx.guild.id, member.id)
        partner_id = None
        if marriage:
            partner_id = int(marriage["user2_id"] if int(marriage["user1_id"]) == member.id else marriage["user1_id"])
        parents = await self.db.get_parents(ctx.guild.id, member.id)
        children = await self.db.get_children(ctx.guild.id, member.id)

        embed = discord.Embed(
            title=f"{member.display_name}'s Family",
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Partner", value=f"<@{partner_id}>" if partner_id else "None", inline=False)
        embed.add_field(name="Parents", value=self._mention_list([row["parent_id"] for row in parents]), inline=True)
        embed.add_field(name="Children", value=self._mention_list([row["child_id"] for row in children]), inline=True)
        await ctx.reply(embed=embed)

    @commands.command(name="marry", aliases=["propose"])
    @commands.guild_only()
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def marry(self, ctx, member: discord.Member = None):
        """Propose marriage to a server member."""
        if not await self._ensure_db(ctx):
            return
        if member is None:
            return await ctx.reply(embed=error_embed("Missing Partner", f"Usage: `{self._prefix(ctx)}marry @user`"))
        if member.bot:
            return await ctx.reply(embed=error_embed("Invalid Partner", "You cannot marry a bot."))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=error_embed("Invalid Partner", "Self-love is valid, but this command needs another person."))
        if await self.db.get_marriage(ctx.guild.id, ctx.author.id):
            return await ctx.reply(embed=error_embed("Already Married", "You are already married. Divorce first if you want a new marriage."))
        if await self.db.get_marriage(ctx.guild.id, member.id):
            return await ctx.reply(embed=error_embed("Already Married", f"{member.mention} is already married."))

        await self.db.increment_stat(ctx.guild.id, ctx.author.id, "proposals_sent")
        await self.db.increment_stat(ctx.guild.id, member.id, "proposals_received")

        embed = discord.Embed(
            title="Marriage Proposal",
            description=f"{member.mention}, {ctx.author.mention} wants to marry you.\nAccept or decline below.",
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        view = ProposalView(self, ctx, ctx.author, member)
        view.message = await ctx.reply(embed=embed, view=view)

    @commands.command(name="divorce")
    @commands.guild_only()
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def divorce(self, ctx):
        """Divorce your current partner after confirmation."""
        if not await self._ensure_db(ctx):
            return
        marriage = await self.db.get_marriage(ctx.guild.id, ctx.author.id)
        if not marriage:
            return await ctx.reply(embed=error_embed("Not Married", "You are not married."))
        partner_id = int(marriage["user2_id"] if int(marriage["user1_id"]) == ctx.author.id else marriage["user1_id"])
        view = DivorceView(self, ctx, marriage)
        view.message = await ctx.reply(
            embed=info_embed(
                "Confirm Divorce",
                f"Divorce <@{partner_id}> after **{_duration_words(marriage['created_at'])}** together?",
            ),
            view=view,
        )

    @commands.command(name="partner", aliases=["spouse", "wife", "husband"])
    @commands.guild_only()
    async def partner(self, ctx, member: discord.Member = None):
        """Show a user's current marriage partner."""
        if not await self._ensure_db(ctx):
            return
        await self._send_partner_embed(ctx, member or ctx.author)

    @commands.command(name="anniversary", aliases=["marriedsince"])
    @commands.guild_only()
    async def anniversary(self, ctx, member: discord.Member = None):
        """Show when a user got married and how long the marriage has lasted."""
        if not await self._ensure_db(ctx):
            return
        member = member or ctx.author
        marriage = await self.db.get_marriage(ctx.guild.id, member.id)
        if not marriage:
            return await ctx.reply(embed=info_embed("Not Married", f"{member.mention} is not married yet."))
        partner_id = int(marriage["user2_id"] if int(marriage["user1_id"]) == member.id else marriage["user1_id"])
        await ctx.reply(embed=success_embed(
            "Anniversary",
            f"{member.mention} is married to <@{partner_id}>.\n"
            f"They have been married for **{_duration_words(marriage['created_at'])}**.\n"
            f"Wedding date: <t:{int(marriage['created_at'])}:F>",
        ))

    @commands.command(name="marriagelb", aliases=["marrylb", "lovelb"])
    @commands.guild_only()
    async def marriage_leaderboard(self, ctx, limit: int = 10):
        """Show the longest active marriages in this server."""
        if not await self._ensure_db(ctx):
            return
        await self._send_leaderboard(ctx, limit)

    @commands.command(name="marriagegraph", aliases=["lovegraph", "relationshipgraph"])
    @commands.guild_only()
    async def marriage_graph(self, ctx, limit: int = 10):
        """Generate a visual graph of the longest active marriages."""
        if not await self._ensure_db(ctx):
            return
        await self._send_graph(ctx, limit)

    @commands.command(name="tree", aliases=["familytree", "bloodtree"])
    @commands.guild_only()
    async def tree(self, ctx, member: discord.Member = None):
        """Show a MarriageBot-style family tree."""
        if not await self._ensure_db(ctx):
            return
        member = member or ctx.author
        async with ctx.typing():
            image = await self._make_family_tree_card(ctx.guild, member)
        await ctx.reply(file=discord.File(image, filename="family_tree.png"))

    @commands.command(name="fulltree", aliases=["connectedtree", "bigtree"])
    @commands.guild_only()
    async def fulltree(self, ctx, member: discord.Member = None):
        """Show the full connected family graph."""
        if not await self._ensure_db(ctx):
            return
        member = member or ctx.author
        async with ctx.typing():
            image = await self._make_connected_family_tree_card(ctx.guild, member)
        await ctx.reply(file=discord.File(image, filename="family_fulltree.png"))

    @commands.command(name="familysize", aliases=["familys", "fsize"])
    @commands.guild_only()
    async def familysize(self, ctx, member: discord.Member = None):
        """Show how many users are connected in a user's family tree."""
        if not await self._ensure_db(ctx):
            return
        member = member or ctx.author
        family = await self._family_size(ctx.guild.id, member.id)
        embed = discord.Embed(
            title=f"{member.display_name}'s Family Size",
            description=f"Found **{len(family):,}** connected family member(s), including {member.mention}.",
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.command(name="adopt")
    @commands.guild_only()
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def adopt(self, ctx, member: discord.Member = None):
        """Ask a member to become your adopted child."""
        if not await self._ensure_db(ctx):
            return
        if member is None:
            return await ctx.reply(embed=error_embed("Missing User", f"Usage: `{self._prefix(ctx)}adopt @user`"))
        if member.bot:
            return await ctx.reply(embed=error_embed("Invalid User", "You cannot adopt bots."))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=error_embed("Invalid User", "You cannot adopt yourself."))
        existing_parent = await self.db.get_any_parent(ctx.guild.id, member.id)
        if existing_parent:
            return await ctx.reply(embed=error_embed("Already Adopted", f"{member.mention} already has parent <@{int(existing_parent['parent_id'])}>. They must `runaway` or be disowned first."))
        if await self.db.get_adoption(ctx.guild.id, ctx.author.id, member.id):
            return await ctx.reply(embed=error_embed("Already Family", f"You have already adopted {member.mention}."))

        embed = discord.Embed(
            title="Adoption Request",
            description=f"{member.mention}, {ctx.author.mention} wants to adopt you.\nAccept or decline below.",
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        view = AdoptionView(self, ctx, ctx.author, member)
        view.message = await ctx.reply(embed=embed, view=view)

    @commands.command(name="children", aliases=["kids"])
    @commands.guild_only()
    async def children(self, ctx, member: discord.Member = None):
        """Show a user's adopted children."""
        if not await self._ensure_db(ctx):
            return
        member = member or ctx.author
        rows = await self.db.get_children(ctx.guild.id, member.id)
        embed = discord.Embed(
            title=f"{member.display_name}'s Children",
            description=self._mention_list([row["child_id"] for row in rows], "No adopted children yet."),
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.command(name="parents", aliases=["parent"])
    @commands.guild_only()
    async def parents(self, ctx, member: discord.Member = None):
        """Show a user's adopted parents."""
        if not await self._ensure_db(ctx):
            return
        member = member or ctx.author
        rows = await self.db.get_parents(ctx.guild.id, member.id)
        embed = discord.Embed(
            title=f"{member.display_name}'s Parents",
            description=self._mention_list([row["parent_id"] for row in rows], "No adopted parents yet."),
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.group(name="family", aliases=["relationships"], invoke_without_command=True)
    @commands.guild_only()
    async def family(self, ctx, member: discord.Member = None):
        """Show a user's partner, parents, and children."""
        if not await self._ensure_db(ctx):
            return
        await self._send_family_embed(ctx, member or ctx.author)

    @family.command(name="tree")
    @commands.guild_only()
    async def family_tree(self, ctx, member: discord.Member = None):
        """Show a MarriageBot-style family tree."""
        if not await self._ensure_db(ctx):
            return
        member = member or ctx.author
        async with ctx.typing():
            image = await self._make_family_tree_card(ctx.guild, member)
        await ctx.reply(file=discord.File(image, filename="family_tree.png"))

    @family.command(name="fulltree", aliases=["connectedtree", "bigtree"])
    @commands.guild_only()
    async def family_fulltree(self, ctx, member: discord.Member = None):
        """Show the full connected family graph."""
        if not await self._ensure_db(ctx):
            return
        member = member or ctx.author
        async with ctx.typing():
            image = await self._make_connected_family_tree_card(ctx.guild, member)
        await ctx.reply(file=discord.File(image, filename="family_fulltree.png"))

    @commands.command(name="disown")
    @commands.guild_only()
    async def disown(self, ctx, member: discord.Member = None):
        """Remove one of your adopted children."""
        if not await self._ensure_db(ctx):
            return
        if member is None:
            return await ctx.reply(embed=error_embed("Missing Child", f"Usage: `{self._prefix(ctx)}disown @user`"))
        row = await self.db.delete_adoption(ctx.guild.id, ctx.author.id, member.id)
        if not row:
            return await ctx.reply(embed=info_embed("Not Your Child", f"{member.mention} is not your adopted child."))
        await ctx.reply(embed=success_embed("Disowned", f"{ctx.author.mention} disowned {member.mention}."))

    @commands.command(name="runaway")
    @commands.guild_only()
    async def runaway(self, ctx, member: discord.Member = None):
        """Leave one adopted parent, or all parents if no parent is mentioned."""
        if not await self._ensure_db(ctx):
            return
        if member:
            row = await self.db.delete_adoption(ctx.guild.id, member.id, ctx.author.id)
            if not row:
                return await ctx.reply(embed=info_embed("Not Your Parent", f"{member.mention} is not your adopted parent."))
            return await ctx.reply(embed=success_embed("Ran Away", f"{ctx.author.mention} left {member.mention}'s family."))

        rows = await self.db.get_parents(ctx.guild.id, ctx.author.id)
        if not rows:
            return await ctx.reply(embed=info_embed("No Parents", "You do not have any adopted parents."))
        for row in rows:
            await self.db.delete_adoption(ctx.guild.id, int(row["parent_id"]), ctx.author.id)
        await ctx.reply(embed=success_embed("Ran Away", f"Removed **{len(rows)}** adopted parent relationship(s)."))

    @commands.command(name="adoptionlb", aliases=["adoptlb", "familylb"])
    @commands.guild_only()
    async def adoption_leaderboard(self, ctx, limit: int = 10):
        """Show the users with the most adopted children."""
        if not await self._ensure_db(ctx):
            return
        limit = max(1, min(int(limit), 20))
        rows = await self.db.adoption_leaderboard(ctx.guild.id, limit)
        if not rows:
            return await ctx.reply(embed=info_embed("Adoption Leaderboard", "No adoptions yet."))
        lines = [
            f"`#{index}` <@{int(row['parent_id'])}> - `{int(row['total']):,}` child/children"
            for index, row in enumerate(rows, start=1)
        ]
        embed = discord.Embed(
            title="Adoption Leaderboard",
            description="\n".join(lines),
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        await ctx.reply(embed=embed)

    @commands.command(name="forcemarry")
    @commands.guild_only()
    @is_owner()
    async def forcemarry(self, ctx, member1: discord.Member = None, member2: discord.Member = None):
        """Bot owner only: force-create a marriage between two users."""
        if not await self._ensure_db(ctx):
            return
        if member1 is None or member2 is None:
            return await ctx.reply(embed=error_embed("Missing Users", f"Usage: `{self._prefix(ctx)}forcemarry @user1 @user2`"))
        if member1.id == member2.id:
            return await ctx.reply(embed=error_embed("Invalid Users", "Pick two different users."))
        if member1.bot or member2.bot:
            return await ctx.reply(embed=error_embed("Invalid Users", "Forced marriage does not support bots."))

        old_rows = []
        for member in (member1, member2):
            row = await self.db.delete_marriage(ctx.guild.id, member.id)
            if row:
                old_rows.append(row)
        created = await self.db.create_marriage(ctx.guild.id, member1.id, member2.id)
        if not created:
            return await ctx.reply(embed=error_embed("Force Marry Failed", "Could not create the marriage."))
        note = f"\nRemoved **{len(old_rows)}** previous marriage(s)." if old_rows else ""
        await ctx.reply(embed=success_embed("Forced Marriage", f"{member1.mention} and {member2.mention} are now married.{note}"))

    @commands.command(name="forcedivorce")
    @commands.guild_only()
    @is_owner()
    async def forcedivorce(self, ctx, member: discord.Member = None):
        """Bot owner only: force-remove a user's marriage."""
        if not await self._ensure_db(ctx):
            return
        if member is None:
            return await ctx.reply(embed=error_embed("Missing User", f"Usage: `{self._prefix(ctx)}forcedivorce @user`"))
        row = await self.db.delete_marriage(ctx.guild.id, member.id)
        if not row:
            return await ctx.reply(embed=info_embed("Not Married", f"{member.mention} is not married."))
        partner_id = int(row["user2_id"] if int(row["user1_id"]) == member.id else row["user1_id"])
        await ctx.reply(embed=success_embed("Forced Divorce", f"Removed the marriage between {member.mention} and <@{partner_id}>."))

    @commands.command(name="forceadopt")
    @commands.guild_only()
    @is_owner()
    async def forceadopt(self, ctx, parent: discord.Member = None, child: discord.Member = None):
        """Bot owner only: force-create an adoption."""
        if not await self._ensure_db(ctx):
            return
        if parent is None or child is None:
            return await ctx.reply(embed=error_embed("Missing Users", f"Usage: `{self._prefix(ctx)}forceadopt @parent @child`"))
        if parent.id == child.id:
            return await ctx.reply(embed=error_embed("Invalid Users", "A user cannot adopt themselves."))
        if parent.bot or child.bot:
            return await ctx.reply(embed=error_embed("Invalid Users", "Forced adoption does not support bots."))
        created, blocker = await self.db.create_adoption(ctx.guild.id, parent.id, child.id)
        if not created:
            parent_id = int(blocker["parent_id"]) if blocker and blocker.get("parent_id") else parent.id
            return await ctx.reply(embed=error_embed("Already Adopted", f"{child.mention} already has parent <@{parent_id}>. Clear that parent first."))
        await ctx.reply(embed=success_embed("Forced Adoption", f"{parent.mention} adopted {child.mention}."))

    @commands.command(name="forcedisown", aliases=["forceunadopt"])
    @commands.guild_only()
    @is_owner()
    async def forcedisown(self, ctx, parent: discord.Member = None, child: discord.Member = None):
        """Bot owner only: force-remove one adoption relationship."""
        if not await self._ensure_db(ctx):
            return
        if parent is None or child is None:
            return await ctx.reply(embed=error_embed("Missing Users", f"Usage: `{self._prefix(ctx)}forcedisown @parent @child`"))
        row = await self.db.delete_adoption(ctx.guild.id, parent.id, child.id)
        if not row:
            return await ctx.reply(embed=info_embed("Not Family", f"{parent.mention} has not adopted {child.mention}."))
        await ctx.reply(embed=success_embed("Forced Disown", f"Removed the adoption between {parent.mention} and {child.mention}."))

    @commands.command(name="forceclearfamily", aliases=["clearfamily"])
    @commands.guild_only()
    @is_owner()
    async def forceclearfamily(self, ctx, member: discord.Member = None):
        """Bot owner only: remove all adoption rows involving a user."""
        if not await self._ensure_db(ctx):
            return
        if member is None:
            return await ctx.reply(embed=error_embed("Missing User", f"Usage: `{self._prefix(ctx)}forceclearfamily @user`"))
        rows = await self.db.clear_adoptions_for_user(ctx.guild.id, member.id)
        await ctx.reply(embed=success_embed("Family Cleared", f"Removed **{len(rows)}** adoption relationship(s) involving {member.mention}."))

    @commands.command(name="marriagehelp", aliases=["mhelp"])
    @commands.guild_only()
    async def marriage_help(self, ctx):
        """Show marriage command help."""
        prefix = self._prefix(ctx)
        embed = discord.Embed(
            title="Marriage Commands",
            description="All marriage commands are prefix-based.",
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Core",
            value=(
                f"`{prefix}marry @user` - propose\n"
                f"`{prefix}divorce` - divorce with confirmation\n"
                f"`{prefix}partner [@user]` - show partner\n"
                f"`{prefix}anniversary [@user]` - show spouse and wedding date\n"
                f"`{prefix}family [@user]` - show partner, parents, and children"
            ),
            inline=False,
        )
        embed.add_field(
            name="Adoption",
            value=(
                f"`{prefix}adopt @user` - request adoption\n"
                f"`{prefix}children [@user]` - show adopted children\n"
                f"`{prefix}parents [@user]` - show adopted parents\n"
                f"`{prefix}disown @user` - remove one of your adopted children\n"
                f"`{prefix}runaway [@parent]` - leave one or all adopted parents\n"
                f"`{prefix}adoptionlb [limit]` - adoption leaderboard"
            ),
            inline=False,
        )
        embed.add_field(
            name="Trees & Graphs",
            value=(
                f"`{prefix}tree [@user]` - simple MarriageBot-style family tree\n"
                f"`{prefix}fulltree [@user]` - full connected family graph\n"
                f"`{prefix}familysize [@user]` - connected family count\n"
                f"`{prefix}marriagelb [limit]` - longest marriages\n"
                f"`{prefix}marriagegraph [limit]` - PNG server graph"
            ),
            inline=False,
        )
        embed.add_field(
            name="Bot Owner Force",
            value=(
                f"`{prefix}forcemarry @user1 @user2`\n"
                f"`{prefix}forcedivorce @user`\n"
                f"`{prefix}forceadopt @parent @child`\n"
                f"`{prefix}forcedisown @parent @child`\n"
                f"`{prefix}forceclearfamily @user`"
            ),
            inline=False,
        )
        await ctx.reply(embed=embed)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.reply(embed=error_embed("Cooldown", f"Try again in `{error.retry_after:.1f}s`."))
        if isinstance(error, commands.MissingPermissions):
            return await ctx.reply(embed=error_embed("Missing Permissions", "You need Manage Server for that command."))
        if isinstance(error, commands.CheckFailure):
            return
        if isinstance(error, commands.BadArgument):
            return await ctx.reply(embed=error_embed("Invalid User", "Mention a valid server member."))
        raise error


async def setup(bot):
    await bot.add_cog(Marriage(bot))
