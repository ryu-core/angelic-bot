"""
Booster Check Decorator
Restricts commands to server boosters only
"""
import discord
from discord.ext import commands
from functools import wraps
import config

# Your main server where users can boost to unlock commands globally
BOOSTER_SERVER_ID = 1466494845118976186
BOOSTER_SERVER_INVITE = "https://discord.gg/89Q9Sa6ZSQ"

def booster_required():
    """
    Decorator to restrict command to server boosters only.
    Users must boost either:
    1. The current server, OR
    2. The main booster server (ID: 1466494845118976186)
    """
    def predicate(ctx):
        # Owners and co-owners bypass booster check
        if ctx.author.id in config.OWNER_IDS or ctx.author.id in config.CO_OWNER_IDS:
            return True
        
        # Only check if user is boosting the main booster server
        booster_guild = ctx.bot.get_guild(BOOSTER_SERVER_ID)
        if booster_guild:
            booster_member = booster_guild.get_member(ctx.author.id)
            if booster_member and booster_member.premium_since:
                return True
        
        return False
    
    async def extended_check(ctx):
        if not predicate(ctx):
            # Create embed explaining booster requirement
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Booster Only Command",
                description=(
                    f"{config.EMOJIS.get('crown', '')} **This command is exclusive to Server Boosters!**\n\n"
                    "To unlock this command, you must:\n"
                    f"{config.EMOJIS.get('info', '')} Boost our **main server** to unlock in ALL servers\n\n"
                    f"[{config.EMOJIS.get('gem', '')} Join & Boost Our Main Server]({BOOSTER_SERVER_INVITE})\n\n"
                    "*Boosting supports the bot and unlocks premium features globally!*"
                ),
                color=config.COLORS['error']
            )
            embed.set_footer(text="Thank you for supporting xiel!")
            await ctx.reply(embed=embed)
            return False
        return True
    
    return commands.check(extended_check)
