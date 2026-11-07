"""
Staff Supervision Cog
━━━━━━━━━━━━━━━━━━━━━
All configuration stored in SQLite via slash commands.
Supports multiple staff roles AND multiple staff moderators.

Features:
  • Message tracking for staff roles
  • LOA system with approval flow & auto-expiry
  • Manual /staff-report command for activity overview

Config Keys (per guild):
  staff_roles       — JSON list of role IDs to track
  loa_role          — single role ID assigned during LOA
  admin_channel     — channel ID for LOA approvals
  staff_moderators  — JSON list of user IDs who can approve/deny LOAs
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Modal, TextInput, View, Button
from datetime import datetime, timedelta, date, timezone

# ── Embed colors ─────────────────────────────────────────────────────────────
COLOR_GREEN  = 0x2ecc71
COLOR_RED    = 0xe74c3c
COLOR_BLUE   = 0x3498db
COLOR_PURPLE = 0x9b59b6
COLOR_ORANGE = 0xe67e22
COLOR_GOLD   = 0xf1c40f


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _cfg(db, guild_id: int):
    return {
        'staff_roles':      db.get_config_list(guild_id, 'staff_roles'),
        'loa_role':         db.get_config_int(guild_id, 'loa_role', 0),
        'admin_channel':    db.get_config_int(guild_id, 'admin_channel', 0),
        'staff_moderators': db.get_config_list(guild_id, 'staff_moderators'),
    }


def _is_configured(cfg: dict) -> bool:
    return cfg['admin_channel'] != 0 and cfg['loa_role'] != 0


def _has_staff_role(member: discord.Member, staff_role_ids: list[int]) -> bool:
    return any(r.id in staff_role_ids for r in member.roles)


def _is_moderator(user_id: int, cfg: dict) -> bool:
    return user_id in cfg['staff_moderators']


def _can_manage(user: discord.Member, cfg: dict) -> bool:
    """Staff Moderators OR server Administrators."""
    return _is_moderator(user.id, cfg) or user.guild_permissions.administrator


# ═══════════════════════════════════════════════════════════════════════════════
#  UI COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════

class LOAModal(Modal, title="📋 Leave of Absence Request"):
    reason = TextInput(
        label="Reason for Leave",
        style=discord.TextStyle.paragraph,
        placeholder="Explain why you need time off...",
        required=True, max_length=500,
    )
    days = TextInput(
        label="Number of Days",
        style=discord.TextStyle.short,
        placeholder="e.g. 3",
        required=True, max_length=3,
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num_days = int(self.days.value)
            if num_days < 1 or num_days > 365:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ **Invalid number of days.** Enter a number between 1 and 365.", ephemeral=True
            )

        cfg = _cfg(self.cog.db, interaction.guild.id)
        end_date = (date.today() + timedelta(days=num_days)).isoformat()
        member = interaction.user

        embed = discord.Embed(
            title="📋 LOA Request",
            description=f"**{member.mention}** is requesting a Leave of Absence.",
            color=COLOR_ORANGE, timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 Staff Member", value=f"{member} (`{member.id}`)", inline=False)
        embed.add_field(name="📝 Reason", value=self.reason.value, inline=False)
        embed.add_field(name="📅 Duration", value=f"**{num_days}** day(s)", inline=True)
        embed.add_field(name="🗓️ End Date", value=f"`{end_date}`", inline=True)
        if interaction.guild.icon:
            embed.set_footer(text="Staff Supervision • LOA System", icon_url=interaction.guild.icon.url)
        else:
            embed.set_footer(text="Staff Supervision • LOA System")

        admin_channel = interaction.guild.get_channel(cfg['admin_channel'])
        if not admin_channel:
            return await interaction.response.send_message(
                "❌ **Admin channel not found.** Ask an admin to run `/supervision setup`.", ephemeral=True
            )

        view = LOAApprovalView(
            cog=self.cog, requester_id=member.id, reason=self.reason.value,
            num_days=num_days, end_date=end_date, guild_id=interaction.guild.id,
        )

        mod_pings = ' '.join(f"<@{mid}>" for mid in cfg['staff_moderators'])
        ping_text = f"🔔 {mod_pings} — New LOA request!" if mod_pings else "🔔 New LOA request!"

        await admin_channel.send(content=ping_text, embed=embed, view=view)
        await interaction.response.send_message(
            "✅ **Your LOA request has been submitted!** You'll receive a DM once it's reviewed.", ephemeral=True
        )


class LOAApprovalView(View):
    def __init__(self, cog, requester_id, reason, num_days, end_date, guild_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.requester_id = requester_id
        self.reason = reason
        self.num_days = num_days
        self.end_date = end_date
        self.guild_id = guild_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅")
    async def approve_button(self, interaction: discord.Interaction, button: Button):
        try:
            cfg = _cfg(self.cog.db, interaction.guild.id)
            if not _can_manage(interaction.user, cfg):
                return await interaction.response.send_message(
                    "❌ Only **Staff Moderators** or **Administrators** can approve.", ephemeral=True
                )

            guild = interaction.guild
            member = guild.get_member(self.requester_id)
            if not member:
                return await interaction.response.send_message("❌ Staff member not found.", ephemeral=True)

            # Only track & remove STAFF roles, leave other roles untouched
            staff_role_ids = cfg['staff_roles']
            member_staff_roles = [r for r in member.roles if r.id in staff_role_ids]
            stored_role_ids = [r.id for r in member_staff_roles]

            self.cog.db.add_loa(
                user_id=member.id, reason=self.reason,
                end_date=self.end_date, role_ids=stored_role_ids,
            )

            loa_role = guild.get_role(cfg['loa_role'])
            try:
                # Add LOA role first
                if loa_role:
                    await member.add_roles(loa_role, reason="LOA Approved")
                # Remove only staff roles
                if member_staff_roles:
                    await member.remove_roles(*member_staff_roles, reason="LOA Approved — staff roles stored")
            except discord.Forbidden:
                pass

            dm_embed = discord.Embed(
                title="✅ LOA Approved!",
                description="Your Leave of Absence has been **approved**.",
                color=COLOR_GREEN, timestamp=datetime.now(timezone.utc),
            )
            dm_embed.set_thumbnail(url=member.display_avatar.url)
            dm_embed.add_field(name="📝 Reason", value=self.reason, inline=False)
            dm_embed.add_field(name="📅 Duration", value=f"**{self.num_days}** day(s)", inline=True)
            dm_embed.add_field(name="🗓️ Ends On", value=f"`{self.end_date}`", inline=True)
            dm_embed.add_field(name="ℹ️ Note", value="Your roles will be **automatically restored** when your LOA ends.", inline=False)
            dm_embed.set_footer(text="Staff Supervision • LOA System")
            try:
                await member.send(embed=dm_embed)
            except discord.Forbidden:
                pass

            approved_embed = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed()
            approved_embed.color = COLOR_GREEN
            approved_embed.title = "✅ LOA Approved"
            approved_embed.add_field(name="✅ Approved By", value=f"{interaction.user.mention}", inline=False)
            await interaction.response.edit_message(embed=approved_embed, view=None)

        except Exception as e:
            print(f"❌ LOA Approve error: {e}")
            try:
                await interaction.response.send_message(f"❌ Error: `{e}`", ephemeral=True)
            except discord.InteractionResponded:
                pass

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❌")
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        try:
            cfg = _cfg(self.cog.db, interaction.guild.id)
            if not _can_manage(interaction.user, cfg):
                return await interaction.response.send_message(
                    "❌ Only **Staff Moderators** or **Administrators** can deny.", ephemeral=True
                )

            member = interaction.guild.get_member(self.requester_id)
            if member:
                dm_embed = discord.Embed(
                    title="❌ LOA Denied",
                    description="Your Leave of Absence request has been **denied**.",
                    color=COLOR_RED, timestamp=datetime.now(timezone.utc),
                )
                dm_embed.set_thumbnail(url=member.display_avatar.url)
                dm_embed.add_field(name="📝 Reason Submitted", value=self.reason, inline=False)
                dm_embed.add_field(name="ℹ️ What Now?", value="Reach out to a Staff Moderator for clarification.", inline=False)
                dm_embed.set_footer(text="Staff Supervision • LOA System")
                try:
                    await member.send(embed=dm_embed)
                except discord.Forbidden:
                    pass

            denied_embed = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed()
            denied_embed.color = COLOR_RED
            denied_embed.title = "❌ LOA Denied"
            denied_embed.add_field(name="❌ Denied By", value=f"{interaction.user.mention}", inline=False)
            await interaction.response.edit_message(embed=denied_embed, view=None)

        except Exception as e:
            print(f"❌ LOA Deny error: {e}")
            try:
                await interaction.response.send_message(f"❌ Error: `{e}`", ephemeral=True)
            except discord.InteractionResponded:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN COG
# ═══════════════════════════════════════════════════════════════════════════════

class StaffSupervision(commands.Cog):
    """Staff message tracking, LOA management, and activity reports."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        from utils.staff_db import staff_db
        self.db = staff_db

    async def cog_load(self):
        self.loa_expiry_check.start()
        print('📋 Staff Supervision cog loaded')

    async def cog_unload(self):
        self.loa_expiry_check.cancel()
        print('📋 Staff Supervision cog unloaded')

    # ═══════════════════════════════════════════════════════════════════════
    #  SETUP / CONFIG COMMANDS
    # ═══════════════════════════════════════════════════════════════════════

    supervision_group = app_commands.Group(
        name="supervision",
        description="Configure the Staff Supervision system",
    )

    @supervision_group.command(name="setup", description="Initial setup — set admin channel and LOA role")
    @app_commands.describe(
        admin_channel="Channel for LOA approvals",
        loa_role="Role assigned to staff on leave",
    )
    async def supervision_setup(
        self, interaction: discord.Interaction,
        admin_channel: discord.TextChannel,
        loa_role: discord.Role,
    ):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ You need **Administrator** permission.", ephemeral=True)

        gid = interaction.guild.id
        self.db.set_config(gid, 'admin_channel', admin_channel.id)
        self.db.set_config(gid, 'loa_role', loa_role.id)

        embed = discord.Embed(title="⚙️ Supervision Setup Complete", color=COLOR_GOLD, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="📢 Admin Channel", value=admin_channel.mention, inline=True)
        embed.add_field(name="🏖️ LOA Role", value=loa_role.mention, inline=True)

        staff_roles = self.db.get_config_list(gid, 'staff_roles')
        mods = self.db.get_config_list(gid, 'staff_moderators')
        embed.add_field(name="👥 Staff Roles", value=', '.join(f"<@&{r}>" for r in staff_roles) if staff_roles else "⚠️ Use `/supervision add-role`", inline=False)
        embed.add_field(name="🛡️ Moderators", value=', '.join(f"<@{m}>" for m in mods) if mods else "⚠️ Use `/supervision add-moderator`", inline=False)
        embed.set_footer(text="Staff Supervision • Config")
        await interaction.response.send_message(embed=embed)

    @supervision_group.command(name="add-role", description="Add a staff role to track")
    @app_commands.describe(role="The staff role to start tracking")
    async def supervision_add_role(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ You need **Administrator** permission.", ephemeral=True)
        added = self.db.add_to_config_list(interaction.guild.id, 'staff_roles', role.id)
        if not added:
            return await interaction.response.send_message(f"⚠️ {role.mention} is already tracked.", ephemeral=True)
        all_roles = self.db.get_config_list(interaction.guild.id, 'staff_roles')
        embed = discord.Embed(title="✅ Staff Role Added", description=f"{role.mention} will now be tracked.", color=COLOR_GREEN, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👥 All Tracked Roles", value=', '.join(f"<@&{r}>" for r in all_roles), inline=False)
        embed.set_footer(text="Staff Supervision • Config")
        await interaction.response.send_message(embed=embed)

    @supervision_group.command(name="remove-role", description="Stop tracking a staff role")
    @app_commands.describe(role="The staff role to stop tracking")
    async def supervision_remove_role(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ You need **Administrator** permission.", ephemeral=True)
        removed = self.db.remove_from_config_list(interaction.guild.id, 'staff_roles', role.id)
        if not removed:
            return await interaction.response.send_message(f"⚠️ {role.mention} was not tracked.", ephemeral=True)
        all_roles = self.db.get_config_list(interaction.guild.id, 'staff_roles')
        embed = discord.Embed(title="🗑️ Staff Role Removed", description=f"{role.mention} no longer tracked.", color=COLOR_RED, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👥 Remaining Roles", value=', '.join(f"<@&{r}>" for r in all_roles) if all_roles else "None", inline=False)
        embed.set_footer(text="Staff Supervision • Config")
        await interaction.response.send_message(embed=embed)

    @supervision_group.command(name="add-moderator", description="Add a user who can approve/deny LOA requests")
    @app_commands.describe(user="The user to grant Staff Moderator permissions")
    async def supervision_add_moderator(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ You need **Administrator** permission.", ephemeral=True)
        added = self.db.add_to_config_list(interaction.guild.id, 'staff_moderators', user.id)
        if not added:
            return await interaction.response.send_message(f"⚠️ {user.mention} is already a Staff Moderator.", ephemeral=True)
        all_mods = self.db.get_config_list(interaction.guild.id, 'staff_moderators')
        embed = discord.Embed(title="✅ Staff Moderator Added", description=f"{user.mention} can now approve/deny LOA requests.", color=COLOR_GREEN, timestamp=datetime.now(timezone.utc))
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="🛡️ All Staff Moderators", value=', '.join(f"<@{m}>" for m in all_mods), inline=False)
        embed.set_footer(text="Staff Supervision • Config")
        await interaction.response.send_message(embed=embed)

    @supervision_group.command(name="remove-moderator", description="Remove a Staff Moderator")
    @app_commands.describe(user="The user to remove from Staff Moderators")
    async def supervision_remove_moderator(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ You need **Administrator** permission.", ephemeral=True)
        removed = self.db.remove_from_config_list(interaction.guild.id, 'staff_moderators', user.id)
        if not removed:
            return await interaction.response.send_message(f"⚠️ {user.mention} was not a Staff Moderator.", ephemeral=True)
        all_mods = self.db.get_config_list(interaction.guild.id, 'staff_moderators')
        embed = discord.Embed(title="🗑️ Staff Moderator Removed", description=f"{user.mention} removed.", color=COLOR_RED, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🛡️ Remaining", value=', '.join(f"<@{m}>" for m in all_mods) if all_mods else "None", inline=False)
        embed.set_footer(text="Staff Supervision • Config")
        await interaction.response.send_message(embed=embed)

    @supervision_group.command(name="config", description="View the current supervision configuration")
    async def supervision_config(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ You need **Administrator** permission.", ephemeral=True)
        cfg = _cfg(self.db, interaction.guild.id)
        embed = discord.Embed(title="⚙️ Staff Supervision Configuration", color=COLOR_PURPLE, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👥 Staff Roles", value=', '.join(f"<@&{r}>" for r in cfg['staff_roles']) if cfg['staff_roles'] else "⚠️ None", inline=False)
        embed.add_field(name="🛡️ Staff Moderators", value=', '.join(f"<@{m}>" for m in cfg['staff_moderators']) if cfg['staff_moderators'] else "⚠️ None", inline=False)
        embed.add_field(name="📢 Admin Channel", value=f"<#{cfg['admin_channel']}>" if cfg['admin_channel'] else "⚠️ Not set", inline=True)
        embed.add_field(name="🏖️ LOA Role", value=f"<@&{cfg['loa_role']}>" if cfg['loa_role'] else "⚠️ Not set", inline=True)
        embed.set_footer(text="Staff Supervision • Config")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ═══════════════════════════════════════════════════════════════════════
    #  MESSAGE TRACKING
    # ═══════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        staff_roles = self.db.get_config_list(message.guild.id, 'staff_roles')
        if not staff_roles:
            return
        if _has_staff_role(message.author, staff_roles):
            self.db.increment_message(message.author.id)

    # ═══════════════════════════════════════════════════════════════════════
    #  STAFF REPORT (manual command)
    # ═══════════════════════════════════════════════════════════════════════

    @app_commands.command(name="staff-report", description="View staff activity report (messages & LOA status)")
    async def staff_report(self, interaction: discord.Interaction):
        cfg = _cfg(self.db, interaction.guild.id)

        if not _can_manage(interaction.user, cfg):
            return await interaction.response.send_message("❌ Staff Moderators or Administrators only.", ephemeral=True)

        if not cfg['staff_roles']:
            return await interaction.response.send_message("❌ No staff roles configured. Use `/supervision add-role`.", ephemeral=True)

        await interaction.response.defer()

        # Collect all tracked staff members
        tracked = []
        for role_id in cfg['staff_roles']:
            role = interaction.guild.get_role(role_id)
            if role:
                for m in role.members:
                    if not m.bot and m not in tracked:
                        tracked.append(m)

        if not tracked:
            return await interaction.followup.send("📋 No staff members found in tracked roles.", ephemeral=True)

        all_counts = self.db.get_all_counts()
        count_map = {row['user_id']: row for row in all_counts}

        embed = discord.Embed(
            title="📊 Staff Activity Report",
            description=f"**{len(tracked)}** staff member(s) across tracked roles.",
            color=COLOR_PURPLE, timestamp=datetime.now(timezone.utc),
        )

        sorted_members = sorted(tracked, key=lambda m: count_map.get(m.id, {}).get('weekly_count', 0), reverse=True)

        lines = []
        for i, member in enumerate(sorted_members, 1):
            data = count_map.get(member.id, {})
            daily = data.get('daily_count', 0)
            weekly = data.get('weekly_count', 0)
            on_loa = self.db.is_on_loa(member.id)

            if on_loa:
                loa_data = self.db.get_active_loa(member.id)
                days_left = (date.fromisoformat(loa_data['end_date']) - date.today()).days if loa_data else 0
                status = f"🏖️ LOA ({days_left}d left)"
            else:
                status = "✅ Active"

            lines.append(
                f"`{i:>2}.` **{member.display_name}** — {status}\n"
                f"      📨 Today: **{daily}** • This Week: **{weekly}**"
            )

        # Split into chunks of 10 for embed field limits
        for idx in range(0, len(lines), 10):
            chunk = lines[idx:idx + 10]
            name = "👥 Staff Members" if idx == 0 else "​"
            embed.add_field(name=name, value="\n".join(chunk), inline=False)

        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text="Staff Supervision • Activity Report")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="staff-reset", description="Reset all daily and weekly message counters")
    async def staff_reset(self, interaction: discord.Interaction):
        cfg = _cfg(self.db, interaction.guild.id)
        if not _can_manage(interaction.user, cfg):
            return await interaction.response.send_message("❌ Staff Moderators or Administrators only.", ephemeral=True)

        self.db.reset_daily()
        self.db.reset_weekly()
        await interaction.response.send_message("✅ All staff message counters have been **reset**.", ephemeral=True)

    # ═══════════════════════════════════════════════════════════════════════
    #  LOA COMMANDS
    # ═══════════════════════════════════════════════════════════════════════

    @app_commands.command(name="loa", description="Request a Leave of Absence")
    async def loa_command(self, interaction: discord.Interaction):
        cfg = _cfg(self.db, interaction.guild.id)
        if not _is_configured(cfg):
            return await interaction.response.send_message("❌ Supervision not configured. Ask an admin to run `/supervision setup`.", ephemeral=True)
        if not cfg['staff_roles']:
            return await interaction.response.send_message("❌ No staff roles configured. Ask an admin to run `/supervision add-role`.", ephemeral=True)
        if not _has_staff_role(interaction.user, cfg['staff_roles']):
            return await interaction.response.send_message("❌ You must be a staff member to request LOA.", ephemeral=True)
        if self.db.is_on_loa(interaction.user.id):
            return await interaction.response.send_message("⚠️ You already have an active LOA.", ephemeral=True)
        await interaction.response.send_modal(LOAModal(cog=self))

    @app_commands.command(name="loa-edit", description="[Staff Moderator] Edit a staff member's active LOA")
    @app_commands.describe(user="Staff member", days="New total days from today", reason="New reason (optional)")
    async def loa_edit(self, interaction: discord.Interaction, user: discord.Member, days: int, reason: str = None):
        cfg = _cfg(self.db, interaction.guild.id)
        if not _can_manage(interaction.user, cfg):
            return await interaction.response.send_message("❌ Staff Moderators or Administrators only.", ephemeral=True)
        if not self.db.is_on_loa(user.id):
            return await interaction.response.send_message(f"⚠️ **{user.display_name}** has no active LOA.", ephemeral=True)

        new_end = (date.today() + timedelta(days=days)).isoformat()
        self.db.update_loa(user.id, new_end_date=new_end, new_reason=reason)

        embed = discord.Embed(title="📝 LOA Updated", description=f"LOA for {user.mention} modified.", color=COLOR_GOLD, timestamp=datetime.now(timezone.utc))
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="🗓️ New End Date", value=f"`{new_end}`", inline=True)
        embed.add_field(name="📅 Days from Now", value=f"**{days}**", inline=True)
        if reason:
            embed.add_field(name="📝 New Reason", value=reason, inline=False)
        embed.set_footer(text=f"Updated by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

        dm_embed = discord.Embed(title="📝 Your LOA Has Been Updated", description="A Staff Moderator has modified your LOA.", color=COLOR_BLUE, timestamp=datetime.now(timezone.utc))
        dm_embed.set_thumbnail(url=user.display_avatar.url)
        dm_embed.add_field(name="🗓️ New End Date", value=f"`{new_end}`", inline=True)
        if reason:
            dm_embed.add_field(name="📝 New Reason", value=reason, inline=False)
        dm_embed.set_footer(text="Staff Supervision • LOA System")
        try:
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

    @app_commands.command(name="loa-remove", description="[Staff Moderator] Immediately end a staff member's LOA")
    @app_commands.describe(user="Staff member whose LOA to end")
    async def loa_remove(self, interaction: discord.Interaction, user: discord.Member):
        cfg = _cfg(self.db, interaction.guild.id)
        if not _can_manage(interaction.user, cfg):
            return await interaction.response.send_message("❌ Staff Moderators or Administrators only.", ephemeral=True)

        active_loa = self.db.get_active_loa(user.id)
        if not active_loa:
            return await interaction.response.send_message(f"⚠️ **{user.display_name}** has no active LOA.", ephemeral=True)

        await interaction.response.defer()
        await self._restore_member_roles(interaction.guild, user, active_loa, cfg)
        self.db.remove_loa_by_user(user.id)

        embed = discord.Embed(title="🔄 LOA Removed", description=f"{user.mention}'s LOA ended. Roles restored.", color=COLOR_GOLD, timestamp=datetime.now(timezone.utc))
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"Removed by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed)

        dm_embed = discord.Embed(title="🔄 Your LOA Has Been Ended Early", description="A Staff Moderator ended your LOA. Your roles have been **restored**.", color=COLOR_BLUE, timestamp=datetime.now(timezone.utc))
        dm_embed.set_thumbnail(url=user.display_avatar.url)
        dm_embed.set_footer(text="Staff Supervision • LOA System")
        try:
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

    @app_commands.command(name="loa-list", description="[Staff Moderator] View all active LOAs")
    async def loa_list(self, interaction: discord.Interaction):
        cfg = _cfg(self.db, interaction.guild.id)
        if not _can_manage(interaction.user, cfg):
            return await interaction.response.send_message("❌ Staff Moderators or Administrators only.", ephemeral=True)

        active_loas = self.db.get_all_active_loas()
        if not active_loas:
            return await interaction.response.send_message("📋 **No active LOAs.** All staff are on duty.", ephemeral=True)

        embed = discord.Embed(
            title="📋 Active LOAs", description=f"**{len(active_loas)}** staff on leave.",
            color=COLOR_PURPLE, timestamp=datetime.now(timezone.utc),
        )
        for loa in active_loas:
            member = interaction.guild.get_member(loa['user_id'])
            name = member.display_name if member else f"Unknown (`{loa['user_id']}`)"
            if member:
                embed.set_thumbnail(url=member.display_avatar.url)
            days_left = (date.fromisoformat(loa['end_date']) - date.today()).days
            embed.add_field(
                name=f"👤 {name}",
                value=f"**Reason:** {loa['reason']}\n**Ends:** `{loa['end_date']}` ({days_left}d left)",
                inline=False,
            )
        embed.set_footer(text="Staff Supervision • LOA System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ═══════════════════════════════════════════════════════════════════════
    #  LOA AUTO-EXPIRY (only background task remaining)
    # ═══════════════════════════════════════════════════════════════════════

    async def _restore_member_roles(self, guild, member, loa_data, cfg=None):
        if cfg is None:
            cfg = _cfg(self.db, guild.id)
        try:
            # Remove LOA role
            loa_role = guild.get_role(cfg['loa_role'])
            if loa_role and loa_role in member.roles:
                await member.remove_roles(loa_role, reason="LOA Ended — removing LOA role")
            # Restore only the stored staff roles
            role_ids = [int(r) for r in loa_data['original_roles'].split(',') if r.strip()]
            roles_to_add = [guild.get_role(rid) for rid in role_ids if guild.get_role(rid)]
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="LOA Ended — staff roles restored")
        except discord.Forbidden:
            print(f"  ⚠️ Could not restore roles for {member.id}")
        except Exception as e:
            print(f"  ⚠️ Error restoring roles for {member.id}: {e}")

    @tasks.loop(hours=1)
    async def loa_expiry_check(self):
        expired = self.db.get_expired_loas()
        if not expired:
            return
        for guild in self.bot.guilds:
            cfg = _cfg(self.db, guild.id)
            if not cfg['admin_channel']:
                continue
            for loa in expired:
                member = guild.get_member(loa['user_id'])
                if not member:
                    continue
                await self._restore_member_roles(guild, member, loa, cfg)
                self.db.remove_loa(loa['id'])

                dm_embed = discord.Embed(
                    title="🔔 Your LOA Has Ended",
                    description="Your LOA has **expired** and your roles have been **restored**.\nWelcome back!",
                    color=COLOR_BLUE, timestamp=datetime.now(timezone.utc),
                )
                dm_embed.set_thumbnail(url=member.display_avatar.url)
                dm_embed.add_field(name="📝 Original Reason", value=loa['reason'], inline=False)
                dm_embed.set_footer(text="Staff Supervision • LOA System")
                try:
                    await member.send(embed=dm_embed)
                except discord.Forbidden:
                    pass

                admin_ch = guild.get_channel(cfg['admin_channel'])
                if admin_ch:
                    embed = discord.Embed(title="🔄 LOA Expired", description=f"{member.mention}'s LOA has ended. Roles restored.", color=COLOR_BLUE, timestamp=datetime.now(timezone.utc))
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text="Staff Supervision • Auto-Expiry")
                    await admin_ch.send(embed=embed)

    @loa_expiry_check.before_loop
    async def before_loa_expiry(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(StaffSupervision(bot))
