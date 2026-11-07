"""
👑 GF Cog — Exclusive bot powers for the queen herself.

This cog gives one specific user (GF_ID) a personal suite of commands
that no one else can use. It includes:
  • gfannounce  — Rich pink embed announcement
  • gfreward    — Gift economy gems to anyone
  • queenmode   — Auto-react 👑 to her messages
  • Auto-protection against rude replies/mentions
"""

import discord
from discord.ext import commands
from datetime import timedelta
import os
import re

from config import COLORS, EMOJIS
import config
from utils.database import settings_db
from utils.economy_db import economy_db

# ======================== CONFIGURATION ========================
_gf_id_value = os.getenv("GF_USER_ID", "").strip()
GF_ID = int(_gf_id_value) if _gf_id_value.isdigit() else 0

# Signature pink/rose color used for all GF embeds (hot pink)
GF_COLOR = 0xff69b4

# Hardcoded slur/rude-word filter list (lowercase)
# Add or remove words as needed — keep them lowercase
BLOCKED_WORDS = [
    "idiot", "stupid", "dumb", "ugly", "trash", "loser",
    "stfu", "shut up", "die", "kys", "kill yourself",
    "bitch", "whore", "slut", "hoe", "thot",
    "retard", "retarded", "fatass", "fat",
    "cringe", "pathetic", "disgusting", "useless",
    "nobody asked", "ratio", "cope", "seethe",
]

