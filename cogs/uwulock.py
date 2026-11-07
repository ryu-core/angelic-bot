"""
UwU Lock cog.

Keeps the uwu-lock command and message enforcement separate from the GF cog.
Queen and bot owners can manage binders; queen, owners, and binders can lock users.
"""

import inspect
import random
import re

import discord
from discord.ext import commands

import config
from cogs.gf import GF_COLOR, GF_ID
from utils.database import settings_db


UWU_SUFFIXES = ["uwu", "OwO", "~", ">.< ", "rawr", ":3", "^^"]

JEJE_REPLACEMENTS = {
    "A": ["a", "A", "4", "@"],
    "B": ["b", "B", "8"],
    "C": ["c", "C", "k", "<"],
    "D": ["d", "D"],
    "E": ["e", "E", "3"],
    "F": ["f", "F", "ph"],
    "G": ["g", "G", "6"],
    "H": ["h", "H", "#-#"],
    "I": ["i", "I", "1", "!"],
    "J": ["j", "J"],
    "K": ["k", "K", "q"],
    "L": ["l", "L", "1"],
    "M": ["m", "M"],
    "N": ["n", "N"],
    "O": ["o", "O", "0"],
    "P": ["p", "P"],
    "Q": ["q", "Q"],
    "R": ["r", "R"],
    "S": ["s", "S", "5", "z", "$"],
    "T": ["t", "T", "7"],
    "U": ["u", "U", "v"],
    "V": ["v", "V", "/"],
    "W": ["w", "W", "vv"],
    "X": ["x", "X", "><"],
    "Y": ["y", "Y"],
    "Z": ["z", "Z", "2"],
}

JEJE_EMOJIS = {
    "love": ["💕", "💖", "💗", "🥰", "😍", "😘", "🫶"],
    "sad": ["😭", "😢", "🥺", "💔", "😔", "☹️", "😞"],
    "angry": ["😡", "😤", "🙄", "💢", "😒", "🤬"],
    "laugh": ["😭", "💀", "😂", "🤣", "😹"],
    "hype": ["✨", "🔥", "🤩", "😩", "💅", "‼️", "💯"],
    "default": ["😭", "💀", "✨", "😩", "💅", "🫶", "‼️"],
}

JEJE_LAUGH_SUFFIXES = ["xD", "HSHSHS", "LMAOO", "SKSKSK", "HELP"]


def uwufy(text: str) -> str:
    """
    Transform normal text into uwu-speak:
      1. r/l -> w, R/L -> W
      2. n + vowel -> ny + vowel
      3. Random stutter on some words' first letters
      4. Random cute suffix at the end
    """
    if not text:
        return text

    result = text.replace("r", "w").replace("l", "w")
    result = result.replace("R", "W").replace("L", "W")

    result = re.sub(r"n([aeiou])", r"ny\1", result)
    result = re.sub(r"N([aeiou])", r"Ny\1", result)
    result = re.sub(r"N([AEIOU])", r"NY\1", result)

    words = result.split(" ")
    stuttered = []
    for word in words:
        if word and word[0].isalpha() and random.random() < 0.3:
            stuttered.append(f"{word[0]}-{word}")
        else:
            stuttered.append(word)

    return f"{' '.join(stuttered)} {random.choice(UWU_SUFFIXES)}"


def _jeje_emotion(sentence: str) -> str:
    lowered = sentence.lower()
    if any(word in lowered for word in ("love", "luv", "ily", "miss", "cute", "kiss", "heart")):
        return "love"
    if any(word in lowered for word in ("sad", "cry", "hurt", "sorry", "alone", "hate me", "miss you")):
        return "sad"
    if any(word in lowered for word in ("angry", "mad", "annoy", "hate", "shut", "stfu", "ugh")):
        return "angry"
    if any(word in lowered for word in ("haha", "lol", "lmao", "funny", "joke", "xd", "hshs")):
        return "laugh"
    if any(word in lowered for word in ("omg", "wow", "yay", "slay", "best", "so much", "very", "really")):
        return "hype"
    return "default"


def _jeje_emojis(sentence: str) -> str:
    mood = _jeje_emotion(sentence)
    pool = JEJE_EMOJIS[mood]
    amount = random.randint(4, 6)
    emojis = [random.choice(pool) for _ in range(amount)]
    if mood == "laugh" and random.random() < 0.65:
        emojis.append(random.choice(JEJE_LAUGH_SUFFIXES))
    return " ".join(emojis)


def _jeje_transform_text(text: str) -> str:
    transformed = []
    for char in text:
        replacements = JEJE_REPLACEMENTS.get(char.upper())
        transformed.append(random.choice(replacements) if replacements else char)
    return "".join(transformed)


