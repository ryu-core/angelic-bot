import discord
from discord.ext import commands
from utils.embeds import success_embed, error_embed, info_embed
from utils.autorole_db import autorole_db
import config

class AutoRoles(commands.Cog):
    """Auto-role system for vanity URLs in custom status"""
    
    def __init__(self, bot):
        self.bot = bot
        # Cache for configurations to reduce database queries
        self.config_cache = {}
    
    async def load_configs(self):
        """Load all auto-role configurations into cache"""
        configs = autorole_db.get_all_configs()
        for config_data in configs:
            self.config_cache[config_data['guild_id']] = config_data
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Load configurations when bot is ready"""
        await self.load_configs()
        print("✓ Auto-role system loaded")
    
    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        """Detect custom status changes for vanity URL detection"""
        # Skip if user is a bot
        if after.id == self.bot.user.id or after.bot:
            return
        
        # Get all guilds the user is in
        for guild in self.bot.guilds:
            member = guild.get_member(after.id)
            if not member:
                continue
            
            # Get config for this guild
            guild_id = str(guild.id)
            config_data = self.config_cache.get(guild_id)
            
            if not config_data:
                # Try to load from database
                config_data = autorole_db.get_config(guild_id)
                if config_data:
                    self.config_cache[guild_id] = config_data
                else:
                    continue
            
            # Check vanity URL detection
            if config_data.get('vanity_enabled') and config_data.get('vanity_text'):
                await self.handle_vanity_detection(member, guild, config_data, after)
    

    

    
    async def handle_vanity_detection(self, member, guild, config_data, presence):
        """Handle vanity URL detection and role assignment"""
        try:
            vanity_role = guild.get_role(int(config_data['vanity_role_id']))
            if not vanity_role:
                return
            
            vanity_text = config_data['vanity_text'].lower()
            
            # Check if user has vanity URL in custom status
            has_vanity = False
            if hasattr(presence, 'activities'):
                for activity in presence.activities:
                    if isinstance(activity, discord.CustomActivity):
                        if activity.name and vanity_text in activity.name.lower():
                            has_vanity = True
                            break
            
            # Assign or remove role based on vanity status
            if has_vanity and vanity_role not in member.roles:
                await member.add_roles(vanity_role, reason="Auto-role: Vanity URL in status")
            elif not has_vanity and vanity_role in member.roles:
                await member.remove_roles(vanity_role, reason="Auto-role: Vanity URL removed")
        
        except Exception as e:
            print(f"Error in vanity detection: {e}")
    
    @commands.group(name='autorole', invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def autorole(self, ctx):
        """Auto-role management commands"""
        await ctx.send(embed=info_embed(
            'Auto-Role System',
            f'**Available Commands:**\n'
            f'`{config.PREFIX}autorole vanity <url> <@role>` - Set role for vanity URL in status\n'
            f'`{config.PREFIX}autorole status` - View current configuration\n'
            f'`{config.PREFIX}autorole disable` - Disable vanity detection\n'
            f'`{config.PREFIX}autorole debug` - Debug autorole system\n\n'
            f'**How it works:**\n'
            f'When users add your vanity URL (e.g. discord.gg/xiel) to their **custom status**, '
            f'they automatically get the configured role!'
        ))
    
    @autorole.command(name='debug')
    @commands.has_permissions(administrator=True)
    async def autorole_debug(self, ctx):
        """Debug autorole system to find issues"""
        try:
            debug_info = []
            
            # Check if presence intent is enabled
            has_presences = self.bot.intents.presences
            has_members = self.bot.intents.members
            debug_info.append(f"**Presence Intent:** {'✅ Enabled' if has_presences else '❌ Disabled (REQUIRED!)'}")
            debug_info.append(f"**Members Intent:** {'✅ Enabled' if has_members else '❌ Disabled (REQUIRED!)'}")
            
            # Check database configuration
            guild_id = str(ctx.guild.id)
            config_data = autorole_db.get_config(guild_id)
            
            if config_data:
                debug_info.append(f"\n**Database Config Found:**")
                vanity_role_id = config_data.get('vanity_role_id')
                debug_info.append(f"Vanity Role: {f'<@&{vanity_role_id}>' if vanity_role_id else 'Not set'}")
                debug_info.append(f"Vanity Text: `{config_data.get('vanity_text', 'Not set')}`")
                debug_info.append(f"Vanity Enabled: {'✅' if config_data.get('vanity_enabled', True) else '❌'}")
            else:
                debug_info.append(f"\n**Database Config:** ❌ Not found")
            
            # Check cache
            cached = guild_id in self.config_cache
            debug_info.append(f"\n**Cache Status:** {'✅ Loaded' if cached else '❌ Not cached'}")
            
            if cached:
                cache_data = self.config_cache[guild_id]
                debug_info.append(f"Cached Vanity Role: {cache_data.get('vanity_role_id', 'None')}")
            
            # Check if listeners are registered
            debug_info.append(f"\n**Event Listeners:**")
            debug_info.append(f"on_presence_update: ✅ Registered")
            debug_info.append(f"on_member_update: ✅ Registered")
            
            # Check bot permissions
            bot_member = ctx.guild.me
            can_manage_roles = bot_member.guild_permissions.manage_roles
            debug_info.append(f"\n**Bot Permissions:**")
            debug_info.append(f"Manage Roles: {'✅' if can_manage_roles else '❌ Missing!'}")
            
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('info', 'ℹ️')} Auto-Role Debug Info",
                description='\n'.join(debug_info),
                color=config.COLORS.get('primary', 0x2ecc71)
            )
            
            # Add troubleshooting tips
            if not has_presences or not has_members:
                embed.add_field(
                    name="⚠️ Missing Intents",
                    value="The bot needs **Presence Intent** and **Members Intent** enabled in the Discord Developer Portal!\n"
                          "Go to: Discord Developer Portal → Your App → Bot → Privileged Gateway Intents",
                    inline=False
                )
            
            if not config_data:
                embed.add_field(
                    name="💡 No Configuration",
                    value=f"Use `{config.PREFIX}autorole tag @role` or `{config.PREFIX}autorole vanity <url> @role` to configure auto-roles.",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            # Catch any error and display it
            await ctx.send(embed=error_embed(
                "Debug Command Error",
                f"An error occurred while running debug:\n```{type(e).__name__}: {str(e)}```"
            ))
            import traceback
            traceback.print_exc()

    
    @autorole.command(name='vanity')
    @commands.has_permissions(administrator=True)
    async def autorole_vanity(self, ctx, vanity_text: str = None, *, role: discord.Role = None):
        """Set role for users with vanity URL in status
        
        Usage: ,autorole vanity <url> @role
        Example: ,autorole vanity .gg/xiel @Supporter
        """
        if not vanity_text:
            return await ctx.send(embed=error_embed(
                'Invalid Usage',
                f'Usage: `{config.PREFIX}autorole vanity <url> @role`\n\n'
                f'Example: `{config.PREFIX}autorole vanity .gg/xiel @Supporter`\n\n'
                f'Users with this text in their custom status will automatically receive the role.'
            ))
        
        if not role:
            return await ctx.send(embed=error_embed(
                'Missing Role',
                f'Please mention a role!\n\n'
                f'Usage: `{config.PREFIX}autorole vanity {vanity_text} @role`\n\n'
                f'Make sure to @mention the role, not just type its name.'
            ))
        
        # Check if bot can manage the role
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed(
                'Role Too High',
                'I cannot manage this role as it is higher than or equal to my highest role.'
            ))
        
        # Save to database
        if autorole_db.set_vanity_role(str(ctx.guild.id), vanity_text, str(role.id)):
            # Update cache
            config_data = autorole_db.get_config(str(ctx.guild.id))
            self.config_cache[str(ctx.guild.id)] = config_data
            
            await ctx.send(embed=success_embed(
                'Vanity URL Role Set',
                f'{config.EMOJIS["success"]} Users with **{vanity_text}** in their custom status will automatically receive {role.mention}'
            ))
        else:
            await ctx.send(embed=error_embed('Database Error', 'Failed to save configuration.'))
    
    @autorole.command(name='status')
    async def autorole_status(self, ctx):
        """View current auto-role configuration"""
        config_data = autorole_db.get_config(str(ctx.guild.id))
        
        if not config_data:
            return await ctx.send(embed=info_embed(
                'Auto-Role Status',
                f'{config.EMOJIS.get("info", "ℹ️")} No auto-role configuration set for this server.\n\n'
                f'Use `{config.PREFIX}autorole vanity` to set up auto-roles.'
            ))
        
        embed = discord.Embed(
            title=f"{config.EMOJIS.get('settings', '⚙️')} Auto-Role Configuration",
            color=config.COLORS.get('primary', 0x2ecc71)
        )
        
        # Vanity URL status
        if config_data.get('vanity_enabled') and config_data.get('vanity_text'):
            vanity_role = ctx.guild.get_role(int(config_data['vanity_role_id']))
            vanity_status = f"{config.EMOJIS.get('success', '✅')} Enabled\n**Text:** `{config_data['vanity_text']}`\n**Role:** {vanity_role.mention if vanity_role else 'Role not found'}"
        else:
            vanity_status = f"{config.EMOJIS.get('fail', '❌')} Disabled"
        
        embed.add_field(name='Vanity URL Detection', value=vanity_status, inline=False)
        embed.set_footer(text="Users who add the vanity URL to their custom status get the role automatically!")
        
        await ctx.send(embed=embed)
    
    @autorole.command(name='disable')
    @commands.has_permissions(administrator=True)
    async def autorole_disable(self, ctx):
        """Disable vanity URL detection"""
        guild_id = str(ctx.guild.id)
        
        if autorole_db.disable_vanity(guild_id):
            # Update cache
            if guild_id in self.config_cache:
                self.config_cache[guild_id]['vanity_enabled'] = False
            
            await ctx.send(embed=success_embed(
                'Vanity Detection Disabled',
                f'{config.EMOJIS.get("success", "✅")} Vanity URL detection has been disabled.'
            ))
        else:
            await ctx.send(embed=error_embed('Database Error', 'Failed to disable vanity detection.'))
    
    @autorole.error
    async def autorole_error(self, ctx, error):
        """Error handler for autorole command group"""
        # Get the original error if it's wrapped
        error = getattr(error, 'original', error)
        
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed(
                f'{config.EMOJIS.get("error", "❌")} Missing Permissions',
                f'You need **Administrator** permission to use autorole commands!\n\n'
                f'**Your Permissions:** {", ".join([p[0].replace("_", " ").title() for p in ctx.author.guild_permissions if p[1]])}\n\n'
                f'Ask a server administrator to give you the Administrator permission.'
            ))
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(embed=error_embed(
                f'{config.EMOJIS.get("error", "❌")} Bot Missing Permissions',
                f'I need the following permissions:\n**{", ".join(error.missing_permissions)}**'
            ))
        else:
            # Re-raise other errors to be caught by global handler
            raise error

async def setup(bot):
    await bot.add_cog(AutoRoles(bot))