# ======================== PERMISSION CHECK ========================
def is_gf():
    """
    Custom check decorator — allows the GF (GF_ID) and bot owners
    (config.OWNER_IDS) to run the decorated command.
    Everyone else gets a pink 'no perms' embed.
    """
    async def predicate(ctx):
        if (GF_ID and ctx.author.id == GF_ID) or ctx.author.id in config.OWNER_IDS:
            return True
        embed = discord.Embed(
            title="❌ Access Denied",
            description="Only the **queen** can use this command! 👑",
            color=GF_COLOR,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Nice try though~ OwO")
        await ctx.send(embed=embed)
        return False
    return commands.check(predicate)


# ======================== COG CLASS ========================
class GF(commands.Cog):
    """👑 Exclusive commands for the queen — GF-only powers"""

    QUEENMODE_NAMESPACE = "gf_queenmode"
    QUEENMODE_KEY = "enabled"

    def __init__(self, bot):
        self.bot = bot

        # Initialize queen mode cache on bot instance if not present.
        # Structure: {guild_id: bool}
        if not hasattr(self.bot, "queen_mode"):
            self.bot.queen_mode = {}

    def _get_queen_mode(self, guild_id: int) -> bool:
        """Return whether queen mode is enabled for a guild."""
        cached = self.bot.queen_mode.get(guild_id)
        if cached is not None:
            return cached

        enabled = False
        if settings_db:
            enabled = bool(
                settings_db.get_setting(self.QUEENMODE_NAMESPACE, guild_id, self.QUEENMODE_KEY, False)
            )

        self.bot.queen_mode[guild_id] = enabled
        return enabled

    def _set_queen_mode(self, guild_id: int, enabled: bool) -> None:
        """Persist queen mode for a guild."""
        self.bot.queen_mode[guild_id] = enabled
        if settings_db:
            settings_db.set_setting(self.QUEENMODE_NAMESPACE, guild_id, self.QUEENMODE_KEY, enabled)

    # ==================== COMMANDS ====================

    # ---------- ,gfannounce ----------
    @commands.command(name="gfannounce")
    @is_gf()
    async def gfannounce(self, ctx, *, message: str):
        """👑 Send a rich pink announcement embed in the current channel."""
        try:
            if not ctx.guild:
                return await ctx.send("This command only works in a server.")

            embed = discord.Embed(
                title="👑 Royal Announcement 👑",
                description=message,
                color=GF_COLOR,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(
                text=f"Announced by {ctx.author.display_name}",
                icon_url=ctx.author.display_avatar.url
            )

            await ctx.send(embed=embed)

            # Try to delete the invoking command message for cleanliness
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass  # Missing permissions to delete — silently skip

        except Exception as e:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Announcement Failed",
                    description=f"Something went wrong:\n```{e}```",
                    color=GF_COLOR
                )
            )

    # ---------- ,gfreward ----------
    @commands.command(name="gfreward")
    @commands.has_permissions(manage_guild=True)
    @is_gf()
    async def gfreward(self, ctx, member: discord.Member, amount: int):
        """
        👑 Reward a user with economy gems.
        No upper limit — the queen gives as many as she wants.
        """
        try:
            if not ctx.guild:
                return await ctx.send("This command only works in a server.")

            if amount <= 0:
                return await ctx.send(
                    embed=discord.Embed(
                        title="❌ Invalid Amount",
                        description="Amount must be a positive number!",
                        color=GF_COLOR
                    )
                )

            # Ensure the target user exists in the economy DB, then add gems
            economy_db.get_user(str(member.id))
            economy_db.add_earnings(str(member.id), amount)
            economy_db.log_transaction(
                str(member.id),
                "admin_add", amount,
                f"Queen's reward from {ctx.author.display_name}"
            )

            embed = discord.Embed(
                title=f"👑 Royal Reward! {EMOJIS.get('gem', '💎')}",
                description=(
                    f"**{member.display_name}** has been blessed with "
                    f"**{amount:,}** {EMOJIS.get('gem', '💎')} gems!\n\n"
                    f"*A gift from the queen herself~ ✨*"
                ),
                color=GF_COLOR,
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(
                text=f"Rewarded by {ctx.author.display_name} 👑",
                icon_url=ctx.author.display_avatar.url
            )
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Reward Failed",
                    description=f"Something went wrong:\n```{e}```",
                    color=GF_COLOR
                )
            )

    # ---------- ,queenmode ----------
    @commands.command(name="queenmode")
    @commands.has_permissions(manage_guild=True)
    @is_gf()
    async def queenmode(self, ctx):
        """
        👑 Toggle queen mode on/off.
        When ON, the bot auto-reacts 👑 to every message she sends.
        """
        try:
            if not ctx.guild:
                return await ctx.send("This command only works in a server.")

            enabled = not self._get_queen_mode(ctx.guild.id)
            self._set_queen_mode(ctx.guild.id, enabled)
            status = "**ON** 👑✨" if enabled else "**OFF** 😴"

            embed = discord.Embed(
                title="👑 Queen Mode",
                description=f"Queen Mode is now {status}",
                color=GF_COLOR,
                timestamp=discord.utils.utcnow()
            )

            if enabled:
                embed.add_field(
                    name="What does this do?",
                    value="Every message you send will get an automatic 👑 reaction!",
                    inline=False
                )

            embed.set_footer(
                text=f"Toggled by {ctx.author.display_name}",
                icon_url=ctx.author.display_avatar.url
            )
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Queen Mode Error",
                    description=f"Something went wrong:\n```{e}```",
                    color=GF_COLOR
                )
            )

    # ==================== LISTENERS ====================

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Listener that handles two things:
          1. Queen mode — auto-react 👑 to the GF's messages
          2. Auto-protection — defend her against rude replies/mentions
        """

        # Ignore bot messages entirely
        if message.author.bot or not message.guild:
            return

        # --- 1. QUEEN MODE AUTO-REACT ---
        # If queen mode is ON and the message is from the GF, react with 👑
        if self._get_queen_mode(message.guild.id) and message.author.id == GF_ID:
            try:
                await message.add_reaction("👑")
            except (discord.Forbidden, discord.HTTPException):
                pass  # Can't react — missing perms or message deleted

        # --- 2. AUTO-PROTECTION ---
        # Check if the message is a reply to GF or mentions GF
        await self._handle_auto_protection(message)

    async def _handle_auto_protection(self, message):
        """
        If a message is a reply to the GF or mentions her, AND contains
        a blocked word, auto-delete it, warn in the channel, and timeout
        the offender for 10 minutes.
        """
        # Don't punish the GF herself or bots
        if message.author.id == GF_ID or message.author.bot:
            return
        if (
            message.author.guild_permissions.manage_messages
            or message.author.guild_permissions.moderate_members
            or message.author.guild_permissions.administrator
        ):
            return
        bot_member = message.guild.me
        if bot_member and message.author.top_role >= bot_member.top_role:
            return

        # Check if this message targets the GF via reply or mention
        targets_gf = False

        # Check if it's a reply to one of her messages
        if message.reference and message.reference.message_id:
            try:
                replied_msg = await message.channel.fetch_message(message.reference.message_id)
                if replied_msg.author.id == GF_ID:
                    targets_gf = True
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        # Check if she is directly mentioned
        if not targets_gf:
            for user in message.mentions:
                if user.id == GF_ID:
                    targets_gf = True
                    break

        if not targets_gf:
            return

        # Check message content against the blocked words list
        msg_lower = message.content.lower()
        offending_word = None
        for word in BLOCKED_WORDS:
            # Use word-boundary matching so "class" doesn't trigger "ass"
            if re.search(r'\b' + re.escape(word) + r'\b', msg_lower):
                offending_word = word
                break

        if not offending_word:
            return

        # --- OFFENSE DETECTED — take action ---

        # 1. Delete the offending message
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        # 2. Send a warning embed
        warning_embed = discord.Embed(
            title="👑 Watch Your Mouth!",
            description=(
                f"**{message.author.display_name}**, that kind of language towards "
                f"the **queen** is NOT tolerated here.\n\n"
                f"🔇 You have been timed out for **10 minutes**."
            ),
            color=GF_COLOR,
            timestamp=discord.utils.utcnow()
        )
        warning_embed.set_thumbnail(url=message.author.display_avatar.url)
        warning_embed.set_footer(text="Be respectful. 👑")

        try:
            await message.channel.send(embed=warning_embed)
        except discord.Forbidden:
            pass  # Can't send messages in this channel

        # 3. Timeout the offender for 10 minutes
        try:
            await message.author.timeout(
                discord.utils.utcnow() + timedelta(minutes=10),
                reason=f"Auto-protection: rude message towards the queen (word: {offending_word})"
            )
        except discord.Forbidden:
            # Bot doesn't have permission to timeout this user (e.g. higher role)
            try:
                await message.channel.send(
                    embed=discord.Embed(
                        description=(
                            f"⚠️ I couldn't timeout **{message.author.display_name}** — "
                            f"they may have a higher role than me."
                        ),
                        color=GF_COLOR
                    )
                )
            except discord.Forbidden:
                pass
        except Exception as e:
            print(f"[GF Cog] Auto-protection timeout error: {e}")


# ======================== COG SETUP ========================
async def setup(bot):
    """Register the GF cog with the bot."""
    await bot.add_cog(GF(bot))
