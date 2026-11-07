import discord
from discord.ext import commands
from datetime import datetime
import config
from utils.embeds import success_embed, info_embed

class AFK(commands.Cog):
    """AFK system for users"""
    
    def __init__(self, bot):
        self.bot = bot
        self.afk_users = {}  # {user_id: {'reason': str, 'time': datetime, 'guild_id': int}}
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Check for AFK users and mentions"""
        if message.author.bot:
            return
        
        # Ignore command messages (don't remove AFK when using ,afk command)
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        
        user_id = str(message.author.id)
        
        # Check if user is AFK and just sent a message (return from AFK)
        if user_id in self.afk_users:
            afk_data = self.afk_users[user_id]
            time_afk = datetime.now() - afk_data['time']
            
            # Calculate time
            hours = int(time_afk.total_seconds() // 3600)
            minutes = int((time_afk.total_seconds() % 3600) // 60)
            
            time_str = ""
            if hours > 0:
                time_str = f"{hours}h {minutes}m"
            else:
                time_str = f"{minutes}m"
            
            # Remove AFK status
            del self.afk_users[user_id]
            
            # Send welcome back message
            try:
                await message.channel.send(
                    embed=info_embed(
                        'Welcome Back!',
                        f'{message.author.mention} is no longer AFK (was away for {time_str})'
                    ),
                    delete_after=5
                )
            except:
                pass
            
            return
        
        # Check if anyone mentioned is AFK
        if message.mentions:
            for mentioned_user in message.mentions:
                mentioned_id = str(mentioned_user.id)
                
                if mentioned_id in self.afk_users:
                    afk_data = self.afk_users[mentioned_id]
                    time_afk = datetime.now() - afk_data['time']
                    
                    # Calculate time
                    hours = int(time_afk.total_seconds() // 3600)
                    minutes = int((time_afk.total_seconds() % 3600) // 60)
                    
                    time_str = ""
                    if hours > 0:
                        time_str = f"{hours}h {minutes}m ago"
                    else:
                        time_str = f"{minutes}m ago"
                    
                    # Send AFK notification
                    reason = afk_data['reason'] if afk_data['reason'] else "No reason provided"
                    
                    embed = discord.Embed(
                        description=f"{config.EMOJIS.get('sleep', '💤')} **{mentioned_user.display_name}** is currently AFK\n\n"
                                  f"**Reason:** {reason}\n"
                                  f"**Since:** {time_str}",
                        color=config.COLORS.get('warning', 0xffa500)
                    )
                    
                    try:
                        await message.channel.send(embed=embed, delete_after=10)
                    except:
                        pass
    
    @commands.command(name='afk')
    async def afk(self, ctx, *, reason: str = None):
        """Set your AFK status"""
        user_id = str(ctx.author.id)
        
        # Set AFK
        self.afk_users[user_id] = {
            'reason': reason,
            'time': datetime.now(),
            'guild_id': ctx.guild.id
        }
        
        # Create response
        if reason:
            description = f"{config.EMOJIS.get('sleep', '💤')} {ctx.author.mention} is now AFK\n\n**Reason:** {reason}"
        else:
            description = f"{config.EMOJIS.get('sleep', '💤')} {ctx.author.mention} is now AFK"
        
        embed = discord.Embed(
            description=description,
            color=config.COLORS.get('primary', 0x2ecc71)
        )
        embed.set_footer(text="Send a message to remove your AFK status")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='afklist', aliases=['afks'])
    async def afk_list(self, ctx):
        """View all AFK users in this server"""
        guild_afk_users = []
        
        for user_id, data in self.afk_users.items():
            if data['guild_id'] == ctx.guild.id:
                user = ctx.guild.get_member(int(user_id))
                if user:
                    time_afk = datetime.now() - data['time']
                    hours = int(time_afk.total_seconds() // 3600)
                    minutes = int((time_afk.total_seconds() % 3600) // 60)
                    
                    time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                    reason = data['reason'] if data['reason'] else "No reason"
                    
                    guild_afk_users.append(f"**{user.display_name}** - {reason} ({time_str})")
        
        if not guild_afk_users:
            return await ctx.send(embed=info_embed(
                'AFK Users',
                'No users are currently AFK in this server.'
            ))
        
        embed = discord.Embed(
            title=f"{config.EMOJIS.get('sleep', '💤')} AFK Users",
            description='\n'.join(guild_afk_users[:10]),  # Limit to 10 users
            color=config.COLORS.get('primary', 0x2ecc71)
        )
        
        if len(guild_afk_users) > 10:
            embed.set_footer(text=f"Showing 10 of {len(guild_afk_users)} AFK users")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='unafk', aliases=['back'])
    async def unafk(self, ctx):
        """Manually remove your AFK status"""
        user_id = str(ctx.author.id)
        
        if user_id not in self.afk_users:
            return await ctx.send(embed=info_embed(
                'Not AFK',
                'You are not currently AFK.'
            ), delete_after=5)
        
        afk_data = self.afk_users[user_id]
        time_afk = datetime.now() - afk_data['time']
        
        hours = int(time_afk.total_seconds() // 3600)
        minutes = int((time_afk.total_seconds() % 3600) // 60)
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        
        del self.afk_users[user_id]
        
        await ctx.send(embed=success_embed(
            'Welcome Back!',
            f'{ctx.author.mention} is no longer AFK (was away for {time_str})'
        ), delete_after=5)

async def setup(bot):
    await bot.add_cog(AFK(bot))
