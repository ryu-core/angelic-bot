import discord
import asyncio
import traceback
import io
import os
import aiohttp
from discord import app_commands
from discord.ext import commands
import mysql.connector
from mysql.connector import Error


def _get_mysql_connection():
    """Create a MySQL connection using environment variables."""
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', ''),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER', ''),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DATABASE', ''),
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci'
    )


class Transparency(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Cache to track who triggered moderation actions
        # Format: {(guild_id, user_id): {'action': 'mute/unmute/etc', 'moderator': user_obj, 'timestamp': time}}
        self.action_cache = {}

    def _sync_execute(self, query, params=None, fetchone=False, fetchall=False):
        """Execute a MySQL query synchronously."""
        conn = _get_mysql_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params)
            result = None
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            conn.commit()
            return result
        finally:
            cursor.close()
            conn.close()

    async def _execute(self, query, params=None, fetchone=False, fetchall=False):
        """Execute a MySQL query asynchronously."""
        return await asyncio.to_thread(
            self._sync_execute, query, params, fetchone, fetchall
        )

    # =====================================================
    # 🛠️ DATABASE SETUP
    # =====================================================
    @commands.Cog.listener()
    async def on_ready(self):
        def _init():
            conn = _get_mysql_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS log_settings (
                        guild_id BIGINT PRIMARY KEY,
                        mod_channel BIGINT,
                        msg_channel BIGINT,
                        member_channel BIGINT,
                        join_leave_channel BIGINT,
                        vc_channel BIGINT
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS server_logs (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT, 
                        user_id BIGINT, 
                        category VARCHAR(50), 
                        action VARCHAR(255), 
                        details TEXT, 
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                conn.commit()
            finally:
                cursor.close()
                conn.close()
        await asyncio.to_thread(_init)
        print("✅ Transparency Cog: Ready.")

    # =====================================================
    # ⚙️ SLASH COMMANDS
    # =====================================================
    
    logs_group = app_commands.Group(name="logs", description="Configure server logging channels")

    @logs_group.command(name="setup_universal", description="Use ONE channel for ALL logs")
    @app_commands.describe(channel="The channel where everything will go")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_universal(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets every log type to a single channel."""
        await interaction.response.defer()

        try:
            await self._execute("""
                INSERT INTO log_settings (guild_id, mod_channel, msg_channel, member_channel, join_leave_channel, vc_channel)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                mod_channel = VALUES(mod_channel),
                msg_channel = VALUES(msg_channel),
                member_channel = VALUES(member_channel),
                join_leave_channel = VALUES(join_leave_channel),
                vc_channel = VALUES(vc_channel)
            """, (interaction.guild.id, channel.id, channel.id, channel.id, channel.id, channel.id))
            
            embed = discord.Embed(title="✅ Universal Logs Configured", color=discord.Color.green())
            embed.description = f"**All** logs will now be sent to: {channel.mention}"
            await interaction.followup.send(embed=embed)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error: {e}")

    @logs_group.command(name="setup_advanced", description="Set specific channels. Unset fields will be DISABLED.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_advanced(self, interaction: discord.Interaction, 
                             mod_channel: discord.TextChannel = None,
                             msg_channel: discord.TextChannel = None,
                             vc_channel: discord.TextChannel = None,
                             join_leave_channel: discord.TextChannel = None,
                             member_channel: discord.TextChannel = None):
        """Sets logs to specific channels. Unspecified channels are disabled."""
        await interaction.response.defer()

        try:
            new_mod = mod_channel.id if mod_channel else None
            new_msg = msg_channel.id if msg_channel else None
            new_mem = member_channel.id if member_channel else None
            new_join = join_leave_channel.id if join_leave_channel else None
            new_vc = vc_channel.id if vc_channel else None

            await self._execute("""
                INSERT INTO log_settings (guild_id, mod_channel, msg_channel, member_channel, join_leave_channel, vc_channel)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                mod_channel = VALUES(mod_channel),
                msg_channel = VALUES(msg_channel),
                member_channel = VALUES(member_channel),
                join_leave_channel = VALUES(join_leave_channel),
                vc_channel = VALUES(vc_channel)
            """, (interaction.guild.id, new_mod, new_msg, new_mem, new_join, new_vc))

            embed = discord.Embed(title="✅ Advanced Logs Updated", color=discord.Color.blue())
            embed.description = "Unspecified channels have been disabled."
            embed.add_field(name="🛡️ Mod Logs", value=f"<#{new_mod}>" if new_mod else "❌ Disabled", inline=True)
            embed.add_field(name="💬 Msg Logs", value=f"<#{new_msg}>" if new_msg else "❌ Disabled", inline=True)
            embed.add_field(name="🔊 Voice Logs", value=f"<#{new_vc}>" if new_vc else "❌ Disabled", inline=True)
            embed.add_field(name="👋 Join/Leave", value=f"<#{new_join}>" if new_join else "❌ Disabled", inline=True)
            embed.add_field(name="👤 Member Logs", value=f"<#{new_mem}>" if new_mem else "❌ Disabled", inline=True)
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error: {e}")

    # ✅ NEW COMMAND: DISABLE
    @logs_group.command(name="disable", description="Turn off ALL logging for this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(self, interaction: discord.Interaction):
        """Completely disables logging by removing the configuration."""
        await interaction.response.defer()
        
        try:
            await self._execute("DELETE FROM log_settings WHERE guild_id = %s", (interaction.guild.id,))

            embed = discord.Embed(title="🚫 Logging Disabled", color=discord.Color.red())
            embed.description = "All logging channels have been cleared. The bot will stop logging events."
            await interaction.followup.send(embed=embed)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error: {e}")

    @logs_group.command(name="status", description="Check current log channels")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            row = await self._execute("SELECT * FROM log_settings WHERE guild_id = %s", (interaction.guild.id,), fetchone=True)
            
            if not row:
                return await interaction.followup.send("❌ Logs are not configured yet.")

            embed = discord.Embed(title="⚙️ Current Log Configuration", color=discord.Color.gold())
            embed.add_field(name="🛡️ Mod Logs", value=f"<#{row['mod_channel']}>" if row['mod_channel'] else "❌ Disabled", inline=True)
            embed.add_field(name="💬 Message Logs", value=f"<#{row['msg_channel']}>" if row['msg_channel'] else "❌ Disabled", inline=True)
            embed.add_field(name="👤 Member Logs", value=f"<#{row['member_channel']}>" if row['member_channel'] else "❌ Disabled", inline=True)
            embed.add_field(name="👋 Join/Leave", value=f"<#{row['join_leave_channel']}>" if row['join_leave_channel'] else "❌ Disabled", inline=True)
            embed.add_field(name="🔊 Voice Logs", value=f"<#{row['vc_channel']}>" if row['vc_channel'] else "❌ Disabled", inline=True)
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error: {e}")

    # =====================================================
    # 📨 LOGGING HELPER
    # =====================================================
    async def log(self, guild, embed, log_type, user_id=None, details="", files=None):
        try:
            row = await self._execute("SELECT * FROM log_settings WHERE guild_id = %s", (guild.id,), fetchone=True)
            
            if not row: return 
            
            mapping = {'mod': 'mod_channel', 'msg': 'msg_channel', 'member': 'member_channel', 'join': 'join_leave_channel', 'vc': 'vc_channel'}
            col = mapping.get(log_type)
            
            if col and row.get(col):
                channel = guild.get_channel(row[col])
                if channel:
                    try: 
                        await channel.send(embed=embed, files=files or [])
                    except: pass
                
                if user_id:
                    await self._execute(
                        "INSERT INTO server_logs (guild_id, user_id, category, action, details) VALUES (%s, %s, %s, %s, %s)",
                        (guild.id, user_id, log_type, embed.title, details)
                    )
        except: pass

    # =====================================================
    # 👂 1. MESSAGE LOGS (With Image & Sticker Fix)
    # =====================================================
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild: return
        
        # Skip logging if this is part of a bulk delete (we'll log it in on_bulk_message_delete instead)
        # Check if there's a recent bulk delete cache entry
        import time
        cache_key = (message.guild.id, message.channel.id)
        cached_action = self.action_cache.get(cache_key)
        
        # If there's a recent purge action (within 2 seconds), skip individual logging
        if cached_action and cached_action.get('action') == 'purge' and (time.time() - cached_action['timestamp']) < 2:
            return
        
        parts = []
        files_to_send = []

        # 1. Text Content
        if message.content: 
            parts.append(message.content[:1800])  # Limit to prevent embed overflow
        
        # 2. Attachments (Images/Videos)
        if message.attachments:
            parts.append(f"\n📎 **{len(message.attachments)} attachment(s)**")
            for attachment in message.attachments:
                if attachment.size < 8000000 and attachment.content_type and ('image' in attachment.content_type or 'video' in attachment.content_type):
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(attachment.url) as resp:
                                if resp.status == 200:
                                    data = await resp.read()
                                    file = discord.File(io.BytesIO(data), filename=attachment.filename)
                                    files_to_send.append(file)
                    except:
                        parts.append(f"⚠️ Failed to recover: {attachment.filename}")

        # 3. STICKERS
        if message.stickers:
            sticker_list = []
            for sticker in message.stickers:
                sticker_list.append(f"[{sticker.name}]({sticker.url})")
            parts.append(f"\n🏷️ **Sticker:** " + ", ".join(sticker_list))

        content = "\n".join(parts) if parts else "*[No content]*"
        
        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=0xe74c3c,  # Red
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="📍 Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="👤 Author", value=f"{message.author.mention}\n`{message.author.name}`", inline=True)
        embed.add_field(name="📝 Content", value=content, inline=False)
        
        # Show when message was originally sent
        created = f"<t:{int(message.created_at.timestamp())}:R>"
        embed.add_field(name="⏰ Sent", value=created, inline=True)
        
        embed.set_footer(text=f"Message ID: {message.id} | User ID: {message.author.id}")
        
        # Track for snipe command
        if hasattr(self.bot, 'track_snipe'):
            self.bot.track_snipe(message)
        
        await self.log(message.guild, embed, 'msg', message.author.id, content, files=files_to_send)
    
    # BULK DELETE (Purge)
    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        """Log bulk message deletions (purge operations)"""
        if not messages:
            return
        
        # Only log if 2+ messages deleted (ignore single message deletes)
        if len(messages) < 2:
            return
        
        guild = messages[0].guild
        channel = messages[0].channel
        
        # Check cache first for purge command moderator
        import time
        cache_key = (guild.id, channel.id)
        cached_action = self.action_cache.get(cache_key)
        
        if cached_action and cached_action['action'] == 'purge' and (time.time() - cached_action['timestamp']) < 5:
            # Use cached moderator info
            mod = cached_action['moderator']
            # Keep in cache for a bit longer to suppress individual on_message_delete calls
        else:
            # Fallback to audit logs
            await asyncio.sleep(0.5)
            mod = None
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.message_bulk_delete):
                if entry.target.id == channel.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                    mod = entry.user
                    break
            
            if not mod:
                mod = self.bot.user
        
        # Sort messages by timestamp (oldest first)
        sorted_messages = sorted(messages, key=lambda m: m.created_at)
        
        # Create text log of all deleted messages (for file attachment)
        log_content = f"=== PURGE LOG ===\n"
        log_content += f"Channel: #{channel.name} ({channel.id})\n"
        log_content += f"Moderator: {mod} ({mod.id})\n"
        log_content += f"Total Messages: {len(messages)}\n"
        log_content += f"Timestamp: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        log_content += "=" * 50 + "\n\n"
        
        for msg in sorted_messages:
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            content = msg.content if msg.content else "[No text content]"
            
            # Add attachments info
            if msg.attachments:
                attachment_list = ", ".join([f"{att.filename}" for att in msg.attachments])
                content += f"\n[Attachments: {attachment_list}]"
            
            # Add stickers info
            if msg.stickers:
                sticker_list = ", ".join([s.name for s in msg.stickers])
                content += f"\n[Stickers: {sticker_list}]"
            
            log_content += f"[{timestamp}] {msg.author} (ID: {msg.author.id}):\n{content}\n\n"
        
        # Create concise embed (no individual message list)
        embed = discord.Embed(
            title="🧹 Messages Purged (Bulk Delete)",
            color=0xe67e22,  # Orange
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="📍 Channel", value=channel.mention, inline=True)
        embed.add_field(name="⚖️ Moderator", value=f"{mod.mention}\n`{mod.name}`", inline=True)
        embed.add_field(name="📊 Total Deleted", value=f"**{len(messages)}** messages", inline=True)
        
        # Show preview of first few messages
        preview_lines = []
        for msg in sorted_messages[:5]:  # Show first 5 messages
            content_preview = msg.content[:100] if msg.content else "[No content]"
            preview_lines.append(f"**{msg.author.name}**: {content_preview}")
        
        if len(messages) > 5:
            preview_lines.append(f"*...and {len(messages) - 5} more (see attached file)*")
        
        embed.add_field(name="📝 Preview", value="\n".join(preview_lines) or "*No preview*", inline=False)
        embed.set_footer(text=f"Channel ID: {channel.id} | Full log attached")
        
        # Create text file
        file = discord.File(
            io.BytesIO(log_content.encode('utf-8')),
            filename=f"purge_log_{channel.id}_{int(time.time())}.txt"
        )
        
        await self.log(guild, embed, 'mod', mod.id, f"Purged {len(messages)} messages", files=[file])

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content or not before.guild: return
        try:
            embed = discord.Embed(
                title="📝 Message Edited",
                color=0x3498db,  # Blue
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=before.author.display_name, icon_url=before.author.display_avatar.url)
            
            # Before content
            before_content = before.content[:1000] if before.content else "*[Image/Embed/Sticker]*"
            after_content = after.content[:1000] if after.content else "*[Image/Embed/Sticker]*"
            
            embed.add_field(name="📍 Channel", value=before.channel.mention, inline=True)
            embed.add_field(name="👤 Author", value=f"{before.author.mention}\n`{before.author.name}`", inline=True)
            embed.add_field(name="📋 Before", value=before_content, inline=False)
            embed.add_field(name="✏️ After", value=after_content, inline=False)
            embed.add_field(name="🔗 Jump", value=f"[Go to Message]({after.jump_url})", inline=True)
            
            embed.set_footer(text=f"Message ID: {after.id} | User ID: {before.author.id}")
            
            # Track for editsnipe command
            if hasattr(self.bot, 'track_editsnipe'):
                self.bot.track_editsnipe(before, after)
            
            await self.log(before.guild, embed, 'msg', before.author.id, "Edit")
        except: pass


    # =====================================================
    # 👂 2. MOD LOGS (Kick, Ban, Mute, Unmute, Warn)
    # =====================================================
    
    # BAN
    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        # Small delay to let audit log populate
        await asyncio.sleep(0.5)
        
        mod = None
        reason = "No reason provided"
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                mod = entry.user
                reason = entry.reason or "No reason provided"
                break
        
        if not mod:
            mod = self.bot.user

        embed = discord.Embed(
            title="🔨 Member Banned",
            color=0xe74c3c,  # Red
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{user.name}", icon_url=user.display_avatar.url)
        embed.add_field(name="👤 User", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="⚖️ Moderator", value=f"{mod.mention}\n`{mod.name}`", inline=True)
        embed.add_field(name="📋 Reason", value=f"```{reason}```", inline=False)
        
        # Account age
        account_age = f"<t:{int(user.created_at.timestamp())}:R>"
        embed.add_field(name="📅 Account Created", value=account_age, inline=True)
        
        embed.set_footer(text=f"User ID: {user.id}")
        await self.log(guild, embed, 'mod', user.id, "Banned")

    # UNBAN
    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        # Small delay to let audit log populate
        await asyncio.sleep(0.5)
        
        mod = None
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
            if entry.target.id == user.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                mod = entry.user
                break
        
        if not mod:
            mod = self.bot.user

        embed = discord.Embed(
            title="🔓 Member Unbanned",
            color=0x2ecc71,  # Green
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{user.name}", icon_url=user.display_avatar.url)
        embed.add_field(name="👤 User", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="⚖️ Moderator", value=f"{mod.mention}\n`{mod.name}`", inline=True)
        embed.set_footer(text=f"User ID: {user.id}")
        await self.log(guild, embed, 'mod', user.id, "Unbanned")

    # KICK
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # Small delay to let audit log populate
        await asyncio.sleep(0.5)
        
        # Check if kicked
        async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
            if entry.target.id == member.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                embed = discord.Embed(
                    title="👢 Member Kicked",
                    color=0xe67e22,  # Orange
                    timestamp=discord.utils.utcnow()
                )
                embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
                embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.id}`", inline=True)
                embed.add_field(name="⚖️ Moderator", value=f"{entry.user.mention}\n`{entry.user.name}`", inline=True)
                embed.add_field(name="📋 Reason", value=f"```{entry.reason or 'No reason provided'}```", inline=False)
                
                # Account age
                account_age = f"<t:{int(member.created_at.timestamp())}:R>"
                embed.add_field(name="📅 Account Created", value=account_age, inline=True)
                
                embed.set_footer(text=f"User ID: {member.id}")
                await self.log(member.guild, embed, 'mod', member.id, "Kicked")
                return 
        
        # Regular Leave
        embed = discord.Embed(
            title="📤 Member Left",
            color=0x95a5a6,  # Gray
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=member.display_name, icon_url=member.avatar.url if member.avatar else None)
        embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.id}`", inline=True)
        embed.add_field(name="📊 Server Members", value=f"{member.guild.member_count}", inline=True)
        
        # Joined date
        if member.joined_at:
            joined = f"<t:{int(member.joined_at.timestamp())}:R>"
            embed.add_field(name="⏱️ Was Here For", value=joined, inline=True)
        
        embed.set_footer(text=f"User ID: {member.id}")
        await self.log(member.guild, embed, 'join', member.id, "Left")

    # WARN - Listen for warn command execution
    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        # Only log warn commands
        if ctx.command.name not in ['warn', 'warning']:
            return
        
        # Extract member and reason from context
        if not ctx.args or len(ctx.args) < 3:  # self, ctx, member are first 3 args
            return
            
        member = ctx.args[2] if len(ctx.args) > 2 else None
        if not isinstance(member, discord.Member):
            return
        
        reason = ctx.kwargs.get('reason', 'No reason provided')
        
        # Get warning count
        from utils.database import warnings_db
        guild_id = str(ctx.guild.id)
        guild_warnings = warnings_db.get(guild_id, {})
        user_id = str(member.id)
        warn_count = len(guild_warnings.get(user_id, []))
        
        embed = discord.Embed(
            title="⚠️ Member Warned",
            color=0xf39c12,  # Orange
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{member.name}", icon_url=member.display_avatar.url)
        embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.id}`", inline=True)
        embed.add_field(name="⚖️ Moderator", value=f"{ctx.author.mention}\n`{ctx.author.name}`", inline=True)
        embed.add_field(name="📋 Reason", value=f"```{reason}```", inline=False)
        embed.add_field(name="🔢 Total Warnings", value=f"**{warn_count}** warning(s)", inline=True)
        embed.set_footer(text=f"User ID: {member.id}")
        await self.log(ctx.guild, embed, 'mod', member.id, "Warned")


    # TIMEOUT / UNTIMEOUT
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # 1. Nickname
        if before.nick != after.nick:
            embed = discord.Embed(
                title="🏷️ Nickname Changed",
                color=0x9b59b6,  # Purple
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
            embed.add_field(name="👤 User", value=f"{after.mention}\n`{after.name}`", inline=True)
            embed.add_field(name="📋 Before", value=before.nick or "*[None]*", inline=True)
            embed.add_field(name="✏️ After", value=after.nick or "*[None]*", inline=True)
            embed.set_footer(text=f"User ID: {after.id}")
            await self.log(after.guild, embed, 'member', after.id, "Nick Change")
            return

        # 2. Timeout
        if before.timed_out_until != after.timed_out_until:
            # Muted
            if after.timed_out_until and after.timed_out_until > discord.utils.utcnow():
                # Check cache first
                import time
                cache_key = (after.guild.id, after.id)
                cached_action = self.action_cache.get(cache_key)
                
                if cached_action and cached_action['action'] == 'mute' and (time.time() - cached_action['timestamp']) < 5:
                    # Use cached moderator info
                    mod = cached_action['moderator']
                    reason = cached_action['reason']
                    # Remove from cache
                    del self.action_cache[cache_key]
                else:
                    # Fallback to audit logs
                    await asyncio.sleep(0.5)
                    mod = None
                    reason = "No reason provided"
                    async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                        if entry.target.id == after.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                            mod = entry.user
                            reason = entry.reason or "No reason provided"
                            break
                    
                    if not mod:
                        mod = self.bot.user
                
                duration = int((after.timed_out_until - discord.utils.utcnow()).total_seconds() / 60)
                
                embed = discord.Embed(
                    title="🔇 Member Muted (Timeout)",
                    color=0xf39c12,  # Orange
                    timestamp=discord.utils.utcnow()
                )
                embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                embed.add_field(name="👤 User", value=f"{after.mention}\n`{after.id}`", inline=True)
                embed.add_field(name="⚖️ Moderator", value=f"{mod.mention}\n`{mod.name}`", inline=True)
                embed.add_field(name="⏱️ Duration", value=f"**{duration}** minutes", inline=True)
                embed.add_field(name="📋 Reason", value=f"```{reason}```", inline=False)
                embed.set_footer(text=f"User ID: {after.id}")
                await self.log(after.guild, embed, 'mod', after.id, "Muted")

            # Unmuted
            elif before.timed_out_until and not after.timed_out_until:
                # Check cache first
                import time
                cache_key = (after.guild.id, after.id)
                cached_action = self.action_cache.get(cache_key)
                
                if cached_action and cached_action['action'] == 'unmute' and (time.time() - cached_action['timestamp']) < 5:
                    # Use cached moderator info
                    mod = cached_action['moderator']
                    # Remove from cache
                    del self.action_cache[cache_key]
                else:
                    # Fallback to audit logs
                    await asyncio.sleep(1.5)
                    mod = None
                    async for entry in after.guild.audit_logs(limit=10, action=discord.AuditLogAction.member_update):
                        if entry.target.id == after.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 15:
                            # Verify this is actually a timeout removal
                            if hasattr(entry.changes, 'before') and hasattr(entry.changes, 'after'):
                                for change in entry.changes.before:
                                    if change.key == 'communication_disabled_until':
                                        mod = entry.user
                                        break
                            else:
                                # Fallback: assume it's the right entry if timing is close
                                mod = entry.user
                            if mod:
                                break
                    
                    if not mod:
                        mod = self.bot.user

                embed = discord.Embed(
                    title="🔊 Member Unmuted",
                    color=0x2ecc71,  # Green
                    timestamp=discord.utils.utcnow()
                )
                embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                embed.add_field(name="👤 User", value=f"{after.mention}\n`{after.id}`", inline=True)
                embed.add_field(name="⚖️ Moderator", value=f"{mod.mention}\n`{mod.name}`", inline=True)
                embed.set_footer(text=f"User ID: {after.id}")
                await self.log(after.guild, embed, 'mod', after.id, "Unmuted")
            return

        # 3. Roles
        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            
            if added:
                embed = discord.Embed(
                    title="📈 Role Added",
                    color=0x2ecc71,  # Green
                    timestamp=discord.utils.utcnow()
                )
                embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                embed.add_field(name="👤 User", value=f"{after.mention}\n`{after.name}`", inline=True)
                embed.add_field(name="➕ Added Role(s)", value=" ".join([r.mention for r in added]), inline=False)
                embed.set_footer(text=f"User ID: {after.id}")
                await self.log(after.guild, embed, 'member', after.id, "Role Add")
            
            if removed:
                embed = discord.Embed(
                    title="📉 Role Removed",
                    color=0xe67e22,  # Orange
                    timestamp=discord.utils.utcnow()
                )
                embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
                embed.add_field(name="👤 User", value=f"{after.mention}\n`{after.name}`", inline=True)
                embed.add_field(name="➖ Removed Role(s)", value=" ".join([r.mention for r in removed]), inline=False)
                embed.set_footer(text=f"User ID: {after.id}")
                await self.log(after.guild, embed, 'member', after.id, "Role Remove")

    # =====================================================
    # 👂 3. JOIN & VOICE
    # =====================================================
    @commands.Cog.listener()
    async def on_member_join(self, member):
        embed = discord.Embed(
            title="📥 Member Joined",
            color=0x2ecc71,  # Green
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.id}`", inline=True)
        embed.add_field(name="📊 Server Members", value=f"**{member.guild.member_count}**", inline=True)
        
        # Account age
        account_age = f"<t:{int(member.created_at.timestamp())}:R>"
        embed.add_field(name="📅 Account Created", value=account_age, inline=True)
        
        embed.set_footer(text=f"User ID: {member.id}")
        await self.log(member.guild, embed, 'join', member.id, "Joined")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        if before.channel is None and after.channel is not None:
            embed = discord.Embed(
                title="🔊 Joined Voice Channel",
                color=0x2ecc71,  # Green
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.name}`", inline=True)
            embed.add_field(name="📢 Channel", value=f"**{after.channel.name}**", inline=True)
            embed.set_footer(text=f"User ID: {member.id}")
            await self.log(member.guild, embed, 'vc', member.id, "VC Join")

        elif before.channel is not None and after.channel is None:
            embed = discord.Embed(
                title="🔇 Left Voice Channel",
                color=0xe74c3c,  # Red
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.name}`", inline=True)
            embed.add_field(name="📢 Channel", value=f"**{before.channel.name}**", inline=True)
            embed.set_footer(text=f"User ID: {member.id}")
            await self.log(member.guild, embed, 'vc', member.id, "VC Leave")

        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            embed = discord.Embed(
                title="↔️ Moved Voice Channel",
                color=0x3498db,  # Blue
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.name}`", inline=True)
            embed.add_field(name="📤 From", value=f"**{before.channel.name}**", inline=True)
            embed.add_field(name="📥 To", value=f"**{after.channel.name}**", inline=True)
            embed.set_footer(text=f"User ID: {member.id}")
            await self.log(member.guild, embed, 'vc', member.id, "VC Move")

async def setup(bot):
    await bot.add_cog(Transparency(bot))
