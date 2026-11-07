import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import config
from utils.embeds import success_embed, error_embed, info_embed

class BumpReminder(commands.Cog):
    """Bump reminder system for Disboard"""
    
    def __init__(self, bot):
        self.bot = bot
        self.bump_data = {}  # {guild_id: {'channel_id': int, 'last_bump': timestamp, 'reminder_role': role_id}}
        self.check_reminders.start()
    
    def cog_unload(self):
        self.check_reminders.cancel()
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Detect successful Disboard bumps"""
        # Disboard bot ID
        if message.author.id != 302050872383242240:
            return
        
        # Check if it's a successful bump message
        if not message.embeds:
            return
        
        embed = message.embeds[0]
        if not embed.description:
            return
        
        # Detect bump success message
        if "Bump done!" in embed.description or "表示順をアップしたよ" in embed.description:
            guild_id = str(message.guild.id)
            
            # Store bump data
            if guild_id not in self.bump_data:
                self.bump_data[guild_id] = {}
            
            self.bump_data[guild_id]['channel_id'] = message.channel.id
            self.bump_data[guild_id]['last_bump'] = datetime.now()
            
            # Get the user who bumped (from embed description)
            try:
                # Extract user mention from embed
                user_mention = embed.description.split(',')[0]
                await message.channel.send(
                    embed=success_embed(
                        '✅ Bump Successful!',
                        f'{user_mention} thanks for bumping! I\'ll remind you in **2 hours**. ⏰'
                    ),
                    delete_after=10
                )
            except:
                pass
    
    @tasks.loop(minutes=1)
    async def check_reminders(self):
        """Check if it's time to send bump reminders"""
        now = datetime.now()
        
        for guild_id, data in list(self.bump_data.items()):
            if 'last_bump' not in data:
                continue
            
            last_bump = data['last_bump']
            time_since_bump = now - last_bump
            
            # Check if 2 hours have passed
            if time_since_bump >= timedelta(hours=2):
                try:
                    guild = self.bot.get_guild(int(guild_id))
                    if not guild:
                        continue
                    
                    channel = guild.get_channel(data['channel_id'])
                    if not channel:
                        continue
                    
                    # Create reminder embed
                    reminder_msg = f"{config.EMOJIS.get('info', 'ℹ️')} **Bump Reminder!**\n\n"
                    reminder_msg += "It's been 2 hours since the last bump!\n"
                    reminder_msg += "Use `/bump` to bump the server! 🚀"
                    
                    embed = discord.Embed(
                        description=reminder_msg,
                        color=config.COLORS.get('primary', 0x2ecc71)
                    )
                    embed.set_footer(text="Bump to get your server to the top!")
                    
                    # Mention role if set (must be in message content, not embed, to ping)
                    content = None
                    allowed_mentions = discord.AllowedMentions(roles=True)
                    
                    if 'reminder_role' in data and data['reminder_role']:
                        role = guild.get_role(data['reminder_role'])
                        if role:
                            content = role.mention
                    
                    await channel.send(content=content, embed=embed, allowed_mentions=allowed_mentions)
                    
                    # Remove from tracking until next bump
                    del self.bump_data[guild_id]['last_bump']
                
                except Exception as e:
                    print(f"Error sending bump reminder: {e}")
    
    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()
    
    @commands.group(name='bumpreminder', aliases=['bumpr'], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def bumpreminder(self, ctx):
        """Bump reminder management"""
        await ctx.send(embed=info_embed(
            'Bump Reminder System',
            f'**Available Commands:**\n'
            f'`{config.PREFIX}bumpreminder role <@role>` - Set role to ping for reminders\n'
            f'`{config.PREFIX}bumpreminder remove` - Remove ping role\n'
            f'`{config.PREFIX}bumpreminder status` - View current settings\n\n'
            f'**How it works:**\n'
            f'I automatically detect when someone bumps with `/bump` and remind you after 2 hours!'
        ))
    
    @bumpreminder.command(name='role')
    @commands.has_permissions(administrator=True)
    async def set_role(self, ctx, role: discord.Role):
        """Set role to ping for bump reminders"""
        guild_id = str(ctx.guild.id)
        
        if guild_id not in self.bump_data:
            self.bump_data[guild_id] = {}
        
        self.bump_data[guild_id]['reminder_role'] = role.id
        
        await ctx.send(embed=success_embed(
            'Bump Reminder Role Set',
            f'{config.EMOJIS.get("success", "✅")} {role.mention} will be pinged for bump reminders!'
        ))
    
    @bumpreminder.command(name='remove')
    @commands.has_permissions(administrator=True)
    async def remove_role(self, ctx):
        """Remove bump reminder role"""
        guild_id = str(ctx.guild.id)
        
        if guild_id in self.bump_data and 'reminder_role' in self.bump_data[guild_id]:
            del self.bump_data[guild_id]['reminder_role']
            await ctx.send(embed=success_embed(
                'Role Removed',
                f'{config.EMOJIS.get("success", "✅")} Bump reminders will no longer ping a role.'
            ))
        else:
            await ctx.send(embed=error_embed(
                'No Role Set',
                'There is no bump reminder role configured.'
            ))
    
    @bumpreminder.command(name='status')
    async def status(self, ctx):
        """View bump reminder status"""
        guild_id = str(ctx.guild.id)
        
        if guild_id not in self.bump_data:
            return await ctx.send(embed=info_embed(
                'Bump Reminder Status',
                'No bump data yet. Use `/bump` to get started!'
            ))
        
        data = self.bump_data[guild_id]
        
        embed = discord.Embed(
            title=f"{config.EMOJIS.get('settings', '⚙️')} Bump Reminder Status",
            color=config.COLORS.get('primary', 0x2ecc71)
        )
        
        # Last bump time
        if 'last_bump' in data:
            last_bump = data['last_bump']
            time_since = datetime.now() - last_bump
            hours = int(time_since.total_seconds() // 3600)
            minutes = int((time_since.total_seconds() % 3600) // 60)
            
            time_until_reminder = timedelta(hours=2) - time_since
            if time_until_reminder.total_seconds() > 0:
                reminder_hours = int(time_until_reminder.total_seconds() // 3600)
                reminder_minutes = int((time_until_reminder.total_seconds() % 3600) // 60)
                embed.add_field(
                    name='Last Bump',
                    value=f'{hours}h {minutes}m ago\n**Next reminder in:** {reminder_hours}h {reminder_minutes}m',
                    inline=False
                )
            else:
                embed.add_field(
                    name='Last Bump',
                    value=f'{hours}h {minutes}m ago\n**Ready to bump!**',
                    inline=False
                )
        else:
            embed.add_field(
                name='Last Bump',
                value='No recent bump detected',
                inline=False
            )
        
        # Reminder role
        if 'reminder_role' in data and data['reminder_role']:
            role = ctx.guild.get_role(data['reminder_role'])
            if role:
                embed.add_field(
                    name='Reminder Role',
                    value=role.mention,
                    inline=False
                )
        else:
            embed.add_field(
                name='Reminder Role',
                value='Not set',
                inline=False
            )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(BumpReminder(bot))
