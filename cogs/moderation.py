import discord
from discord.ext import commands
from datetime import timedelta
import asyncio
import re
from utils.embeds import success_embed, error_embed
from utils.permissions import can_moderate_target
import config

class Moderation(commands.Cog):
    """Moderation commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='ban', aliases=['b'])
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member = None, delete_days: int = 0, *, reason='No reason provided'):
        """Ban a member from the server"""
        if not member:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}ban <@user> [days] [reason]`'))
        
        if not can_moderate_target(ctx.author, member):
            return await ctx.reply(embed=error_embed('Cannot Ban', 'You cannot ban this user due to role hierarchy.'))
        
        if not can_moderate_target(ctx.guild.me, member):
            return await ctx.reply(embed=error_embed('Cannot Ban', 'I cannot ban this user due to my role hierarchy.'))
        
        try:
            await member.ban(delete_message_days=min(delete_days, 7), reason=f"{reason} | Banned by {ctx.author}")
            
            # Update modstats
            from utils.database import modstats_db
            from utils.mysql_logs import mysql_case_logs
            from utils.modlog import send_to_modlog
            guild_id = str(ctx.guild.id)
            mod_id = str(ctx.author.id)
            
            if not modstats_db.has(guild_id):
                modstats_db.set(guild_id, {})
            
            guild_stats = modstats_db.get(guild_id, {})
            if mod_id not in guild_stats:
                guild_stats[mod_id] = {'warns': 0, 'kicks': 0, 'bans': 0, 'jails': 0, 'mutes': 0}
            
            guild_stats[mod_id]['bans'] = guild_stats[mod_id].get('bans', 0) + 1
            modstats_db.set(guild_id, guild_stats)
            
            # Log to MySQL
            try:
                case_id = mysql_case_logs.log_case(
                    guild_id=guild_id,
                    case_type='ban',
                    user_id=str(member.id),
                    username=str(member),
                    moderator_id=mod_id,
                    moderator_name=str(ctx.author),
                    reason=reason,
                    additional_data={'delete_days': delete_days}
                )
                mysql_case_logs.log_ban(guild_id, str(member.id), str(member), mod_id, reason, False)
            except Exception as e:
                print(f"MySQL logging error: {e}")
            
            # Send to modlog channel
            await send_to_modlog(ctx.guild, 'ban', user=member, moderator=ctx.author, reason=reason, delete_days=delete_days)
            
            embed = success_embed(
                'Member Banned',
                f"{config.EMOJIS['ban']} **User:** {member.mention} (`{member.id}`)\\n**Reason:** {reason}"
            )
            if delete_days > 0:
                embed.description += f"\\n**Messages Deleted:** Last {delete_days} day(s)"
            try:
                if case_id:
                    embed.set_footer(text=f"Case #{case_id}")
            except:
                pass
            await ctx.reply(embed=embed)
        except Exception as e:
            await ctx.reply(embed=error_embed('Ban Failed', f'Could not ban member: {str(e)}'))
    
    @commands.command(name='unban', aliases=['ub'])
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: str = None, *, reason='No reason provided'):
        """Unban a user from the server"""
        if not user_id:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}unban <user_id> [reason]`'))
        
        try:
            # Convert to int
            user_id_int = int(user_id)
        except ValueError:
            return await ctx.reply(embed=error_embed('Invalid User ID', 'Please provide a valid user ID (numbers only).'))
        
        try:
            # Get user object
            user = await self.bot.fetch_user(user_id_int)
            
            # Unban the user
            await ctx.guild.unban(user, reason=f"{reason} | Unbanned by {ctx.author}")
            
            await ctx.reply(embed=success_embed(
                'User Unbanned',
                f"{config.EMOJIS['success']} **User:** {user.mention} (`{user.id}`)\\n**Reason:** {reason}"
            ))
        except discord.NotFound:
            await ctx.reply(embed=error_embed('Not Banned', 'This user is not currently banned.'))
        except Exception as e:
            await ctx.reply(embed=error_embed('Unban Failed', f'Could not unban user: {str(e)}'))
    
    @commands.command(name='kick', aliases=['k'])
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member = None, *, reason='No reason provided'):
        """Kick a member from the server"""
        if not member:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}kick <@user> [reason]`'))
        
        if not can_moderate_target(ctx.author, member):
            return await ctx.reply(embed=error_embed('Cannot Kick', 'You cannot kick this user due to role hierarchy.'))
        
        if not can_moderate_target(ctx.guild.me, member):
            return await ctx.reply(embed=error_embed('Cannot Kick', 'I cannot kick this user due to my role hierarchy.'))
        
        try:
            await member.kick(reason=f"{reason} | Kicked by {ctx.author}")
            
            # Update modstats
            from utils.database import modstats_db
            from utils.mysql_logs import mysql_case_logs
            guild_id = str(ctx.guild.id)
            mod_id = str(ctx.author.id)
            
            if not modstats_db.has(guild_id):
                modstats_db.set(guild_id, {})
            
            guild_stats = modstats_db.get(guild_id, {})
            if mod_id not in guild_stats:
                guild_stats[mod_id] = {'warns': 0, 'kicks': 0, 'bans': 0, 'jails': 0, 'mutes': 0}
            
            guild_stats[mod_id]['kicks'] = guild_stats[mod_id].get('kicks', 0) + 1
            modstats_db.set(guild_id, guild_stats)
            
            # Log to MySQL
            case_id = None
            try:
                case_id = mysql_case_logs.log_case(
                    guild_id=guild_id,
                    case_type='kick',
                    user_id=str(member.id),
                    username=str(member),
                    moderator_id=mod_id,
                    moderator_name=str(ctx.author),
                    reason=reason
                )
            except Exception as e:
                print(f"MySQL logging error: {e}")
            
            embed = success_embed(
                'Member Kicked',
                f"{config.EMOJIS['kick']} **User:** {member.mention} (`{member.id}`)\n**Reason:** {reason}"
            )
            if case_id:
                embed.set_footer(text=f"Case #{case_id}")
            await ctx.reply(embed=embed)
        except Exception as e:
            await ctx.reply(embed=error_embed('Kick Failed', f'Could not kick member: {str(e)}'))
    
    @commands.command(name='mute', aliases=['timeout'])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member = None, duration: str = None, *, reason='No reason provided'):
        """Timeout a member"""
        if not member or not duration:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}mute <@user> <duration> [reason]`\nExample: `,mute @user 10m Spamming`'))
        
        if not can_moderate_target(ctx.author, member):
            return await ctx.reply(embed=error_embed('Cannot Mute', 'You cannot mute this user due to role hierarchy.'))
        
        if not can_moderate_target(ctx.guild.me, member):
            return await ctx.reply(embed=error_embed('Cannot Mute', 'I cannot mute this user due to my role hierarchy.'))
        
        # Parse duration
        import re
        time_regex = r"(\d+)([smhd])"
        match = re.match(time_regex, duration)
        if not match:
            return await ctx.reply(embed=error_embed('Invalid Duration', 'Use format like: 10s, 5m, 1h, 7d'))
        
        amount, unit = int(match.group(1)), match.group(2)
        seconds = amount * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]
        
        if seconds > 2419200:  # 28 days max
            return await ctx.reply(embed=error_embed('Duration Too Long', 'Maximum timeout is 28 days.'))
        
        try:
            # Register action in transparency cache
            transparency_cog = self.bot.get_cog('Transparency')
            if transparency_cog:
                import time
                transparency_cog.action_cache[(ctx.guild.id, member.id)] = {
                    'action': 'mute',
                    'moderator': ctx.author,
                    'reason': reason,
                    'timestamp': time.time()
                }
            
            await member.timeout(discord.utils.utcnow() + timedelta(seconds=seconds), reason=f"{reason} | Muted by {ctx.author}")
            
            # Update modstats
            from utils.database import modstats_db
            guild_id = str(ctx.guild.id)
            mod_id = str(ctx.author.id)
            
            if not modstats_db.has(guild_id):
                modstats_db.set(guild_id, {})
            
            guild_stats = modstats_db.get(guild_id, {})
            if mod_id not in guild_stats:
                guild_stats[mod_id] = {'warns': 0, 'kicks': 0, 'bans': 0, 'jails': 0, 'mutes': 0}
            
            guild_stats[mod_id]['mutes'] = guild_stats[mod_id].get('mutes', 0) + 1
            modstats_db.set(guild_id, guild_stats)
            
            # Log to MySQL
            case_id = None
            try:
                from utils.mysql_logs import mysql_case_logs
                case_id = mysql_case_logs.log_case(
                    guild_id=guild_id,
                    case_type='mute',
                    user_id=str(member.id),
                    username=str(member),
                    moderator_id=mod_id,
                    moderator_name=str(ctx.author),
                    reason=reason,
                    duration=seconds
                )
            except Exception as e:
                print(f"MySQL logging error: {e}")
            
            embed = success_embed(
                'Member Muted',
                f"{config.EMOJIS['mute']} **User:** {member.mention}\n**Duration:** {duration}\n**Reason:** {reason}"
            )
            if case_id:
                embed.set_footer(text=f"Case #{case_id}")
            await ctx.reply(embed=embed)
        except Exception as e:
            await ctx.reply(embed=error_embed('Mute Failed', f'Could not mute member: {str(e)}'))
    
    @commands.command(name='unmute', aliases=['untimeout'])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member = None, *, reason='No reason provided'):
        """Remove timeout from a member"""
        if not member:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}unmute <@user> [reason]`'))
        
        if not member.is_timed_out():
            return await ctx.reply(embed=error_embed('Not Muted', 'This user is not currently muted.'))
        
        try:
            # Register action in transparency cache
            transparency_cog = self.bot.get_cog('Transparency')
            if transparency_cog:
                import time
                transparency_cog.action_cache[(ctx.guild.id, member.id)] = {
                    'action': 'unmute',
                    'moderator': ctx.author,
                    'reason': reason,
                    'timestamp': time.time()
                }
            
            await member.timeout(None, reason=f"{reason} | Unmuted by {ctx.author}")
            await ctx.reply(embed=success_embed(
                'Member Unmuted',
                f"{config.EMOJIS['success']} **User:** {member.mention}\n**Reason:** {reason}"
            ))
        except Exception as e:
            await ctx.reply(embed=error_embed('Unmute Failed', f'Could not unmute member: {str(e)}'))
    
    @commands.command(name='clear', aliases=['purge', 'clean'])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = None, member: discord.Member = None):
        """Bulk delete messages
        
        Usage:
          ,purge <amount> - Delete last X messages
          ,purge <amount> @user - Delete last X messages from specific user
        
        Examples:
          ,purge 10 - Delete last 10 messages
          ,purge 50 @user - Delete last 50 messages from @user
        """
        if not amount or amount < 1 or amount > 100:
            return await ctx.reply(embed=error_embed(
                'Invalid Amount', 
                f'Please specify a number between 1 and 100.\n\n'
                f'**Usage:**\n'
                f'`{config.PREFIX}purge <amount>` - Delete messages\n'
                f'`{config.PREFIX}purge <amount> @user` - Delete user\'s messages'
            ))
        
        try:
            # Register action in transparency cache
            transparency_cog = self.bot.get_cog('Transparency')
            if transparency_cog:
                import time
                transparency_cog.action_cache[(ctx.guild.id, ctx.channel.id)] = {
                    'action': 'purge',
                    'moderator': ctx.author,
                    'timestamp': time.time()
                }
            
            def check(msg):
                # Don't delete Disboard bump messages
                if msg.author.bot and msg.author.id == 302050872383242240:  # DISBOARD bot ID
                    return False
                if member:
                    return msg.author == member
                return True
            
            # If filtering by user, check more messages to find enough from that user
            limit_to_check = amount * 3 if member else amount + 1
            deleted = await ctx.channel.purge(limit=limit_to_check, check=check)
            
            # Create success message
            if member:
                description = f"{config.EMOJIS['success']} Deleted **{len(deleted) - 1}** message(s) from {member.mention}"
            else:
                description = f"{config.EMOJIS['success']} Deleted **{len(deleted) - 1}** message(s)"
            
            msg = await ctx.send(embed=success_embed('Messages Cleared', description))
            await msg.delete(delay=2)
        except Exception as e:
            await ctx.reply(embed=error_embed('Clear Failed', f'Could not delete messages: {str(e)}'))

    @commands.command(name='purgeafter', aliases=['clearafter'])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_after(self, ctx, value: str = None):
        """Delete messages after a replied-to message or within a time window.

        Usage:
          ,purgeafter <amount> - Reply to a message and delete up to X messages after it
          ,purgeafter <duration> - Delete messages from the last 10s, 5m, 2h, or 1d
        """
        usage = (
            f'**Usage:**\n'
            f'Reply to a message with `{config.PREFIX}purgeafter <amount>` (1-100)\n'
            f'Or use `{config.PREFIX}purgeafter <duration>` (for example: `30m`, `2h`, `1d`)'
        )
        if not value:
            return await ctx.reply(embed=error_embed('Invalid Usage', usage))

        reference = ctx.message.reference
        if reference and reference.message_id:
            try:
                amount = int(value)
            except ValueError:
                return await ctx.reply(embed=error_embed(
                    'Invalid Amount',
                    f'When replying to a message, specify a number between 1 and 100.\n\n{usage}'
                ))

            if amount < 1 or amount > 100:
                return await ctx.reply(embed=error_embed(
                    'Invalid Amount',
                    f'Please specify a number between 1 and 100.\n\n{usage}'
                ))

            try:
                target = reference.resolved
                if not isinstance(target, discord.Message):
                    target = await ctx.channel.fetch_message(reference.message_id)
            except (discord.NotFound, discord.Forbidden):
                return await ctx.reply(embed=error_embed(
                    'Message Not Found',
                    'I could not access the message you replied to.'
                ))

            after = target
            limit = amount + 1  # Include the purgeafter command itself.
            window_label = f'after the replied-to message (up to {amount})'
        else:
            match = re.fullmatch(r'(\d+)([smhd])', value.lower())
            if not match:
                return await ctx.reply(embed=error_embed(
                    'Invalid Time',
                    f'Use a duration such as `30s`, `10m`, `2h`, or `1d`.\n\n{usage}'
                ))

            amount, unit = int(match.group(1)), match.group(2)
            seconds = amount * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]
            if seconds < 1 or seconds > 14 * 86400:
                return await ctx.reply(embed=error_embed(
                    'Invalid Time',
                    'The time window must be between 1 second and 14 days.'
                ))

            after = discord.utils.utcnow() - timedelta(seconds=seconds)
            limit = 101  # At most 100 messages, plus the command message.
            window_label = f'from the last {value.lower()} (up to 100)'

        try:
            transparency_cog = self.bot.get_cog('Transparency')
            if transparency_cog:
                import time
                transparency_cog.action_cache[(ctx.guild.id, ctx.channel.id)] = {
                    'action': 'purge',
                    'moderator': ctx.author,
                    'timestamp': time.time()
                }

            def check(msg):
                # Preserve DISBOARD bump messages, as the regular purge command does.
                return not (msg.author.bot and msg.author.id == 302050872383242240)

            deleted = await ctx.channel.purge(limit=limit, after=after, check=check)
            deleted_count = sum(message.id != ctx.message.id for message in deleted)
            description = (
                f"{config.EMOJIS['success']} Deleted **{deleted_count}** message(s) {window_label}."
            )
            message = await ctx.send(embed=success_embed('Messages Cleared', description))
            await message.delete(delay=3)
        except Exception as e:
            await ctx.reply(embed=error_embed(
                'Purge After Failed',
                f'Could not delete messages: {str(e)}'
            ))

    async def _filtered_clear(self, ctx, amount: int, check, title: str, empty_message: str):
        if not amount or amount < 1 or amount > 100:
            return await ctx.reply(embed=error_embed(
                'Invalid Amount',
                f'Please specify a number between 1 and 100.\n\n'
                f'**Usage:** `{config.PREFIX}{ctx.command.name} <amount>`'
            ))

        try:
            transparency_cog = self.bot.get_cog('Transparency')
            if transparency_cog:
                import time
                transparency_cog.action_cache[(ctx.guild.id, ctx.channel.id)] = {
                    'action': 'purge',
                    'moderator': ctx.author,
                    'timestamp': time.time()
                }

            deleted = await ctx.channel.purge(limit=amount + 1, check=check)
            deleted_count = max(0, len(deleted) - 1)
            description = (
                f"{config.EMOJIS['success']} Deleted **{deleted_count}** message(s)."
                if deleted_count else empty_message
            )
            msg = await ctx.send(embed=success_embed(title, description))
            await msg.delete(delay=3)
        except Exception as e:
            await ctx.reply(embed=error_embed('Clear Failed', f'Could not delete messages: {str(e)}'))

    @commands.command(name='clearnonbots', aliases=['clearhumans', 'purgehumans'])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear_non_bots(self, ctx, amount: int = None):
        """Delete only non-bot messages from recent chat"""
        def check(msg):
            return not msg.author.bot

        await self._filtered_clear(
            ctx,
            amount,
            check,
            'Non-Bot Messages Cleared',
            'No non-bot messages matched in that range.'
        )

    @commands.command(name='clearnonmedia', aliases=['cleartext', 'purgetext'])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear_non_media(self, ctx, amount: int = None):
        """Delete only messages without media attachments/embeds"""
        def has_media(msg):
            if msg.attachments:
                return True
            if msg.stickers:
                return True
            return any(embed.image or embed.thumbnail or embed.video for embed in msg.embeds)

        await self._filtered_clear(
            ctx,
            amount,
            lambda msg: not has_media(msg),
            'Non-Media Messages Cleared',
            'No non-media messages matched in that range.'
        )
    
    @commands.command(name='warn', aliases=['warning'])
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member = None, *, reason='No reason provided'):
        """Warn a member"""
        if not member:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}warn <@user> [reason]`'))
        
        if not can_moderate_target(ctx.author, member):
            return await ctx.reply(embed=error_embed('Cannot Warn', 'You cannot warn this user due to role hierarchy.'))
        
        try:
            from utils.database import warnings_db, modstats_db
            import time
            
            # Get guild warnings
            guild_id = str(ctx.guild.id)
            if not warnings_db.has(guild_id):
                warnings_db.set(guild_id, {})
            
            guild_warnings = warnings_db.get(guild_id, {})
            user_id = str(member.id)
            
            if user_id not in guild_warnings:
                guild_warnings[user_id] = []
            
            # Add warning
            warning = {
                'reason': reason,
                'moderator': str(ctx.author.id),
                'moderator_name': str(ctx.author),
                'timestamp': int(time.time())
            }
            guild_warnings[user_id].append(warning)
            warnings_db.set(guild_id, guild_warnings)
            
            # Update modstats
            mod_id = str(ctx.author.id)
            if not modstats_db.has(guild_id):
                modstats_db.set(guild_id, {})
            
            guild_stats = modstats_db.get(guild_id, {})
            if mod_id not in guild_stats:
                guild_stats[mod_id] = {'warns': 0, 'kicks': 0, 'bans': 0, 'jails': 0, 'mutes': 0}
            
            guild_stats[mod_id]['warns'] = guild_stats[mod_id].get('warns', 0) + 1
            modstats_db.set(guild_id, guild_stats)
            
            # Log to MySQL
            case_id = None
            try:
                from utils.mysql_logs import mysql_case_logs
                case_id = mysql_case_logs.log_case(
                    guild_id=guild_id,
                    case_type='warn',
                    user_id=str(member.id),
                    username=str(member),
                    moderator_id=mod_id,
                    moderator_name=str(ctx.author),
                    reason=reason
                )
            except Exception as e:
                print(f"MySQL logging error: {e}")
            
            warn_count = len(guild_warnings[user_id])
            
            embed = success_embed(
                'Member Warned',
                f"{config.EMOJIS['warning']} **User:** {member.mention}\n**Reason:** {reason}\n**Total Warnings:** {warn_count}"
            )
            if case_id:
                embed.set_footer(text=f"Case #{case_id}")
            await ctx.reply(embed=embed)
            
            # Try to DM the user
            try:
                dm_embed = discord.Embed(
                    title='⚠️ Warning',
                    description=f'You have been warned in **{ctx.guild.name}**\n**Reason:** {reason}\n**Total Warnings:** {warn_count}',
                    color=config.COLORS['warning']
                )
                await member.send(embed=dm_embed)
            except:
                pass
                
        except Exception as e:
            await ctx.reply(embed=error_embed('Warning Failed', f'Could not warn member: {str(e)}'))
    
    @commands.command(name='jail')
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def jail(self, ctx, member: discord.Member = None, duration: str = None, *, reason='No reason provided'):
        """Jail a member by removing roles and adding jail role"""
        if not member:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}jail <@user> [duration] [reason]`\\nExample: `,jail @user 10m Spamming`'))
        
        if not can_moderate_target(ctx.author, member):
            return await ctx.reply(embed=error_embed('Cannot Jail', 'You cannot jail this user due to role hierarchy.'))
        
        if not can_moderate_target(ctx.guild.me, member):
            return await ctx.reply(embed=error_embed('Cannot Jail', 'I cannot jail this user due to my role hierarchy.'))
        
        try:
            from utils.database import jail_db, modstats_db, config_db
            import time
            
            # Define guild_id early to avoid scope issues
            guild_id = str(ctx.guild.id)
            
            # Parse duration if provided
            duration_seconds = None
            duration_text = "Permanent"
            if duration and duration.lower() not in ['perm', 'permanent']:
                import re
                time_regex = r"(\d+)([smhd])"
                match = re.match(time_regex, duration)
                if match:
                    amount, unit = int(match.group(1)), match.group(2)
                    duration_seconds = amount * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]
                    duration_text = duration
                else:
                    # Duration is actually part of reason
                    reason = f"{duration} {reason}"
            elif duration:
                reason = f"{duration} {reason}" if duration.lower() in ['perm', 'permanent'] else reason
            
            # Get or create jailed role
            jailed_role = discord.utils.get(ctx.guild.roles, name="Jailed")
            if not jailed_role:
                try:
                    jailed_role = await ctx.guild.create_role(
                        name="Jailed",
                        color=discord.Color.dark_gray(),
                        reason="Auto-created for jail system"
                    )
                except discord.Forbidden:
                    return await ctx.reply(embed=error_embed(
                        'Permission Error',
                        '❌ I lack permission to create roles. Please ensure my role has "Manage Roles" permission and is positioned higher in the role hierarchy.'
                    ))
            
            # Check if bot's role can modify the jailed role
            if jailed_role >= ctx.guild.me.top_role:
                return await ctx.reply(embed=error_embed(
                    'Role Hierarchy Error',
                    f'❌ The "Jailed" role is equal to or higher than my highest role.\n\n**Fix:** Move my role **above** the "Jailed" role in Server Settings > Roles.'
                ))
            
            # Check if any of the member's roles are higher than bot's role
            for role in member.roles:
                if role >= ctx.guild.me.top_role and role != ctx.guild.default_role:
                    return await ctx.reply(embed=error_embed(
                        'Role Hierarchy Error',
                        f'❌ {member.mention} has roles higher than or equal to my highest role. I cannot jail them.'
                    ))
            
            # Store current roles
            role_ids = [str(role.id) for role in member.roles if role != ctx.guild.default_role and role != jailed_role]
            
            # Auto-configure jail channel permissions
            try:
                guild_config = config_db.get(guild_id, {})
                jail_channel_id = guild_config.get('jail_channel')
                jail_channel = None
                
                # Collect permission update tasks for concurrent execution
                import asyncio
                permission_tasks = []
                
                for channel in ctx.guild.channels:
                    if jail_channel_id and channel.id == int(jail_channel_id):
                        # Save the jail channel reference for later
                        jail_channel = channel
                    else:
                        # Add task to deny view access to all other channels
                        permission_tasks.append(
                            channel.set_permissions(
                                jailed_role,
                                view_channel=False,
                                reason='Jail: Restrict access'
                            )
                        )
                
                # Execute all permission updates concurrently (MUCH FASTER!)
                if permission_tasks:
                    await asyncio.gather(*permission_tasks, return_exceptions=True)
                
                # Now explicitly allow access to jail channel (do this AFTER restricting others)
                if jail_channel:
                    try:
                        await jail_channel.set_permissions(
                            jailed_role,
                            view_channel=True,
                            send_messages=True,
                            attach_files=True,
                            read_message_history=True,
                            add_reactions=True,
                            reason='Jail: Allow jail channel access'
                        )
                    except Exception as perm_error:
                        print(f"Could not set jail channel permissions: {perm_error}")
                else:
                    print(f"Warning: Jail channel not configured or not found (ID: {jail_channel_id})")
            except Exception as e:
                print(f"Warning: Could not set all channel permissions: {e}")
            
            # Remove all roles and add jailed role
            try:
                roles_to_remove = [r for r in member.roles if r != ctx.guild.default_role]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason=f"Jailed by {ctx.author}")
                await member.add_roles(jailed_role, reason=f"Jailed by {ctx.author}: {reason}")
            except discord.Forbidden as e:
                return await ctx.reply(embed=error_embed(
                    'Permission Error',
                    f'❌ Could not modify roles: Missing permissions.\n\n**Ensure:**\n• My role is higher than the target\'s roles\n• I have "Manage Roles" permission\n\n**Error:** {str(e)}'
                ))
            except Exception as e:
                return await ctx.reply(embed=error_embed('Jail Failed', f'Could not modify roles: {str(e)}'))
            
            # Save to database
            if not jail_db.has(guild_id):
                jail_db.set(guild_id, {})
            
            guild_jails = jail_db.get(guild_id, {})
            guild_jails[str(member.id)] = {
                'roles': role_ids,
                'reason': reason,
                'moderator': str(ctx.author.id),
                'timestamp': int(time.time()),
                'duration': duration_seconds,
                'duration_text': duration_text
            }
            jail_db.set(guild_id, guild_jails)
            
            # Update modstats
            mod_id = str(ctx.author.id)
            if not modstats_db.has(guild_id):
                modstats_db.set(guild_id, {})
            
            guild_stats = modstats_db.get(guild_id, {})
            if mod_id not in guild_stats:
                guild_stats[mod_id] = {'warns': 0, 'kicks': 0, 'bans': 0, 'jails': 0, 'mutes': 0}
            
            guild_stats[mod_id]['jails'] = guild_stats[mod_id].get('jails', 0) + 1
            modstats_db.set(guild_id, guild_stats)
            
            # Log to MySQL
            case_id = None
            try:
                from utils.mysql_logs import mysql_case_logs
                case_id = mysql_case_logs.log_case(
                    guild_id=guild_id,
                    case_type='jail',
                    user_id=str(member.id),
                    username=str(member),
                    moderator_id=mod_id,
                    moderator_name=str(ctx.author),
                    reason=reason,
                    duration=duration_seconds
                )
            except Exception as e:
                print(f"MySQL logging error: {e}")
            
            embed = success_embed(
                'Member Jailed',
                f"{config.EMOJIS['jail']} **User:** {member.mention}\\n**Duration:** {duration_text}\\n**Reason:** {reason}"
            )
            if case_id:
                embed.set_footer(text=f"Case #{case_id}")
            await ctx.reply(embed=embed)
            
            # Try to DM the user
            try:
                dm_embed = discord.Embed(
                    title='⛓️ Jailed',
                    description=f'You have been jailed in **{ctx.guild.name}**\\n**Duration:** {duration_text}\\n**Reason:** {reason}',
                    color=config.COLORS['error']
                )
                await member.send(embed=dm_embed)
            except:
                pass
                
        except discord.Forbidden as e:
            await ctx.reply(embed=error_embed(
                'Permission Error',
                f'❌ Missing required permissions.\n\n**Ensure:**\n• I have "Manage Roles" permission\n• My role is higher in hierarchy\n\n**Error:** {str(e)}'
            ))
        except Exception as e:
            await ctx.reply(embed=error_embed('Jail Failed', f'Could not jail member: {str(e)}'))
    
    @commands.command(name='unjail')
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unjail(self, ctx, member: discord.Member = None, *, reason='No reason provided'):
        """Unjail a member and restore their roles"""
        if not member:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}unjail <@user> [reason]`'))
        
        try:
            from utils.database import jail_db
            
            guild_id = str(ctx.guild.id)
            if not jail_db.has(guild_id):
                return await ctx.reply(embed=error_embed('Not Jailed', 'This user is not currently jailed.'))
            
            guild_jails = jail_db.get(guild_id, {})
            user_id = str(member.id)
            
            if user_id not in guild_jails:
                return await ctx.reply(embed=error_embed('Not Jailed', 'This user is not currently jailed.'))
            
            # Get stored roles
            jail_data = guild_jails[user_id]
            role_ids = jail_data['roles']
            
            # Remove jailed role
            jailed_role = discord.utils.get(ctx.guild.roles, name="Jailed")
            if jailed_role in member.roles:
                await member.remove_roles(jailed_role)
            
            # Restore roles
            roles_to_add = []
            for role_id in role_ids:
                role = ctx.guild.get_role(int(role_id))
                if role:
                    roles_to_add.append(role)
            
            if roles_to_add:
                await member.add_roles(*roles_to_add)
            
            # Remove from database
            del guild_jails[user_id]
            jail_db.set(guild_id, guild_jails)
            
            await ctx.reply(embed=success_embed(
                'Member Unjailed',
                f"{config.EMOJIS['success']} **User:** {member.mention}\n**Reason:** {reason}"
            ))
            
            # Try to DM the user
            try:
                dm_embed = discord.Embed(
                    title='✅ Unjailed',
                    description=f'You have been unjailed in **{ctx.guild.name}**\n**Reason:** {reason}',
                    color=config.COLORS['success']
                )
                await member.send(embed=dm_embed)
            except:
                pass
                
        except Exception as e:
            await ctx.reply(embed=error_embed('Unjail Failed', f'Could not unjail member: {str(e)}'))
    
    @commands.command(name='jaillist', aliases=['jails'])
    @commands.has_permissions(manage_roles=True)
    async def jaillist(self, ctx):
        """Show all jailed members in the server"""
        try:
            from utils.database import jail_db
            
            guild_id = str(ctx.guild.id)
            if not jail_db.has(guild_id):
                return await ctx.reply(embed=error_embed('No Jails', 'No members are currently jailed in this server.'))
            
            guild_jails = jail_db.get(guild_id, {})
            
            if not guild_jails:
                return await ctx.reply(embed=error_embed('No Jails', 'No members are currently jailed in this server.'))
            
            embed = discord.Embed(
                title=f"{config.EMOJIS['jail']} Jailed Members",
                color=config.COLORS['primary']
            )
            
            import time
            for user_id, jail_data in guild_jails.items():
                member = ctx.guild.get_member(int(user_id))
                member_name = member.mention if member else f"Unknown User ({user_id})"
                
                moderator = ctx.guild.get_member(int(jail_data['moderator']))
                mod_name = moderator.name if moderator else jail_data['moderator']
                
                timestamp = jail_data['timestamp']
                duration_text = jail_data['duration_text']
                
                value = f"**Jailed by:** {mod_name}\n**Reason:** {jail_data['reason']}\n**Duration:** {duration_text}\n**Since:** <t:{timestamp}:R>"
                
                embed.add_field(name=member_name, value=value, inline=False)
            
            embed.set_footer(text=f'Total: {len(guild_jails)} jailed member(s)')
            await ctx.reply(embed=embed)
            
        except Exception as e:
            await ctx.reply(embed=error_embed('Error', f'Could not fetch jail list: {str(e)}'))
    
    @commands.command(name='modstats', aliases=['ms'])
    @commands.has_permissions(manage_messages=True)
    async def modstats(self, ctx, member: discord.Member = None):
        """Show moderation statistics"""
        try:
            from utils.database import modstats_db, warnings_db
            
            guild_id = str(ctx.guild.id)
            
            if member:
                # Show stats for specific moderator
                if not modstats_db.has(guild_id):
                    return await ctx.reply(embed=error_embed('No Stats', 'No moderation statistics available.'))
                
                guild_stats = modstats_db.get(guild_id, {})
                mod_id = str(member.id)
                
                if mod_id not in guild_stats:
                    return await ctx.reply(embed=error_embed('No Stats', f'{member.mention} has no moderation actions recorded.'))
                
                stats = guild_stats[mod_id]
                
                embed = discord.Embed(
                    title=f"{config.EMOJIS['shield']} Moderation Stats - {member.name}",
                    color=config.COLORS['primary']
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.add_field(name='Warnings', value=stats.get('warns', 0), inline=True)
                embed.add_field(name='Kicks', value=stats.get('kicks', 0), inline=True)
                embed.add_field(name='Bans', value=stats.get('bans', 0), inline=True)
                embed.add_field(name='Jails', value=stats.get('jails', 0), inline=True)
                embed.add_field(name='Mutes', value=stats.get('mutes', 0), inline=True)
                
                total = sum(stats.values())
                embed.add_field(name='Total Actions', value=total, inline=True)
                
            else:
                # Show server-wide stats
                embed = discord.Embed(
                    title=f"{config.EMOJIS['shield']} Server Moderation Stats",
                    description=f'**{ctx.guild.name}**',
                    color=config.COLORS['primary']
                )
                
                # Count total warnings
                total_warnings = 0
                if warnings_db.has(guild_id):
                    guild_warnings = warnings_db.get(guild_id, {})
                    total_warnings = sum(len(warns) for warns in guild_warnings.values())
                
                # Count total actions by moderators
                total_actions = {'warns': 0, 'kicks': 0, 'bans': 0, 'jails': 0, 'mutes': 0}
                if modstats_db.has(guild_id):
                    guild_stats = modstats_db.get(guild_id, {})
                    for mod_stats in guild_stats.values():
                        for action, count in mod_stats.items():
                            total_actions[action] = total_actions.get(action, 0) + count
                
                embed.add_field(name='Total Warnings', value=total_warnings, inline=True)
                embed.add_field(name='Total Kicks', value=total_actions.get('kicks', 0), inline=True)
                embed.add_field(name='Total Bans', value=total_actions.get('bans', 0), inline=True)
                embed.add_field(name='Total Jails', value=total_actions.get('jails', 0), inline=True)
                embed.add_field(name='Total Mutes', value=total_actions.get('mutes', 0), inline=True)
                
                total = sum(total_actions.values())
                embed.add_field(name='Total Actions', value=total, inline=True)
            
            await ctx.reply(embed=embed)
            
        except Exception as e:
            await ctx.reply(embed=error_embed('Error', f'Could not fetch stats: {str(e)}'))
    
    @commands.command(name='nick', aliases=['nickname'])
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def nick(self, ctx, member: discord.Member = None, *, nickname: str = None):
        """Change a member's nickname"""
        if not member:
            return await ctx.reply(embed=error_embed('Invalid Usage', f'Usage: `{config.PREFIX}nick <@user> <new_nickname>`\nUse `{config.PREFIX}nick <@user> reset` to reset nickname'))
        
        if not can_moderate_target(ctx.author, member):
            return await ctx.reply(embed=error_embed('Cannot Change Nickname', 'You cannot change this user\'s nickname due to role hierarchy.'))
        
        if not can_moderate_target(ctx.guild.me, member):
            return await ctx.reply(embed=error_embed('Cannot Change Nickname', 'I cannot change this user\'s nickname due to my role hierarchy.'))
        
        try:
            old_nick = member.nick or member.name
            
            if nickname and nickname.lower() == 'reset':
                await member.edit(nick=None)
                await ctx.reply(embed=success_embed(
                    'Nickname Reset',
                    f"{config.EMOJIS['success']} Reset nickname for {member.mention}\n**Old:** {old_nick}\n**New:** {member.name}"
                ))
            elif nickname:
                if len(nickname) > 32:
                    return await ctx.reply(embed=error_embed('Nickname Too Long', 'Nicknames must be 32 characters or less.'))
                
                await member.edit(nick=nickname)
                await ctx.reply(embed=success_embed(
                    'Nickname Changed',
                    f"{config.EMOJIS['success']} Changed nickname for {member.mention}\\n**Old:** {old_nick}\\n**New:** {nickname}"
                ))
            else:
                return await ctx.reply(embed=error_embed('No Nickname', f'Usage: `{config.PREFIX}nick <@user> <new_nickname>`'))
                
        except Exception as e:
            await ctx.reply(embed=error_embed('Nickname Change Failed', f'Could not change nickname: {str(e)}'))
    
    @commands.command(name='jail_setup')
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def jail_setup(self, ctx):
        """Auto-configure jail role permissions across the server"""
        setup_msg = await ctx.reply(embed=success_embed(
            'Jail Setup Started',
            f'{config.EMOJIS["loading"]} Setting up jail system...'
        ))
        
        # Get or create Jailed role
        jailed_role = discord.utils.get(ctx.guild.roles, name='Jailed')
        if not jailed_role:
            jailed_role = await ctx.guild.create_role(
                name='Jailed',
                color=discord.Color.dark_gray(),
                reason='Jail system setup'
            )
        
        # Ask for jail channel
        await ctx.send(embed=success_embed(
            'Jail Channel Setup',
            'Please mention the channel where jailed users can talk (e.g., #jail)\\nType `cancel` to abort.'
        ))
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            msg = await self.bot.wait_for('message', timeout=60.0, check=check)
            
            if msg.content.lower() == 'cancel':
                return await ctx.send(embed=error_embed('Setup Cancelled', 'Jail setup has been cancelled.'))
            
            if not msg.channel_mentions:
                return await ctx.send(embed=error_embed('No Channel', 'Please mention a valid channel.'))
            
            jail_channel = msg.channel_mentions[0]
            
        except asyncio.TimeoutError:
            return await ctx.send(embed=error_embed('Timeout', 'Setup timed out. Please try again.'))
        
        # Configure permissions for all channels
        processed = 0
        total = len(ctx.guild.channels)
        
        for channel in ctx.guild.channels:
            try:
                if channel == jail_channel:
                    # Allow view, send messages, send media in jail channel
                    await channel.set_permissions(
                        jailed_role,
                        view_channel=True,
                        send_messages=True,
                        attach_files=True,
                        read_message_history=True,
                        reason='Jail setup - jail channel permissions'
                    )
                else:
                    # Deny view_channel in all other channels
                    await channel.set_permissions(
                        jailed_role,
                        view_channel=False,
                        reason='Jail setup - restrict access'
                    )
                processed += 1
                
                if processed % 10 == 0:
                    await setup_msg.edit(embed=success_embed(
                        'Jail Setup in Progress',
                        f'{config.EMOJIS["loading"]} Configuring channels... ({processed}/{total})'
                    ))
            except:
                pass
        
        # Save jail channel to config
        from utils.database import config_db
        guild_id = str(ctx.guild.id)
        if not config_db.has(guild_id):
            config_db.set(guild_id, {})
        
        guild_config = config_db.get(guild_id, {})
        guild_config['jail_channel'] = str(jail_channel.id)
        config_db.set(guild_id, guild_config)
        
        await setup_msg.edit(embed=success_embed(
            'Jail Setup Complete!',
            f'{config.EMOJIS["success"]} **Role:** {jailed_role.mention}\\n'
            f'**Jail Channel:** {jail_channel.mention}\\n'
            f'**Channels Configured:** {processed}/{total}\\n\\n'
            f'Jailed users will only be able to see and message in {jail_channel.mention}!'
        ))
    
    @commands.command(name='lock', aliases=['lockdown'])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: discord.TextChannel = None):
        """Lock a channel (prevent @everyone from sending messages)"""
        channel = channel or ctx.channel
        
        try:
            await channel.set_permissions(
                ctx.guild.default_role,
                send_messages=False,
                reason=f'Channel locked by {ctx.author}'
            )
            
            await ctx.reply(embed=success_embed(
                'Channel Locked',
                f'{config.EMOJIS["lock"]} {channel.mention} has been locked.\n@everyone can no longer send messages.'
            ))
        except Exception as e:
            await ctx.reply(embed=error_embed('Lock Failed', f'Could not lock channel: {str(e)}'))
    
    @commands.command(name='unlock')
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        """Unlock a channel (allow @everyone to send messages)"""
        channel = channel or ctx.channel
        
        try:
            # Restore send_messages permission (set to None to inherit)
            await channel.set_permissions(
                ctx.guild.default_role,
                send_messages=None,
                reason=f'Channel unlocked by {ctx.author}'
            )
            
            await ctx.reply(embed=success_embed(
                'Channel Unlocked',
                f'{config.EMOJIS["unlock"]} {channel.mention} has been unlocked.\n@everyone can now send messages.'
            ))
        except Exception as e:
            await ctx.reply(embed=error_embed('Unlock Failed', f'Could not unlock channel: {str(e)}'))
    
    @commands.command(name='modlog_setup', aliases=['logsetup'])
    @commands.has_permissions(administrator=True)
    async def modlog_setup(self, ctx, channel: discord.TextChannel = None):
        """Set the moderation log channel"""
        if not channel:
            return await ctx.reply(embed=error_embed('No Channel', f'Usage: `{config.PREFIX}modlog_setup #channel`'))
        
        from utils.database import config_db
        guild_id = str(ctx.guild.id)
        
        if not config_db.has(guild_id):
            config_db.set(guild_id, {})
        
        guild_config = config_db.get(guild_id, {})
        guild_config['modlog_channel'] = str(channel.id)
        config_db.set(guild_id, guild_config)
        
        await ctx.reply(embed=success_embed(
            'Modlog Channel Set',
            f'{config.EMOJIS["log"]} Moderation logs will be sent to {channel.mention}'
        ))
    
    # =====================================================
    # CASES COMMAND - View User Moderation History
    # =====================================================
    @discord.app_commands.command(name="cases", description="View moderation history for a user")
    @discord.app_commands.describe(user="The user to check cases for")
    @discord.app_commands.checks.has_permissions(moderate_members=True)
    async def cases(self, interaction: discord.Interaction, user: discord.User):
        """View all moderation cases for a specific user"""
        await interaction.response.defer()
        
        try:
            from utils.mysql_logs import mysql_case_logs
            guild_id = str(interaction.guild.id)
            user_id = str(user.id)
            
            # Fetch all cases for this user
            cases = mysql_case_logs.get_user_cases(guild_id, user_id, limit=50)
            
            if not cases:
                embed = discord.Embed(
                    title="📋 No Cases Found",
                    description=f"{user.mention} has no moderation history in this server.",
                    color=0x95a5a6  # Gray
                )
                embed.set_thumbnail(url=user.display_avatar.url)
                return await interaction.followup.send(embed=embed)
            
            # Calculate statistics
            stats = {
                'warn': 0,
                'kick': 0,
                'ban': 0,
                'mute': 0,
                'jail': 0,
                'unban': 0,
                'unmute': 0,
                'unjail': 0
            }
            
            for case in cases:
                case_type = case['case_type']
                if case_type in stats:
                    stats[case_type] += 1
            
            # Create main embed
            embed = discord.Embed(
                title=f"📋 Moderation Cases for {user.name}",
                description=f"Total: **{len(cases)}** case(s)",
                color=0xe74c3c if stats['ban'] > 0 else 0xf39c12 if stats['warn'] > 3 else 0x3498db,
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            
            # Add statistics
            punishments = []
            if stats['warn'] > 0:
                punishments.append(f"⚠️ Warns: **{stats['warn']}**")
            if stats['kick'] > 0:
                punishments.append(f"👢 Kicks: **{stats['kick']}**")
            if stats['ban'] > 0:
                punishments.append(f"🔨 Bans: **{stats['ban']}**")
            if stats['mute'] > 0:
                punishments.append(f"🔇 Mutes: **{stats['mute']}**")
            if stats['jail'] > 0:
                punishments.append(f"⛓️ Jails: **{stats['jail']}**")
            
            if punishments:
                embed.add_field(
                    name="📊 Statistics",
                    value=" • ".join(punishments),
                    inline=False
                )
            
            # Display recent cases (up to 10)
            case_list = []
            for case in cases[:10]:
                case_type_emoji = {
                    'warn': '⚠️',
                    'kick': '👢',
                    'ban': '🔨',
                    'mute': '🔇',
                    'jail': '⛓️',
                    'unban': '🔓',
                    'unmute': '🔊',
                    'unjail': '🔗'
                }
                
                emoji = case_type_emoji.get(case['case_type'], '📌')
                case_type = case['case_type'].upper()
                case_id = case['case_id']
                moderator = case['moderator_name']
                reason = case['reason'][:50] + "..." if len(case['reason']) > 50 else case['reason']
                timestamp = f"<t:{case['timestamp']}:R>"
                
                case_text = f"{emoji} **Case #{case_id}** • {case_type}\n"
                case_text += f"├ Moderator: `{moderator}`\n"
                case_text += f"├ Reason: *{reason}*\n"
                case_text += f"└ {timestamp}\n"
                
                case_list.append(case_text)
            
            if case_list:
                embed.add_field(
                    name=f"📜 Recent Cases (Showing {len(case_list)} of {len(cases)})",
                    value="\n".join(case_list),
                    inline=False
                )
            
            embed.set_footer(text=f"User ID: {user.id} • Requested by {interaction.user.name}")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error fetching cases: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
