"""
Private Voice Channel System
Users can create temporary private VCs with full control
"""

import discord
from discord.ext import commands
from discord import ui
import asyncio
import os
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


class VCControlView(ui.View):
    """Control panel for private voice channels"""
    
    def __init__(self, bot, vc_id, owner_id, cog=None):
        super().__init__(timeout=None)  # Persistent view
        self.bot = bot
        self.vc_id = vc_id
        self.owner_id = owner_id
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user can use this button"""
        # Allow claim button for anyone
        if interaction.data.get('custom_id') == 'pvc_claim':
            return True
            
        # Check if owner or admin
        if interaction.user.id == self.owner_id or interaction.user.guild_permissions.administrator:
            return True
        
        await interaction.response.send_message("❌ You are not the owner of this VC.", ephemeral=True)
        return False

    async def get_channel(self, interaction):
        """Get the channel and verify it exists"""
        channel = interaction.guild.get_channel(self.vc_id)
        if not channel:
            await interaction.response.send_message("❌ This VC no longer exists.", ephemeral=True)
            return None
        return channel

    @ui.button(label="Lock/Unlock", style=discord.ButtonStyle.secondary, emoji="🔒", custom_id="pvc_lock")
    async def lock(self, interaction: discord.Interaction, button: ui.Button):
        """Toggle VC lock"""
        channel = await self.get_channel(interaction)
        if not channel:
            return

        current_perm = channel.overwrites_for(interaction.guild.default_role).connect
        
        if current_perm is False:
            await channel.set_permissions(interaction.guild.default_role, connect=None)
            await interaction.response.send_message("🔓 VC **Unlocked** for everyone.", ephemeral=True)
        else:
            await channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("🔒 VC **Locked**. Only permitted users can join.", ephemeral=True)

    @ui.button(label="Ghost", style=discord.ButtonStyle.secondary, emoji="👻", custom_id="pvc_ghost")
    async def ghost(self, interaction: discord.Interaction, button: ui.Button):
        """Toggle VC visibility"""
        channel = await self.get_channel(interaction)
        if not channel:
            return

        current_view = channel.overwrites_for(interaction.guild.default_role).view_channel
        
        if current_view is False:
            await channel.set_permissions(interaction.guild.default_role, view_channel=None)
            await interaction.response.send_message("👁️ **Reveal** - Channel is now visible to everyone.", ephemeral=True)
        else:
            await channel.set_permissions(interaction.guild.default_role, view_channel=False)
            await channel.set_permissions(interaction.user, view_channel=True, connect=True)
            await interaction.response.send_message("👻 **Ghost** - Channel is now invisible to others.", ephemeral=True)

    @ui.button(label="Rename", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="pvc_rename")
    async def rename(self, interaction: discord.Interaction, button: ui.Button):
        """Show rename modal"""
        await interaction.response.send_modal(RenameModal(self.vc_id))

    @ui.button(label="Limit", style=discord.ButtonStyle.primary, emoji="👥", custom_id="pvc_limit")
    async def limit(self, interaction: discord.Interaction, button: ui.Button):
        """Show user limit modal"""
        await interaction.response.send_modal(LimitModal(self.vc_id))

    @ui.button(label="Kick User", style=discord.ButtonStyle.danger, emoji="👢", custom_id="pvc_kick")
    async def kick_user(self, interaction: discord.Interaction, button: ui.Button):
        """Kick a user from VC"""
        channel = await self.get_channel(interaction)
        if not channel:
            return
        
        members = [m for m in channel.members if m.id != self.owner_id and not m.bot]
        if not members:
            return await interaction.response.send_message("❌ No one else is in the VC to kick.", ephemeral=True)
            
        view = KickUserView(members)
        await interaction.response.send_message("Select user to kick:", view=view, ephemeral=True)

    @ui.button(label="Claim", style=discord.ButtonStyle.success, emoji="👑", custom_id="pvc_claim")
    async def claim(self, interaction: discord.Interaction, button: ui.Button):
        """Claim ownership if owner left"""
        channel = await self.get_channel(interaction)
        if not channel:
            return
        
        cog = self.cog or self.bot.get_cog("PrivateVC")
        if cog is None:
            return await interaction.response.send_message(
                "❌ The private VC system is not ready. Please try again.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        try:
            success, message, new_owner_id = await cog.claim_private_vc(
                channel, interaction.user
            )
        except Exception as exc:
            print(f"Unexpected private VC claim error for {channel.id}: {exc}")
            success = False
            message = "❌ Ownership could not be transferred. Please try again."
            new_owner_id = None
        if success:
            self.owner_id = new_owner_id
        await interaction.followup.send(message, ephemeral=True)


class RenameModal(ui.Modal, title="Rename Voice Channel"):
    """Modal for renaming VC"""
    
    name = ui.TextInput(label="New Name", placeholder="My Awesome VC", max_length=50)
    
    def __init__(self, vc_id):
        super().__init__()
        self.vc_id = vc_id

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.vc_id)
        if channel:
            await channel.edit(name=self.name.value)
            await interaction.response.send_message(f"✅ Renamed to **{self.name.value}**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)


class LimitModal(ui.Modal, title="Set User Limit"):
    """Modal for setting user limit"""
    
    limit = ui.TextInput(label="Limit (0 = Unlimited)", placeholder="0", max_length=2)
    
    def __init__(self, vc_id):
        super().__init__()
        self.vc_id = vc_id

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.vc_id)
        if not channel:
            return await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            
        try:
            val = int(self.limit.value)
            if 0 <= val <= 99:
                await channel.edit(user_limit=val)
                limit_text = "Unlimited" if val == 0 else str(val)
                await interaction.response.send_message(f"✅ User limit set to **{limit_text}**", ephemeral=True)
            else:
                raise ValueError
        except:
            await interaction.response.send_message("❌ Invalid number. Use 0-99.", ephemeral=True)


class KickUserView(ui.View):
    """View for selecting user to kick"""
    
    def __init__(self, members):
        super().__init__()
        options = [discord.SelectOption(label=m.display_name, value=str(m.id)) for m in members[:25]]
        self.add_item(KickSelect(options))


class KickSelect(ui.Select):
    """Dropdown to select user to kick"""
    
    def __init__(self, options):
        super().__init__(placeholder="Select user to kick...", options=options)

    async def callback(self, interaction: discord.Interaction):
        member_id = int(self.values[0])
        member = interaction.guild.get_member(member_id)
        if member:
            try:
                await member.move_to(None)  # Disconnect them
                await interaction.response.send_message(f"👢 Kicked **{member.display_name}**.", ephemeral=True)
            except:
                await interaction.response.send_message("❌ Failed to kick. Check permissions.", ephemeral=True)


class PrivateVC(commands.Cog):
    """Private Voice Channel System"""
    
    def __init__(self, bot):
        self.bot = bot
        self._db_initialized = False
        self._db_init_lock = asyncio.Lock()
        self._restore_lock = asyncio.Lock()
        self._restore_task = None
        self._registered_panel_ids = set()
        self._claim_locks = {}

    async def cog_load(self):
        """Initialize storage and schedule persistent view restoration."""
        await self._ensure_db()
        if self._restore_task is None or self._restore_task.done():
            self._restore_task = asyncio.create_task(
                self._restore_views_after_ready(),
                name="private-vc-view-restoration"
            )

    def cog_unload(self):
        if self._restore_task and not self._restore_task.done():
            self._restore_task.cancel()

    def _sync_execute(
        self, query, params=None, fetchone=False, fetchall=False,
        return_rowcount=False
    ):
        """Execute a MySQL query synchronously."""
        conn = _get_mysql_connection()
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params)
            result = None
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            elif return_rowcount:
                result = cursor.rowcount
            conn.commit()
            return result
        finally:
            if cursor is not None:
                cursor.close()
            conn.close()

    async def _execute(
        self, query, params=None, fetchone=False, fetchall=False,
        return_rowcount=False
    ):
        """Execute a MySQL query asynchronously."""
        return await asyncio.to_thread(
            self._sync_execute, query, params, fetchone, fetchall,
            return_rowcount
        )

    async def _ensure_db(self):
        if self._db_initialized:
            return
        async with self._db_init_lock:
            if not self._db_initialized:
                await self.init_db()
                self._db_initialized = True

    async def init_db(self):
        """Initialize database tables"""
        def _init():
            conn = _get_mysql_connection()
            cursor = None
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS private_vc_settings (
                        guild_id BIGINT PRIMARY KEY,
                        hub_channel_id BIGINT,
                        category_id BIGINT
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS active_private_vcs (
                        voice_channel_id BIGINT PRIMARY KEY,
                        owner_id BIGINT,
                        guild_id BIGINT,
                        panel_message_id BIGINT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)

                # Backward-compatible migration for existing installations.
                cursor.execute(
                    "SHOW COLUMNS FROM active_private_vcs LIKE 'panel_message_id'"
                )
                if cursor.fetchone() is None:
                    cursor.execute(
                        "ALTER TABLE active_private_vcs "
                        "ADD COLUMN panel_message_id BIGINT NULL"
                    )
                
                conn.commit()
            finally:
                if cursor is not None:
                    cursor.close()
                conn.close()
        await asyncio.to_thread(_init)

    @staticmethod
    def _control_panel_embed():
        embed = discord.Embed(
            title="🎙️ VoiceZone Interface",
            description="Use the buttons below to control your voice channel.",
            color=0x5865F2
        )
        button_guide = (
            "**Button Usage**\n"
            "🔒 — **Lock** the voice channel\n"
            "🔓 — **Unlock** the voice channel\n"
            "👻 — **Ghost** the voice channel\n"
            "👁️ — **Reveal** the voice channel\n"
            "👑 — **Claim** the voice channel\n"
            "👢 — **Disconnect** a member\n"
            "ℹ️ — **View** channel information\n"
            "👥 — **Increase** the user limit\n"
            "➖ — **Decrease** the user limit\n"
            "✏️ — **Rename** the voice channel"
        )
        embed.add_field(name="\u200b", value=button_guide, inline=False)
        return embed

    def _register_panel_view(self, voice_channel_id, owner_id, message_id):
        message_id = int(message_id)
        if message_id in self._registered_panel_ids:
            return
        self.bot.add_view(
            VCControlView(
                self.bot, int(voice_channel_id), int(owner_id), cog=self
            ),
            message_id=message_id
        )
        self._registered_panel_ids.add(message_id)

    @staticmethod
    def _is_control_panel_message(message):
        for action_row in getattr(message, "components", ()):
            for component in getattr(action_row, "children", ()):
                if getattr(component, "custom_id", None) == "pvc_claim":
                    return True
        return False

    async def _find_existing_panel(self, channel):
        """Find a pre-migration panel message without generating duplicates."""
        try:
            async for message in channel.history(limit=50):
                if self._is_control_panel_message(message):
                    return message
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    async def _create_control_panel(self, channel, owner_id):
        view = VCControlView(self.bot, channel.id, owner_id, cog=self)
        message = await channel.send(
            content=f"<@{owner_id}>",
            embed=self._control_panel_embed(),
            view=view
        )
        # Sending stores this view in discord.py immediately; mark the message
        # so restoration does not add a second dispatcher for it.
        self._registered_panel_ids.add(int(message.id))
        return message

    async def _restore_views_after_ready(self):
        try:
            await self.bot.wait_until_ready()
            await self.restore_persistent_views()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"Error restoring private VC control panels: {exc}")

    async def restore_persistent_views(self):
        """Restore active message-bound views once after startup."""
        await self._ensure_db()
        async with self._restore_lock:
            rows = await self._execute(
                "SELECT voice_channel_id, owner_id, guild_id, panel_message_id "
                "FROM active_private_vcs",
                fetchall=True
            )
            for row in rows or ():
                voice_channel_id = int(row["voice_channel_id"])
                guild = self.bot.get_guild(int(row["guild_id"]))
                channel = (
                    guild.get_channel(voice_channel_id)
                    if guild is not None else None
                )

                # Once the bot is ready, a missing guild/channel cannot service
                # this panel and the active row is stale.
                if channel is None:
                    await self._execute(
                        "DELETE FROM active_private_vcs "
                        "WHERE voice_channel_id = %s",
                        (voice_channel_id,)
                    )
                    continue

                panel_message = None
                panel_message_id = row.get("panel_message_id")
                if panel_message_id:
                    try:
                        panel_message = await channel.fetch_message(
                            int(panel_message_id)
                        )
                        if not self._is_control_panel_message(panel_message):
                            panel_message = None
                    except discord.NotFound:
                        panel_message = None
                    except (discord.Forbidden, discord.HTTPException) as exc:
                        print(
                            "Unable to fetch private VC panel "
                            f"{panel_message_id}: {exc}"
                        )
                        continue
                else:
                    panel_message = await self._find_existing_panel(channel)

                if panel_message is None:
                    try:
                        panel_message = await self._create_control_panel(
                            channel, int(row["owner_id"])
                        )
                    except (discord.Forbidden, discord.HTTPException) as exc:
                        print(
                            "Unable to recreate private VC panel for "
                            f"{voice_channel_id}: {exc}"
                        )
                        continue

                if int(panel_message.id) != int(panel_message_id or 0):
                    await self._execute(
                        "UPDATE active_private_vcs SET panel_message_id = %s "
                        "WHERE voice_channel_id = %s",
                        (panel_message.id, voice_channel_id)
                    )

                self._register_panel_view(
                    voice_channel_id,
                    int(row["owner_id"]),
                    panel_message.id
                )

    async def _set_member_overwrite(self, channel, member_id, overwrite):
        """Set an overwrite even if the former owner left the guild."""
        member = channel.guild.get_member(int(member_id))
        if member is not None:
            await channel.set_permissions(member, overwrite=overwrite)
            return

        # discord.py requires a cached Member in set_permissions, but Discord's
        # API can still address a stale member overwrite by its snowflake.
        if overwrite is None:
            await channel._state.http.delete_channel_permissions(
                channel.id, int(member_id),
                reason="Private VC ownership transfer"
            )
            return
        allow, deny = overwrite.pair()
        await channel._state.http.edit_channel_permissions(
            channel.id,
            int(member_id),
            str(allow.value),
            str(deny.value),
            1,  # Discord overwrite type: member
            reason="Private VC ownership transfer"
        )

    async def claim_private_vc(self, channel, claimant):
        """Persist and apply a private VC ownership transfer."""
        await self._ensure_db()
        lock = self._claim_locks.setdefault(channel.id, asyncio.Lock())
        async with lock:
            try:
                row = await self._execute(
                    "SELECT owner_id, guild_id FROM active_private_vcs "
                    "WHERE voice_channel_id = %s",
                    (channel.id,), fetchone=True
                )
            except Exception as exc:
                print(f"Error reading private VC owner for {channel.id}: {exc}")
                return (
                    False,
                    "❌ Ownership could not be verified. Please try again.",
                    None
                )

            if not row or int(row["guild_id"]) != channel.guild.id:
                return (
                    False,
                    "❌ This voice channel is no longer registered as private.",
                    None
                )

            old_owner_id = int(row["owner_id"])
            if old_owner_id == claimant.id:
                return False, "❌ You already own this voice channel.", None

            current_owner = channel.guild.get_member(old_owner_id)
            if any(member.id == old_owner_id for member in channel.members):
                owner_mention = (
                    current_owner.mention
                    if current_owner is not None else f"<@{old_owner_id}>"
                )
                return (
                    False,
                    f"❌ Owner {owner_mention} is still here!",
                    None
                )

            old_overwrite = channel.overwrites_for(
                current_owner or discord.Object(id=old_owner_id)
            )
            old_neutralized = discord.PermissionOverwrite.from_pair(
                *old_overwrite.pair()
            )
            old_neutralized.update(
                connect=None,
                move_members=None,
                manage_channels=None
            )
            if old_neutralized.is_empty():
                old_neutralized = None

            new_overwrite = channel.overwrites_for(claimant)
            original_new_overwrite = discord.PermissionOverwrite.from_pair(
                *new_overwrite.pair()
            )
            new_overwrite.update(
                connect=True,
                move_members=True,
                manage_channels=True
            )

            try:
                changed = await self._execute(
                    "UPDATE active_private_vcs SET owner_id = %s "
                    "WHERE voice_channel_id = %s AND owner_id = %s",
                    (claimant.id, channel.id, old_owner_id),
                    return_rowcount=True
                )
            except Exception as exc:
                print(f"Error persisting private VC claim for {channel.id}: {exc}")
                return (
                    False,
                    "❌ Ownership could not be saved. Please try again.",
                    None
                )

            if changed != 1:
                return (
                    False,
                    "❌ Ownership changed while you were claiming. Please retry.",
                    None
                )

            try:
                await channel.set_permissions(
                    claimant, overwrite=new_overwrite,
                    reason="Private VC ownership transfer"
                )
                await self._set_member_overwrite(
                    channel, old_owner_id, old_neutralized
                )
            except Exception as exc:
                print(
                    f"Error applying private VC claim permissions for "
                    f"{channel.id}: {exc}"
                )
                try:
                    await channel.set_permissions(
                        claimant, overwrite=original_new_overwrite,
                        reason="Rollback failed private VC ownership transfer"
                    )
                    await self._set_member_overwrite(
                        channel, old_owner_id, old_overwrite
                    )
                except Exception as rollback_exc:
                    print(
                        f"Error rolling back permissions for {channel.id}: "
                        f"{rollback_exc}"
                    )
                try:
                    await self._execute(
                        "UPDATE active_private_vcs SET owner_id = %s "
                        "WHERE voice_channel_id = %s AND owner_id = %s",
                        (old_owner_id, channel.id, claimant.id)
                    )
                except Exception as rollback_exc:
                    print(
                        f"Error rolling back private VC owner for {channel.id}: "
                        f"{rollback_exc}"
                    )
                return (
                    False,
                    "❌ Discord permissions could not be updated. "
                    "Ownership was not announced.",
                    None
                )

            return (
                True,
                f"👑 **Ownership Transferred!** {claimant.mention} is now "
                "the VC Owner.",
                claimant.id
            )

    async def get_hub_config(self, guild_id):
        """Get hub configuration for guild"""
        await self._ensure_db()
        row = await self._execute(
            "SELECT hub_channel_id, category_id FROM private_vc_settings WHERE guild_id = %s",
            (guild_id,), fetchone=True
        )
        if row:
            return (row['hub_channel_id'], row['category_id'])
        return None

    @commands.command(name='vcsetup')
    @commands.has_permissions(administrator=True)
    async def vc_setup(self, ctx):
        """Set up the join-to-create voice channel system
        
        Usage: ,vcsetup
        """
        await self._ensure_db()
        # Create category and hub channel
        category = await ctx.guild.create_category("🔊 Private Voice Channels")
        hub = await ctx.guild.create_voice_channel("➕ Join to Create", category=category)
        
        # Save to database
        await self._execute(
            """INSERT INTO private_vc_settings (guild_id, hub_channel_id, category_id)
               VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE hub_channel_id = VALUES(hub_channel_id), category_id = VALUES(category_id)""",
            (ctx.guild.id, hub.id, category.id)
        )
        
        embed = discord.Embed(
            title="✅ Private VC Setup Complete!",
            description=f"Join {hub.mention} to create your own temporary voice channel!",
            color=0x2ecc71
        )
        embed.add_field(name="How it works:", value="• Join the hub channel\n• Your VC is created automatically\n• Use the control panel to manage it\n• VC deletes when empty", inline=False)
        
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle VC creation and deletion"""
        await self._ensure_db()
        
        # CREATE VC when joining hub
        if after.channel and not member.bot:
            config = await self.get_hub_config(member.guild.id)
            
            if config and after.channel.id == config[0]:  # Joined hub
                category = member.guild.get_channel(config[1])
                
                # Set permissions
                overwrites = {
                    member.guild.default_role: discord.PermissionOverwrite(connect=True),
                    member: discord.PermissionOverwrite(
                        connect=True,
                        move_members=True,
                        manage_channels=True
                    )
                }
                
                # Create VC
                new_vc = await member.guild.create_voice_channel(
                    name=f"{member.display_name}'s VC",
                    category=category,
                    overwrites=overwrites
                )
                
                # Move user to their VC
                try:
                    await member.move_to(new_vc)
                except:
                    await new_vc.delete()
                    return

                panel_message = None
                try:
                    panel_message = await self._create_control_panel(
                        new_vc, member.id
                    )
                    await self._execute(
                        "INSERT INTO active_private_vcs "
                        "(voice_channel_id, owner_id, guild_id, "
                        "panel_message_id) VALUES (%s, %s, %s, %s)",
                        (
                            new_vc.id,
                            member.id,
                            member.guild.id,
                            panel_message.id
                        )
                    )
                    self._registered_panel_ids.add(panel_message.id)
                except Exception as exc:
                    print(
                        f"Error creating private VC control panel for "
                        f"{new_vc.id}: {exc}"
                    )
                    if panel_message is not None:
                        self._registered_panel_ids.discard(panel_message.id)
                    try:
                        await new_vc.delete()
                    except Exception as cleanup_exc:
                        print(
                            f"Error cleaning up untracked private VC "
                            f"{new_vc.id}: {cleanup_exc}"
                        )
                    return

        # DELETE VC when empty
        if before.channel:
            # Check if this is a private VC
            is_private = await self._execute(
                "SELECT 1 FROM active_private_vcs WHERE voice_channel_id = %s",
                (before.channel.id,), fetchone=True
            )
            
            if is_private:
                # Count humans only (ignore bots)
                humans = [m for m in before.channel.members if not m.bot]
                
                if len(humans) == 0:
                    try:
                        # Delete channel
                        await before.channel.delete()
                        
                        # Cleanup database
                        await self._execute(
                            "DELETE FROM active_private_vcs WHERE voice_channel_id = %s",
                            (before.channel.id,)
                        )
                    except Exception as e:
                        print(f"Error deleting private VC: {e}")


async def setup(bot):
    await bot.add_cog(PrivateVC(bot))
