import asyncio
import io
import re
from datetime import datetime, timezone
from html import escape

import discord
from discord.ext import commands
from discord.ui import Button, Select, View

import config
from utils.database import settings_db
from utils.embeds import error_embed, info_embed, success_embed


def utc_timestamp():
    return int(datetime.now(timezone.utc).timestamp())


def channel_safe_name(*parts):
    raw = "-".join(str(part or "") for part in parts)
    raw = raw.lower()
    raw = re.sub(r"[^a-z0-9-]+", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    return (raw or "therapy-session")[:90]


PANEL_DEFAULT_TITLE = "Private Therapy Sessions"
PANEL_DEFAULT_DESCRIPTION = "Press the button below to choose a therapist and open a private support channel."
OLD_PANEL_PRIVACY_FOOTER = "Only you, your selected therapist, and the bot can see your session channel."
PANEL_DEFAULT_FOOTER = ""


class TherapyPanelView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Start Session",
        style=discord.ButtonStyle.primary,
        custom_id="xiel:therapy:start",
    )
    async def start_session(self, interaction: discord.Interaction, button: Button):
        await self.cog.handle_panel_click(interaction)


class TherapyCloseView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="End Session",
        style=discord.ButtonStyle.danger,
        custom_id="xiel:therapy:close",
    )
    async def close_session(self, interaction: discord.Interaction, button: Button):
        await self.cog.handle_close_interaction(interaction)


class TherapistSelect(Select):
    def __init__(self, cog, therapists):
        self.cog = cog
        options = [
            discord.SelectOption(
                label=member.display_name[:100],
                value=str(member.id),
                description=str(member)[:100],
            )
            for member in therapists[:25]
        ]
        super().__init__(
            placeholder="Choose a therapist",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="xiel:therapy:therapist_select",
        )

    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_therapist_selected(interaction, int(self.values[0]))


class TherapistSelectView(View):
    def __init__(self, cog, therapists):
        super().__init__(timeout=180)
        self.add_item(TherapistSelect(cog, therapists))


class SessionTherapistSelect(Select):
    def __init__(self, cog, action, therapists, author_id, reason=None):
        self.cog = cog
        self.action = action
        self.author_id = author_id
        self.reason = reason
        verb = "add to this session" if action == "add" else "pass this session to"
        options = [
            discord.SelectOption(
                label=member.display_name[:100],
                value=str(member.id),
                description=f"{verb} {str(member)[:70]}",
            )
            for member in therapists[:25]
        ]
        super().__init__(
            placeholder=f"Choose a therapist to {action}",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"xiel:therapy:session_{action}_select",
        )

    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_session_therapist_selected(
            interaction,
            self.action,
            int(self.values[0]),
            self.author_id,
            self.reason,
        )


class SessionTherapistSelectView(View):
    def __init__(self, cog, action, therapists, author_id, reason=None):
        super().__init__(timeout=180)
        self.add_item(SessionTherapistSelect(cog, action, therapists, author_id, reason))


