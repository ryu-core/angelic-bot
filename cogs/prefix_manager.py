"""
Prefix Manager Cog
Allows server owners to set custom prefixes
"""
import discord
from discord.ext import commands
import config
import sys
import os

# Add database directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'database'))
from models import Database, ServerPrefix


class PrefixManager(commands.Cog):
    """Custom prefix management"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.db.create_tables()
    
    # Set category for help command
    @property
    def qualified_name(self):
        return "Customization"
    
    @commands.command(name='setprefix')
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setprefix(self, ctx, new_prefix: str = None):
        """⚙️ Set a custom prefix for this server
        
        Usage: ,setprefix <new_prefix>
        Example: ,setprefix !
        
        **Note:** Once set, the default prefix (,) will stop working.
        Only the custom prefix will work in this server.
        """
        if not new_prefix:
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Missing Prefix",
                description=f"Please provide a new prefix!\n\n**Usage:** `{config.PREFIX}setprefix <new_prefix>`\n**Example:** `{config.PREFIX}setprefix !`",
                color=config.COLORS['error']
            )
            return await ctx.reply(embed=embed)
        
        # Validate prefix
        if len(new_prefix) > 10:
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Prefix Too Long",
                description="Prefix must be 10 characters or less!",
                color=config.COLORS['error']
            )
            return await ctx.reply(embed=embed)
        
        if new_prefix.strip() == '':
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Invalid Prefix",
                description="Prefix cannot be empty or just spaces!",
                color=config.COLORS['error']
            )
            return await ctx.reply(embed=embed)
        
        session = self.db.get_session()
        try:
            # Check if prefix already exists
            server_prefix = session.query(ServerPrefix).filter_by(server_id=ctx.guild.id).first()
            
            if server_prefix:
                old_prefix = server_prefix.prefix
                server_prefix.prefix = new_prefix
                server_prefix.set_by = ctx.author.id
                server_prefix.set_at = discord.utils.utcnow()
            else:
                server_prefix = ServerPrefix(
                    server_id=ctx.guild.id,
                    prefix=new_prefix,
                    set_by=ctx.author.id
                )
                session.add(server_prefix)
                old_prefix = config.PREFIX
            
            session.commit()
            
            # Update cache
            if hasattr(self.bot, 'prefix_cache'):
                self.bot.prefix_cache[ctx.guild.id] = new_prefix
            
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('success', '✅')} Prefix Updated",
                description=(
                    f"**Old Prefix:** `{old_prefix}`\n"
                    f"**New Prefix:** `{new_prefix}`\n\n"
                    f"**Example:** `{new_prefix}help`\n\n"
                    f"⚠️ **Note:** The default prefix `{config.PREFIX}` will no longer work in this server."
                ),
                color=config.COLORS['success']
            )
            embed.set_footer(text=f"Set by {ctx.author.display_name}")
            await ctx.reply(embed=embed)
            
        except Exception as e:
            session.rollback()
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Error",
                description=f"Failed to set prefix: {e}",
                color=config.COLORS['error']
            )
            await ctx.reply(embed=embed)
        finally:
            session.close()
    
    @commands.command(name='resetprefix')
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def resetprefix(self, ctx):
        """🔄 Reset prefix to default (,)
        
        Usage: ,resetprefix
        """
        session = self.db.get_session()
        try:
            deleted = session.query(ServerPrefix).filter_by(server_id=ctx.guild.id).delete()
            session.commit()
            
            # Update cache
            if hasattr(self.bot, 'prefix_cache') and ctx.guild.id in self.bot.prefix_cache:
                del self.bot.prefix_cache[ctx.guild.id]
            
            if deleted:
                embed = discord.Embed(
                    title=f"{config.EMOJIS.get('success', '✅')} Prefix Reset",
                    description=f"Prefix has been reset to the default: `{config.PREFIX}`\n\n**Example:** `{config.PREFIX}help`",
                    color=config.COLORS['success']
                )
            else:
                embed = discord.Embed(
                    title=f"{config.EMOJIS.get('info', 'ℹ️')} Already Default",
                    description=f"This server is already using the default prefix: `{config.PREFIX}`",
                    color=config.COLORS['primary']
                )
            
            await ctx.reply(embed=embed)
            
        except Exception as e:
            session.rollback()
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Error",
                description=f"Failed to reset prefix: {e}",
                color=config.COLORS['error']
            )
            await ctx.reply(embed=embed)
        finally:
            session.close()
    
    @commands.command(name='prefix')
    @commands.guild_only()
    async def show_prefix(self, ctx):
        """📋 Show the current server prefix
        
        Usage: ,prefix
        """
        session = self.db.get_session()
        try:
            server_prefix = session.query(ServerPrefix).filter_by(server_id=ctx.guild.id).first()
            
            if server_prefix:
                embed = discord.Embed(
                    title="⚙️ Server Prefix",
                    description=f"**Current Prefix:** `{server_prefix.prefix}`\n\n**Example:** `{server_prefix.prefix}help`",
                    color=config.COLORS['primary']
                )
                embed.add_field(
                    name="Set By",
                    value=f"<@{server_prefix.set_by}>",
                    inline=True
                )
                embed.add_field(
                    name="Set At",
                    value=f"<t:{int(server_prefix.set_at.timestamp())}:R>",
                    inline=True
                )
            else:
                embed = discord.Embed(
                    title="⚙️ Server Prefix",
                    description=f"**Current Prefix:** `{config.PREFIX}` (default)\n\n**Example:** `{config.PREFIX}help`",
                    color=config.COLORS['primary']
                )
                embed.add_field(
                    name="💡 Tip",
                    value=f"Use `{config.PREFIX}setprefix <prefix>` to set a custom prefix!",
                    inline=False
                )
            
            await ctx.reply(embed=embed)
            
        finally:
            session.close()
    
    @setprefix.error
    @resetprefix.error
    async def prefix_error(self, ctx, error):
        """Error handler for prefix commands"""
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Missing Permissions",
                description="You need **Manage Server** permission to change the prefix!",
                color=config.COLORS['error']
            )
            await ctx.reply(embed=embed)
        elif isinstance(error, commands.NoPrivateMessage):
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Server Only",
                description="This command can only be used in servers!",
                color=config.COLORS['error']
            )
            await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(PrefixManager(bot))
