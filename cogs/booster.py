import re
import os

import discord
from discord.ext import commands

import config
from utils.database import settings_db
from utils.embeds import error_embed, info_embed, success_embed
from utils.role_tools import parse_color_value


ROLE_MENTION_RE = re.compile(r"<@&\d+>")
DELETE_AFTER_RE = re.compile(r"\s+--delete-after\s+(\d{1,5})\s*$", re.IGNORECASE)
IMAGE_FLAG_RE = re.compile(r"\s+--image\s+(\S+)\s*$", re.IGNORECASE)
CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:(\d+)>")
BOOST_IMAGE_DIR = os.path.join("data", "boost_images")


class Booster(commands.Cog):
    """Booster announcements and personal booster roles."""

    def __init__(self, bot):
        self.bot = bot

    def _prefix(self, ctx):
        return getattr(ctx, "prefix", None) or config.PREFIX

    def _db_ready(self):
        return settings_db is not None

    def _clean_template(self, message):
        message = str(message or "").strip()
        delete_after = None
        image_url = None

        changed = True
        while changed:
            changed = False
            match = DELETE_AFTER_RE.search(message)
            if match:
                delete_after = max(1, min(86400, int(match.group(1))))
                message = DELETE_AFTER_RE.sub("", message).strip()
                changed = True

            match = IMAGE_FLAG_RE.search(message)
            if match:
                image_url = match.group(1).strip()
                message = IMAGE_FLAG_RE.sub("", message).strip()
                changed = True

        return message, delete_after, image_url

    async def _attachment_image_ref(self, ctx, channel):
        if not ctx.message.attachments:
            return None
        attachment = ctx.message.attachments[0]
        content_type = (attachment.content_type or "").lower()
        filename = (attachment.filename or "").lower()
        if not content_type.startswith("image/") and not filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return None

        _, ext = os.path.splitext(filename)
        ext = ext if ext.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"} else ".png"
        os.makedirs(BOOST_IMAGE_DIR, exist_ok=True)
        path = os.path.join(BOOST_IMAGE_DIR, f"{ctx.guild.id}_{channel.id}_{attachment.id}{ext}")
        await attachment.save(path)
        return f"local:{path}"

    def _image_send_parts(self, image_ref):
        if not image_ref:
            return None, None
        embed = discord.Embed(color=config.COLORS["primary"])
        if str(image_ref).startswith("local:"):
            path = str(image_ref)[len("local:"):]
            if not os.path.exists(path):
                return None, None
            filename = os.path.basename(path)
            embed.set_image(url=f"attachment://{filename}")
            return embed, discord.File(path, filename=filename)
        embed.set_image(url=image_ref)
        return embed, None

    def _validate_image_url(self, image_url):
        if not image_url:
            return None
        if str(image_url).startswith("local:"):
            return None
        if not image_url.startswith(("http://", "https://")):
            return "Image must be an attachment or an `http(s)` URL."
        if len(image_url) > 1000:
            return "Image URL is too long."
        return None

    def _validate_template(self, message):
        if not message:
            return "Message cannot be empty."
        if len(message) > 1800:
            return "Boost messages must be 1800 characters or less."
        lowered = message.lower()
        if "@everyone" in lowered or "@here" in lowered or ROLE_MENTION_RE.search(message):
            return "Boost messages cannot include @everyone, @here, or role mentions."
        return None

    def _format_boost_message(self, member, template):
        guild = member.guild
        replacements = {
            "{user}": member.mention,
            "{mention}": member.mention,
            "{username}": str(member),
            "{display}": member.display_name,
            "{server}": guild.name,
            "{count}": str(guild.member_count or 0),
            "{boosts}": str(guild.premium_subscription_count or 0),
            "{tier}": str(guild.premium_tier or 0),
        }
        text = template
        for key, value in replacements.items():
            text = text.replace(key, value)
        return text

    def _boost_embed_description(self, rows):
        lines = []
        for index, row in enumerate(rows, start=1):
            template = row["message_template"]
            if len(template) > 80:
                template = template[:77] + "..."
            delete_after = row.get("self_destruct_seconds")
            image = " | image" if row.get("image_url") else ""
            suffix = f" | deletes after {delete_after}s" if delete_after else ""
            lines.append(f"`{index}.` <#{row['channel_id']}> - {template}{image}{suffix}")
        return "\n".join(lines)

    async def _send_boost_list(self, ctx):
        if not self._db_ready():
            return await ctx.reply(embed=error_embed("Database Offline", "Boost messages cannot be loaded right now."))
        rows = settings_db.get_system_messages(ctx.guild.id, "boost")
        if not rows:
            return await ctx.reply(embed=info_embed("No Boost Messages", f"Use `{self._prefix(ctx)}boost add <#channel> <message>`."))
        await ctx.reply(embed=info_embed(f"Boost Messages ({len(rows)})", self._boost_embed_description(rows)))

    async def _send_boost_message(self, member, row, channel=None, use_config_delete_after=True):
        channel = channel or member.guild.get_channel(int(row["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return False, "Channel missing"
        perms = channel.permissions_for(member.guild.me)
        if not perms.send_messages:
            return False, "Missing Send Messages"

        text = self._format_boost_message(member, row["message_template"])
        embed, file = self._image_send_parts(row.get("image_url"))
        kwargs = {
            "content": text,
            "allowed_mentions": discord.AllowedMentions(users=True, roles=False, everyone=False),
            "delete_after": row.get("self_destruct_seconds") if use_config_delete_after else None,
        }
        if embed:
            kwargs["embed"] = embed
        if file:
            kwargs["file"] = file
        await channel.send(**kwargs)
        return True, None

    def _is_booster(self, member):
        return bool(member and member.premium_since)

    async def _get_owned_booster_role(self, ctx, remove_stale=True):
        if not self._db_ready():
            await ctx.reply(embed=error_embed("Database Offline", "Booster roles cannot be saved right now."))
            return None, None

        row = settings_db.get_booster_role(ctx.guild.id, ctx.author.id)
        if not row:
            return None, None

        role = ctx.guild.get_role(int(row["role_id"]))
        if role:
            return role, row

        if remove_stale:
            settings_db.remove_booster_role(ctx.guild.id, ctx.author.id)
        return None, row

    async def _ensure_booster_role(self, ctx):
        if not self._is_booster(ctx.author):
            await ctx.reply(embed=error_embed("Boosters Only", "You need to be actively boosting this server to use booster roles."))
            return None
        role, row = await self._get_owned_booster_role(ctx)
        if not role:
            await ctx.reply(embed=error_embed("No Booster Role", f"Create one first with `{self._prefix(ctx)}boosterrole create <name> [#color]`."))
            return None
        if role.managed:
            await ctx.reply(embed=error_embed("Cannot Edit Role", "That role is managed by Discord and cannot be edited."))
            return None
        if role >= ctx.guild.me.top_role:
            await ctx.reply(embed=error_embed("Role Too High", "Move my bot role above your booster role so I can manage it."))
            return None
        return role

    def _parse_name_color(self, payload):
        parts = str(payload or "").strip().split()
        if not parts:
            return None, None, "Tell me the role name."
        color = None
        parsed = parse_color_value(parts[-1])
        if parsed is not None and len(parts) > 1:
            color = parsed
            parts.pop()
        name = " ".join(parts).strip()
        if not name:
            return None, None, "Tell me the role name."
        if len(name) > 100:
            return None, None, "Role names must be 100 characters or less."
        return name, color, None

    @commands.group(name="boost", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def boost(self, ctx):
        """Manage boost announcement messages."""
        await self._send_boost_list(ctx)

    @boost.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def boost_list(self, ctx):
        """List configured boost announcement messages."""
        await self._send_boost_list(ctx)

    @boost.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def boost_add(self, ctx, channel: discord.TextChannel = None, *, message: str = None):
        """Add or update a boost announcement message."""
        if not channel or not message:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}boost add <#channel> <message> [--image <url>]`\nYou can also attach an image to the command."))
        if not self._db_ready():
            return await ctx.reply(embed=error_embed("Database Offline", "Boost messages cannot be saved right now."))
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages:
            return await ctx.reply(embed=error_embed("Missing Permission", f"I cannot send messages in {channel.mention}."))

        template, delete_after, image_url = self._clean_template(message)
        image_url = image_url or await self._attachment_image_ref(ctx, channel)
        problem = self._validate_template(template)
        if problem:
            return await ctx.reply(embed=error_embed("Invalid Message", problem))
        problem = self._validate_image_url(image_url)
        if problem:
            return await ctx.reply(embed=error_embed("Invalid Image", problem))

        ok = settings_db.add_system_message(ctx.guild.id, "boost", channel.id, template, delete_after, image_url)
        if not ok:
            return await ctx.reply(embed=error_embed("Save Failed", "I could not save that boost message."))
        extra = ""
        if image_url:
            extra += "\nImage attached."
        if delete_after:
            extra += f"\nMessages will delete after **{delete_after}s**."
        await ctx.reply(embed=success_embed("Boost Message Saved", f"Boost announcements will be sent to {channel.mention}.{extra}"))

    @boost.command(name="remove", aliases=["delete"])
    @commands.has_permissions(manage_guild=True)
    async def boost_remove(self, ctx, channel: discord.TextChannel = None):
        """Remove a boost announcement channel."""
        if not channel:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}boost remove <#channel>`"))
        if not self._db_ready():
            return await ctx.reply(embed=error_embed("Database Offline", "Boost messages cannot be changed right now."))
        if settings_db.remove_system_message(ctx.guild.id, "boost", channel.id):
            return await ctx.reply(embed=success_embed("Boost Message Removed", f"Removed boost announcements from {channel.mention}."))
        await ctx.reply(embed=error_embed("Not Found", f"No boost message was configured for {channel.mention}."))

    @boost.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def boost_clear(self, ctx):
        """Remove every boost announcement in this server."""
        if not self._db_ready():
            return await ctx.reply(embed=error_embed("Database Offline", "Boost messages cannot be changed right now."))
        count = settings_db.clear_system_messages(ctx.guild.id, "boost")
        await ctx.reply(embed=success_embed("Boost Messages Cleared", f"Removed **{count}** boost message configuration(s)."))

    @boost.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def boost_test(self, ctx, member: discord.Member = None):
        """Send configured boost announcements as a test."""
        if not self._db_ready():
            return await ctx.reply(embed=error_embed("Database Offline", "Boost messages cannot be loaded right now."))
        member = member or ctx.author
        rows = settings_db.get_system_messages(ctx.guild.id, "boost")
        if not rows:
            return await ctx.reply(embed=info_embed("No Boost Messages", f"Use `{self._prefix(ctx)}boost add <#channel> <message>` first."))

        sent = 0
        failed = []
        for row in rows:
            try:
                ok, reason = await self._send_boost_message(member, row)
                if ok:
                    sent += 1
                else:
                    failed.append(f"<#{row['channel_id']}>: {reason}")
            except Exception as exc:
                failed.append(f"<#{row['channel_id']}>: {exc}")
        desc = f"Sent **{sent}** test boost announcement(s)."
        if failed:
            desc += "\n\nFailed:\n" + "\n".join(failed[:5])
        await ctx.reply(embed=success_embed("Boost Test Complete", desc))

    @boost.command(name="preview", aliases=["display"])
    @commands.has_permissions(manage_guild=True)
    async def boost_preview(self, ctx, member: discord.Member = None):
        """Preview configured boost announcements in the current channel."""
        if not self._db_ready():
            return await ctx.reply(embed=error_embed("Database Offline", "Boost messages cannot be loaded right now."))
        member = member or ctx.author
        rows = settings_db.get_system_messages(ctx.guild.id, "boost")
        if not rows:
            return await ctx.reply(embed=info_embed("No Boost Messages", f"Use `{self._prefix(ctx)}boost add <#channel> <message>` first."))

        sent = 0
        failed = []
        for row in rows:
            try:
                ok, reason = await self._send_boost_message(
                    member,
                    row,
                    channel=ctx.channel,
                    use_config_delete_after=False,
                )
                if ok:
                    sent += 1
                else:
                    failed.append(f"<#{row['channel_id']}>: {reason}")
            except Exception as exc:
                failed.append(f"<#{row['channel_id']}>: {exc}")

        desc = f"Previewed **{sent}** boost announcement(s) in {ctx.channel.mention}."
        if failed:
            desc += "\n\nFailed:\n" + "\n".join(failed[:5])
        await ctx.reply(embed=success_embed("Boost Preview Complete", desc))

    @boost.command(name="variables", aliases=["vars"])
    @commands.has_permissions(manage_guild=True)
    async def boost_variables(self, ctx):
        """Show boost announcement placeholders."""
        placeholders = "`{user}`, `{mention}`, `{username}`, `{display}`, `{server}`, `{count}`, `{boosts}`, `{tier}`"
        await ctx.reply(embed=info_embed("Boost Variables", placeholders))

    @commands.command(name="boosters")
    @commands.guild_only()
    async def boosters(self, ctx):
        """List all current server boosters."""
        boosters = [member for member in ctx.guild.members if member.premium_since]
        if not boosters:
            return await ctx.reply(embed=info_embed("No Boosters", "This server has no boosters yet."))
        boosters.sort(key=lambda member: member.premium_since)
        desc = "\n".join(
            f"**{index}.** {member.mention} - since <t:{int(member.premium_since.timestamp())}:R>"
            for index, member in enumerate(boosters[:25], start=1)
        )
        await ctx.reply(embed=info_embed(f"Server Boosters ({len(boosters)})", desc))

    @commands.group(name="boosterrole", aliases=["boostrole", "br"], invoke_without_command=True)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True)
    async def boosterrole(self, ctx):
        """Manage your personal booster role."""
        if not self._is_booster(ctx.author):
            return await ctx.reply(embed=error_embed("Boosters Only", "You need to be actively boosting this server to use booster roles."))
        role, _ = await self._get_owned_booster_role(ctx)
        if not role:
            return await ctx.reply(embed=info_embed("No Booster Role", f"Use `{self._prefix(ctx)}boosterrole create <name> [#color]`."))
        await ctx.reply(embed=info_embed("Your Booster Role", f"{role.mention}\nUse `{self._prefix(ctx)}boosterrole name`, `color`, `icon`, or `delete`."))

    @boosterrole.command(name="create")
    @commands.bot_has_permissions(manage_roles=True)
    async def boosterrole_create(self, ctx, *, payload: str = None):
        """Create your personal booster role."""
        if not self._is_booster(ctx.author):
            return await ctx.reply(embed=error_embed("Boosters Only", "You need to be actively boosting this server to create a booster role."))
        if not self._db_ready():
            return await ctx.reply(embed=error_embed("Database Offline", "Booster roles cannot be saved right now."))

        existing, _ = await self._get_owned_booster_role(ctx)
        if existing:
            return await ctx.reply(embed=error_embed("Already Exists", f"You already own {existing.mention}."))

        name, color, problem = self._parse_name_color(payload)
        if problem:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}boosterrole create <name> [#color]`"))

        try:
            role = await ctx.guild.create_role(
                name=name,
                colour=discord.Color(color or 0),
                permissions=discord.Permissions.none(),
                mentionable=False,
                hoist=False,
                reason=f"Booster role created by {ctx.author} ({ctx.author.id})",
            )
            await ctx.author.add_roles(role, reason="Assigned personal booster role")
        except discord.Forbidden:
            return await ctx.reply(embed=error_embed("Missing Permission", "I need Manage Roles and a higher bot role to create booster roles."))
        except Exception as exc:
            return await ctx.reply(embed=error_embed("Create Failed", f"Could not create your booster role: {exc}"))

        if not settings_db.set_booster_role(ctx.guild.id, ctx.author.id, role.id):
            try:
                await role.delete(reason="Booster role DB save failed")
            except Exception:
                pass
            return await ctx.reply(embed=error_embed("Save Failed", "I created the role but could not save ownership, so I removed it."))
        await ctx.reply(embed=success_embed("Booster Role Created", f"Created and assigned {role.mention}."))

    @boosterrole.command(name="name", aliases=["rename"])
    async def boosterrole_name(self, ctx, *, new_name: str = None):
        """Rename your personal booster role."""
        role = await self._ensure_booster_role(ctx)
        if not role:
            return
        new_name = str(new_name or "").strip()
        if not new_name or len(new_name) > 100:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}boosterrole name <new name>`"))
        await role.edit(name=new_name, reason=f"Booster role renamed by {ctx.author}")
        await ctx.reply(embed=success_embed("Booster Role Renamed", f"Your booster role is now {role.mention}."))

    @boosterrole.command(name="color", aliases=["colour"])
    async def boosterrole_color(self, ctx, color: str = None):
        """Change your personal booster role color."""
        role = await self._ensure_booster_role(ctx)
        if not role:
            return
        parsed = parse_color_value(color)
        if parsed is None:
            return await ctx.reply(embed=error_embed("Invalid Color", "Use a hex color like `#ff66aa`, a color name, or `reset`."))
        await role.edit(colour=discord.Color(parsed), reason=f"Booster role color changed by {ctx.author}")
        await ctx.reply(embed=success_embed("Booster Role Updated", f"{role.mention} color set to `#{parsed:06X}`."))

    @boosterrole.command(name="icon")
    async def boosterrole_icon(self, ctx, emoji: str = None):
        """Set your personal booster role icon."""
        role = await self._ensure_booster_role(ctx)
        if not role:
            return
        if "ROLE_ICONS" not in ctx.guild.features:
            return await ctx.reply(embed=error_embed("Role Icons Locked", "This server needs Discord role icons unlocked to use booster role icons."))
        match = CUSTOM_EMOJI_RE.fullmatch(str(emoji or "").strip())
        if not match:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}boosterrole icon <custom emoji>`"))
        emoji_obj = self.bot.get_emoji(int(match.group(1)))
        if not emoji_obj or emoji_obj.guild.id != ctx.guild.id:
            return await ctx.reply(embed=error_embed("Invalid Emoji", "Use a custom emoji from this server."))
        try:
            await role.edit(display_icon=await emoji_obj.read(), reason=f"Booster role icon changed by {ctx.author}")
        except Exception as exc:
            return await ctx.reply(embed=error_embed("Icon Failed", f"Could not set the role icon: {exc}"))
        await ctx.reply(embed=success_embed("Booster Role Icon Updated", f"Updated the icon for {role.mention}."))

    @boosterrole.command(name="delete", aliases=["remove"])
    async def boosterrole_delete(self, ctx):
        """Delete your personal booster role."""
        role, row = await self._get_owned_booster_role(ctx)
        if not row:
            return await ctx.reply(embed=error_embed("No Booster Role", "You do not have a saved booster role."))
        if role:
            if role >= ctx.guild.me.top_role:
                return await ctx.reply(embed=error_embed("Role Too High", "Move my bot role above your booster role so I can delete it."))
            try:
                await role.delete(reason=f"Booster role deleted by owner {ctx.author}")
            except Exception as exc:
                return await ctx.reply(embed=error_embed("Delete Failed", f"Could not delete your booster role: {exc}"))
        settings_db.remove_booster_role(ctx.guild.id, ctx.author.id)
        await ctx.reply(embed=success_embed("Booster Role Deleted", "Your booster role was deleted."))

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.premium_since is None and after.premium_since is not None:
            if self._db_ready():
                rows = settings_db.get_system_messages(after.guild.id, "boost")
                for row in rows:
                    try:
                        await self._send_boost_message(after, row)
                    except Exception as exc:
                        print(f"Boost message send error in {after.guild.id}: {exc}")
            return

        if before.premium_since is not None and after.premium_since is None:
            await self._cleanup_booster_role(after)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self._cleanup_booster_role(member)

    async def _cleanup_booster_role(self, member):
        if not self._db_ready():
            return
        row = settings_db.get_booster_role(member.guild.id, member.id)
        if not row:
            return
        role = member.guild.get_role(int(row["role_id"]))
        if role and role < member.guild.me.top_role:
            try:
                await role.delete(reason=f"Booster role cleanup for {member} ({member.id})")
            except Exception as exc:
                print(f"Booster role cleanup error in {member.guild.id}: {exc}")
                return
        settings_db.remove_booster_role(member.guild.id, member.id)


async def setup(bot):
    await bot.add_cog(Booster(bot))
