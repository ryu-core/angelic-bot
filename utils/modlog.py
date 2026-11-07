"""
Modlog utility for sending moderation action logs to configured channel
"""
import discord
from utils.database import config_db
import config

async def send_to_modlog(guild: discord.Guild, action_type: str, **kwargs):
    """
    Send a moderation action to the configured modlog channel
    
    Args:
        guild: The Discord guild
        action_type: Type of action ('ban', 'kick', 'mute', 'jail', 'warn', 'clear')
        **kwargs: Action-specific data (user, moderator, reason, duration, etc.)
    """
    try:
        guild_id = str(guild.id)
        
        # Get modlog channel
        guild_config = config_db.get(guild_id, {})
        if 'modlog_channel' not in guild_config:
            return  # No modlog configured
        
        modlog_channel = guild.get_channel(int(guild_config['modlog_channel']))
        if not modlog_channel:
            return  # Channel not found
        
        # Create embed based on action type
        embed = None
        
        if action_type == 'ban':
            embed = discord.Embed(
                title='🔨 Member Banned',
                color=config.COLORS['error'],
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name='User', value=f"{kwargs['user'].mention} (`{kwargs['user'].id}`)", inline=False)
            embed.add_field(name='Moderator', value=kwargs['moderator'].mention, inline=True)
            embed.add_field(name='Reason', value=kwargs.get('reason', 'No reason provided'), inline=False)
            if 'delete_days' in kwargs and kwargs['delete_days'] > 0:
                embed.add_field(name='Messages Deleted', value=f"{kwargs['delete_days']} day(s)", inline=True)
            embed.set_thumbnail(url=kwargs['user'].display_avatar.url)
            
        elif action_type == 'kick':
            embed = discord.Embed(
                title='👢 Member Kicked',
                color=config.COLORS['warning'],
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name='User', value=f"{kwargs['user'].mention} (`{kwargs['user'].id}`)", inline=False)
            embed.add_field(name='Moderator', value=kwargs['moderator'].mention, inline=True)
            embed.add_field(name='Reason', value=kwargs.get('reason', 'No reason provided'), inline=False)
            embed.set_thumbnail(url=kwargs['user'].display_avatar.url)
            
        elif action_type == 'mute':
            embed = discord.Embed(
                title='🔇 Member Muted',
                color=config.COLORS['warning'],
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name='User', value=f"{kwargs['user'].mention} (`{kwargs['user'].id}`)", inline=False)
            embed.add_field(name='Moderator', value=kwargs['moderator'].mention, inline=True)
            embed.add_field(name='Duration', value=kwargs.get('duration', 'Unknown'), inline=True)
            embed.add_field(name='Reason', value=kwargs.get('reason', 'No reason provided'), inline=False)
            embed.set_thumbnail(url=kwargs['user'].display_avatar.url)
            
        elif action_type == 'jail':
            embed = discord.Embed(
                title='⛓️ Member Jailed',
                color=config.COLORS['error'],
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name='User', value=f"{kwargs['user'].mention} (`{kwargs['user'].id}`)", inline=False)
            embed.add_field(name='Moderator', value=kwargs['moderator'].mention, inline=True)
            embed.add_field(name='Duration', value=kwargs.get('duration', 'Permanent'), inline=True)
            embed.add_field(name='Reason', value=kwargs.get('reason', 'No reason provided'), inline=False)
            embed.set_thumbnail(url=kwargs['user'].display_avatar.url)
            
        elif action_type == 'warn':
            embed = discord.Embed(
                title='⚠️ Member Warned',
                color=config.COLORS['warning'],
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name='User', value=f"{kwargs['user'].mention} (`{kwargs['user'].id}`)", inline=False)
            embed.add_field(name='Moderator', value=kwargs['moderator'].mention, inline=True)
            embed.add_field(name='Warning Count', value=str(kwargs.get('warning_count', 1)), inline=True)
            embed.add_field(name='Reason', value=kwargs.get('reason', 'No reason provided'), inline=False)
            embed.set_thumbnail(url=kwargs['user'].display_avatar.url)
            
        elif action_type == 'clear':
            embed = discord.Embed(
                title='🗑️ Messages Cleared',
                color=config.COLORS['warning'],
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name='Channel', value=kwargs['channel'].mention, inline=True)
            embed.add_field(name='Amount', value=f"{kwargs['amount']} messages", inline=True)
            embed.add_field(name='Moderator', value=kwargs['moderator'].mention, inline=False)
        
        if embed:
            await modlog_channel.send(embed=embed)
            print(f"✅ Modlog: {action_type} logged in {guild.name}")
            
    except Exception as e:
        print(f"❌ Modlog error: {e}")
