import discord
from discord.ext import commands
from utils.embeds import success_embed, error_embed, info_embed
from utils.permissions import is_owner
from utils.database import blacklist_db
from utils.premium import grant_premium, revoke_premium, get_all_premium, PREMIUM_COMMANDS
import config
import os
import sys
import psutil
import time
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'database'))
from models import Database, GlobalBan, BotToggle, BotProfileAccess

start_time = time.time()

class Owner(commands.Cog):
    """Owner-only commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.maintenance_mode = False
    
    # ========================
    # EXISTING COMMANDS
    # ========================
    
    @commands.command(name='eval')
    @is_owner()
    async def eval_command(self, ctx, *, code: str = None):
        """Execute Python code (DANGEROUS - Owner only)"""
        if not code:
            return await ctx.reply(embed=error_embed('No Code', f'Usage: `{config.PREFIX}eval <code>`'))
        
        # Remove code blocks if present
        if code.startswith('```') and code.endswith('```'):
            code = code[3:-3]
            if code.startswith('py\n') or code.startswith('python\n'):
                code = '\n'.join(code.split('\n')[1:])
        
        try:
            result = eval(code)
            embed = success_embed('Eval Success', f'```py\n{result}\n```')
        except Exception as e:
            embed = error_embed('Eval Error', f'```py\n{type(e).__name__}: {e}\n```')
        
        await ctx.reply(embed=embed)
    
    @commands.command(name='reload')
    @is_owner()
    async def reload(self, ctx, cog: str = None):
        """Reload a cog"""
        if not cog:
            return await ctx.reply(embed=error_embed('No Cog', f'Usage: `{config.PREFIX}reload <cog_name>`'))
        
        try:
            await self.bot.reload_extension(f'cogs.{cog}')
            await ctx.reply(embed=success_embed('Cog Reloaded', f'Successfully reloaded `{cog}`.'))
        except Exception as e:
            await ctx.reply(embed=error_embed('Reload Failed', f'```{e}```'))
    
    @commands.command(name='stats')
    @is_owner()
    async def stats(self, ctx):
        """Show bot statistics"""
        process = psutil.Process(os.getpid())
        memory_usage = process.memory_info().rss / 1024 ** 2  # Convert to MB
        uptime = int(time.time() - start_time)
        
        embed = discord.Embed(
            title=f"{config.EMOJIS['crown']} Bot Statistics",
            color=config.COLORS['primary']
        )
        
        embed.add_field(name='Servers', value=len(self.bot.guilds), inline=True)
        embed.add_field(name='Users', value=len(self.bot.users), inline=True)
        embed.add_field(name='Commands', value=len(self.bot.commands), inline=True)
        embed.add_field(name='Memory', value=f'{memory_usage:.2f} MB', inline=True)
        embed.add_field(name='Uptime', value=f'<t:{int(start_time)}:R>', inline=True)
        embed.add_field(name='Latency', value=f'{round(self.bot.latency * 1000)}ms', inline=True)
        
        await ctx.reply(embed=embed)
    
    @commands.command(name='servers')
    @is_owner()
    async def servers(self, ctx):
        """List all servers"""
        guilds = self.bot.guilds
        
        description = '\n'.join([
            f"**{guild.name}** - {guild.member_count} members (ID: `{guild.id}`)"
            for guild in guilds[:10]
        ])
        
        embed = discord.Embed(
            title=f"{config.EMOJIS['shield']} Server List ({len(guilds)} total)",
            description=description,
            color=config.COLORS['primary']
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name='blacklist', aliases=['bl'])
    @is_owner()
    async def blacklist(self, ctx, action: str = None, user_id: int = None):
        """Manage user blacklist"""
        if not action or action.lower() not in ['add', 'remove', 'list']:
            return await ctx.reply(embed=error_embed('Invalid Action', f'Usage: `{config.PREFIX}blacklist <add|remove|list> [user_id]`'))
        
        if action.lower() == 'list':
            blacklisted = blacklist_db.all()
            if not blacklisted:
                return await ctx.reply(embed=info_embed('Blacklist', 'No users are blacklisted.'))
            
            desc = '\n'.join([f"<@{uid}> (`{uid}`)" for uid in blacklisted.keys()])
            await ctx.reply(embed=info_embed('Blacklisted Users', desc))
        
        elif action.lower() == 'add':
            if not user_id:
                return await ctx.reply(embed=error_embed('No User ID', f'Usage: `{config.PREFIX}blacklist add <user_id>`'))
            
            blacklist_db.set(str(user_id), True)
            await ctx.reply(embed=success_embed('User Blacklisted', f'User `{user_id}` has been blacklisted.'))
        
        elif action.lower() == 'remove':
            if not user_id:
                return await ctx.reply(embed=error_embed('No User ID', f'Usage: `{config.PREFIX}blacklist remove <user_id>`'))
            
            blacklist_db.delete(str(user_id))
            await ctx.reply(embed=success_embed('User Unblacklisted', f'User `{user_id}` has been removed from blacklist.'))
    
    @commands.command(name='synccommands', aliases=['sync'])
    @is_owner()
    async def sync(self, ctx):
        """Sync all slash commands globally"""
        try:
            await ctx.reply(embed=success_embed('Syncing Commands', '⏳ Syncing slash commands globally...'))
            
            # Sync commands globally
            synced = await self.bot.tree.sync()
            
            await ctx.send(embed=success_embed(
                'Commands Synced!',
                f'✅ Successfully synced **{len(synced)}** slash command(s) globally.\n\n'
                f'**Note:** It may take up to 1 hour for Discord to update slash commands globally.'
            ))
        except Exception as e:
            await ctx.send(embed=error_embed('Sync Failed', f'```{e}```'))
    
    @commands.command(name='checkowner', aliases=['amowner', 'ownercheck'])
    async def checkowner(self, ctx):
        """Check if you're an owner"""
        is_owner_check = ctx.author.id in config.OWNER_IDS
        
        embed = discord.Embed(
            title=f"{config.EMOJIS.get('info', 'ℹ️')} Owner Check",
            description=f"**User:** {ctx.author.mention}\n"
                       f"**User ID:** `{ctx.author.id}`\n"
                       f"**Is Owner:** {'✅ Yes' if is_owner_check else '❌ No'}\n\n"
                       f"**Owner IDs:** {', '.join(f'`{id}`' for id in config.OWNER_IDS)}",
            color=config.COLORS['success'] if is_owner_check else config.COLORS['error']
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='checkperms')
    async def checkperms(self, ctx):
        """Check your permissions (diagnose autorole issues)"""
        perms = ctx.author.guild_permissions
        
        # Critical permissions for autorole
        has_admin = perms.administrator
        has_manage_roles = perms.manage_roles
        
        embed = discord.Embed(
            title=f"🔐 Your Permissions in {ctx.guild.name}",
            description=f"**User:** {ctx.author.mention}\n\n"
                       f"**Administrator:** {'✅ Yes' if has_admin else '❌ No (REQUIRED for ,autorole!)'}\n"
                       f"**Manage Roles:** {'✅ Yes' if has_manage_roles else '❌ No'}\n"
                       f"**Manage Server:** {'✅ Yes' if perms.manage_guild else '❌ No'}",
            color=config.COLORS['success'] if has_admin else config.COLORS.get('warning', config.COLORS['error'])
        )
        
        if not has_admin:
            embed.add_field(
                name="⚠️ Why Autorole Doesn't Work",
                value="You need **Administrator** permission to use `,autorole` commands!\n"
                      "Ask a server admin to give you a role with Administrator enabled.",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='shutdown')
    @is_owner()
    async def shutdown(self, ctx):
        """Shutdown the bot"""
        await ctx.reply(embed=success_embed('Shutting Down', 'Bot is shutting down...'))
        await self.bot.close()
    
    # ========================
    # NEW: GLOBAL BAN
    # ========================
    
    @commands.command(name='globalban', aliases=['gban'])
    @is_owner()
    async def globalban(self, ctx, user_id: int = None, *, reason: str = "Global ban by bot owner"):
        """🌐 Ban a user from ALL servers the bot is in"""
        # Hard guard — extra safety in case decorator is bypassed
        if ctx.author.id not in config.OWNER_IDS:
            return await ctx.reply(embed=error_embed('🔒 Owner Only', 'This command is restricted to bot owners only.'))
        if not user_id:
            return await ctx.reply(embed=error_embed('Missing User', f'Usage: `{config.PREFIX}globalban <user_id> [reason]`'))

        
        # Save to database
        session = self.db.get_session()
        try:
            # Check if already banned
            existing = session.query(GlobalBan).filter_by(user_id=user_id).first()
            if existing:
                return await ctx.reply(embed=error_embed('Already Banned', f'User `{user_id}` is already globally banned.'))
            
            # Try to fetch user info
            try:
                user = await self.bot.fetch_user(user_id)
                username = str(user)
            except:
                username = f"Unknown#{user_id}"
            
            # Add to global ban database
            gban = GlobalBan(
                user_id=user_id,
                username=username,
                reason=reason,
                banned_by=ctx.author.id
            )
            session.add(gban)
            session.commit()
        finally:
            session.close()
        
        # Execute bans across all servers
        success_count = 0
        fail_count = 0
        
        loading = await ctx.reply(embed=info_embed(
            '🌐 Global Ban in Progress',
            f'Banning `{username}` across **{len(self.bot.guilds)}** servers...'
        ))
        
        for guild in self.bot.guilds:
            try:
                await guild.ban(discord.Object(id=user_id), reason=f"[GLOBAL BAN] {reason}")
                success_count += 1
            except:
                fail_count += 1
        
        embed = discord.Embed(
            title="🌐 Global Ban Complete",
            description=(
                f"**User:** {username} (`{user_id}`)\n"
                f"**Reason:** {reason}\n\n"
                f"✅ Banned from **{success_count}** servers\n"
                f"❌ Failed in **{fail_count}** servers"
            ),
            color=config.COLORS['error']
        )
        await loading.edit(embed=embed)
    
    @commands.command(name='globalunban', aliases=['gunban'])
    @is_owner()
    async def globalunban(self, ctx, user_id: int = None):
        """🌐 Unban a user from ALL servers the bot is in"""
        if not user_id:
            return await ctx.reply(embed=error_embed('Missing User', f'Usage: `{config.PREFIX}globalunban <user_id>`'))
        
        # Remove from database
        session = self.db.get_session()
        try:
            deleted = session.query(GlobalBan).filter_by(user_id=user_id).delete()
            session.commit()
            if not deleted:
                return await ctx.reply(embed=error_embed('Not Found', f'User `{user_id}` is not globally banned.'))
        finally:
            session.close()
        
        # Execute unbans across all servers
        success_count = 0
        fail_count = 0
        
        for guild in self.bot.guilds:
            try:
                await guild.unban(discord.Object(id=user_id), reason="[GLOBAL UNBAN] Revoked by bot owner")
                success_count += 1
            except:
                fail_count += 1
        
        embed = discord.Embed(
            title="🌐 Global Unban Complete",
            description=(
                f"**User ID:** `{user_id}`\n\n"
                f"✅ Unbanned from **{success_count}** servers\n"
                f"❌ Failed/not banned in **{fail_count}** servers"
            ),
            color=config.COLORS['success']
        )
        await ctx.reply(embed=embed)
    
    # ========================
    # NEW: ANNOUNCE
    # ========================
    
    @commands.command(name='announce')
    @is_owner()
    async def announce(self, ctx, *, message: str = None):
        """📢 Broadcast a message to all servers"""
        if not message:
            return await ctx.reply(embed=error_embed('Missing Message', f'Usage: `{config.PREFIX}announce <message>`'))
        
        embed = discord.Embed(
            title="📢 Announcement from xiel",
            description=message,
            color=config.COLORS['primary'],
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Sent by {ctx.author.display_name} • Bot Owner")
        
        loading = await ctx.reply(embed=info_embed(
            '📢 Sending Announcement',
            f'Broadcasting to **{len(self.bot.guilds)}** servers...'
        ))
        
        success_count = 0
        fail_count = 0
        
        for guild in self.bot.guilds:
            try:
                # Find first text channel where bot can send messages
                target_channel = None
                for channel in guild.text_channels:
                    perms = channel.permissions_for(guild.me)
                    if perms.send_messages:
                        target_channel = channel
                        break
                
                if target_channel:
                    await target_channel.send(embed=embed)
                    success_count += 1
                else:
                    fail_count += 1
            except:
                fail_count += 1
        
        result_embed = success_embed(
            '📢 Announcement Sent',
            f'✅ Sent to **{success_count}** servers\n'
            f'❌ Failed in **{fail_count}** servers'
        )
        await loading.edit(embed=result_embed)
    
    # ========================
    # NEW: MAINTENANCE MODE
    # ========================
    
    @commands.command(name='maintenance')
    @is_owner()
    async def maintenance(self, ctx, toggle: str = None):
        """🔧 Toggle maintenance mode — blocks all non-owner commands"""
        if toggle is None:
            status = "**🔧 ON** — Only owner commands work" if self.maintenance_mode else "**✅ OFF** — All commands work"
            return await ctx.reply(embed=info_embed('Maintenance Mode', f'Status: {status}'))
        
        self.maintenance_mode = toggle.lower() in ['on', 'enable', 'true', '1']
        self.bot.maintenance_mode = self.maintenance_mode
        
        if self.maintenance_mode:
            # Set status to maintenance
            await self.bot.change_presence(
                status=discord.Status.dnd,
                activity=discord.Activity(type=discord.ActivityType.playing, name="🔧 Maintenance Mode")
            )
            await ctx.reply(embed=success_embed(
                '🔧 Maintenance Mode ON',
                'All non-owner commands are now **disabled**.\n'
                'Use `,maintenance off` to re-enable.'
            ))
        else:
            # Reset status
            await self.bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.playing, name=f"{config.PREFIX}help")
            )
            await ctx.reply(embed=success_embed(
                '✅ Maintenance Mode OFF',
                'All commands are now **enabled** again.'
            ))
    
    # ========================
    # NEW: PREMIUM MANAGEMENT
    # ========================
    
    @commands.command(name='grantpremium', aliases=['gp'])
    @is_owner()
    async def grantpremium_cmd(self, ctx, user_id: int = None, server_id: int = None, command_name: str = None):
        """💎 Grant premium command access to a user"""
        if not all([user_id, server_id, command_name]):
            cmds_list = ', '.join([f'`{c}`' for c in PREMIUM_COMMANDS + ['all']])
            return await ctx.reply(embed=error_embed(
                'Missing Arguments',
                f'Usage: `{config.PREFIX}grantpremium <user_id> <server_id> <command>`\n\n'
                f'**Available commands:** {cmds_list}'
            ))
        
        if command_name != 'all' and command_name not in PREMIUM_COMMANDS:
            return await ctx.reply(embed=error_embed('Invalid Command', f'`{command_name}` is not a premium command.'))
        
        result = grant_premium(user_id, server_id, command_name, ctx.author.id)
        
        if result:
            # Try to fetch user for display
            try:
                user = await self.bot.fetch_user(user_id)
                user_display = f"{user} (`{user_id}`)"
            except:
                user_display = f"`{user_id}`"
            
            await ctx.reply(embed=success_embed(
                '💎 Premium Granted',
                f'**User:** {user_display}\n'
                f'**Server:** `{server_id}`\n'
                f'**Command:** `{command_name}`'
            ))
        else:
            await ctx.reply(embed=error_embed('Already Granted', 'This user already has access to this command in that server.'))
    
    @commands.command(name='revokepremium', aliases=['rp'])
    @is_owner()
    async def revokepremium_cmd(self, ctx, user_id: int = None, server_id: int = None, command_name: str = None):
        """💎 Revoke premium command access from a user"""
        if not all([user_id, server_id, command_name]):
            return await ctx.reply(embed=error_embed(
                'Missing Arguments',
                f'Usage: `{config.PREFIX}revokepremium <user_id> <server_id> <command>`'
            ))
        
        result = revoke_premium(user_id, server_id, command_name)
        
        if result:
            await ctx.reply(embed=success_embed(
                '💎 Premium Revoked',
                f'Revoked `{command_name}` access from `{user_id}` in server `{server_id}`.'
            ))
        else:
            await ctx.reply(embed=error_embed('Not Found', 'No matching premium access found to revoke.'))
    
    @commands.command(name='listpremium', aliases=['lp'])
    @is_owner()
    async def listpremium_cmd(self, ctx, server_id: int = None):
        """💎 List all premium access grants"""
        records = get_all_premium(server_id)
        
        if not records:
            return await ctx.reply(embed=info_embed('💎 Premium Users', 'No premium access grants found.'))
        
        desc_lines = []
        for r in records[:15]:  # Show max 15
            desc_lines.append(
                f"👤 `{r['user_id']}` → `{r['command_name']}` in server `{r['server_id']}`"
            )
        
        desc = '\n'.join(desc_lines)
        if len(records) > 15:
            desc += f"\n\n*...and {len(records) - 15} more*"
        
        await ctx.reply(embed=info_embed(f'💎 Premium Users ({len(records)} total)', desc))
    
    # ========================
    # NEW: BOT TOGGLE
    # ========================
    
    @commands.command(name='togglebot', aliases=['tb'])
    @is_owner()
    async def togglebot(self, ctx, server_id: int = None):
        """🔌 Enable/disable bot in a specific server"""
        if not server_id:
            return await ctx.reply(embed=error_embed('Missing Server', f'Usage: `{config.PREFIX}togglebot <server_id>`'))
        
        guild = self.bot.get_guild(server_id)
        if not guild:
            return await ctx.reply(embed=error_embed('Not Found', f'Bot is not in server `{server_id}`.'))
        
        session = self.db.get_session()
        try:
            toggle = session.query(BotToggle).filter_by(server_id=server_id).first()
            if not toggle:
                toggle = BotToggle(server_id=server_id, is_enabled=False, toggled_by=ctx.author.id)
                session.add(toggle)
            else:
                toggle.is_enabled = not toggle.is_enabled
                toggle.toggled_by = ctx.author.id
            
            new_state = toggle.is_enabled
            session.commit()
        finally:
            session.close()
        
        status = "✅ **Enabled**" if new_state else "❌ **Disabled**"
        await ctx.reply(embed=success_embed(
            '🔌 Bot Toggle',
            f'Bot is now {status} in **{guild.name}**.\n'
            f'{"Commands will work normally." if new_state else "All commands will be ignored in that server."}'
        ))
    
    # ========================
    # NEW: BOT PROFILE (OWNER)
    # ========================
    
    @commands.command(name='botprofile')
    @is_owner()
    async def botprofile(self, ctx, *, name: str = None):
        """✏️ Change the bot's username"""
        if not name:
            return await ctx.reply(embed=error_embed('Missing Name', f'Usage: `{config.PREFIX}botprofile <new_name>`'))
        
        try:
            await self.bot.user.edit(username=name)
            await ctx.reply(embed=success_embed('✏️ Profile Updated', f'Bot name changed to **{name}**'))
        except discord.HTTPException as e:
            await ctx.reply(embed=error_embed('Failed', f'Discord rate limited this action.\n`{e}`'))
    
    # ========================
    # BOT PROFILE ACCESS MANAGEMENT
    # ========================
    
    @commands.command(name='grantprofile', aliases=['gpa'])
    @is_owner()
    async def grantprofile(self, ctx, user_id: int = None, server_id: int = None):
        """🖼️ Grant bot profile access (botavatar) to a user for a server"""
        if not user_id or not server_id:
            return await ctx.reply(embed=error_embed(
                'Missing Args',
                f'Usage: `{config.PREFIX}grantprofile <user_id> <server_id>`'
            ))
        
        session = self.db.get_session()
        try:
            existing = session.query(BotProfileAccess).filter_by(
                user_id=user_id, server_id=server_id
            ).first()
            
            if existing:
                return await ctx.reply(embed=error_embed('Already Granted', 'User already has profile access for that server.'))
            
            access = BotProfileAccess(
                user_id=user_id,
                server_id=server_id,
                granted_by=ctx.author.id
            )
            session.add(access)
            session.commit()
            
            guild = self.bot.get_guild(server_id)
            guild_name = guild.name if guild else str(server_id)
            
            await ctx.reply(embed=success_embed(
                '🖼️ Profile Access Granted',
                f'User `{user_id}` can now use `botavatar` and `botreset` in **{guild_name}**.'
            ))
        except Exception as e:
            session.rollback()
            await ctx.reply(embed=error_embed('Error', f'Failed: {e}'))
        finally:
            session.close()
    
    @commands.command(name='revokeprofile', aliases=['rpa'])
    @is_owner()
    async def revokeprofile(self, ctx, user_id: int = None, server_id: int = None):
        """🖼️ Revoke bot profile access from a user for a server"""
        if not user_id or not server_id:
            return await ctx.reply(embed=error_embed(
                'Missing Args',
                f'Usage: `{config.PREFIX}revokeprofile <user_id> <server_id>`'
            ))
        
        session = self.db.get_session()
        try:
            deleted = session.query(BotProfileAccess).filter_by(
                user_id=user_id, server_id=server_id
            ).delete()
            session.commit()
            
            if deleted:
                await ctx.reply(embed=success_embed(
                    '🖼️ Profile Access Revoked',
                    f'User `{user_id}` can no longer use `botavatar` or `botreset` in server `{server_id}`.'
                ))
            else:
                await ctx.reply(embed=error_embed('Not Found', 'No profile access found for that user/server.'))
        except Exception as e:
            session.rollback()
            await ctx.reply(embed=error_embed('Error', f'Failed: {e}'))
        finally:
            session.close()
    
    # ========================
    # MAINTENANCE CHECK LISTENER
    # ========================
    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        """Log command usage; global command counts are updated in app.py."""
        # Log to database
        try:
            session = self.db.get_session()
            from models import CommandUsage
            usage = CommandUsage(
                command_name=ctx.command.qualified_name if ctx.command else 'unknown',
                user_id=ctx.author.id,
                server_id=ctx.guild.id if ctx.guild else None
            )
            session.add(usage)
            session.commit()
            session.close()
        except:
            pass
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Check maintenance mode and bot toggle before processing"""
        if message.author.bot or not message.guild:
            return
        
        # Check maintenance mode
        if getattr(self.bot, 'maintenance_mode', False):
            if message.author.id not in config.OWNER_IDS:
                # Silently ignore commands during maintenance
                if message.content.startswith(config.PREFIX):
                    embed = discord.Embed(
                        title="🔧 Maintenance Mode",
                        description="The bot is currently under maintenance. Please try again later.",
                        color=0xfbbf24
                    )
                    try:
                        await message.reply(embed=embed, delete_after=10)
                    except:
                        pass
                    return
        
        # Check bot toggle for this server
        try:
            session = self.db.get_session()
            toggle = session.query(BotToggle).filter_by(server_id=message.guild.id).first()
            session.close()
            
            if toggle and not toggle.is_enabled:
                if message.author.id not in config.OWNER_IDS:
                    return  # Silently ignore
        except:
            pass
    
    # ========================
    # GLOBAL BAN CHECK
    # ========================
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Auto-ban globally banned users when they join a server"""
        session = self.db.get_session()
        try:
            gban = session.query(GlobalBan).filter_by(user_id=member.id).first()
            if gban:
                try:
                    await member.ban(reason=f"[GLOBAL BAN] {gban.reason}")
                except:
                    pass
        finally:
            session.close()

    # ========================
    # BOT CHECKUP — FULL DIAGNOSTIC
    # ========================

    @commands.command(name='botcheckup', aliases=['healthcheck', 'diagnose'])
    async def botcheckup(self, ctx):
        """🩺 [OWNER] Run a full bot diagnostic — checks all cogs, commands, and databases"""
        if ctx.author.id not in config.OWNER_IDS:
            return await ctx.send(embed=error_embed("Permission Denied", "This command is only for bot owners."))

        # ── Confirmation prompt ──
        confirm_embed = discord.Embed(
            title="🩺 Bot Checkup",
            description=(
                "This will run a **full diagnostic** on the bot:\n\n"
                "• Check all loaded cogs\n"
                "• Validate every command callback\n"
                "• Test database connections (MySQL + SQLite)\n"
                "• Check for missing imports\n"
                "• Verify config keys\n\n"
                "⚠️ **This may take a few seconds.**\n\n"
                "React with ✅ to proceed or ❌ to cancel."
            ),
            color=0xf1c40f,
            timestamp=discord.utils.utcnow(),
        )
        confirm_embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        msg = await ctx.send(embed=confirm_embed)
        await msg.add_reaction('✅')
        await msg.add_reaction('❌')

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['✅', '❌'] and reaction.message.id == msg.id

        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await msg.edit(embed=discord.Embed(
                title="🩺 Bot Checkup — Cancelled",
                description="Timed out. No checkup was run.",
                color=0xe74c3c
            ))
            return

        if str(reaction.emoji) == '❌':
            await msg.edit(embed=discord.Embed(
                title="🩺 Bot Checkup — Cancelled",
                description="Checkup cancelled by owner.",
                color=0xe74c3c
            ))
            return

        # ── Start diagnostic ──
        await msg.edit(embed=discord.Embed(
            title="🩺 Bot Checkup — Running...",
            description="<a:loading:1470802096050802698> Please wait, running diagnostics...",
            color=0x3498db
        ))

        results = {
            'cogs_loaded': [],
            'cogs_failed': [],
            'cmds_ok': 0,
            'cmds_failed': [],
            'db_results': [],
            'import_errors': [],
            'warnings': [],
        }

        total_start = time.time()

        # ═══════════════════════════════════════════
        # 1. CHECK ALL COGS
        # ═══════════════════════════════════════════
        cog_files = [f[:-3] for f in os.listdir('cogs') if f.endswith('.py') and not f.startswith('_')]
        loaded_cogs = list(self.bot.cogs.keys())

        for cog_file in cog_files:
            cog_name = cog_file
            # Check if cog is loaded (match by file name)
            found = False
            for loaded in loaded_cogs:
                if loaded.lower().replace(' ', '').replace('_', '') == cog_name.lower().replace('_', ''):
                    results['cogs_loaded'].append(f"{loaded} (`{cog_file}.py`)")
                    found = True
                    break
            if not found:
                # Try to figure out why it's not loaded
                try:
                    import importlib
                    mod = importlib.import_module(f'cogs.{cog_file}')
                    results['cogs_failed'].append(f"`{cog_file}.py` — imports OK but **not loaded** (check `on_ready` or `cog_load` errors)")
                except Exception as e:
                    results['cogs_failed'].append(f"`{cog_file}.py` — **Import Error:** `{type(e).__name__}: {e}`")

        # ═══════════════════════════════════════════
        # 2. CHECK ALL COMMANDS
        # ═══════════════════════════════════════════
        for cmd in self.bot.walk_commands():
            try:
                # Verify callback is callable
                if not callable(cmd.callback):
                    results['cmds_failed'].append(f"`{cmd.qualified_name}` — callback is not callable")
                    continue

                # Check if cog reference is valid
                if cmd.cog and not isinstance(cmd.cog, commands.Cog):
                    results['cmds_failed'].append(f"`{cmd.qualified_name}` — invalid cog reference")
                    continue

                results['cmds_ok'] += 1
            except Exception as e:
                results['cmds_failed'].append(f"`{cmd.qualified_name}` — `{type(e).__name__}: {e}`")

        # Also check slash commands
        slash_count = 0
        slash_errors = []
        for cmd in self.bot.tree.get_commands():
            try:
                if hasattr(cmd, 'commands'):  # Group
                    for sub in cmd.commands:
                        slash_count += 1
                else:
                    slash_count += 1
            except Exception as e:
                slash_errors.append(f"`/{cmd.name}` — `{e}`")

        # ═══════════════════════════════════════════
        # 3. CHECK DATABASE CONNECTIONS
        # ═══════════════════════════════════════════

        # MySQL (Economy)
        try:
            from utils.economy_db import economy_db
            test_user = economy_db.get_user("0")  # Dummy user test
            if test_user is not None:
                results['db_results'].append("✅ **MySQL (Economy)** — Connected & responsive")
            else:
                results['db_results'].append("⚠️ **MySQL (Economy)** — Connected but returned None for test query")
        except Exception as e:
            results['db_results'].append(f"❌ **MySQL (Economy)** — `{type(e).__name__}: {e}`")

        # SQLite (Staff Supervision)
        try:
            from utils.staff_db import staff_db
            # Simple test query
            staff_db.get_config_list(0, 'staff_roles')
            results['db_results'].append("✅ **SQLite (Staff DB)** — Connected & responsive")
        except Exception as e:
            results['db_results'].append(f"❌ **SQLite (Staff DB)** — `{type(e).__name__}: {e}`")

        # SQLite (Settings)
        try:
            from utils.database import settings_db
            results['db_results'].append("✅ **SQLite (Settings)** — Connected")
        except Exception as e:
            results['db_results'].append(f"❌ **SQLite (Settings)** — `{type(e).__name__}: {e}`")

        # ORM Database
        try:
            session = self.db.get_session()
            session.close()
            results['db_results'].append("✅ **ORM Database** — Connected")
        except Exception as e:
            results['db_results'].append(f"❌ **ORM Database** — `{type(e).__name__}: {e}`")

        # ═══════════════════════════════════════════
        # 4. CHECK CRITICAL IMPORTS
        # ═══════════════════════════════════════════
        critical_imports = [
            'utils.embeds', 'utils.permissions', 'utils.database',
            'utils.premium', 'utils.economy_db', 'utils.economy_embeds',
            'utils.shop_items', 'utils.staff_db',
        ]
        for mod_name in critical_imports:
            try:
                __import__(mod_name)
            except Exception as e:
                results['import_errors'].append(f"`{mod_name}` — `{type(e).__name__}: {e}`")

        # ═══════════════════════════════════════════
        # 5. CONFIG CHECKS
        # ═══════════════════════════════════════════
        required_colors = ['primary', 'secondary', 'success', 'error']
        for key in required_colors:
            if key not in config.COLORS:
                results['warnings'].append(f"Missing `COLORS['{key}']` in config")

        if not config.OWNER_IDS:
            results['warnings'].append("⚠️ `OWNER_IDS` is empty!")

        if not config.TOKEN:
            results['warnings'].append("⚠️ `TOKEN` is empty!")

        # ═══════════════════════════════════════════
        # 6. BOT STATUS CHECKS
        # ═══════════════════════════════════════════
        latency = round(self.bot.latency * 1000)
        guild_count = len(self.bot.guilds)
        member_count = sum(g.member_count or 0 for g in self.bot.guilds)
        uptime_seconds = int(time.time() - start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        elapsed = round(time.time() - total_start, 2)

        # ═══════════════════════════════════════════
        # BUILD REPORT
        # ═══════════════════════════════════════════
        total_issues = len(results['cogs_failed']) + len(results['cmds_failed']) + len(results['import_errors']) + len(results['warnings']) + len(slash_errors)
        has_db_errors = any(r.startswith('❌') for r in results['db_results'])
        if has_db_errors:
            total_issues += sum(1 for r in results['db_results'] if r.startswith('❌'))

        if total_issues == 0:
            health_status = "🟢 **HEALTHY** — All systems operational"
            embed_color = 0x2ecc71
        elif total_issues <= 3:
            health_status = f"🟡 **WARNING** — {total_issues} issue(s) found"
            embed_color = 0xf1c40f
        else:
            health_status = f"🔴 **CRITICAL** — {total_issues} issue(s) found"
            embed_color = 0xe74c3c

        report = discord.Embed(
            title="🩺 Bot Checkup — Report",
            description=f"{health_status}\n*Completed in {elapsed}s*",
            color=embed_color,
            timestamp=discord.utils.utcnow(),
        )

        # Bot Status
        report.add_field(
            name="📡 Bot Status",
            value=(
                f"**Ping:** `{latency}ms`\n"
                f"**Guilds:** `{guild_count}`\n"
                f"**Members:** `{member_count:,}`\n"
                f"**Uptime:** `{hours}h {minutes}m {seconds}s`"
            ),
            inline=True
        )

        # Cogs
        report.add_field(
            name="📦 Cogs",
            value=(
                f"**Loaded:** `{len(results['cogs_loaded'])}` / `{len(cog_files)}`\n"
                f"**Failed:** `{len(results['cogs_failed'])}`"
            ),
            inline=True
        )

        # Commands
        report.add_field(
            name="⚡ Commands",
            value=(
                f"**Prefix:** `{results['cmds_ok']}` OK, `{len(results['cmds_failed'])}` failed\n"
                f"**Slash:** `{slash_count}` registered, `{len(slash_errors)}` errors"
            ),
            inline=True
        )

        # Databases
        db_text = "\n".join(results['db_results']) if results['db_results'] else "✅ All OK"
        report.add_field(name="🗄️ Databases", value=db_text, inline=False)

        # Errors section (only if there are errors)
        if results['cogs_failed']:
            cogs_err = "\n".join(results['cogs_failed'][:5])
            if len(results['cogs_failed']) > 5:
                cogs_err += f"\n... and {len(results['cogs_failed']) - 5} more"
            report.add_field(name="❌ Cog Errors", value=cogs_err, inline=False)

        if results['cmds_failed']:
            cmds_err = "\n".join(results['cmds_failed'][:5])
            if len(results['cmds_failed']) > 5:
                cmds_err += f"\n... and {len(results['cmds_failed']) - 5} more"
            report.add_field(name="❌ Command Errors", value=cmds_err, inline=False)

        if results['import_errors']:
            imp_err = "\n".join(results['import_errors'][:5])
            report.add_field(name="❌ Import Errors", value=imp_err, inline=False)

        if results['warnings']:
            warn_text = "\n".join(results['warnings'][:5])
            report.add_field(name="⚠️ Warnings", value=warn_text, inline=False)

        if slash_errors:
            slash_err = "\n".join(slash_errors[:5])
            report.add_field(name="❌ Slash Command Errors", value=slash_err, inline=False)

        if total_issues == 0:
            report.add_field(
                name="🎉 All Clear!",
                value="No issues found. All cogs, commands, and databases are operational.",
                inline=False
            )

        report.set_footer(text=f"Checkup by {ctx.author} • {elapsed}s", icon_url=ctx.author.display_avatar.url)
        report.set_thumbnail(url=self.bot.user.display_avatar.url)

        await msg.edit(embed=report)
        try:
            await msg.clear_reactions()
        except discord.Forbidden:
            pass


async def setup(bot):
    await bot.add_cog(Owner(bot))