class TherapySessions(commands.Cog):
    """Private therapy/support session channels."""

    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TherapyPanelView(self))
        self.bot.add_view(TherapyCloseView(self))

    def _prefix(self, ctx):
        return getattr(ctx, "prefix", None) or config.PREFIX

    def _db_ready(self):
        return settings_db is not None

    def _config(self, guild_id):
        if not self._db_ready():
            return None
        return settings_db.get_therapy_config(guild_id)

    async def _reply_db_offline(self, ctx):
        await ctx.reply(embed=error_embed("Database Offline", "Therapy sessions cannot be saved right now."))

    async def _send_therapist_list(self, ctx):
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        therapists = self._all_therapists(ctx.guild)
        config_row = self._config(ctx.guild.id) or {}
        role_text = "None"
        if config_row.get("therapist_role_id"):
            role = ctx.guild.get_role(int(config_row["therapist_role_id"]))
            role_text = role.mention if role else "Missing role"
        recommend_text = "None"
        if config_row.get("recommend_role_id"):
            role = ctx.guild.get_role(int(config_row["recommend_role_id"]))
            recommend_text = role.mention if role else "Missing role"
        if not therapists:
            desc = f"No therapists configured.\nTherapist role: {role_text}\nRecommend role: {recommend_text}"
        else:
            desc = "\n".join(f"`{index}.` {member.mention}" for index, member in enumerate(therapists[:25], start=1))
            desc += f"\n\nTherapist role: {role_text}\nRecommend role: {recommend_text}"
        await ctx.reply(embed=info_embed(f"Therapists ({len(therapists)})", desc))

    async def _get_config_or_error(self, interaction):
        if not self._db_ready():
            await interaction.response.send_message("Therapy sessions are unavailable because the database is offline.", ephemeral=True)
            return None
        config_row = settings_db.get_therapy_config(interaction.guild.id)
        if not config_row or not config_row.get("panel_channel_id"):
            await interaction.response.send_message("Therapy sessions are not set up yet.", ephemeral=True)
            return None
        return config_row

    def _is_admin(self, member):
        return bool(member.guild_permissions.manage_guild or member.guild_permissions.manage_channels or member.guild_permissions.administrator)

    def _has_recommend_role(self, member):
        config_row = self._config(member.guild.id) or {}
        role_id = config_row.get("recommend_role_id")
        if not role_id:
            return False
        role = member.guild.get_role(int(role_id))
        return bool(role and role in member.roles)

    def _can_recommend_therapists(self, member):
        return self._is_admin(member) or member.id in config.OWNER_IDS or self._has_recommend_role(member)

    def _is_configured_therapist(self, member):
        if not member or member.bot:
            return False
        return any(therapist.id == member.id for therapist in self._all_therapists(member.guild))

    def _member_can_close(self, member, session):
        return (
            str(member.id) in {str(session["requester_id"]), str(session["therapist_id"])}
            or self._is_admin(member)
            or member.id in config.OWNER_IDS
        )

    def _member_can_pass_session(self, member, session):
        return (
            self._can_recommend_therapists(member)
            and str(member.id) == str(session["therapist_id"])
        ) or self._is_admin(member) or member.id in config.OWNER_IDS

    def _session_therapist_choices(self, guild, session, action):
        excluded = {str(session["requester_id"])}
        if action == "pass":
            excluded.add(str(session["therapist_id"]))
        choices = [
            member
            for member in self._all_therapists(guild)
            if str(member.id) not in excluded
        ]
        choices.sort(key=lambda member: member.display_name.lower())
        return choices[:25]

    def _all_therapists(self, guild, requester=None):
        if not self._db_ready():
            return []
        config_row = settings_db.get_therapy_config(guild.id) or {}
        ids = {str(row["user_id"]) for row in settings_db.get_therapy_therapists(guild.id)}

        role_id = config_row.get("therapist_role_id")
        if role_id:
            role = guild.get_role(int(role_id))
            if role:
                ids.update(str(member.id) for member in role.members)

        members = []
        for user_id in ids:
            member = guild.get_member(int(user_id))
            if not member or member.bot:
                continue
            if requester and member.id == requester.id:
                continue
            members.append(member)
        members.sort(key=lambda member: member.display_name.lower())
        return members

    def _panel_embed(self, title=PANEL_DEFAULT_TITLE, description=PANEL_DEFAULT_DESCRIPTION, footer=PANEL_DEFAULT_FOOTER):
        embed = discord.Embed(
            title=title or PANEL_DEFAULT_TITLE,
            description=description or PANEL_DEFAULT_DESCRIPTION,
            color=config.COLORS.get("primary", 0x9B59B6),
            timestamp=discord.utils.utcnow(),
        )
        if footer:
            embed.set_footer(text=footer)
        return embed

    def _panel_parts_from_message(self, message):
        current = message.embeds[0] if message.embeds else self._panel_embed()
        title = current.title or PANEL_DEFAULT_TITLE
        description = current.description or PANEL_DEFAULT_DESCRIPTION
        footer = current.footer.text if current.footer and current.footer.text else PANEL_DEFAULT_FOOTER
        if footer == OLD_PANEL_PRIVACY_FOOTER:
            footer = PANEL_DEFAULT_FOOTER
        return title, description, footer

    async def _edit_saved_panel(self, ctx, title=None, description=None, footer=None):
        config_row = settings_db.get_therapy_config(ctx.guild.id)
        message, error = await self._get_panel_message(ctx.guild, config_row)
        if error:
            return await ctx.reply(embed=error_embed("Panel Not Found", error))

        current_title, current_description, current_footer = self._panel_parts_from_message(message)
        title = current_title if title is None else title
        description = current_description if description is None else description
        footer = current_footer if footer is None else footer

        try:
            await message.edit(embed=self._panel_embed(title, description, footer), view=TherapyPanelView(self))
        except discord.Forbidden:
            return await ctx.reply(embed=error_embed("Missing Permission", "I cannot edit the saved panel message."))
        except Exception as exc:
            return await ctx.reply(embed=error_embed("Edit Failed", str(exc)))

        await ctx.reply(embed=success_embed("Panel Updated", f"Edited the therapy panel in {message.channel.mention}."))

    async def _get_panel_message(self, guild, config_row):
        if not config_row or not config_row.get("panel_channel_id") or not config_row.get("panel_message_id"):
            return None, "No saved panel message. Use `therapy panel` first."
        channel = guild.get_channel(int(config_row["panel_channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return None, "The configured therapy panel channel no longer exists."
        try:
            return await channel.fetch_message(int(config_row["panel_message_id"])), None
        except discord.NotFound:
            return None, "The saved panel message no longer exists. Use `therapy panel` to send a new one."
        except discord.Forbidden:
            return None, f"I cannot read message history in {channel.mention}."
        except Exception as exc:
            return None, f"I could not fetch the panel message: {exc}"

    def _session_dt(self, value):
        if isinstance(value, datetime):
            return value.replace(tzinfo=value.tzinfo or timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return str(value or "Unknown")

    async def _build_transcript_file(self, channel, session, closed_by, reason):
        rows = []
        async for message in channel.history(limit=None, oldest_first=True):
            author = escape(str(message.author))
            display_name = escape(message.author.display_name)
            avatar = escape(str(message.author.display_avatar.url))
            timestamp = message.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            content = escape(message.content or "").replace("\n", "<br>")

            attachments = ""
            if message.attachments:
                links = "".join(
                    f'<li><a href="{escape(attachment.url)}">{escape(attachment.filename)}</a></li>'
                    for attachment in message.attachments
                )
                attachments = f'<ul class="attachments">{links}</ul>'

            embeds = ""
            if message.embeds:
                embed_rows = []
                for embed in message.embeds:
                    title = escape(embed.title or "Embed")
                    desc = escape(embed.description or "").replace("\n", "<br>")
                    embed_rows.append(f'<div class="embed"><strong>{title}</strong><p>{desc}</p></div>')
                embeds = "".join(embed_rows)

            rows.append(
                f"""
                <article class="message">
                    <img src="{avatar}" alt="" class="avatar">
                    <div>
                        <div class="meta"><strong>{display_name}</strong> <span>{author}</span> <time>{timestamp}</time></div>
                        <div class="content">{content or '<em>No text content</em>'}</div>
                        {attachments}
                        {embeds}
                    </div>
                </article>
                """
            )

        requester = channel.guild.get_member(int(session["requester_id"]))
        therapist = channel.guild.get_member(int(session["therapist_id"]))
        closed_by_text = escape(str(closed_by or "Unknown"))
        html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Therapy Session #{escape(str(session["id"]))}</title>
<style>
body {{ margin: 0; background: #101318; color: #edf2f7; font: 15px/1.5 Arial, sans-serif; }}
main {{ max-width: 980px; margin: 0 auto; padding: 32px 18px; }}
header {{ border-bottom: 1px solid #2d3748; margin-bottom: 24px; padding-bottom: 18px; }}
h1 {{ margin: 0 0 8px; font-size: 26px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; color: #cbd5e0; }}
.message {{ display: grid; grid-template-columns: 44px 1fr; gap: 12px; padding: 14px 0; border-bottom: 1px solid #252c38; }}
.avatar {{ width: 40px; height: 40px; border-radius: 50%; }}
.meta {{ color: #a0aec0; font-size: 13px; }}
.meta strong {{ color: #fff; margin-right: 8px; }}
.meta time {{ display: block; margin-top: 2px; }}
.content {{ margin-top: 6px; white-space: normal; }}
.attachments {{ margin: 8px 0 0; padding-left: 18px; }}
a {{ color: #63b3ed; }}
.embed {{ margin-top: 8px; padding: 10px; border-left: 3px solid #9f7aea; background: #171b23; }}
em {{ color: #8f9bad; }}
</style>
</head>
<body>
<main>
<header>
<h1>Therapy Session #{escape(str(session["id"]))}</h1>
<div class="grid">
<div><strong>Channel:</strong> #{escape(channel.name)} ({escape(str(channel.id))})</div>
<div><strong>Requester:</strong> {escape(str(requester or session["requester_id"]))}</div>
<div><strong>Therapist:</strong> {escape(str(therapist or session["therapist_id"]))}</div>
<div><strong>Opened:</strong> {escape(self._session_dt(session.get("opened_at")))}</div>
<div><strong>Closed By:</strong> {closed_by_text}</div>
<div><strong>Reason:</strong> {escape(reason or "No reason provided.")}</div>
</div>
</header>
{''.join(rows) or '<p><em>No messages were found in this session.</em></p>'}
</main>
</body>
</html>"""
        filename = f"therapy_session_{session['id']}_{channel.id}.html"
        return discord.File(io.BytesIO(html.encode("utf-8")), filename=filename)

    async def _log_session_close(self, guild, session, closed_by, reason, transcript_file=None):
        config_row = self._config(guild.id) or {}
        channel_id = config_row.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        requester = guild.get_member(int(session["requester_id"]))
        therapist = guild.get_member(int(session["therapist_id"]))
        embed = discord.Embed(
            title="Therapy Session Closed",
            color=config.COLORS.get("secondary", 0x3498DB),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Requester", value=requester.mention if requester else f"<@{session['requester_id']}>", inline=True)
        embed.add_field(name="Therapist", value=therapist.mention if therapist else f"<@{session['therapist_id']}>", inline=True)
        embed.add_field(name="Closed By", value=closed_by.mention if closed_by else "Unknown", inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided.", inline=False)
        embed.add_field(name="Opened", value=self._session_dt(session.get("opened_at")), inline=True)
        embed.set_footer(text=f"Session #{session['id']} | Channel {session['channel_id']}")
        try:
            kwargs = {"embed": embed, "allowed_mentions": discord.AllowedMentions.none()}
            if transcript_file:
                kwargs["file"] = transcript_file
            await channel.send(**kwargs)
        except Exception as exc:
            print(f"Therapy log send error in {guild.id}: {exc}")

    async def _close_session(self, guild, channel, session, closed_by=None, reason=None, announce=True):
        if not self._db_ready():
            return False
        transcript_file = None
        if channel:
            try:
                transcript_file = await self._build_transcript_file(channel, session, closed_by, reason)
            except Exception as exc:
                print(f"Therapy transcript build error in {guild.id}: {exc}")
        settings_db.close_therapy_session(guild.id, session["channel_id"], closed_by.id if closed_by else None, reason)
        await self._log_session_close(guild, session, closed_by, reason, transcript_file)

        if channel and announce:
            try:
                await channel.send(embed=success_embed("Session Ending", "This therapy session will be deleted shortly."))
                await asyncio.sleep(3)
            except Exception:
                pass
        if channel:
            try:
                await channel.delete(reason=f"Therapy session closed by {closed_by} ({closed_by.id if closed_by else 'unknown'})")
            except discord.NotFound:
                pass
            except Exception as exc:
                print(f"Therapy channel delete error in {guild.id}: {exc}")
                return False
        return True

    async def _create_session_channel(self, interaction, therapist, config_row):
        guild = interaction.guild
        requester = interaction.user
        category = None
        if config_row.get("category_id"):
            category = guild.get_channel(int(config_row["category_id"]))
        if not isinstance(category, discord.CategoryChannel) and config_row.get("panel_channel_id"):
            panel_channel = guild.get_channel(int(config_row["panel_channel_id"]))
            category = panel_channel.category if isinstance(panel_channel, discord.TextChannel) else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            ),
            requester: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            therapist: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
        }

        name = channel_safe_name("therapy", requester.display_name, therapist.display_name)
        return await guild.create_text_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            reason=f"Therapy session for {requester} with {therapist}",
        )

    async def handle_panel_click(self, interaction):
        if not interaction.guild or interaction.user.bot:
            return
        config_row = await self._get_config_or_error(interaction)
        if not config_row:
            return

        existing = settings_db.get_open_therapy_session_for_user(interaction.guild.id, interaction.user.id)
        if existing:
            channel = interaction.guild.get_channel(int(existing["channel_id"]))
            if channel:
                return await interaction.response.send_message(f"You already have an open session: {channel.mention}", ephemeral=True)
            settings_db.close_therapy_session(interaction.guild.id, existing["channel_id"], None, "Stale session channel was missing.")

        therapists = self._all_therapists(interaction.guild, requester=interaction.user)
        if not therapists:
            return await interaction.response.send_message("No therapists are available yet. Please ask staff to configure therapists.", ephemeral=True)
        await interaction.response.send_message(
            "Choose the therapist you want to talk to.",
            view=TherapistSelectView(self, therapists),
            ephemeral=True,
        )

    async def handle_therapist_selected(self, interaction, therapist_id):
        if not interaction.guild:
            return
        if not self._db_ready():
            return await interaction.response.edit_message(content="Therapy sessions are unavailable because the database is offline.", view=None)
        config_row = settings_db.get_therapy_config(interaction.guild.id)
        if not config_row:
            return await interaction.response.edit_message(content="Therapy sessions are not set up yet.", view=None)

        therapist = interaction.guild.get_member(therapist_id)
        if not therapist or therapist.bot:
            return await interaction.response.edit_message(content="That therapist is no longer available.", view=None)
        if therapist.id == interaction.user.id:
            return await interaction.response.edit_message(content="You cannot open a session with yourself.", view=None)
        if therapist not in self._all_therapists(interaction.guild, requester=interaction.user):
            return await interaction.response.edit_message(content="That therapist is not currently configured.", view=None)

        existing = settings_db.get_open_therapy_session_for_user(interaction.guild.id, interaction.user.id)
        if existing:
            channel = interaction.guild.get_channel(int(existing["channel_id"]))
            if channel:
                return await interaction.response.edit_message(content=f"You already have an open session: {channel.mention}", view=None)
            settings_db.close_therapy_session(interaction.guild.id, existing["channel_id"], None, "Stale session channel was missing.")

        guild_perms = interaction.guild.me.guild_permissions
        if not guild_perms.manage_channels:
            return await interaction.response.edit_message(content="I need Manage Channels to create therapy session rooms.", view=None)

        await interaction.response.edit_message(content="Creating your private session...", view=None)
        try:
            channel = await self._create_session_channel(interaction, therapist, config_row)
        except Exception as exc:
            return await interaction.edit_original_response(content=f"I could not create the therapy channel: {exc}", view=None)

        session_id = settings_db.create_therapy_session(interaction.guild.id, interaction.user.id, therapist.id, channel.id)
        if not session_id:
            try:
                await channel.delete(reason="Therapy session DB save failed")
            except Exception:
                pass
            return await interaction.edit_original_response(content="I created the channel but could not save the session, so I removed it.", view=None)

        embed = discord.Embed(
            title="Private Therapy Session",
            description=(
                f"{interaction.user.mention}, {therapist.mention} is here with you.\n\n"
                "This is a private support space. When you are done, press **End Session** "
                f"or use `{config.PREFIX}therapy close [reason]`."
            ),
            color=config.COLORS.get("primary", 0x9B59B6),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Session #{session_id}")
        await channel.send(
            content=f"{interaction.user.mention} {therapist.mention}",
            embed=embed,
            view=TherapyCloseView(self),
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )
        try:
            await interaction.delete_original_response()
        except Exception:
            try:
                await interaction.edit_original_response(content=f"Your private session is ready: {channel.mention}", view=None)
            except Exception:
                pass

    async def handle_close_interaction(self, interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return
        if not self._db_ready():
            return await interaction.response.send_message("Database is offline, so I cannot close this session safely.", ephemeral=True)
        session = settings_db.get_open_therapy_session_by_channel(interaction.guild.id, interaction.channel.id)
        if not session:
            return await interaction.response.send_message("This is not an open therapy session channel.", ephemeral=True)
        if not self._member_can_close(interaction.user, session):
            return await interaction.response.send_message("Only the requester, selected therapist, or staff can end this session.", ephemeral=True)
        await interaction.response.send_message("Ending this session now.", ephemeral=True)
        await self._close_session(interaction.guild, interaction.channel, session, interaction.user, "Closed from session button.")

    async def _add_therapist_to_session(self, channel, actor, session, member):
        if not self._member_can_pass_session(actor, session):
            return False, error_embed("Missing Permission", "Only the selected therapist with the recommend role, or staff, can add therapists here.")
        if not member or member.bot:
            return False, error_embed("Invalid Therapist", "Choose a valid therapist.")
        if not self._is_configured_therapist(member):
            return False, error_embed("Not A Therapist", f"{member.mention} is not configured as a therapist yet.")
        try:
            await channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                reason=f"Therapy therapist added by {actor}",
            )
        except Exception as exc:
            return False, error_embed("Add Failed", f"I could not update channel permissions: {exc}")
        return True, success_embed("Therapist Added To Session", f"{member.mention} can now access this session.")

    async def _pass_session_to_therapist(self, channel, actor, session, member, reason=None):
        if not self._member_can_pass_session(actor, session):
            return False, error_embed("Missing Permission", "Only the selected therapist with the recommend role, or staff, can pass this session.")
        if not member or member.bot:
            return False, error_embed("Invalid Therapist", "Choose a valid therapist.")
        if member.id == int(session["therapist_id"]):
            return False, error_embed("Already Assigned", f"{member.mention} is already the selected therapist.")
        if not self._is_configured_therapist(member):
            return False, error_embed("Not A Therapist", f"{member.mention} is not configured as a therapist yet.")

        old_therapist = channel.guild.get_member(int(session["therapist_id"]))
        try:
            await channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                reason=f"Therapy session passed by {actor}",
            )
        except Exception as exc:
            return False, error_embed("Pass Failed", f"I could not update channel permissions: {exc}")

        if not settings_db.transfer_therapy_session(channel.guild.id, channel.id, member.id):
            return False, error_embed("Save Failed", "I updated permissions but could not save the new therapist.")

        if old_therapist:
            try:
                await channel.set_permissions(old_therapist, overwrite=None, reason=f"Therapy session passed to {member}")
            except Exception as exc:
                print(f"Therapy pass old therapist remove error in {channel.guild.id}: {exc}")

        note = f" Reason: {reason}" if reason else ""
        return True, success_embed("Session Passed", f"This session is now assigned to {member.mention}.{note}")

    async def handle_session_therapist_selected(self, interaction, action, therapist_id, author_id, reason=None):
        if interaction.user.id != author_id:
            return await interaction.response.send_message("This therapist picker is not for you.", ephemeral=True)
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return
        if not self._db_ready():
            return await interaction.response.send_message("Database is offline, so I cannot update this session.", ephemeral=True)
        session = settings_db.get_open_therapy_session_by_channel(interaction.guild.id, interaction.channel.id)
        if not session:
            return await interaction.response.send_message("This is not an open therapy session channel.", ephemeral=True)
        member = interaction.guild.get_member(therapist_id)
        if action == "add":
            ok, embed = await self._add_therapist_to_session(interaction.channel, interaction.user, session, member)
        else:
            ok, embed = await self._pass_session_to_therapist(interaction.channel, interaction.user, session, member, reason)
        if ok:
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.group(name="therapy", invoke_without_command=True)
    @commands.guild_only()
    async def therapy(self, ctx):
        """Manage private therapy/support sessions."""
        prefix = self._prefix(ctx)
        desc = (
            f"`{prefix}therapy setup <#channel> [category]`\n"
            f"`{prefix}therapy panel`\n"
            f"`{prefix}therapy panel title <text>`\n"
            f"`{prefix}therapy panel description <text>`\n"
            f"`{prefix}therapy panel footer <text|clear>`\n"
            f"`{prefix}therapy therapist add @user`\n"
            f"`{prefix}therapy recommendrole @role|clear`\n"
            f"`{prefix}therapy add @therapist`\n"
            f"`{prefix}therapy pass @therapist [reason]`\n"
            f"`{prefix}therapy close [reason]`"
        )
        await ctx.reply(embed=info_embed("Therapy Sessions", desc))

    @therapy.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(send_messages=True, manage_channels=True)
    async def therapy_setup(self, ctx, channel: discord.TextChannel = None, category: discord.CategoryChannel = None):
        """Set the therapy panel channel and optional session category."""
        if not channel:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}therapy setup <#channel> [category]`"))
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        category = category or channel.category
        ok = settings_db.set_therapy_config(
            ctx.guild.id,
            panel_channel_id=channel.id,
            category_id=category.id if category else None,
        )
        if not ok:
            return await ctx.reply(embed=error_embed("Save Failed", "I could not save therapy setup."))
        where = f" Sessions will be created in **{category.name}**." if category else ""
        await ctx.reply(embed=success_embed("Therapy Setup Saved", f"Panel channel set to {channel.mention}.{where}"))

    @therapy.group(name="therapist", invoke_without_command=True)
    async def therapy_therapist(self, ctx):
        """Manage manually configured therapists."""
        if not self._can_recommend_therapists(ctx.author):
            return await ctx.reply(embed=error_embed("Missing Permission", "You need the therapy recommend role or Manage Server."))
        await self._send_therapist_list(ctx)

    @therapy_therapist.command(name="add")
    async def therapy_therapist_add(self, ctx, member: discord.Member = None):
        if not self._can_recommend_therapists(ctx.author):
            return await ctx.reply(embed=error_embed("Missing Permission", "You need the therapy recommend role or Manage Server."))
        if not member or member.bot:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}therapy therapist add @user`"))
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        settings_db.add_therapy_therapist(ctx.guild.id, member.id, ctx.author.id)
        await ctx.reply(embed=success_embed("Therapist Added", f"{member.mention} can now be selected for therapy sessions."))

    @therapy_therapist.command(name="remove", aliases=["delete"])
    async def therapy_therapist_remove(self, ctx, member: discord.Member = None):
        if not self._can_recommend_therapists(ctx.author):
            return await ctx.reply(embed=error_embed("Missing Permission", "You need the therapy recommend role or Manage Server."))
        if not member:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}therapy therapist remove @user`"))
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        removed = settings_db.remove_therapy_therapist(ctx.guild.id, member.id)
        if removed:
            return await ctx.reply(embed=success_embed("Therapist Removed", f"{member.mention} was removed from the manual therapist list."))
        await ctx.reply(embed=error_embed("Not Found", f"{member.mention} was not in the manual therapist list."))

    @therapy_therapist.command(name="list")
    async def therapy_therapist_list(self, ctx):
        if not self._can_recommend_therapists(ctx.author):
            return await ctx.reply(embed=error_embed("Missing Permission", "You need the therapy recommend role or Manage Server."))
        await self._send_therapist_list(ctx)

    @therapy.command(name="role")
    @commands.has_permissions(manage_guild=True)
    async def therapy_role(self, ctx, *, role_arg: str = None):
        """Set or clear the therapist role."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        role_arg = str(role_arg or "").strip()
        if role_arg.lower() == "clear":
            settings_db.set_therapy_config(ctx.guild.id, therapist_role_id=None)
            return await ctx.reply(embed=success_embed("Therapist Role Cleared", "Only manually added therapists will be shown."))
        try:
            role = await commands.RoleConverter().convert(ctx, role_arg)
        except commands.BadArgument:
            role = None
        if not role:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}therapy role @role|clear`"))
        settings_db.set_therapy_config(ctx.guild.id, therapist_role_id=role.id)
        await ctx.reply(embed=success_embed("Therapist Role Set", f"Members with {role.mention} can be selected as therapists."))

    @therapy.command(
        name="recommendrole",
        aliases=["recommend", "recommenderole", "recommedrole", "recommed", "reccomendrole", "reccomend"],
    )
    @commands.has_permissions(manage_guild=True)
    async def therapy_recommend_role(self, ctx, *, role_arg: str = None):
        """Set or clear the role allowed to recommend, add, and pass therapists."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        role_arg = str(role_arg or "").strip()
        lowered = role_arg.lower()
        for prefix in ("role ", "set "):
            if lowered.startswith(prefix):
                role_arg = role_arg[len(prefix):].strip()
                lowered = role_arg.lower()
        if role_arg.lower() == "clear":
            settings_db.set_therapy_config(ctx.guild.id, recommend_role_id=None)
            return await ctx.reply(embed=success_embed("Recommend Role Cleared", "Only staff can recommend or pass therapy sessions now."))
        try:
            role = await commands.RoleConverter().convert(ctx, role_arg)
        except commands.BadArgument:
            role = None
        if not role:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}therapy recommendrole @role|clear`"))
        settings_db.set_therapy_config(ctx.guild.id, recommend_role_id=role.id)
        await ctx.reply(embed=success_embed("Recommend Role Set", f"Members with {role.mention} can add therapists and pass active sessions."))

    @therapy.command(name="logchannel", aliases=["logs"])
    @commands.has_permissions(manage_guild=True)
    async def therapy_logchannel(self, ctx, *, channel_arg: str = None):
        """Set or clear the therapy session log channel."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        channel_arg = str(channel_arg or "").strip()
        if channel_arg.lower() == "clear":
            settings_db.set_therapy_config(ctx.guild.id, log_channel_id=None)
            return await ctx.reply(embed=success_embed("Log Channel Cleared", "Therapy session close logs are disabled."))
        try:
            channel = await commands.TextChannelConverter().convert(ctx, channel_arg)
        except commands.BadArgument:
            channel = None
        if not channel:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}therapy logchannel #channel|clear`"))
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.reply(embed=error_embed("Missing Permission", f"I cannot send logs in {channel.mention}."))
        if not channel.permissions_for(ctx.guild.me).attach_files:
            return await ctx.reply(embed=error_embed("Missing Permission", f"I need Attach Files in {channel.mention} to upload HTML transcripts."))
        settings_db.set_therapy_config(ctx.guild.id, log_channel_id=channel.id)
        await ctx.reply(embed=success_embed("Log Channel Set", f"Therapy session close logs will be sent to {channel.mention}."))

    @therapy.group(name="panel", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def therapy_panel(self, ctx):
        """Send the therapy session panel."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        config_row = settings_db.get_therapy_config(ctx.guild.id)
        if not config_row or not config_row.get("panel_channel_id"):
            return await ctx.reply(embed=error_embed("Not Set Up", f"Use `{self._prefix(ctx)}therapy setup <#channel> [category]` first."))
        channel = ctx.guild.get_channel(int(config_row["panel_channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return await ctx.reply(embed=error_embed("Missing Channel", "The configured therapy panel channel no longer exists."))
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.reply(embed=error_embed("Missing Permission", f"I cannot send messages in {channel.mention}."))

        message = await channel.send(embed=self._panel_embed(), view=TherapyPanelView(self))
        settings_db.set_therapy_config(ctx.guild.id, panel_message_id=message.id)
        await ctx.reply(embed=success_embed("Therapy Panel Sent", f"Panel sent in {channel.mention}."))

    @therapy_panel.command(name="title")
    @commands.has_permissions(manage_guild=True)
    async def therapy_panel_title(self, ctx, *, title: str = None):
        """Edit only the therapy panel title."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        title = str(title or "").strip()
        if not title:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}therapy panel title <text>`"))
        await self._edit_saved_panel(ctx, title=title)

    @therapy_panel.command(name="description", aliases=["desc"])
    @commands.has_permissions(manage_guild=True)
    async def therapy_panel_description(self, ctx, *, description: str = None):
        """Edit only the therapy panel description."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        description = str(description or "").strip()
        if not description:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}therapy panel description <text>`"))
        await self._edit_saved_panel(ctx, description=description)

    @therapy_panel.command(name="footer")
    @commands.has_permissions(manage_guild=True)
    async def therapy_panel_footer(self, ctx, *, footer: str = None):
        """Edit or clear only the therapy panel footer."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        footer = str(footer or "").strip()
        if footer.lower() in {"", "clear", "none", "remove", "off"}:
            footer = ""
        await self._edit_saved_panel(ctx, footer=footer)

    @therapy_panel.command(name="edit")
    @commands.has_permissions(manage_guild=True)
    async def therapy_panel_edit(self, ctx, field: str = None, *, value: str = None):
        """Edit the saved therapy panel message."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)

        raw = " ".join(part for part in (field, value) if part).strip()
        if not raw:
            return await ctx.reply(
                embed=error_embed(
                    "Usage",
                    f"`{self._prefix(ctx)}therapy panel edit title <text>`\n"
                    f"`{self._prefix(ctx)}therapy panel edit description <text>`\n"
                    f"`{self._prefix(ctx)}therapy panel edit footer <text>`\n"
                    f"`{self._prefix(ctx)}therapy panel title <text>`\n"
                    f"`{self._prefix(ctx)}therapy panel description <text>`\n"
                    f"`{self._prefix(ctx)}therapy panel footer <text|clear>`\n"
                    f"`{self._prefix(ctx)}therapy panel edit <title> | <description>`"
                )
            )

        field_name = (field or "").lower()
        if field_name in {"title", "description", "desc", "footer"} and value:
            if field_name == "title":
                return await self._edit_saved_panel(ctx, title=value.strip())
            if field_name in {"description", "desc"}:
                return await self._edit_saved_panel(ctx, description=value.strip())
            footer = value.strip()
            if footer.lower() in {"clear", "none", "remove", "off"}:
                footer = ""
            return await self._edit_saved_panel(ctx, footer=footer)
        if "|" in raw:
            new_title, new_description = (part.strip() for part in raw.split("|", 1))
            return await self._edit_saved_panel(
                ctx,
                title=new_title or None,
                description=new_description or None,
            )
        await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}therapy panel title|description|footer <text>`"))

    @therapy.command(name="add", aliases=["invite"])
    async def therapy_add_to_session(self, ctx, member: discord.Member = None):
        """Add another configured therapist to the current session channel."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        session = settings_db.get_open_therapy_session_by_channel(ctx.guild.id, ctx.channel.id)
        if not session:
            return await ctx.reply(embed=error_embed("Not A Session", "Use this inside an open therapy session channel."))
        if not self._member_can_pass_session(ctx.author, session):
            return await ctx.reply(embed=error_embed("Missing Permission", "Only the selected therapist with the recommend role, or staff, can add therapists here."))
        if not member:
            therapists = self._session_therapist_choices(ctx.guild, session, "add")
            if not therapists:
                return await ctx.reply(embed=error_embed("No Therapists", "There are no other configured therapists to add."))
            return await ctx.reply(
                embed=info_embed("Choose Therapist To Add", "Pick another therapist to give access to this session."),
                view=SessionTherapistSelectView(self, "add", therapists, ctx.author.id),
            )
        ok, embed = await self._add_therapist_to_session(ctx.channel, ctx.author, session, member)
        await ctx.reply(embed=embed)

    @therapy.command(name="pass", aliases=["transfer", "handoff"])
    async def therapy_pass_session(self, ctx, member: discord.Member = None, *, reason: str = None):
        """Pass the current session to another configured therapist."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        session = settings_db.get_open_therapy_session_by_channel(ctx.guild.id, ctx.channel.id)
        if not session:
            return await ctx.reply(embed=error_embed("Not A Session", "Use this inside an open therapy session channel."))
        if not self._member_can_pass_session(ctx.author, session):
            return await ctx.reply(embed=error_embed("Missing Permission", "Only the selected therapist with the recommend role, or staff, can pass this session."))
        if not member:
            therapists = self._session_therapist_choices(ctx.guild, session, "pass")
            if not therapists:
                return await ctx.reply(embed=error_embed("No Therapists", "There are no other configured therapists to pass this session to."))
            return await ctx.reply(
                embed=info_embed("Choose Therapist To Pass To", "Pick the therapist who should take over this session."),
                view=SessionTherapistSelectView(self, "pass", therapists, ctx.author.id, reason),
            )
        ok, embed = await self._pass_session_to_therapist(ctx.channel, ctx.author, session, member, reason)
        await ctx.reply(embed=embed)

    @therapy.command(name="sessions")
    @commands.has_permissions(manage_guild=True)
    async def therapy_sessions(self, ctx):
        """List active therapy sessions."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        sessions = settings_db.get_open_therapy_sessions(ctx.guild.id)
        if not sessions:
            return await ctx.reply(embed=info_embed("No Open Sessions", "There are no active therapy sessions."))
        lines = []
        for session in sessions[:20]:
            channel = ctx.guild.get_channel(int(session["channel_id"]))
            requester = ctx.guild.get_member(int(session["requester_id"]))
            therapist = ctx.guild.get_member(int(session["therapist_id"]))
            lines.append(
                f"`#{session['id']}` {channel.mention if channel else 'missing-channel'} | "
                f"{requester.mention if requester else '<@' + session['requester_id'] + '>'} -> "
                f"{therapist.mention if therapist else '<@' + session['therapist_id'] + '>'}"
            )
        await ctx.reply(embed=info_embed(f"Open Therapy Sessions ({len(sessions)})", "\n".join(lines)))

    @therapy.command(name="cleanup")
    @commands.has_permissions(manage_guild=True)
    async def therapy_cleanup(self, ctx):
        """Close DB sessions whose channels no longer exist."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        sessions = settings_db.get_open_therapy_sessions(ctx.guild.id)
        cleaned = 0
        for session in sessions:
            if not ctx.guild.get_channel(int(session["channel_id"])):
                settings_db.close_therapy_session(ctx.guild.id, session["channel_id"], ctx.author.id, "Cleanup: session channel was missing.")
                cleaned += 1
        await ctx.reply(embed=success_embed("Therapy Cleanup Complete", f"Closed **{cleaned}** stale session record(s)."))

    @therapy.command(name="close", aliases=["end"])
    async def therapy_close(self, ctx, *, reason: str = None):
        """Close the current therapy session."""
        if not self._db_ready():
            return await self._reply_db_offline(ctx)
        session = settings_db.get_open_therapy_session_by_channel(ctx.guild.id, ctx.channel.id)
        if not session:
            return await ctx.reply(embed=error_embed("Not A Session", "Use this inside an open therapy session channel."))
        if not self._member_can_close(ctx.author, session):
            return await ctx.reply(embed=error_embed("Cannot Close", "Only the requester, selected therapist, or staff can end this session."))
        await ctx.reply(embed=success_embed("Session Closing", "This channel will be deleted shortly."))
        await self._close_session(ctx.guild, ctx.channel, session, ctx.author, reason or "Closed by command.", announce=False)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not isinstance(channel, discord.TextChannel) or not self._db_ready():
            return
        session = settings_db.get_open_therapy_session_by_channel(channel.guild.id, channel.id)
        if session:
            settings_db.close_therapy_session(channel.guild.id, channel.id, None, "Session channel was deleted.")

    async def cog_command_error(self, ctx, error):
        error = getattr(error, "original", error)
        if isinstance(error, commands.MissingPermissions):
            return await ctx.reply(embed=error_embed("Missing Permission", "You do not have permission to use that therapy command."))
        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            return await ctx.reply(embed=error_embed("Bot Missing Permission", f"I need: {missing}"))
        if isinstance(error, commands.BadArgument):
            return await ctx.reply(embed=error_embed("Invalid Argument", f"Try `{self._prefix(ctx)}therapy` to see the therapy command list."))
        print(f"Therapy command error: {error}")
        await ctx.reply(embed=error_embed("Command Failed", "Something went wrong while running that therapy command."))


async def setup(bot):
    await bot.add_cog(TherapySessions(bot))
