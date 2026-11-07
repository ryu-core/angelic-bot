import discord
from discord.ext import commands
import config

def is_owner():
    """Check if user is bot owner — sends a visible error if not."""
    async def predicate(ctx):
        # Primary check: OWNER_IDS from config / .env
        if ctx.author.id in config.OWNER_IDS:
            return True
        # Fallback: Discord's built-in application owner check
        # (catches the case where OWNER_IDS is empty/misconfigured)
        try:
            app_info = await ctx.bot.application_info()
            if app_info.team:
                if ctx.author.id in [m.id for m in app_info.team.members]:
                    return True
            elif ctx.author.id == app_info.owner.id:
                return True
        except Exception:
            pass
        embed = discord.Embed(
            title='🔒 Bot Owner Only',
            description='This command is restricted to **bot owners** only.',
            color=config.COLORS['error']
        )
        embed.set_footer(text=f'Your ID: {ctx.author.id}')
        await ctx.reply(embed=embed)
        return False
    return commands.check(predicate)

def is_moderator():
    """Check if user has moderator permissions"""
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        return (
            ctx.author.guild_permissions.ban_members or
            ctx.author.guild_permissions.kick_members or
            ctx.author.guild_permissions.moderate_members or
            ctx.author.guild_permissions.manage_messages
        )
    return commands.check(predicate)

def can_moderate_target(executor, target):
    """Check if executor can moderate target"""
    # Owners can moderate anyone
    if executor.id in config.OWNER_IDS:
        return True
    
    # Can't moderate yourself
    if executor.id == target.id:
        return False
    
    # Can't moderate server owner
    if target.id == target.guild.owner_id:
        return False
    
    # Check role hierarchy
    return executor.top_role > target.top_role
