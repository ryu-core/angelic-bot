import discord
from discord.ext import commands
from discord.ui import Button, View
from utils.embeds import success_embed, error_embed, info_embed
from utils.role_tools import find_role_matches, is_exact_role_match
import config
from datetime import datetime


class SnipeView(View):
    def __init__(self, snipes, author_id):
        super().__init__(timeout=180)
        self.snipes = snipes[:10]
        self.author_id = author_id
        self.current_index = 0
        self.update_buttons()

    def update_buttons(self):
        self.previous_snipe.disabled = self.current_index == 0
        self.next_snipe.disabled = self.current_index >= len(self.snipes) - 1

    def create_embed(self):
        snipe = self.snipes[self.current_index]
        content = snipe['content'] or '*No content*'
        if len(content) > 4000:
            content = content[:3997] + '...'

        embed = discord.Embed(
            description=content,
            color=config.COLORS['primary'],
            timestamp=snipe['created_at']
        )
        embed.set_author(name=snipe['author'].name, icon_url=snipe['author'].display_avatar.url)
        embed.set_footer(text=f"Deleted message {self.current_index + 1}/{len(self.snipes)}")

        if snipe['attachments']:
            embed.set_image(url=snipe['attachments'][0])
            if len(snipe['attachments']) > 1:
                embed.add_field(
                    name='Attachments',
                    value=f"{len(snipe['attachments'])} attachment(s) were deleted.",
                    inline=False
                )

        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command user can use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Previous', style=discord.ButtonStyle.secondary)
    async def previous_snipe(self, interaction: discord.Interaction, button: Button):
        self.current_index -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.secondary)
    async def next_snipe(self, interaction: discord.Interaction, button: Button):
        self.current_index += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class Utility(commands.Cog):
    """Utility commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='snipe')
    async def snipe(self, ctx):
        """Show the most recently deleted message"""
        if ctx.channel.id not in self.bot.snipes or not self.bot.snipes[ctx.channel.id]:
            return await ctx.reply(embed=error_embed('No Messages', 'No recently deleted messages in this channel.'))

        view = SnipeView(self.bot.snipes[ctx.channel.id], ctx.author.id)
        await ctx.reply(embed=view.create_embed(), view=view, allowed_mentions=discord.AllowedMentions.none())
    
    @commands.command(name='editsnipe', aliases=['es'])
    async def editsnipe(self, ctx):
        """Show the most recently edited message"""
        if ctx.channel.id not in self.bot.edit_snipes or not self.bot.edit_snipes[ctx.channel.id]:
            return await ctx.reply(embed=error_embed('No Messages', 'No recently edited messages in this channel.'))
        
        snipe = self.bot.edit_snipes[ctx.channel.id][0]
        
        embed = discord.Embed(color=config.COLORS['primary'], timestamp=snipe['edited_at'])
        embed.set_author(name=snipe['author'].name, icon_url=snipe['author'].display_avatar.url)
        embed.add_field(name='Before', value=snipe['before'] or '*No content*', inline=False)
        embed.add_field(name='After', value=snipe['after'] or '*No content*', inline=False)
        embed.set_footer(text='Message edited')
        
        await ctx.reply(embed=embed)
    
    @commands.command(name='avatar', aliases=['av', 'pfp'])
    async def avatar(self, ctx, member: discord.Member = None):
        """Show a user's avatar"""
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f"{member.name}'s Avatar",
            color=config.COLORS['primary']
        )
        embed.set_image(url=member.display_avatar.url)
        embed.add_field(name='Links', value=f"[PNG]({member.display_avatar.with_format('png').url}) | [JPG]({member.display_avatar.with_format('jpg').url})")
        
        await ctx.reply(embed=embed)
    
    @commands.command(name='serverinfo', aliases=['si'])
    async def serverinfo(self, ctx):
        """Show server information"""
        guild = ctx.guild
        
        embed = discord.Embed(
            title=f"{guild.name} Server Info",
            color=config.COLORS['primary'],
            timestamp=discord.utils.utcnow()
        )
        
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.add_field(name='Owner', value=guild.owner.mention, inline=True)
        embed.add_field(name='Created', value=discord.utils.format_dt(guild.created_at, 'R'), inline=True)
        embed.add_field(name='Members', value=f'{guild.member_count}', inline=True)
        embed.add_field(name='Channels', value=f'{len(guild.channels)}', inline=True)
        embed.add_field(name='Roles', value=f'{len(guild.roles)}', inline=True)
        embed.add_field(name='Boosts', value=f'Level {guild.premium_tier} ({guild.premium_subscription_count} boosts)', inline=True)
        
        await ctx.reply(embed=embed)

    @commands.command(name='userinfo', aliases=['ui', 'whois'])
    async def userinfo(self, ctx, member: discord.Member = None):
        """Show user information"""
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f"{member.name}'s Info",
            color=member.color if member.color != discord.Color.default() else config.COLORS['primary'],
            timestamp=discord.utils.utcnow()
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name='ID', value=member.id, inline=True)
        embed.add_field(name='Joined', value=discord.utils.format_dt(member.joined_at, 'R'), inline=True)
        embed.add_field(name='Created', value=discord.utils.format_dt(member.created_at, 'R'), inline=True)
        
        roles = [role.mention for role in member.roles[1:]]
        if roles:
            embed.add_field(name=f'Roles [{len(roles)}]', value=' '.join(roles[:10]), inline=False)
        
        if member.premium_since:
            embed.add_field(name='Boosting Since', value=discord.utils.format_dt(member.premium_since, 'R'), inline=True)
        
        await ctx.reply(embed=embed)
    
    @commands.group(name='role', invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role(self, ctx):
        """Role management commands"""
        await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}role create/delete/give/remove`'))

    def _is_owner(self, ctx):
        return ctx.author.id == ctx.guild.owner_id or ctx.author.id in config.OWNER_IDS

    def _can_assign_member_roles(self, ctx):
        if self._is_owner(ctx):
            return True

        antinuke = self.bot.get_cog('AntiNuke')
        if antinuke:
            try:
                return antinuke._is_whitelisted(ctx.guild.id, ctx.author.id)
            except Exception:
                pass

        try:
            from utils.database import settings_db
            role = settings_db.get_antinuke_whitelist_role(ctx.guild.id, ctx.author.id) if settings_db else None
            return role in {'whitelisted', 'admin'}
        except Exception:
            return False

    async def _resolve_role(self, ctx, query):
        query = str(query or "").strip()
        if not query:
            return None

        roles = [role for role in ctx.guild.roles if role != ctx.guild.default_role]
        matches = find_role_matches(roles, query, limit=5)
        if not matches:
            await ctx.reply(embed=error_embed('Role Not Found', f'No role matched `{query}`.'))
            return None

        exact_matches = [role for role in matches if is_exact_role_match(role, query)]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(matches) == 1:
            return matches[0]

        choices = '\n'.join(
            f'`{index}.` {role.mention} (`{role.name}`)'
            for index, role in enumerate(matches, start=1)
        )
        await ctx.reply(embed=error_embed(
            'Multiple Roles Matched',
            f'Be more specific. I found:\n{choices}'
        ))
        return None

    def _role_manage_error(self, ctx, role, action):
        if role == ctx.guild.default_role:
            return f'You cannot {action} the @everyone role.'
        if role.managed:
            return 'This role is managed by an integration and cannot be changed.'
        if role >= ctx.guild.me.top_role:
            return 'This role is higher than or equal to my highest role.'
        if role >= ctx.author.top_role and not self._is_owner(ctx):
            return 'This role is higher than or equal to your highest role.'
        return None

    def _member_manage_error(self, ctx, member):
        if self._is_owner(ctx):
            return None
        if member.id == ctx.guild.owner_id:
            return 'You cannot manage the server owner.'
        if member != ctx.author and member.top_role >= ctx.author.top_role:
            return 'You cannot manage that member due to role hierarchy.'
        return None
    
    @role.command(name='create')
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_create(self, ctx, name: str = None, color: str = None, hoist: bool = False, mentionable: bool = False):
        """Create a new role"""
        if not name:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}role create <name> [color] [hoist] [mentionable]`\nExample: `,role create "VIP" #ff0000 true false`'))
        
        try:
            # Parse color if provided
            role_color = discord.Color.default()
            if color:
                if color.startswith('#'):
                    color = color[1:]
                try:
                    role_color = discord.Color(int(color, 16))
                except:
                    return await ctx.reply(embed=error_embed('Invalid Color', 'Please provide a valid hex color (e.g., #ff0000)'))
            
            # Create role
            new_role = await ctx.guild.create_role(
                name=name,
                color=role_color,
                hoist=hoist,
                mentionable=mentionable,
                reason=f"Role created by {ctx.author}"
            )
            
            embed = success_embed(
                'Role Created',
                f"{config.EMOJIS['role']} **Role:** {new_role.mention}\n**Color:** {str(role_color)}\n**Hoisted:** {hoist}\n**Mentionable:** {mentionable}"
            )
            await ctx.reply(embed=embed)
            
        except Exception as e:
            await ctx.reply(embed=error_embed('Role Creation Failed', f'Could not create role: {str(e)}'))
    
    @role.command(name='delete')
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_delete(self, ctx, role: discord.Role = None):
        """Delete a role"""
        if not role:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}role delete <@role>`'))
        
        # Check if role is managed (bot roles, integrations, etc.)
        if role.managed:
            return await ctx.reply(embed=error_embed('Cannot Delete', 'This role is managed by an integration and cannot be deleted.'))
        
        # Check if role is higher than bot's highest role
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(embed=error_embed('Cannot Delete', 'This role is higher than my highest role.'))
        
        # Check if role is higher than command user's highest role
        if role >= ctx.author.top_role and ctx.author.id not in config.OWNER_IDS:
            return await ctx.reply(embed=error_embed('Cannot Delete', 'This role is higher than your highest role.'))
        
        try:
            role_name = role.name
            await role.delete(reason=f"Role deleted by {ctx.author}")
            await ctx.reply(embed=success_embed(
                'Role Deleted',
                f"{config.EMOJIS['success']} Successfully deleted role **{role_name}**"
            ))
        except Exception as e:
            await ctx.reply(embed=error_embed('Role Deletion Failed', f'Could not delete role: {str(e)}'))
    
    @role.command(name='give', aliases=['add', 'grant'])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_give(self, ctx, member: discord.Member = None, *, role_query: str = None):
        """Give a role to a member"""
        if not member or not role_query:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}role give <@member> <role shortcut>`'))
        if not self._can_assign_member_roles(ctx):
            return await ctx.reply(embed=error_embed(
                'Not Whitelisted',
                f'Only server owners, bot owners, or antinuke-whitelisted users can give roles.\n'
                f'Ask an antinuke admin to run `{config.PREFIX}antinuke whitelist add {ctx.author.mention}`.'
            ))

        role = await self._resolve_role(ctx, role_query)
        if not role:
            return

        member_error = self._member_manage_error(ctx, member)
        if member_error:
            return await ctx.reply(embed=error_embed('Cannot Give Role', member_error))
        
        # Check if member already has the role
        if role in member.roles:
            return await ctx.reply(embed=error_embed('Already Has Role', f'{member.mention} already has the {role.mention} role.'))
        
        role_error = self._role_manage_error(ctx, role, 'give')
        if role_error:
            return await ctx.reply(embed=error_embed('Cannot Give Role', role_error))
        
        try:
            await member.add_roles(role, reason=f"Role given by {ctx.author}")
            await ctx.reply(embed=success_embed(
                'Role Given',
                f"{config.EMOJIS['success']} Successfully gave {role.mention} to {member.mention}"
            ))
        except Exception as e:
            await ctx.reply(embed=error_embed('Role Give Failed', f'Could not give role: {str(e)}'))
    
    @role.command(name='remove', aliases=['take', 'revoke'])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_remove(self, ctx, member: discord.Member = None, *, role_query: str = None):
        """Remove a role from a member"""
        if not member or not role_query:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}role remove <@member> <role shortcut>`'))
        if not self._can_assign_member_roles(ctx):
            return await ctx.reply(embed=error_embed(
                'Not Whitelisted',
                f'Only server owners, bot owners, or antinuke-whitelisted users can remove roles.\n'
                f'Ask an antinuke admin to run `{config.PREFIX}antinuke whitelist add {ctx.author.mention}`.'
            ))

        role = await self._resolve_role(ctx, role_query)
        if not role:
            return

        member_error = self._member_manage_error(ctx, member)
        if member_error:
            return await ctx.reply(embed=error_embed('Cannot Remove Role', member_error))
        
        # Check if member doesn't have the role
        if role not in member.roles:
            return await ctx.reply(embed=error_embed('Does Not Have Role', f'{member.mention} does not have the {role.mention} role.'))
        
        role_error = self._role_manage_error(ctx, role, 'remove')
        if role_error:
            return await ctx.reply(embed=error_embed('Cannot Remove Role', role_error))
        
        try:
            await member.remove_roles(role, reason=f"Role removed by {ctx.author}")
            await ctx.reply(embed=success_embed(
                'Role Removed',
                f"{config.EMOJIS['success']} Successfully removed {role.mention} from {member.mention}"
            ))
        except Exception as e:
            await ctx.reply(embed=error_embed('Role Remove Failed', f'Could not remove role: {str(e)}'))
    
    @commands.command(name='sticky')
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def sticky(self, ctx, *, message: str = None):
        """Create or manage sticky messages"""
        from utils.database import sticky_db
        
        if not message:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}sticky <message>`\nUse `{config.PREFIX}sticky off` to disable'))
        
        channel_id = str(ctx.channel.id)
        
        if message.lower() == 'off':
            # Disable sticky
            if sticky_db.has(channel_id):
                sticky_data = sticky_db.get(channel_id)
                # Try to delete the last sticky message
                try:
                    channel = ctx.channel
                    msg = await channel.fetch_message(int(sticky_data['message_id']))
                    await msg.delete()
                except:
                    pass
                
                sticky_db.delete(channel_id)
                await ctx.reply(embed=success_embed('Sticky Disabled', f'{config.EMOJIS["success"]} Sticky message disabled in this channel.'))
            else:
                await ctx.reply(embed=error_embed('No Sticky', 'There is no sticky message in this channel.'))
        else:
            # Create/Update sticky
            try:
                # Delete command message
                try:
                    await ctx.message.delete()
                except:
                    pass
                
                # Send sticky message
                embed = discord.Embed(
                    description=message,
                    color=config.COLORS['primary']
                )
                embed.set_footer(text=f'📌 Sticky Message')
                
                sticky_msg = await ctx.send(embed=embed)
                
                # Save to database
                sticky_db.set(channel_id, {
                    'message': message,
                    'message_id': str(sticky_msg.id),
                    'channel_id': channel_id
                })
                
            except Exception as e:
                await ctx.reply(embed=error_embed('Sticky Failed', f'Could not create sticky message: {str(e)}'))
    
    @commands.command(name='time')
    async def time_command(self, ctx, *, location: str = None):
        """Show current time for a timezone or user"""
        from utils.database import timezone_db
        import pytz
        from datetime import datetime
        
        try:
            target_tz = None
            display_name = None
            
            if location:
                # Check if it's a mention
                if ctx.message.mentions:
                    user = ctx.message.mentions[0]
                    user_id = str(user.id)
                    
                    if timezone_db.has(user_id):
                        tz_name = timezone_db.get(user_id)
                        target_tz = pytz.timezone(tz_name)
                        # Privacy: Don't show timezone to others, just time
                        if user.id == ctx.author.id:
                            display_name = f"Your timezone ({tz_name})"
                        else:
                            display_name = f"{user.name}'s local time"
                    else:
                        return await ctx.reply(embed=error_embed('No Timezone Set', f'{user.mention} has not set their timezone yet.'))
                else:
                    # Parse timezone using comprehensive utility
                    from utils.timezones import parse_timezone
                    
                    tz_name, display_name_parsed = parse_timezone(location)
                    
                    if tz_name:
                        target_tz = pytz.timezone(tz_name)
                        display_name = f"{display_name_parsed} ({tz_name})"
                    else:
                        return await ctx.reply(embed=error_embed(
                            'Invalid Timezone',
                            f'Could not find timezone for "{location}".\n\n**Try:**\n'
                            '• Country names: "India", "USA", "Japan"\n'
                            '• City names: "New York", "Tokyo", "Mumbai"\n'
                            '• Abbreviations: "GMT", "EST", "IST", "PST"'
                        ))
            else:
                # Use user's saved timezone or UTC
                user_id = str(ctx.author.id)
                if timezone_db.has(user_id):
                    tz_name = timezone_db.get(user_id)
                    target_tz = pytz.timezone(tz_name)
                    display_name = "Your local time"  # Don't reveal timezone
                else:
                    target_tz = pytz.UTC
                    display_name = "UTC (No timezone set)"
            
            # Get current time in target timezone
            current_time = datetime.now(target_tz)
            
            # Simple output - just show the time
            time_str = current_time.strftime('%I:%M:%S %p')
            
            await ctx.reply(f"{config.EMOJIS['clock']} Your current time is **{time_str}**")
            
        except Exception as e:
            await ctx.reply(embed=error_embed('Error', f'Could not get time: {str(e)}'))
    
    @commands.command(name='timeset', aliases=['settime'])
    async def time_set(self, ctx, *, timezone: str = None):
        """Set your personal timezone"""
        from utils.database import timezone_db
        import pytz
        
        if not timezone:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}time set <timezone>`\nExample: `,time set America/New_York` or `,time set Asia/Tokyo`\n\nCommon timezones:\n• `America/New_York` (EST/EDT)\n• `America/Los_Angeles` (PST/PDT)\n• `Europe/London` (GMT/BST)\n• `Asia/Tokyo` (JST)\n• `Asia/Kolkata` (IST)\n• `Australia/Sydney` (AEDT)'))
        
        try:
            # Parse timezone using comprehensive utility
            from utils.timezones import parse_timezone
            
            tz_name, display_name = parse_timezone(timezone)
            
            if not tz_name:
                return await ctx.reply(embed=error_embed(
                    'Invalid Timezone',
                    f'"{timezone}" is not a valid timezone.\n\n**Try:**\n'
                    '• Country names: "India", "USA", "United Kingdom"\n'
                    '• City names: "New York", "London", "Mumbai"\n'
                    '• Full timezone: "Asia/Kolkata", "America/New_York"\n'
                    '• Abbreviations: "EST", "GMT", "IST", "PST"'
                ))
            
            # Save timezone
            user_id = str(ctx.author.id)
            timezone_db.set(user_id, tz_name)
            
            await ctx.reply(embed=success_embed(
                'Timezone Set',
                f"{config.EMOJIS['success']} Your timezone has been set to **{tz_name}**\n\nUse `{config.PREFIX}time` to view your current time!"
            ))
            
        except Exception as e:
            await ctx.reply(embed=error_embed('Error', f'Could not set timezone: {str(e)}'))

async def setup(bot):
    await bot.add_cog(Utility(bot))
