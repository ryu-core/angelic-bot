import discord
from discord.ext import commands

import config
from utils.database import settings_db
from utils.embeds import error_embed, info_embed, success_embed
from utils.quote_generator import QuoteImageGenerator


class AutoQuote(commands.Cog):
    """Auto-render messages in configured channels as quote images."""

    def __init__(self, bot):
        self.bot = bot
        self.generator = QuoteImageGenerator()

    def _prefix(self, ctx):
        return getattr(ctx, "prefix", None) or config.PREFIX

    def _db_ready(self):
        return settings_db is not None

    def _get_channels(self, guild_id):
        if not self._db_ready():
            return []
        return settings_db.get_setting("autoquote", guild_id, "channels", []) or []

    def _set_channels(self, guild_id, channel_ids):
        if not self._db_ready():
            return False
        settings_db.set_setting("autoquote", guild_id, "channels", [str(channel_id) for channel_id in channel_ids])
        return True

    async def _is_command_message(self, message):
        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        return any(message.content.startswith(prefix) for prefix in prefixes)

    async def _add_channel(self, ctx, channel):
        if not channel:
            channel = ctx.channel
        if not self._db_ready():
            return await ctx.reply(embed=error_embed("Database Offline", "Auto-quote channels cannot be saved right now."))

        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.attach_files or not perms.manage_messages:
            return await ctx.reply(embed=error_embed(
                "Missing Permission",
                f"I need Send Messages, Attach Files, and Manage Messages in {channel.mention}.",
            ))

        channels = self._get_channels(ctx.guild.id)
        channel_id = str(channel.id)
        if channel_id not in channels:
            channels.append(channel_id)
            self._set_channels(ctx.guild.id, channels)
        await ctx.reply(embed=success_embed("Auto Quote Enabled", f"Messages in {channel.mention} will be turned into quote images."))

    @commands.group(name="autoquote", aliases=["quotechannel", "autoquotechannel"], invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def autoquote(self, ctx, channel: discord.TextChannel = None):
        """Enable auto-quote in a channel."""
        await self._add_channel(ctx, channel)

    @autoquote.command(name="add", aliases=["enable", "on", "set"])
    @commands.has_permissions(manage_guild=True)
    async def autoquote_add(self, ctx, channel: discord.TextChannel = None):
        await self._add_channel(ctx, channel)

    @autoquote.command(name="remove", aliases=["disable", "off", "delete"])
    @commands.has_permissions(manage_guild=True)
    async def autoquote_remove(self, ctx, channel: discord.TextChannel = None):
        if not channel:
            channel = ctx.channel
        if not self._db_ready():
            return await ctx.reply(embed=error_embed("Database Offline", "Auto-quote channels cannot be changed right now."))

        channels = self._get_channels(ctx.guild.id)
        channel_id = str(channel.id)
        if channel_id not in channels:
            return await ctx.reply(embed=error_embed("Not Enabled", f"{channel.mention} is not an auto-quote channel."))

        channels.remove(channel_id)
        self._set_channels(ctx.guild.id, channels)
        await ctx.reply(embed=success_embed("Auto Quote Disabled", f"Messages in {channel.mention} will no longer be auto-quoted."))

    @autoquote.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def autoquote_list(self, ctx):
        channels = self._get_channels(ctx.guild.id)
        if not channels:
            return await ctx.reply(embed=info_embed("No Auto Quote Channels", f"Use `{self._prefix(ctx)}autoquote add #channel`."))
        description = "\n".join(f"<#{channel_id}>" for channel_id in channels)
        await ctx.reply(embed=info_embed("Auto Quote Channels", description))

    @autoquote.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def autoquote_clear(self, ctx):
        if not self._db_ready():
            return await ctx.reply(embed=error_embed("Database Offline", "Auto-quote channels cannot be changed right now."))
        count = len(self._get_channels(ctx.guild.id))
        self._set_channels(ctx.guild.id, [])
        await ctx.reply(embed=success_embed("Auto Quote Cleared", f"Removed **{count}** auto-quote channel(s)."))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if str(message.channel.id) not in self._get_channels(message.guild.id):
            return
        if not message.content.strip():
            return
        if await self._is_command_message(message):
            return

        perms = message.channel.permissions_for(message.guild.me)
        if not perms.send_messages or not perms.attach_files:
            return

        try:
            image_bytes = await self.generator.generate(
                quote_text=message.content,
                author=None,
                avatar_url=str(message.author.display_avatar.url),
                username=message.author.name,
                theme="midnight",
            )
            file = discord.File(image_bytes, filename="quote.png")
            await message.channel.send(
                file=file,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            if perms.manage_messages:
                await message.delete()
        except Exception as exc:
            print(f"Auto quote error in {message.guild.id}/{message.channel.id}: {exc}")


async def setup(bot):
    await bot.add_cog(AutoQuote(bot))
