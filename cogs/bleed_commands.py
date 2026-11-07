"""
Bleed-Inspired Commands — Only commands NOT already in xiel
Covers: utility, info, moderation extras, server management
"""
import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from utils.embeds import success_embed, error_embed, info_embed
from utils.database import settings_db
import config
import asyncio
import aiohttp
import re
import time
from datetime import datetime, timedelta, UTC

# ... (rest of file)


class BleedCommands(commands.Cog):
    """Bleed-inspired utility, info, and moderation commands"""

    def __init__(self, bot):
        self.bot = bot
        self.snipe_cache = {}  # Already handled by utility.py — this is for clearsnipes
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    @property
    def qualified_name(self):
        return "Utility"

    # ─── REMINDER LOOP ───
    @tasks.loop(seconds=15)
    async def reminder_loop(self):
        """Check for due reminders and send them."""
        try:
            reminders = settings_db.get_due_reminders()
            for rem in reminders:
                try:
                    channel = self.bot.get_channel(int(rem['channel_id']))
                    if channel:
                        user = self.bot.get_user(int(rem['user_id']))
                        mention = user.mention if user else f"<@{rem['user_id']}>"
                        embed = discord.Embed(
                            title="⏰ Reminder",
                            description=rem['message'],
                            color=config.COLORS['primary'],
                            timestamp=datetime.now(UTC)
                        )
                        await channel.send(content=mention, embed=embed)
                except Exception:
                    pass
                settings_db.delete_reminder(rem['id'])
        except Exception:
            pass

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

    # ─── BANNER ───
    @commands.command(name='banner')
    async def banner(self, ctx, member: discord.Member = None):
        """Show a user's Discord banner"""
        member = member or ctx.author
        user = await self.bot.fetch_user(member.id)
        if not user.banner:
            return await ctx.reply(embed=error_embed('No Banner', f'{member.display_name} has no banner.'))
        embed = discord.Embed(color=member.color or config.COLORS['primary'])
        embed.set_author(name=f"{member.display_name}'s Banner", icon_url=member.display_avatar.url)
        embed.set_image(url=user.banner.url + "?size=4096")
        await ctx.reply(embed=embed)

    # ─── ROLEINFO ───
    @commands.command(name='roleinfo', aliases=['ri'])
    async def roleinfo(self, ctx, *, role: discord.Role = None):
        """Show detailed info about a role"""
        if not role:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}roleinfo <@role>`'))
        embed = discord.Embed(title=f"Role: {role.name}", color=role.color)
        embed.add_field(name="ID", value=role.id, inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Members", value=len(role.members), inline=True)
        embed.add_field(name="Position", value=role.position, inline=True)
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(role.created_at.timestamp())}:R>", inline=True)
        if role.icon:
            embed.set_thumbnail(url=role.icon.url)
        key_perms = [p[0].replace('_', ' ').title() for p in role.permissions if p[1] and p[0] in
                     ('administrator', 'manage_guild', 'manage_channels', 'manage_roles',
                      'manage_messages', 'kick_members', 'ban_members', 'mention_everyone')]
        if key_perms:
            embed.add_field(name="Key Permissions", value=', '.join(key_perms), inline=False)
        await ctx.reply(embed=embed)

    # ─── BOOSTERS ───
    @commands.command(name='legacy_boosters', hidden=True)
    async def boosters(self, ctx):
        """List all server boosters"""
        boosters = [m for m in ctx.guild.members if m.premium_since]
        if not boosters:
            return await ctx.reply(embed=info_embed('No Boosters', 'This server has no boosters yet.'))
        boosters.sort(key=lambda m: m.premium_since)
        desc = '\n'.join(f"**{i+1}.** {m.mention} — since <t:{int(m.premium_since.timestamp())}:R>"
                         for i, m in enumerate(boosters[:25]))
        embed = discord.Embed(title=f"💎 Server Boosters ({len(boosters)})", description=desc,
                              color=0xf47fff)
        await ctx.reply(embed=embed)

    # ─── FIRSTMESSAGE ───
    @commands.command(name='firstmessage', aliases=['fm'])
    async def firstmessage(self, ctx):
        """Get a link to the first message in this channel"""
        async for msg in ctx.channel.history(limit=1, oldest_first=True):
            embed = discord.Embed(description=f"[Jump to first message]({msg.jump_url})",
                                  color=config.COLORS['primary'])
            embed.set_footer(text=f"Sent by {msg.author} on {msg.created_at.strftime('%B %d, %Y')}")
            return await ctx.reply(embed=embed)

    # ─── ENLARGE EMOJI ───
    @commands.command(name='enlarge', aliases=['jumbo', 'bigemoji'])
    async def enlarge(self, ctx, emoji: str = None):
        """Enlarge a custom emoji to full size"""
        if not emoji:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}enlarge <emoji>`'))
        custom = re.match(r'<(a?):(\w+):(\d+)>', emoji)
        if not custom:
            return await ctx.reply(embed=error_embed('Error', 'Only custom emojis can be enlarged.'))
        animated = custom.group(1) == 'a'
        ext = 'gif' if animated else 'png'
        url = f"https://cdn.discordapp.com/emojis/{custom.group(3)}.{ext}?size=4096"
        embed = discord.Embed(title=f":{custom.group(2)}:", color=config.COLORS['primary'])
        embed.set_image(url=url)
        await ctx.reply(embed=embed)

    # ─── POLL ───
    @commands.command(name='poll')
    async def poll(self, ctx, *, question: str = None):
        """Create a reaction poll"""
        if not question:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}poll <question>`'))
        embed = discord.Embed(title="📊 Poll", description=question,
                              color=config.COLORS['primary'], timestamp=datetime.now(UTC))
        embed.set_footer(text=f"Asked by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        msg = await ctx.send(embed=embed)
        await msg.add_reaction('✅')
        await msg.add_reaction('❌')

    # ─── REMIND ───
    @commands.command(name='remind', aliases=['remindme', 'timer'])
    async def remind(self, ctx, duration: str = None, *, message: str = "Reminder!"):
        """Set a timed reminder (e.g. ,remind 30m Check oven)"""
        if not duration:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}remind <time> <message>`\nExamples: `30s`, `5m`, `2h`, `1d`'))
        # Parse duration
        units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        match = re.match(r'^(\d+)([smhd])$', duration.lower())
        if not match:
            return await ctx.reply(embed=error_embed('Invalid Time', 'Use format: `30s`, `5m`, `2h`, `1d`'))
        seconds = int(match.group(1)) * units[match.group(2)]
        if seconds > 604800:  # 7 days max
            return await ctx.reply(embed=error_embed('Too Long', 'Maximum reminder duration is 7 days.'))
        remind_at = int(time.time()) + seconds
        settings_db.add_reminder(ctx.author.id, ctx.channel.id, ctx.guild.id, message, remind_at)
        embed = discord.Embed(title="⏰ Reminder Set",
                              description=f"I'll remind you <t:{remind_at}:R>\n**Message:** {message}",
                              color=config.COLORS['success'])
        await ctx.reply(embed=embed)

    # ─── URBAN DICTIONARY ───
    @commands.command(name='urban', aliases=['define', 'ud'])
    async def urban(self, ctx, *, word: str = None):
        """Look up a word on Urban Dictionary"""
        if not word:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}urban <word>`'))
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.urbandictionary.com/v0/define?term={word}") as resp:
                if resp.status != 200:
                    return await ctx.reply(embed=error_embed('Error', 'Could not reach Urban Dictionary.'))
                data = await resp.json()
        if not data.get('list'):
            return await ctx.reply(embed=error_embed('Not Found', f'No definition found for **{word}**.'))
        entry = data['list'][0]
        definition = entry['definition'][:2000].replace('[', '').replace(']', '')
        example = entry.get('example', '').replace('[', '').replace(']', '')
        embed = discord.Embed(title=f"📖 {entry['word']}", url=entry.get('permalink', ''),
                              description=definition, color=0x1D2439)
        if example:
            embed.add_field(name="Example", value=example[:1000], inline=False)
        embed.set_footer(text=f"👍 {entry.get('thumbs_up', 0)} | 👎 {entry.get('thumbs_down', 0)}")
        await ctx.reply(embed=embed)

    # ─── WEATHER ───
    @commands.command(name='weather', aliases=['w'])
    async def weather(self, ctx, *, city: str = None):
        """Get weather info for a city"""
        if not city:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}weather <city>`'))
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://wttr.in/{city}?format=j1") as resp:
                if resp.status != 200:
                    return await ctx.reply(embed=error_embed('Error', f'Could not find weather for **{city}**.'))
                data = await resp.json()
        current = data['current_condition'][0]
        area = data['nearest_area'][0]
        location = f"{area['areaName'][0]['value']}, {area['country'][0]['value']}"
        embed = discord.Embed(title=f"🌤️ Weather — {location}", color=0x5dadec)
        embed.add_field(name="🌡️ Temperature", value=f"{current['temp_C']}°C / {current['temp_F']}°F", inline=True)
        embed.add_field(name="💧 Humidity", value=f"{current['humidity']}%", inline=True)
        embed.add_field(name="💨 Wind", value=f"{current['windspeedKmph']} km/h", inline=True)
        embed.add_field(name="☁️ Condition", value=current['weatherDesc'][0]['value'], inline=True)
        embed.add_field(name="👁️ Visibility", value=f"{current['visibility']} km", inline=True)
        embed.add_field(name="🌡️ Feels Like", value=f"{current['FeelsLikeC']}°C", inline=True)
        await ctx.reply(embed=embed)

    # ─── SERVERICON / SERVERBANNER ───
    @commands.command(name='servericon', aliases=['sicon'])
    async def servericon(self, ctx):
        """Display the server icon full-size"""
        if not ctx.guild.icon:
            return await ctx.reply(embed=error_embed('No Icon', 'This server has no icon.'))
        embed = discord.Embed(title=f"{ctx.guild.name}'s Icon", color=config.COLORS['primary'])
        embed.set_image(url=ctx.guild.icon.url + "?size=4096")
        await ctx.reply(embed=embed)

    @commands.command(name='serverbanner', aliases=['sbanner'])
    async def serverbanner(self, ctx):
        """Display the server banner"""
        if not ctx.guild.banner:
            return await ctx.reply(embed=error_embed('No Banner', 'This server has no banner.'))
        embed = discord.Embed(title=f"{ctx.guild.name}'s Banner", color=config.COLORS['primary'])
        embed.set_image(url=ctx.guild.banner.url + "?size=4096")
        await ctx.reply(embed=embed)

    # ─── CHANNELINFO ───
    @commands.command(name='channelinfo', aliases=['ci'])
    async def channelinfo(self, ctx, channel: discord.TextChannel = None):
        """Show details about a channel"""
        channel = channel or ctx.channel
        embed = discord.Embed(title=f"#{channel.name}", color=config.COLORS['primary'])
        embed.add_field(name="ID", value=channel.id, inline=True)
        embed.add_field(name="Category", value=channel.category.name if channel.category else "None", inline=True)
        embed.add_field(name="Position", value=channel.position, inline=True)
        embed.add_field(name="NSFW", value="Yes" if channel.is_nsfw() else "No", inline=True)
        embed.add_field(name="Slowmode", value=f"{channel.slowmode_delay}s" if channel.slowmode_delay else "Off", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(channel.created_at.timestamp())}:R>", inline=True)
        if channel.topic:
            embed.add_field(name="Topic", value=channel.topic[:200], inline=False)
        await ctx.reply(embed=embed)

    # ─── EMOJIINFO ───
    @commands.command(name='emojiinfo', aliases=['ei'])
    async def emojiinfo(self, ctx, emoji: str = None):
        """Show info about a custom emoji"""
        if not emoji:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}emojiinfo <emoji>`'))
        match = re.match(r'<(a?):(\w+):(\d+)>', emoji)
        if not match:
            return await ctx.reply(embed=error_embed('Error', 'Provide a custom emoji.'))
        animated = match.group(1) == 'a'
        name = match.group(2)
        eid = int(match.group(3))
        ext = 'gif' if animated else 'png'
        embed = discord.Embed(title=f":{name}:", color=config.COLORS['primary'])
        embed.add_field(name="ID", value=eid, inline=True)
        embed.add_field(name="Animated", value="Yes" if animated else "No", inline=True)
        embed.add_field(name="URL", value=f"[Link](https://cdn.discordapp.com/emojis/{eid}.{ext})", inline=True)
        embed.set_thumbnail(url=f"https://cdn.discordapp.com/emojis/{eid}.{ext}?size=256")
        await ctx.reply(embed=embed)

    # ─── SPOTIFY ───
    @commands.command(name='spotify', aliases=['sp'])
    async def spotify(self, ctx, member: discord.Member = None):
        """Show what someone is listening to on Spotify"""
        member = member or ctx.author
        spotify_act = None
        for act in member.activities:
            if isinstance(act, discord.Spotify):
                spotify_act = act
                break
        if not spotify_act:
            return await ctx.reply(embed=error_embed('Not Listening', f'{member.display_name} is not listening to Spotify.'))
        embed = discord.Embed(title=spotify_act.title, color=spotify_act.color)
        embed.set_author(name=f"{member.display_name} is listening to Spotify", icon_url=member.display_avatar.url)
        embed.add_field(name="Artist", value=', '.join(spotify_act.artists), inline=True)
        embed.add_field(name="Album", value=spotify_act.album, inline=True)
        dur = spotify_act.duration
        elapsed = datetime.now(UTC) - spotify_act.start
        embed.add_field(name="Duration", value=f"{int(elapsed.total_seconds()//60)}:{int(elapsed.total_seconds()%60):02d} / {int(dur.total_seconds()//60)}:{int(dur.total_seconds()%60):02d}", inline=True)
        if spotify_act.album_cover_url:
            embed.set_thumbnail(url=spotify_act.album_cover_url)
        embed.set_footer(text=f"Track ID: {spotify_act.track_id}")
        await ctx.reply(embed=embed)

    # ─── CLEARSNIPES ───
    @commands.command(name='clearsnipes', aliases=['cs'])
    @commands.has_permissions(manage_messages=True)
    async def clearsnipes(self, ctx):
        """Clear snipe cache for this channel"""
        utility = self.bot.get_cog('Utility')
        if utility:
            if hasattr(utility, 'snipe_cache'):
                utility.snipe_cache.pop(ctx.channel.id, None)
            if hasattr(utility, 'edit_snipe_cache'):
                utility.edit_snipe_cache.pop(ctx.channel.id, None)
        await ctx.reply(embed=success_embed('Cleared', 'Snipe cache cleared for this channel.'))

    # ─── ROLEALL / UNROLEALL ───
    @commands.command(name='roleall')
    @commands.has_permissions(manage_roles=True)
    async def roleall(self, ctx, role: discord.Role = None):
        """Give a role to all members"""
        if not role:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}roleall <@role>`'))
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(embed=error_embed('Error', 'That role is higher than my top role.'))
        msg = await ctx.reply(embed=info_embed('Working', f'Adding **{role.name}** to all members...'))
        count = 0
        for member in ctx.guild.members:
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Roleall by {ctx.author}")
                    count += 1
                except:
                    pass
        await msg.edit(embed=success_embed('Done', f'Added **{role.name}** to **{count}** members.'))

    @commands.command(name='unroleall')
    @commands.has_permissions(manage_roles=True)
    async def unroleall(self, ctx, role: discord.Role = None):
        """Remove a role from all members"""
        if not role:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}unroleall <@role>`'))
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(embed=error_embed('Error', 'That role is higher than my top role.'))
        msg = await ctx.reply(embed=info_embed('Working', f'Removing **{role.name}** from all members...'))
        count = 0
        for member in ctx.guild.members:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Unroleall by {ctx.author}")
                    count += 1
                except:
                    pass
        await msg.edit(embed=success_embed('Done', f'Removed **{role.name}** from **{count}** members.'))

    # ─── NUKE CHANNEL ───
    @commands.command(name='nuke')
    @commands.has_permissions(manage_channels=True)
    async def nuke(self, ctx):
        """Clone this channel and delete the original (Owner + AntiNuke Admins only)"""
        # Restrict to server owner, bot owner, or antinuke admins
        is_owner = (ctx.author.id == ctx.guild.owner_id or ctx.author.id in config.OWNER_IDS)
        is_an_admin = settings_db.is_antinuke_admin(ctx.guild.id, ctx.author.id) if not is_owner else False

        if not is_owner and not is_an_admin:
            return await ctx.reply(embed=error_embed('❌ Access Denied',
                'Only the **server owner** and **antinuke admins** can use the nuke command.\n\n'
                f'Ask the server owner to add you via `{config.PREFIX}antinuke admin add @you`'))

        confirm_embed = discord.Embed(title="⚠️ Nuke Channel?",
            description=f"This will **delete** {ctx.channel.mention} and create an identical copy.\nReact ✅ to confirm.",
            color=config.COLORS['error'])
        msg = await ctx.send(embed=confirm_embed)
        await msg.add_reaction('✅')
        def check(r, u):
            return u == ctx.author and str(r.emoji) == '✅' and r.message.id == msg.id
        try:
            await self.bot.wait_for('reaction_add', check=check, timeout=15)
        except asyncio.TimeoutError:
            return await msg.edit(embed=error_embed('Cancelled', 'Nuke cancelled.'))
        pos = ctx.channel.position
        new_channel = await ctx.channel.clone(reason=f"Nuked by {ctx.author}")
        await new_channel.edit(position=pos)
        await ctx.channel.delete(reason=f"Nuked by {ctx.author}")
        nuke_embed = discord.Embed(title="💣 Channel Nuked", description="This channel has been nuked!",
                                    color=config.COLORS['success'])
        nuke_embed.set_image(url="https://media1.tenor.com/m/XHTFM9vKi4AAAAAC/explosion.gif")
        await new_channel.send(embed=nuke_embed)

    # ─── TEMPBAN / SOFTBAN / HARDBAN / MASSBAN ───
    @commands.command(name='tempban')
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member = None, duration: str = None, *, reason="No reason"):
        """Temporarily ban a user (auto-unbans after duration)"""
        if not member or not duration:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}tempban <@user> <duration> [reason]`'))
        units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        match = re.match(r'^(\d+)([smhd])$', duration.lower())
        if not match:
            return await ctx.reply(embed=error_embed('Invalid Duration', 'Use `30m`, `2h`, `1d` etc.'))
        seconds = int(match.group(1)) * units[match.group(2)]
        await member.ban(reason=f"Tempban by {ctx.author}: {reason}")
        embed = success_embed('Temp Banned', f'{member.mention} banned for **{duration}**\nReason: {reason}')
        await ctx.reply(embed=embed)
        await asyncio.sleep(seconds)
        try:
            await ctx.guild.unban(member, reason="Tempban expired")
        except Exception:
            pass

    @commands.command(name='softban', aliases=['sb'])
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def softban(self, ctx, member: discord.Member = None, delete_days: int = 7, *, reason: str = "No reason provided"):
        """Softban a member — ban + immediate unban to purge their recent messages"""
        if not member:
            return await ctx.reply(embed=error_embed(
                'Invalid Usage',
                f'`{config.PREFIX}softban <@user> [delete_days] [reason]`\n\n'
                f'Bans then immediately unbans a user, wiping their recent messages.\n'
                f'`delete_days` defaults to **7** (max 7).'
            ))

        # Guard: self
        if member == ctx.author:
            return await ctx.reply(embed=error_embed('Cannot Softban', 'You cannot softban yourself.'))

        # Guard: bot target
        if member.bot:
            return await ctx.reply(embed=error_embed('Cannot Softban', 'You cannot softban a bot.'))

        # Role hierarchy — invoker
        if ctx.author.id != ctx.guild.owner_id and ctx.author.top_role <= member.top_role:
            return await ctx.reply(embed=error_embed(
                'Cannot Softban',
                f'You cannot softban **{member}** — their role is equal to or above yours.'
            ))

        # Role hierarchy — bot
        if ctx.guild.me.top_role <= member.top_role:
            return await ctx.reply(embed=error_embed(
                'Cannot Softban',
                f'I cannot softban **{member}** — their role is equal to or above mine.'
            ))

        # Clamp delete_days
        delete_days = max(0, min(delete_days, 7))

        # DM before the ban
        try:
            dm_embed = discord.Embed(
                title='🔨 You Were Softbanned',
                description=(
                    f'You were **softbanned** from **{ctx.guild.name}**.\n'
                    f'Your recent messages have been deleted. You may rejoin with a fresh invite.\n\n'
                    f'**Reason:** {reason}\n'
                    f'**Moderator:** {ctx.author}'
                ),
                color=config.COLORS['error']
            )
            await member.send(embed=dm_embed)
        except Exception:
            pass

        # Execute softban
        try:
            await member.ban(
                reason=f'Softban by {ctx.author} ({ctx.author.id}): {reason}',
                delete_message_days=delete_days
            )
            await ctx.guild.unban(member, reason='Softban — immediate unban')
        except discord.Forbidden:
            return await ctx.reply(embed=error_embed(
                'Permission Error',
                'I do not have permission to ban this member.'
            ))
        except Exception as e:
            return await ctx.reply(embed=error_embed('Softban Failed', f'An error occurred: {e}'))

        # Modlog
        try:
            from utils.modlog import send_to_modlog
            await send_to_modlog(ctx.guild, 'softban', user=member, moderator=ctx.author, reason=reason)
        except Exception:
            pass

        # Case log
        case_id = None
        try:
            from utils.mysql_logs import mysql_case_logs
            case_id = mysql_case_logs.log_case(
                guild_id=str(ctx.guild.id),
                case_type='softban',
                user_id=str(member.id),
                username=str(member),
                moderator_id=str(ctx.author.id),
                moderator_name=str(ctx.author),
                reason=reason,
                additional_data={'delete_days': delete_days}
            )
        except Exception:
            pass

        # Success embed
        embed = discord.Embed(title='🔨 Member Softbanned', color=config.COLORS['error'])
        embed.add_field(name='User', value=f'{member.mention} (`{member.id}`)', inline=True)
        embed.add_field(name='Moderator', value=ctx.author.mention, inline=True)
        embed.add_field(name='Messages Deleted', value=f'Last **{delete_days}** day(s)', inline=True)
        embed.add_field(name='Reason', value=reason, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        footer_text = f'Case #{case_id} • User may rejoin with an invite' if case_id else 'User may rejoin with an invite'
        embed.set_footer(text=footer_text, icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.command(name='hardban')
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def hardban(self, ctx, member: discord.Member = None, *, reason="No reason"):
        """Ban with 7-day message deletion"""
        if not member:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}hardban <@user> [reason]`'))
        await member.ban(reason=f"Hardban by {ctx.author}: {reason}", delete_message_days=7)
        await ctx.reply(embed=success_embed('Hard Banned', f'{member.mention} banned with 7-day message purge.\nReason: {reason}'))

    @commands.command(name='massban')
    @commands.has_permissions(ban_members=True)
    async def massban(self, ctx, *members: discord.Member):
        """Ban multiple users at once"""
        if not members:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}massban <@user1> <@user2> ...`'))
        banned = []
        for m in members:
            try:
                await m.ban(reason=f"Massban by {ctx.author}")
                banned.append(m.display_name)
            except Exception:
                pass
        await ctx.reply(embed=success_embed('Mass Banned', f'Banned **{len(banned)}** users: {", ".join(banned)}'))

    # ─── DELETE EMOJI ───
    @commands.command(name='deleteemoji', aliases=['delemoji', 'removeemoji'])
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def deleteemoji(self, ctx, emoji_input: str = None):
        """Delete a server emoji — pass it directly OR reply to a message containing it"""
        target_emoji = None

        # Priority 1: reply to a message containing a custom emoji
        if ctx.message.reference and not emoji_input:
            try:
                ref_msg = ctx.message.reference.resolved
                if isinstance(ref_msg, discord.Message):
                    matches = re.findall(r'<(a?):(\w+):(\d+)>', ref_msg.content)
                    for animated_flag, name, eid in matches:
                        found = discord.utils.get(ctx.guild.emojis, id=int(eid))
                        if found:
                            target_emoji = found
                            break
                    if not target_emoji:
                        return await ctx.reply(embed=error_embed(
                            'No Server Emoji Found',
                            'The replied message does not contain any emoji from this server.'
                        ))
            except Exception as e:
                return await ctx.reply(embed=error_embed('Error', f'Could not read the replied message: {e}'))

        # Priority 2: emoji passed as argument
        elif emoji_input:
            match = re.match(r'<(a?):(\w+):(\d+)>', emoji_input)
            if match:
                eid = int(match.group(3))
                target_emoji = discord.utils.get(ctx.guild.emojis, id=eid)
                if not target_emoji:
                    return await ctx.reply(embed=error_embed(
                        'Not a Server Emoji',
                        f'That emoji does not belong to **{ctx.guild.name}**.'
                    ))
            else:
                name_clean = emoji_input.strip(':').lower()
                target_emoji = discord.utils.get(ctx.guild.emojis, name=name_clean)
                if not target_emoji:
                    return await ctx.reply(embed=error_embed(
                        'Emoji Not Found',
                        f'Could not find a server emoji matching `{emoji_input}`.\n'
                        f'Usage: `{config.PREFIX}deleteemoji <emoji>` or reply to a message with the emoji.'
                    ))
        else:
            return await ctx.reply(embed=error_embed(
                'Invalid Usage',
                f'`{config.PREFIX}deleteemoji <emoji>` — or reply to a message containing the emoji.\n\n'
                f'**Examples:**\n'
                f'• `{config.PREFIX}deleteemoji :coolname:` (by name)\n'
                f'• `{config.PREFIX}deleteemoji <:coolname:123456>` (mention)\n'
                f'• Reply to any message → `{config.PREFIX}deleteemoji`'
            ))

        # Confirm
        animated_tag = '(animated) ' if target_emoji.animated else ''
        confirm_embed = discord.Embed(
            title='🗑️ Delete Emoji?',
            description=(
                f'Are you sure you want to permanently delete {animated_tag}`:{target_emoji.name}:`?\n\n'
                f'React ✅ to confirm or ❌ to cancel.'
            ),
            color=config.COLORS['error']
        )
        confirm_embed.set_thumbnail(url=target_emoji.url)
        msg = await ctx.reply(embed=confirm_embed)
        await msg.add_reaction('✅')
        await msg.add_reaction('❌')

        def check(r, u):
            return u == ctx.author and r.message.id == msg.id and str(r.emoji) in ('✅', '❌')

        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=20, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=error_embed('Timed Out', 'Emoji deletion cancelled.'))

        if str(reaction.emoji) == '❌':
            return await msg.edit(embed=error_embed('Cancelled', 'Emoji deletion cancelled.'))

        try:
            name_snapshot = target_emoji.name
            await target_emoji.delete(reason=f'Deleted by {ctx.author} via deleteemoji')
            done = discord.Embed(
                title='✅ Emoji Deleted',
                description=f'`:{name_snapshot}:` has been permanently deleted.',
                color=config.COLORS['success']
            )
            done.set_footer(text=f'Deleted by {ctx.author}', icon_url=ctx.author.display_avatar.url)
            await msg.edit(embed=done)
        except discord.Forbidden:
            await msg.edit(embed=error_embed('Permission Error', 'I do not have permission to delete emojis.'))
        except Exception as e:
            await msg.edit(embed=error_embed('Delete Failed', f'Could not delete emoji: {e}'))

    # ─── STRIPSTAFF ───
    @commands.command(name='stripstaff')
    @commands.has_permissions(administrator=True)
    async def stripstaff(self, ctx, member: discord.Member = None):
        """Remove all staff/admin roles from a user"""
        if not member:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}stripstaff <@user>`'))
        staff_roles = [r for r in member.roles if r != ctx.guild.default_role and
                       (r.permissions.administrator or r.permissions.manage_guild or
                        r.permissions.manage_channels or r.permissions.manage_roles or
                        r.permissions.ban_members or r.permissions.kick_members)]
        if not staff_roles:
            return await ctx.reply(embed=error_embed('No Staff Roles', f'{member.mention} has no staff roles.'))
        removed = []
        for role in staff_roles:
            try:
                await member.remove_roles(role, reason=f"Stripped by {ctx.author}")
                removed.append(role.name)
            except:
                pass
        await ctx.reply(embed=success_embed('Stripped', f'Removed **{len(removed)}** staff roles from {member.mention}:\n{", ".join(removed)}'))

    # ─── BOTCLEAN ───
    @commands.command(name='botclean', aliases=['bc', 'cleanup'])
    @commands.has_permissions(manage_messages=True)
    async def botclean(self, ctx, amount: int = 50):
        """Purge all bot messages in this channel"""
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author.bot)
        msg = await ctx.send(embed=success_embed('Bot Clean', f'Deleted **{len(deleted)}** bot messages.'))
        await msg.delete(delay=2)

    # ─── ROLEICON ───
    @commands.command(name='roleicon')
    @commands.has_permissions(manage_roles=True)
    async def roleicon(self, ctx, role: discord.Role = None, *, emoji: str = None):
        """Set a role's icon to an emoji"""
        if not role or not emoji:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}roleicon <@role> <emoji>`'))
        if 'ROLE_ICONS' not in ctx.guild.features:
            return await ctx.reply(embed=error_embed('Error', 'Server needs boost level 2+ for role icons.'))
        match = re.match(r'<a?:\w+:(\d+)>', emoji)
        if match:
            emoji_id = int(match.group(1))
            emoji_obj = self.bot.get_emoji(emoji_id)
            if emoji_obj:
                await role.edit(display_icon=await emoji_obj.read())
                return await ctx.reply(embed=success_embed('Done', f'Set icon for **{role.name}**.'))
        await ctx.reply(embed=error_embed('Error', 'Could not set role icon. Use a custom emoji from this server.'))

    # ─── ALIAS SYSTEM ───
    @commands.group(name='alias', invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def alias(self, ctx):
        """Manage command aliases"""
        aliases = settings_db.get_all_aliases(ctx.guild.id)
        if not aliases:
            return await ctx.reply(embed=info_embed('No Aliases', f'Use `{config.PREFIX}alias add <name> <command>` to create one.'))
        desc = '\n'.join(f"`{a['alias_name']}` → `{a['command_string']}`" for a in aliases)
        await ctx.reply(embed=info_embed(f'Aliases ({len(aliases)})', desc))

    @alias.command(name='add')
    @commands.has_permissions(manage_guild=True)
    async def alias_add(self, ctx, name: str = None, *, command: str = None):
        """Create a command alias"""
        if not name or not command:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}alias add <name> <command>`'))
        prefix = getattr(ctx, "prefix", None) or config.PREFIX
        name = name.strip().lower()
        if name.startswith(prefix):
            name = name[len(prefix):].strip().lower()
        elif config.PREFIX and name.startswith(config.PREFIX):
            name = name[len(config.PREFIX):].strip().lower()
        command = command.strip()
        if command.startswith(prefix):
            command = command[len(prefix):].strip()
        elif config.PREFIX and command.startswith(config.PREFIX):
            command = command[len(config.PREFIX):].strip()

        if not name or any(ch.isspace() for ch in name):
            return await ctx.reply(embed=error_embed('Invalid Alias', 'Alias names must be one word.'))
        if self.bot.get_command(name):
            return await ctx.reply(embed=error_embed('Command Exists', f'`{name}` is already a command or built-in alias.'))

        target_name = command.split(maxsplit=1)[0].lower() if command else ''
        if not target_name:
            return await ctx.reply(embed=error_embed('Invalid Command', 'Tell me what command this alias should run.'))
        if target_name == name:
            return await ctx.reply(embed=error_embed('Recursive Alias', 'An alias cannot point to itself.'))
        if not self.bot.get_command(target_name):
            return await ctx.reply(embed=error_embed('Unknown Command', f'`{target_name}` is not a loaded prefix command.'))

        settings_db.add_alias(ctx.guild.id, name, command, ctx.author.id)
        await ctx.reply(embed=success_embed('Alias Created', f'`{name}` → `{command}`'))

    @alias.command(name='remove', aliases=['delete'])
    @commands.has_permissions(manage_guild=True)
    async def alias_remove(self, ctx, name: str = None):
        """Remove a command alias"""
        if not name:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}alias remove <name>`'))
        if settings_db.remove_alias(ctx.guild.id, name):
            await ctx.reply(embed=success_embed('Removed', f'Alias `{name}` deleted.'))
        else:
            await ctx.reply(embed=error_embed('Not Found', f'No alias named `{name}`.'))

    # ─── GOODBYE / BOOST MESSAGES ───
    @commands.group(name='goodbye', invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def goodbye(self, ctx):
        """Manage goodbye messages"""
        msgs = settings_db.get_system_messages(ctx.guild.id, 'goodbye')
        if not msgs:
            return await ctx.reply(embed=info_embed('No Goodbye Messages', f'Use `{config.PREFIX}goodbye add <#channel> <message>`'))
        desc = '\n'.join(f"<#{m['channel_id']}> — {m['message_template'][:50]}" for m in msgs)
        await ctx.reply(embed=info_embed('Goodbye Messages', desc))

    @goodbye.command(name='add')
    @commands.has_permissions(manage_guild=True)
    async def goodbye_add(self, ctx, channel: discord.TextChannel = None, *, message: str = None):
        """Add a goodbye message (use {user} {server} {count})"""
        if not channel or not message:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}goodbye add <#channel> <message>`'))
        settings_db.add_system_message(ctx.guild.id, 'goodbye', channel.id, message)
        await ctx.reply(embed=success_embed('Goodbye Added', f'Goodbye messages will be sent to {channel.mention}'))

    @goodbye.command(name='remove')
    @commands.has_permissions(manage_guild=True)
    async def goodbye_remove(self, ctx, channel: discord.TextChannel = None):
        """Remove goodbye message for a channel"""
        if not channel:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}goodbye remove <#channel>`'))
        settings_db.remove_system_message(ctx.guild.id, 'goodbye', channel.id)
        await ctx.reply(embed=success_embed('Removed', f'Goodbye messages removed from {channel.mention}'))

    @commands.group(name='legacy_boost', invoke_without_command=True, hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def boost_msg(self, ctx):
        """Manage boost celebration messages"""
        msgs = settings_db.get_system_messages(ctx.guild.id, 'boost')
        if not msgs:
            return await ctx.reply(embed=info_embed('No Boost Messages', f'Use `{config.PREFIX}boost add <#channel> <message>`'))
        desc = '\n'.join(f"<#{m['channel_id']}> — {m['message_template'][:50]}" for m in msgs)
        await ctx.reply(embed=info_embed('Boost Messages', desc))

    @boost_msg.command(name='add')
    @commands.has_permissions(manage_guild=True)
    async def boost_add(self, ctx, channel: discord.TextChannel = None, *, message: str = None):
        """Add a boost celebration message"""
        if not channel or not message:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}boost add <#channel> <message>`'))
        settings_db.add_system_message(ctx.guild.id, 'boost', channel.id, message)
        await ctx.reply(embed=success_embed('Boost Message Added', f'Boost messages will be sent to {channel.mention}'))

    @boost_msg.command(name='remove')
    @commands.has_permissions(manage_guild=True)
    async def boost_remove(self, ctx, channel: discord.TextChannel = None):
        """Remove boost message for a channel"""
        if not channel:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}boost remove <#channel>`'))
        settings_db.remove_system_message(ctx.guild.id, 'boost', channel.id)
        await ctx.reply(embed=success_embed('Removed', f'Boost messages removed from {channel.mention}'))

    # ─── LISTENERS: Goodbye/Boost/Autoreact/JoinDM ───
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Send goodbye messages."""
        msgs = settings_db.get_system_messages(member.guild.id, 'goodbye')
        for m in msgs:
            try:
                ch = member.guild.get_channel(int(m['channel_id']))
                if ch:
                    text = m['message_template'].replace('{user}', member.display_name)
                    text = text.replace('{server}', member.guild.name)
                    text = text.replace('{count}', str(member.guild.member_count))
                    await ch.send(text)
            except:
                pass

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Send boost messages."""
        if False and before.premium_since is None and after.premium_since is not None:
            msgs = settings_db.get_system_messages(after.guild.id, 'boost')
            for m in msgs:
                try:
                    ch = after.guild.get_channel(int(m['channel_id']))
                    if ch:
                        text = m['message_template'].replace('{user}', after.mention)
                        text = text.replace('{server}', after.guild.name)
                        await ch.send(text)
                except:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle auto-react."""
        if message.author.bot or not message.guild:
            return
        # Auto-react
        emojis = settings_db.get_autoreacts(message.guild.id, message.channel.id)
        for emoji in emojis:
            try:
                await message.add_reaction(emoji)
            except:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Send join DM if configured."""
        joindm = settings_db.get_joindm(member.guild.id)
        if joindm:
            try:
                text = joindm['message_template'].replace('{user}', member.display_name)
                text = text.replace('{server}', member.guild.name)
                await member.send(text)
            except:
                pass


async def setup(bot):
    await bot.add_cog(BleedCommands(bot))
