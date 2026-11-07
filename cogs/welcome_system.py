"""
Welcome System Cog
Auto-sends welcome cards when members join
Supports add/remove/view commands like Bleed bot
"""

import discord
from discord.ext import commands
from utils.embeds import success_embed, error_embed
from utils.settings_db import settings_db
import config


class WelcomeSystem(commands.Cog):
    """Auto welcome system with MySQL storage"""
    
    def __init__(self, bot):
        self.bot = bot
        # MySQL database is initialized in settings_db
    
    async def get_welcome_config(self, guild_id: int):
        """Get welcome config for a guild (channel + message + image)"""
        result = settings_db.get_welcome_config(str(guild_id))
        if result:
            return {
                'channel_id': int(result['channel_id']),
                'message': result['message'],
                'image_url': result.get('custom_image_url')
            }
        return None
    
    async def set_welcome_channel(self, guild_id: int, channel_id: int, message: str = None):
        """Set welcome channel for a guild"""
        return settings_db.set_welcome_channel(str(guild_id), str(channel_id), message)
    
    async def update_welcome_message(self, guild_id: int, message: str):
        """Update welcome message for a guild"""
        return settings_db.update_welcome_message(str(guild_id), message)
    
    async def update_welcome_image(self, guild_id: int, image_url: str):
        """Update custom welcome image for a guild"""
        return settings_db.update_welcome_image(str(guild_id), image_url)
    
    async def remove_welcome_channel(self, guild_id: int):
        """Remove welcome channel for a guild"""
        return settings_db.remove_welcome_channel(str(guild_id))
    
    @commands.group(name='welcome', invoke_without_command=True)
    async def welcome(self, ctx, member: discord.Member = None):
        """Welcome system - use subcommands to manage"""
        if not member:
            member = ctx.author
        
        # Manual welcome card generation
        async with ctx.typing():
            try:
                from utils.welcome_generator import WelcomeCardGenerator
                
                generator = WelcomeCardGenerator()
                image_bytes = await generator.generate(
                    avatar_url=str(member.display_avatar.url),
                    username=member.name,
                    discriminator=member.discriminator if member.discriminator != "0" else "",
                    server_name=ctx.guild.name,
                    member_count=ctx.guild.member_count,
                    card_type="welcome"
                )
                
                file = discord.File(image_bytes, filename="welcome.png")
                await ctx.send(file=file)
                
            except Exception as e:
                await ctx.reply(embed=error_embed('Welcome Card Failed', f'Could not generate welcome card: {str(e)}'))
    
    @welcome.error
    async def welcome_error(self, ctx, error):
        """Handle errors for welcome command group"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed('Missing Permissions', 'You need **Manage Server** permission to use this command!'))
        elif isinstance(error, commands.CheckFailure):
            await ctx.reply(embed=error_embed('Permission Denied', 'You do not have permission to use this command!'))
        else:
            await ctx.reply(embed=error_embed('Command Error', f'An error occurred: {str(error)}'))
            print(f"Welcome command error: {error}")
    
    @welcome.command(name='add')
    @commands.has_permissions(manage_guild=True)
    async def welcome_add(self, ctx, channel: discord.TextChannel = None):
        """Set up auto-welcome in a channel"""
        if not channel:
            channel = ctx.channel
        
        # Check bot permissions
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.attach_files:
            return await ctx.reply(embed=error_embed(
                'Missing Permissions',
                f'I need **Send Messages** and **Attach Files** permissions in {channel.mention}!'
            ))
        
        # Save to database
        if not await self.set_welcome_channel(ctx.guild.id, channel.id):
            return await ctx.reply(embed=error_embed(
                'Database Unavailable',
                'The welcome setting could not be saved. Please try again later.'
            ))
        
        embed = success_embed(
            'Welcome System Enabled',
            f'✅ Welcome cards will now be sent to {channel.mention} when members join!\n\n'
            f'**Edit message:** `,welcome edit <message>`\n'
            f'**Test it:** `,welcome view {channel.mention}`'
        )
        await ctx.reply(embed=embed)
    
    @welcome_add.error
    async def welcome_add_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed('Missing Permissions', 'You need **Manage Server** permission!'))
        else:
            await ctx.reply(embed=error_embed('Error', f'Failed to add welcome channel: {str(error)}'))
            print(f"welcome add error: {error}")
    
    @welcome.command(name='remove')
    @commands.has_permissions(manage_guild=True)
    async def welcome_remove(self, ctx):
        """Remove auto-welcome from this server"""
        config = await self.get_welcome_config(ctx.guild.id)
        
        if not config:
            return await ctx.reply(embed=error_embed(
                'No Welcome Channel',
                'No welcome channel is configured for this server!'
            ))
        
        if not await self.remove_welcome_channel(ctx.guild.id):
            return await ctx.reply(embed=error_embed(
                'Database Unavailable',
                'The welcome setting could not be removed. Please try again later.'
            ))
        
        embed = success_embed(
            'Welcome System Disabled',
            '✅ Auto-welcome has been disabled for this server.'
        )
        await ctx.reply(embed=embed)
    
    @welcome_remove.error
    async def welcome_remove_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed('Missing Permissions', 'You need **Manage Server** permission!'))
        else:
            await ctx.reply(embed=error_embed('Error', f'{str(error)}'))
    
    @welcome.command(name='edit')
    @commands.has_permissions(manage_guild=True)
    async def welcome_edit(self, ctx, *, message: str = None):
        """Edit the welcome message
        
        Usage:
        ,welcome edit Hello {user}! Welcome to {server}!
        ,welcome edit {user} just joined. We now have {count} members!
        ,welcome edit (removes custom message)
        
        Variables:
        {user} - mentions the user
        {username} - user's name
        {server} - server name
        {count} - member count
        """
        config = await self.get_welcome_config(ctx.guild.id)
        
        if not config:
            return await ctx.reply(embed=error_embed(
                'No Welcome Channel',
                'You need to set up a welcome channel first!\n'
                'Use `,welcome add #channel`'
            ))
        
        # Update message (None to remove)
        if not await self.update_welcome_message(ctx.guild.id, message):
            return await ctx.reply(embed=error_embed(
                'Database Unavailable',
                'The welcome message could not be saved. Please try again later.'
            ))
        
        if message:
            # Show preview
            preview = message.replace('{user}', ctx.author.mention)
            preview = preview.replace('{username}', ctx.author.name)
            preview = preview.replace('{server}', ctx.guild.name)
            preview = preview.replace('{count}', str(ctx.guild.member_count))
            
            embed = success_embed(
                'Welcome Message Updated',
                f'✅ Custom welcome message set!\n\n'
                f'**Preview:**\n{preview}'
            )
        else:
            embed = success_embed(
                'Welcome Message Removed',
                '✅ Custom message removed. Only the welcome card will be sent.'
            )
        
        await ctx.reply(embed=embed)
    
    @welcome_edit.error
    async def welcome_edit_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed('Missing Permissions', 'You need **Manage Server** permission!'))
        else:
            await ctx.reply(embed=error_embed('Error', f'{str(error)}'))
            print(f"welcome edit error: {error}")
    
    @welcome.command(name='image')
    @commands.has_permissions(manage_guild=True)
    async def welcome_image(self, ctx, *, image_url: str = None):
        """Set a custom welcome image
        
        Usage:
        ,welcome image                 → Attach an image file
        ,welcome image <url>           → Use image from URL
        ,welcome image remove          → Use auto-generated cards
        
        The custom image will be sent instead of the auto-generated welcome card.
        """
        config = await self.get_welcome_config(ctx.guild.id)
        
        if not config:
            return await ctx.reply(embed=error_embed(
                'No Welcome Channel',
                'You need to set up a welcome channel first!\n'
                'Use `,welcome add #channel`'
            ))
        
        # Check if removing custom image
        if image_url and image_url.lower() == 'remove':
            if not await self.update_welcome_image(ctx.guild.id, None):
                return await ctx.reply(embed=error_embed(
                    'Database Unavailable',
                    'The custom image could not be removed. Please try again later.'
                ))
            return await ctx.reply(embed=success_embed(
                'Custom Image Removed',
                '✅ Removed custom image. Auto-generated welcome cards will now be used.'
            ))
        
        # Priority 1: Check for attachment first
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            # Check if it's an image
            if not any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                return await ctx.reply(embed=error_embed(
                    'Invalid File Type',
                    'Please upload an image file (PNG, JPG, GIF, or WEBP)'
                ))
            image_url = attachment.url
        
        # Priority 2: Use provided URL
        elif image_url:
            # Validate URL (basic check)
            if not image_url.startswith('http'):
                return await ctx.reply(embed=error_embed(
                    'Invalid URL',
                    'Please provide a valid image URL starting with http:// or https://'
                ))
        
        # No image provided
        else:
            return await ctx.reply(embed=error_embed(
                'No Image Provided',
                'Please either:\n'
                '• **Attach an image** with the command\n'
                '• **Provide a URL:** `,welcome image <url>`\n\n'
                '**Remove custom image:** `,welcome image remove`'
            ))
        
        # Save to database
        if not await self.update_welcome_image(ctx.guild.id, image_url):
            return await ctx.reply(embed=error_embed(
                'Database Unavailable',
                'The custom image could not be saved. Please try again later.'
            ))
        
        embed = success_embed(
            'Custom Welcome Image Set',
            f'✅ Custom welcome image has been set!\n\n'
            f'This image will be sent instead of auto-generated welcome cards.\n'
            f'**Test it:** `,welcome view`'
        )
        embed.set_image(url=image_url)
        await ctx.reply(embed=embed)
    
    @welcome_image.error
    async def welcome_image_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed('Missing Permissions', 'You need **Manage Server** permission!'))
        else:
            await ctx.reply(embed=error_embed('Error', f'{str(error)}'))
            print(f"welcome image error: {error}")
    
    @welcome.command(name='view')
    @commands.has_permissions(manage_guild=True)
    async def welcome_view(self, ctx, channel: discord.TextChannel = None):
        """Test the welcome card"""
        if not channel:
            welcome_config = await self.get_welcome_config(ctx.guild.id)
            if not welcome_config:
                return await ctx.reply(embed=error_embed(
                    'No Welcome Channel',
                    'No welcome channel configured! Use `,welcome add #channel` first.'
                ))
            channel = ctx.guild.get_channel(welcome_config['channel_id'])
            custom_message = welcome_config['message']
        else:
            welcome_config = await self.get_welcome_config(ctx.guild.id)
            custom_message = welcome_config['message'] if welcome_config else None
        
        # Send test welcome card
        async with ctx.typing():
            try:
                # Format custom message
                if custom_message:
                    formatted_msg = custom_message.replace('{user}', ctx.author.mention)
                    formatted_msg = formatted_msg.replace('{username}', ctx.author.name)
                    formatted_msg = formatted_msg.replace('{server}', ctx.guild.name)
                    formatted_msg = formatted_msg.replace('{count}', str(ctx.guild.member_count))
                else:
                    formatted_msg = f"{ctx.author.mention} Welcome! We're glad to have you here!"
                
                # Check if custom image is set
                if welcome_config and welcome_config['image_url']:
                    # Use custom uploaded image
                    embed = discord.Embed(
                        title=f"Welcome to {ctx.guild.name}",
                        description=formatted_msg,
                        color=config.COLORS.get('primary', 0x2ecc71)
                    )
                    embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                    embed.set_image(url=welcome_config['image_url'])
                    embed.set_thumbnail(url=ctx.author.display_avatar.url)
                    await channel.send(embed=embed)
                else:
                    # Generate welcome card
                    from utils.welcome_generator import WelcomeCardGenerator
                    
                    generator = WelcomeCardGenerator()
                    image_bytes = await generator.generate(
                        avatar_url=str(ctx.author.display_avatar.url),
                        username=ctx.author.name,
                        discriminator=ctx.author.discriminator if ctx.author.discriminator != "0" else "",
                        server_name=ctx.guild.name,
                        member_count=ctx.guild.member_count,
                        card_type="welcome"
                    )
                    
                    file = discord.File(image_bytes, filename="welcome.png")
                    
                    # Create embed with avatar thumbnail (Mimu bot style)
                    embed = discord.Embed(
                        title=f"Welcome to {ctx.guild.name}",
                        description=formatted_msg,
                        color=config.COLORS.get('primary', 0x2ecc71)
                    )
                    embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                    embed.set_image(url="attachment://welcome.png")
                    embed.set_thumbnail(url=ctx.author.display_avatar.url)
                    
                    await channel.send(embed=embed, file=file)
                
                if channel.id != ctx.channel.id:
                    await ctx.reply(embed=success_embed('Test Sent', f'Welcome test sent to {channel.mention}!'))
                
            except Exception as e:
                await ctx.reply(embed=error_embed('Test Failed', f'Could not generate welcome card: {str(e)}'))
    
    @welcome_view.error
    async def welcome_view_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed('Missing Permissions', 'You need **Manage Server** permission!'))
        else:
            await ctx.reply(embed=error_embed('Error', f'{str(error)}'))
            print(f"welcome view error: {error}")
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Send welcome card when member joins"""
        if member.bot:
            return
        
        welcome_config = await self.get_welcome_config(member.guild.id)
        if not welcome_config:
            return
        
        channel = member.guild.get_channel(welcome_config['channel_id'])
        if not channel:
            return
        
        try:
            # Format custom message
            if welcome_config['message']:
                formatted_msg = welcome_config['message'].replace('{user}', member.mention)
                formatted_msg = formatted_msg.replace('{username}', member.name)
                formatted_msg = formatted_msg.replace('{server}', member.guild.name)
                formatted_msg = formatted_msg.replace('{count}', str(member.guild.member_count))
            else:
                formatted_msg = f"{member.mention} Welcome! We're glad to have you here!"
            
            # Check if custom image is set
            if welcome_config['image_url']:
                # Send custom image directly with avatar thumbnail
                import config as bot_config
                embed = discord.Embed(
                    title=f"Welcome to {member.guild.name}",
                    description=formatted_msg,
                    color=bot_config.COLORS.get('primary', 0x2ecc71)
                )
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.set_image(url=welcome_config['image_url'])
                embed.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=embed)
            else:
                # Generate welcome card with avatar thumbnail
                from utils.welcome_generator import WelcomeCardGenerator
                
                generator = WelcomeCardGenerator()
                image_bytes = await generator.generate(
                    avatar_url=str(member.display_avatar.url),
                    username=member.name,
                    discriminator=member.discriminator if member.discriminator != "0" else "",
                    server_name=member.guild.name,
                    member_count=member.guild.member_count,
                    card_type="welcome"
                )
                
                file = discord.File(image_bytes, filename="welcome.png")
                
                # Create embed with avatar thumbnail (Mimu bot style)
                import config as bot_config
                embed = discord.Embed(
                    title=f"Welcome to {member.guild.name}",
                    description=formatted_msg,
                    color=bot_config.COLORS.get('primary', 0x2ecc71)
                )
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.set_image(url="attachment://welcome.png")
                embed.set_thumbnail(url=member.display_avatar.url)
                
                await channel.send(embed=embed, file=file)
            
        except Exception as e:
            print(f"Failed to send welcome: {e}")


async def setup(bot):
    await bot.add_cog(WelcomeSystem(bot))
