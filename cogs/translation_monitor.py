"""
Translation Monitor Cog
Monitors and translates messages between two users in a channel.
Uses MyMemoryTranslator (no API key required, reliable on servers).
Also provides standalone ,translate command.
"""
import discord
from discord.ext import commands
from deep_translator import GoogleTranslator
import asyncio
from utils.embeds import success_embed, error_embed, info_embed
import config

# Common language codes for display
LANG_CODES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese", "ar": "Arabic", "hi": "Hindi", "ru": "Russian",
    "tr": "Turkish", "nl": "Dutch", "pl": "Polish", "sv": "Swedish",
    "uk": "Ukrainian", "id": "Indonesian", "vi": "Vietnamese",
}

def _do_translate(text: str, target: str) -> str:
    """Synchronous translation helper (run in executor)."""
    translator = GoogleTranslator(source="auto", target=target)
    return translator.translate(text)


class TranslationMonitor(commands.Cog):
    """Translate messages and monitor conversations between users."""

    def __init__(self, bot):
        self.bot = bot
        # { channel_id: { user1_id, user2_id, lang1, lang2, initiator_id } }
        self.active_monitors: dict = {}

    @property
    def qualified_name(self):
        return "Translation"

    # ──────────────────────────────────────────────────────────────────────────
    # ,translate — one-off translation
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="quicktranslate", aliases=["qt", "qtrans"])
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def translate(self, ctx: commands.Context, lang: str, *, text: str = None):
        """🌐 Translate text to the specified language.

        Usage: ,quicktranslate <lang_code> <text>
          Or: reply to a message → ,quicktranslate <lang_code>
        Example: ,quicktranslate es Hello world!
        """
        # Support reply-to
        if text is None and ctx.message.reference:
            try:
                ref = ctx.message.reference.resolved
                if isinstance(ref, discord.Message):
                    text = ref.content.strip()
            except Exception:
                pass

        if not text:
            return await ctx.send(embed=error_embed(
                "Missing Text",
                f"**Usage:** `{config.PREFIX}translate <lang> <text>`\n"
                f"Example: `{config.PREFIX}translate es Hello, how are you?`\n\n"
                f"Or reply to a message: `{config.PREFIX}translate ja`"
            ))

        lang = lang.lower().strip()
        if len(text) > 500:
            text = text[:500]

        async with ctx.typing():
            try:
                translated = await asyncio.to_thread(_do_translate, text, lang)
                lang_name = LANG_CODES.get(lang, lang.upper())

                embed = discord.Embed(
                    title=f"🌐 Translated to {lang_name}",
                    color=0x3498db,
                )
                embed.add_field(name="Original", value=f"```{text[:500]}```", inline=False)
                embed.add_field(name=f"→ {lang_name}", value=f"```{translated}```", inline=False)
                embed.set_footer(
                    text=f"Requested by {ctx.author.display_name}",
                    icon_url=ctx.author.display_avatar.url,
                )
                await ctx.send(embed=embed)

            except Exception as e:
                err = str(e)
                hint = ""
                if "invalid" in err.lower() or "language" in err.lower():
                    hint = f"\n💡 Use a valid language code like `en`, `es`, `fr`, `de`, `ja`, `ko`, `hi`, `ru`"
                await ctx.send(embed=error_embed(
                    "Translation Failed",
                    f"Could not translate to `{lang}`.{hint}\n\nError: `{err[:150]}`"
                ))

    # ──────────────────────────────────────────────────────────────────────────
    # ,languages — show supported codes
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="languages", aliases=["langs", "langcodes"])
    async def languages(self, ctx: commands.Context):
        """📋 List commonly supported language codes for translation."""
        lines = [f"`{code}` — {name}" for code, name in LANG_CODES.items()]
        embed = discord.Embed(
            title="🌐 Common Language Codes",
            description="\n".join(lines),
            color=config.COLORS["primary"],
        )
        embed.set_footer(text="Use these codes with ,translate and ,monitor_translate")
        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # ,monitor_translate — start monitoring two users
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="monitor_translate", aliases=["monitortrans", "monitor"])
    @commands.has_permissions(manage_messages=True)
    async def start_translation(
        self,
        ctx,
        user1: discord.Member = None,
        user2: discord.Member = None,
        lang1: str = None,
        lang2: str = None,
    ):
        """🌐 Monitor & auto-translate messages between two users.

        Usage: ,monitor_translate @user1 @user2 <lang1> <lang2>
        Example: ,monitor_translate @John @Maria en es
        → John's msgs → Spanish | Maria's msgs → English
        """
        if not all([user1, user2, lang1, lang2]):
            return await ctx.reply(embed=error_embed(
                "Invalid Usage",
                f"**Usage:** `{config.PREFIX}monitor_translate @user1 @user2 <lang1> <lang2>`\n\n"
                "**Example:** `{prefix}monitor_translate @John @Maria en es`\n"
                "This translates John→Spanish and Maria→English.\n\n"
                f"Use `{config.PREFIX}languages` to see all language codes."
            ))

        if user1.bot or user2.bot:
            return await ctx.reply(embed=error_embed("Invalid Users", "Cannot monitor bot messages!"))

        if user1.id == user2.id:
            return await ctx.reply(embed=error_embed("Invalid Users", "Please select two different users!"))

        if ctx.channel.id in self.active_monitors:
            return await ctx.reply(embed=error_embed(
                "Already Monitoring",
                f"Translation is already active in this channel!\n"
                f"Use `{config.PREFIX}stoptranslate` to stop it first."
            ))

        lang1 = lang1.lower().strip()
        lang2 = lang2.lower().strip()

        # Quick validation
        try:
            await asyncio.to_thread(_do_translate, "test", lang1)
        except Exception:
            return await ctx.reply(embed=error_embed(
                "Invalid Language", f"`{lang1}` is not a valid language code.\n"
                f"Use `{config.PREFIX}languages` to see valid codes."
            ))
        try:
            await asyncio.to_thread(_do_translate, "test", lang2)
        except Exception:
            return await ctx.reply(embed=error_embed(
                "Invalid Language", f"`{lang2}` is not a valid language code.\n"
                f"Use `{config.PREFIX}languages` to see valid codes."
            ))

        self.active_monitors[ctx.channel.id] = {
            "user1_id": user1.id,
            "user2_id": user2.id,
            "lang1": lang1,
            "lang2": lang2,
            "initiator_id": ctx.author.id,
        }

        lang1_name = LANG_CODES.get(lang1, lang1.upper())
        lang2_name = LANG_CODES.get(lang2, lang2.upper())

        embed = discord.Embed(
            title="🌐 Translation Monitor Started",
            description=(
                f"Now auto-translating messages in this channel:\n\n"
                f"**{user1.display_name}** → `{lang2_name}` (for {user2.display_name})\n"
                f"**{user2.display_name}** → `{lang1_name}` (for {user1.display_name})\n\n"
                f"Use `{config.PREFIX}stoptranslate` to stop."
            ),
            color=config.COLORS["success"],
        )
        embed.set_footer(text=f"Started by {ctx.author.display_name}")
        await ctx.reply(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # ,stoptranslate
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="stoptranslate", aliases=["stoptrans", "stopmonitor"])
    async def stop_translation(self, ctx):
        """🛑 Stop translation monitoring in this channel."""
        if ctx.channel.id not in self.active_monitors:
            return await ctx.reply(embed=error_embed(
                "No Active Monitor",
                f"No translation monitor is active here.\n"
                f"Start one with `{config.PREFIX}monitor_translate @u1 @u2 lang1 lang2`."
            ))

        monitor = self.active_monitors[ctx.channel.id]
        if ctx.author.id != monitor["initiator_id"] and not ctx.author.guild_permissions.administrator:
            return await ctx.reply(embed=error_embed(
                "Permission Denied",
                "Only the person who started monitoring (or an admin) can stop it!"
            ))

        del self.active_monitors[ctx.channel.id]
        await ctx.reply(embed=success_embed(
            "Translation Stopped",
            "Translation monitoring has been stopped in this channel."
        ))

    # ──────────────────────────────────────────────────────────────────────────
    # Listener — auto-translate monitored messages
    # ──────────────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Auto-translate messages from monitored users."""
        if message.author.bot or not message.guild:
            return
        if message.channel.id not in self.active_monitors:
            return

        monitor = self.active_monitors[message.channel.id]

        if message.author.id == monitor["user1_id"]:
            target_lang = monitor["lang2"]
            target_uid  = monitor["user2_id"]
        elif message.author.id == monitor["user2_id"]:
            target_lang = monitor["lang1"]
            target_uid  = monitor["user1_id"]
        else:
            return

        # Skip commands and empty messages
        if not message.content or message.content.startswith(config.PREFIX):
            return

        text = message.content[:500]

        try:
            translated = await asyncio.to_thread(_do_translate, text, target_lang)

            target_user = message.guild.get_member(target_uid)
            lang_name = LANG_CODES.get(target_lang, target_lang.upper())

            embed = discord.Embed(
                description=translated,
                color=0x3498db,
            )
            embed.set_author(
                name=f"{message.author.display_name} (→ {lang_name})",
                icon_url=message.author.display_avatar.url,
            )
            embed.set_footer(text=f"🌐 Auto-translated to {lang_name}")

            await message.channel.send(embed=embed)

        except Exception as e:
            # Visible error so user knows translation failed
            print(f"[TranslationMonitor] Error: {e}")
            try:
                await message.channel.send(
                    embed=discord.Embed(
                        description=f"⚠️ Translation failed for {message.author.mention}: `{str(e)[:100]}`",
                        color=discord.Color.orange(),
                    ),
                    delete_after=8,
                )
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(TranslationMonitor(bot))