def jejefy(text: str) -> str:
    """Transform text into jeje-style typing and append mood-based emoji bursts."""
    if not text:
        return text

    pieces = re.split(r"([^.!?\n]+[.!?\n]*|[.!?\n]+)", text)
    sentences = []

    for piece in pieces:
        if not piece:
            continue
        if not piece.strip() or re.fullmatch(r"[.!?\n]+", piece):
            sentences.append(piece)
            continue
        sentences.append(f"{_jeje_transform_text(piece).rstrip()} {_jeje_emojis(piece)}")

    return "".join(sentences).strip()


class UwULock(commands.Cog):
    """UwU-lock commands and message enforcement."""

    NAMESPACE = "gf_uwulock"
    JEJE_NAMESPACE = "gf_jejelock"
    LOCKED_KEY = "locked_users"
    BINDERS_KEY = "binders"

    def __init__(self, bot):
        self.bot = bot
        if not hasattr(self.bot, "uwu_users"):
            self.bot.uwu_users = {}
        if not hasattr(self.bot, "uwu_binders"):
            self.bot.uwu_binders = {}
        if not hasattr(self.bot, "jeje_users"):
            self.bot.jeje_users = {}

    def _is_manager(self, user_id: int) -> bool:
        return int(user_id) == GF_ID or int(user_id) in config.OWNER_IDS

    def _get_locked_users(self, guild_id: int) -> set[int]:
        locked = self.bot.uwu_users.get(guild_id)
        if locked is not None:
            return locked

        stored = []
        if settings_db:
            stored = settings_db.get_setting(self.NAMESPACE, guild_id, self.LOCKED_KEY, []) or []

        locked = {int(user_id) for user_id in stored}
        self.bot.uwu_users[guild_id] = locked
        return locked

    def _get_jeje_locked_users(self, guild_id: int) -> set[int]:
        locked = self.bot.jeje_users.get(guild_id)
        if locked is not None:
            return locked

        stored = []
        if settings_db:
            stored = settings_db.get_setting(self.JEJE_NAMESPACE, guild_id, self.LOCKED_KEY, []) or []

        locked = {int(user_id) for user_id in stored}
        self.bot.jeje_users[guild_id] = locked
        return locked

    def _save_locked_users(self, guild_id: int) -> None:
        if not settings_db:
            return
        settings_db.set_setting(
            self.NAMESPACE,
            guild_id,
            self.LOCKED_KEY,
            sorted(self.bot.uwu_users.get(guild_id, set())),
        )

    def _save_jeje_locked_users(self, guild_id: int) -> None:
        if not settings_db:
            return
        settings_db.set_setting(
            self.JEJE_NAMESPACE,
            guild_id,
            self.LOCKED_KEY,
            sorted(self.bot.jeje_users.get(guild_id, set())),
        )

    def _get_binders(self, guild_id: int) -> set[int]:
        binders = self.bot.uwu_binders.get(guild_id)
        if binders is not None:
            return binders

        stored = []
        if settings_db:
            stored = settings_db.get_setting(self.NAMESPACE, guild_id, self.BINDERS_KEY, []) or []

        binders = {int(user_id) for user_id in stored}
        self.bot.uwu_binders[guild_id] = binders
        return binders

    def _save_binders(self, guild_id: int) -> None:
        if not settings_db:
            return
        settings_db.set_setting(
            self.NAMESPACE,
            guild_id,
            self.BINDERS_KEY,
            sorted(self.bot.uwu_binders.get(guild_id, set())),
        )

    def _can_bind(self, guild_id: int, user_id: int) -> bool:
        return self._is_manager(user_id) or int(user_id) in self._get_binders(guild_id)

    async def _deny(self, ctx, message: str = "Only the queen, bot owner, or an uwu binder can use this."):
        embed = discord.Embed(
            title="Access Denied",
            description=message,
            color=GF_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        await ctx.send(embed=embed)

    async def _deny_jeje(self, ctx):
        await self._deny(ctx, "Only the queen and bot owner can use jejelock.")

    async def _is_saved_alias_command(self, message: discord.Message, prefix: str | None) -> bool:
        if not settings_db or not prefix or not message.content.startswith(prefix):
            return False

        without_prefix = message.content[len(prefix):].strip()
        if not without_prefix:
            return False

        alias_name = without_prefix.split(maxsplit=1)[0].lower()
        try:
            alias_cmd = settings_db.get_alias(message.guild.id, alias_name)
        except Exception:
            return False
        if not alias_cmd:
            return False

        target = alias_cmd.strip()
        if target.startswith(prefix):
            target = target[len(prefix):].lstrip()
        elif config.PREFIX and target.startswith(config.PREFIX):
            target = target[len(config.PREFIX):].lstrip()

        command_name = target.split(maxsplit=1)[0].lower() if target else ""
        return bool(command_name and self.bot.get_command(command_name))

    async def _is_real_command_message(self, message: discord.Message) -> bool:
        ctx = await self.bot.get_context(message)
        if ctx.valid and ctx.command:
            return True

        prefix = getattr(ctx, "prefix", None)
        if prefix:
            return await self._is_saved_alias_command(message, prefix)

        command_prefix = self.bot.command_prefix
        if callable(command_prefix):
            result = command_prefix(self.bot, message)
            if inspect.isawaitable(result):
                result = await result
        else:
            result = command_prefix

        prefixes = [result] if isinstance(result, str) else list(result or [])
        for candidate in prefixes:
            if await self._is_saved_alias_command(message, candidate):
                return True
        return False

    @commands.command(name="uwulock", aliases=["uwu"])
    @commands.guild_only()
    async def uwulock(self, ctx, member: discord.Member = None, toggle: str = "on"):
        """UwU-lock a user. Usage: ,uwulock @user [on/off]"""
        if member is None:
            return await ctx.send(
                embed=discord.Embed(
                    title="Missing User",
                    description=f"Usage: `{ctx.clean_prefix}uwulock @user [on/off]`",
                    color=GF_COLOR,
                )
            )
        if not self._can_bind(ctx.guild.id, ctx.author.id):
            return await self._deny(ctx)

        toggle = toggle.lower()
        locked_users = self._get_locked_users(ctx.guild.id)

        if toggle in {"on", "lock", "true", "yes"}:
            locked_users.add(member.id)
            self._save_locked_users(ctx.guild.id)
            embed = discord.Embed(
                title="OwO UwU-Lock Activated!",
                description=(
                    f"**{member.display_name}** has been uwu-locked.\n\n"
                    "Only real bot commands will pass through normally now."
                ),
                color=GF_COLOR,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Locked by {ctx.author.display_name}")
            return await ctx.send(embed=embed)

        if toggle in {"off", "unlock", "false", "no"}:
            locked_users.discard(member.id)
            self._save_locked_users(ctx.guild.id)
            embed = discord.Embed(
                title="OwO UwU-Lock Deactivated!",
                description=f"**{member.display_name}** can speak normally again.",
                color=GF_COLOR,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Unlocked by {ctx.author.display_name}")
            return await ctx.send(embed=embed)

        await ctx.send(
            embed=discord.Embed(
                title="Invalid Option",
                description=f"Use `on` or `off`.\nExample: `{ctx.clean_prefix}uwulock @user on`",
                color=GF_COLOR,
            )
        )

    @commands.command(name="jejelock", aliases=["jeje"])
    @commands.guild_only()
    async def jejelock(self, ctx, member: discord.Member = None, toggle: str = "on"):
        """Jeje-lock a user. Usage: ,jejelock @user [on/off]"""
        if not self._is_manager(ctx.author.id):
            return await self._deny_jeje(ctx)
        if member is None:
            return await ctx.send(
                embed=discord.Embed(
                    title="Missing User",
                    description=f"Usage: `{ctx.clean_prefix}jejelock @user [on/off]`",
                    color=GF_COLOR,
                )
            )

        toggle = toggle.lower()
        locked_users = self._get_jeje_locked_users(ctx.guild.id)

        if toggle in {"on", "lock", "true", "yes"}:
            locked_users.add(member.id)
            self._save_jeje_locked_users(ctx.guild.id)
            embed = discord.Embed(
                title="Jeje-Lock Activated!",
                description=(
                    f"**{member.display_name}** has been jeje-locked.\n\n"
                    "Only real bot commands will pass through normally now."
                ),
                color=GF_COLOR,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Locked by {ctx.author.display_name}")
            return await ctx.send(embed=embed)

        if toggle in {"off", "unlock", "false", "no"}:
            locked_users.discard(member.id)
            self._save_jeje_locked_users(ctx.guild.id)
            embed = discord.Embed(
                title="Jeje-Lock Deactivated!",
                description=f"**{member.display_name}** can speak normally again.",
                color=GF_COLOR,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Unlocked by {ctx.author.display_name}")
            return await ctx.send(embed=embed)

        await ctx.send(
            embed=discord.Embed(
                title="Invalid Option",
                description=f"Use `on` or `off`.\nExample: `{ctx.clean_prefix}jejelock @user on`",
                color=GF_COLOR,
            )
        )

    @commands.command(name="uwugrant", aliases=["grantuwu", "uwubinder"])
    @commands.guild_only()
    async def uwugrant(self, ctx, member: discord.Member = None):
        """Grant uwu binder permission."""
        if not self._is_manager(ctx.author.id):
            return await self._deny(ctx, "Only the queen and bot owner can grant uwu binder permission.")
        if member is None:
            return await ctx.send(f"Usage: `{ctx.clean_prefix}uwugrant @user`")

        binders = self._get_binders(ctx.guild.id)
        binders.add(member.id)
        self._save_binders(ctx.guild.id)
        await ctx.send(
            embed=discord.Embed(
                title="UwU Binder Granted",
                description=f"{member.mention} can now use `{ctx.clean_prefix}uwulock`.",
                color=GF_COLOR,
                timestamp=discord.utils.utcnow(),
            )
        )

    @commands.command(name="uwurevoke", aliases=["revokeuwu", "unuwubinder"])
    @commands.guild_only()
    async def uwurevoke(self, ctx, member: discord.Member = None):
        """Revoke uwu binder permission."""
        if not self._is_manager(ctx.author.id):
            return await self._deny(ctx, "Only the queen and bot owner can revoke uwu binder permission.")
        if member is None:
            return await ctx.send(f"Usage: `{ctx.clean_prefix}uwurevoke @user`")

        binders = self._get_binders(ctx.guild.id)
        binders.discard(member.id)
        self._save_binders(ctx.guild.id)
        await ctx.send(
            embed=discord.Embed(
                title="UwU Binder Revoked",
                description=f"{member.mention} can no longer use `{ctx.clean_prefix}uwulock`.",
                color=GF_COLOR,
                timestamp=discord.utils.utcnow(),
            )
        )

    @commands.command(name="uwubinders", aliases=["uwubinderlist"])
    @commands.guild_only()
    async def uwubinders(self, ctx):
        """List uwu binders."""
        if not self._can_bind(ctx.guild.id, ctx.author.id):
            return await self._deny(ctx)

        binders = sorted(self._get_binders(ctx.guild.id))
        description = "\n".join(f"`#{index}` <@{user_id}>" for index, user_id in enumerate(binders, 1))
        await ctx.send(
            embed=discord.Embed(
                title="UwU Binders",
                description=description or "No uwu binders granted yet.",
                color=GF_COLOR,
                timestamp=discord.utils.utcnow(),
            )
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        locked_users = self._get_locked_users(message.guild.id)
        jeje_locked_users = self._get_jeje_locked_users(message.guild.id)
        is_uwu_locked = message.author.id in locked_users
        is_jeje_locked = message.author.id in jeje_locked_users

        if message.author.id == GF_ID and not is_jeje_locked:
            return

        if not is_uwu_locked and not is_jeje_locked:
            return

        if await self._is_real_command_message(message):
            return

        if is_jeje_locked:
            await self._handle_locked_message(message, jejefy, "xiel Jeje", "Jeje-lock")
            return

        await self._handle_uwu_message(message)

    async def _handle_uwu_message(self, message):
        await self._handle_locked_message(message, uwufy, "xiel UwU", "UwU-lock")

    async def _handle_locked_message(self, message, transform, webhook_name: str, lock_name: str):
        try:
            original_text = message.content
            locked_text = transform(original_text) if original_text else ""
            attachments = message.attachments

            if not locked_text.strip() and not attachments:
                return

            files = []
            for attachment in attachments:
                try:
                    files.append(await attachment.to_file())
                except Exception:
                    pass

            try:
                await message.delete()
            except discord.Forbidden:
                pass
            except discord.NotFound:
                return

            webhook_channel = message.channel.parent if isinstance(message.channel, discord.Thread) else message.channel
            webhook = None
            try:
                webhooks = await webhook_channel.webhooks()
                for wh in webhooks:
                    if wh.user and wh.user.id == self.bot.user.id:
                        webhook = wh
                        break
                if not webhook:
                    webhook = await webhook_channel.create_webhook(
                        name=webhook_name,
                        reason=f"{lock_name} webhook for mimicking user profiles",
                    )
            except discord.Forbidden:
                content = locked_text.strip() or None
                if content or files:
                    await message.channel.send(content=content, files=files or discord.utils.MISSING)
                return

            send_kwargs = {
                "username": message.author.display_name,
                "avatar_url": message.author.display_avatar.url,
                "allowed_mentions": discord.AllowedMentions.none(),
            }
            if isinstance(message.channel, discord.Thread):
                send_kwargs["thread"] = message.channel
            if locked_text.strip():
                send_kwargs["content"] = locked_text.strip()
            if files:
                send_kwargs["files"] = files

            try:
                await webhook.send(**send_kwargs)
            except discord.NotFound:
                try:
                    webhook = await webhook_channel.create_webhook(
                        name=webhook_name,
                        reason=f"{lock_name} webhook recreated after stale 404",
                    )
                    await webhook.send(**send_kwargs)
                except Exception:
                    pass

        except Exception as e:
            print(f"[UwULock Cog] {lock_name} error: {e}")


async def setup(bot):
    await bot.add_cog(UwULock(bot))
