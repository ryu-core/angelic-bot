import asyncio

import discord
from discord.ext import commands
from discord.ui import Button, View

import config
from utils.embeds import error_embed, info_embed, success_embed
from utils.role_tools import find_role_matches, parse_color_value, parse_natural_role_edit, parse_on_off


class RoleListView(View):
    def __init__(self, pages, author_id):
        super().__init__(timeout=180)
        self.pages = pages
        self.author_id = author_id
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.previous_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= len(self.pages) - 1

    def create_embed(self):
        title, description, total_roles = self.pages[self.current_page]
        embed = discord.Embed(
            title=title,
            description=description,
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Roles: {total_roles} | Page {self.current_page + 1}/{len(self.pages)}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command user can use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class RoleChannelTools(commands.Cog):
    """Role and channel management helpers."""

    def __init__(self, bot):
        self.bot = bot

    @property
    def qualified_name(self):
        return "Moderation"

    def _is_owner(self, ctx):
        return ctx.author.id == ctx.guild.owner_id or ctx.author.id in config.OWNER_IDS

    def _prefix(self, ctx):
        return getattr(ctx, "prefix", None) or config.PREFIX

    def _can_assign_member_roles(self, ctx):
        if self._is_owner(ctx):
            return True

        antinuke = self.bot.get_cog("AntiNuke")
        if antinuke:
            try:
                return antinuke._is_whitelisted(ctx.guild.id, ctx.author.id)
            except Exception:
                pass

        try:
            from utils.database import settings_db
            role = settings_db.get_antinuke_whitelist_role(ctx.guild.id, ctx.author.id) if settings_db else None
            return role in {"whitelisted", "admin"}
        except Exception:
            return False

    async def _send_role_list(self, ctx):
        roles = [role for role in reversed(ctx.guild.roles) if role != ctx.guild.default_role]
        if not roles:
            return await ctx.reply(embed=error_embed("No Roles", "This server has no roles."))

        pages = []
        current = []
        current_len = 0
        for index, role in enumerate(roles, start=1):
            color = f"#{role.color.value:06X}" if role.color.value else "default"
            line = f"`{index}.` **{discord.utils.escape_markdown(role.name)}** - `{role.id}` - `{color}`"
            if current_len + len(line) + 1 > 3900:
                pages.append((f"{ctx.guild.name} Roles", "\n".join(current), len(roles)))
                current = []
                current_len = 0
            current.append(line)
            current_len += len(line) + 1

        if current:
            pages.append((f"{ctx.guild.name} Roles", "\n".join(current), len(roles)))

        view = RoleListView(pages, ctx.author.id)
        await ctx.reply(embed=view.create_embed(), view=view, allowed_mentions=discord.AllowedMentions.none())

    def _can_use_role(self, ctx, role):
        if role >= ctx.guild.me.top_role:
            return False, "That role is higher than or equal to my top role."
        if not self._is_owner(ctx) and role >= ctx.author.top_role:
            return False, "That role is higher than or equal to your top role."
        if role.managed:
            return False, "That role is managed by an integration and cannot be edited."
        if role == ctx.guild.default_role:
            return False, "You cannot manage the @everyone role with this command."
        return True, None

    def _can_manage_member(self, ctx, member):
        if self._is_owner(ctx):
            return True, None
        if member.id == ctx.guild.owner_id:
            return False, "You cannot manage the server owner."
        if member != ctx.author and member.top_role >= ctx.author.top_role:
            return False, "You cannot manage that member due to role hierarchy."
        return True, None

    async def _resolve_role(self, ctx, query):
        query = str(query or "").strip()
        if not query:
            return None

        matches = find_role_matches(
            [role for role in ctx.guild.roles if role != ctx.guild.default_role],
            query,
            limit=5,
        )
        if not matches:
            await ctx.reply(embed=error_embed("Role Not Found", f"No role matched `{query}`."))
            return None
        if len(matches) > 1:
            exact = [role for role in matches if role.name.lower() == query.lower() or str(role.id) == query]
            if len(exact) == 1:
                return exact[0]
            choices = "\n".join(f"`{index}.` {role.mention} (`{role.name}`)" for index, role in enumerate(matches, start=1))
            await ctx.reply(
                embed=error_embed(
                    "Multiple Roles Matched",
                    f"Be a little more specific. I found:\n{choices}",
                )
            )
            return None
        return matches[0]

    def _validate_channel_name(self, name):
        name = str(name or "").strip()
        if not name:
            return None, "Channel name cannot be empty."
        if len(name) > 100:
            return None, "Channel names must be 100 characters or less."
        return name, None

    def _category_channel_mismatch(self, channel, category):
        return not channel.category or channel.category.id != category.id

    async def _create_channel_in_category(self, ctx, category, name):
        name, error = self._validate_channel_name(name)
        if not category or not name:
            usage = f"`{self._prefix(ctx)}channel create <category> <name>`"
            return await ctx.reply(embed=error_embed("Usage", usage))
        if error:
            return await ctx.reply(embed=error_embed("Invalid Name", error))

        try:
            channel = await ctx.guild.create_text_channel(
                name=name,
                category=category,
                reason=f"Channel created by {ctx.author}",
            )
            await ctx.reply(embed=success_embed("Channel Created", f"Created {channel.mention} in **{category.name}**."))
        except Exception as exc:
            await ctx.reply(embed=error_embed("Create Failed", f"Could not create channel: {exc}"))

    async def _delete_channel_in_category(self, ctx, category, channel):
        if not category or not channel:
            usage = f"`{self._prefix(ctx)}channel delete <category> <#channel>`"
            return await ctx.reply(embed=error_embed("Usage", usage))
        if self._category_channel_mismatch(channel, category):
            return await ctx.reply(
                embed=error_embed(
                    "Wrong Category",
                    f"{channel.mention} is not inside **{category.name}**.",
                )
            )

        prompt = await ctx.reply(
            embed=error_embed(
                "Confirm Channel Delete",
                f"This will permanently delete {channel.mention} from **{category.name}**.\n"
                "Type `confirm` within 20 seconds to delete it, or `cancel` to stop.",
            )
        )

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel and message.content.lower() in {"confirm", "cancel"}

        try:
            reply = await self.bot.wait_for("message", timeout=20, check=check)
        except asyncio.TimeoutError:
            return await prompt.edit(embed=info_embed("Delete Cancelled", "No confirmation received."))

        if reply.content.lower() == "cancel":
            return await prompt.edit(embed=info_embed("Delete Cancelled", "Channel deletion cancelled."))

        try:
            await channel.delete(reason=f"Deleted from category {category.name} by {ctx.author}")
        except Exception as exc:
            await ctx.send(embed=error_embed("Delete Failed", f"Could not delete channel: {exc}"))

    async def _rename_channel(self, ctx, channel, name):
        channel = channel or ctx.channel
        name, error = self._validate_channel_name(name)
        if not name:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}renamechannel [#channel] <new name>`"))
        if error:
            return await ctx.reply(embed=error_embed("Invalid Name", error))

        old_name = channel.name
        try:
            await channel.edit(name=name, reason=f"Channel renamed by {ctx.author}")
            await ctx.reply(embed=success_embed("Channel Renamed", f"`#{old_name}` is now {channel.mention}."))
        except Exception as exc:
            await ctx.reply(embed=error_embed("Rename Failed", f"Could not rename channel: {exc}"))

    async def _give_role(self, ctx, member, role_query):
        if not member or not role_query:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}giverole @user <partial role name>`"))
        if not self._can_assign_member_roles(ctx):
            return await ctx.reply(embed=error_embed(
                "Not Whitelisted",
                f"Only server owners, bot owners, or antinuke-whitelisted users can give roles.\n"
                f"Ask an antinuke admin to run `{self._prefix(ctx)}antinuke whitelist add {ctx.author.mention}`.",
            ))

        role = await self._resolve_role(ctx, role_query)
        if not role:
            return

        allowed, reason = self._can_manage_member(ctx, member)
        if not allowed:
            return await ctx.reply(embed=error_embed("Cannot Give Role", reason))
        allowed, reason = self._can_use_role(ctx, role)
        if not allowed:
            return await ctx.reply(embed=error_embed("Cannot Give Role", reason))

        if role in member.roles:
            return await ctx.reply(embed=info_embed("Already Has Role", f"{member.mention} already has {role.mention}."))

        await member.add_roles(role, reason=f"Role given by {ctx.author}")
        await ctx.reply(embed=success_embed("Role Given", f"Added {role.mention} to {member.mention}."))

    async def _remove_role(self, ctx, member, role_query):
        if not member or not role_query:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}removerole @user <partial role name>`"))
        if not self._can_assign_member_roles(ctx):
            return await ctx.reply(embed=error_embed(
                "Not Whitelisted",
                f"Only server owners, bot owners, or antinuke-whitelisted users can remove roles.\n"
                f"Ask an antinuke admin to run `{self._prefix(ctx)}antinuke whitelist add {ctx.author.mention}`.",
            ))

        role = await self._resolve_role(ctx, role_query)
        if not role:
            return

        allowed, reason = self._can_manage_member(ctx, member)
        if not allowed:
            return await ctx.reply(embed=error_embed("Cannot Remove Role", reason))
        allowed, reason = self._can_use_role(ctx, role)
        if not allowed:
            return await ctx.reply(embed=error_embed("Cannot Remove Role", reason))

        if role not in member.roles:
            return await ctx.reply(embed=info_embed("Role Missing", f"{member.mention} does not have {role.mention}."))

        await member.remove_roles(role, reason=f"Role removed by {ctx.author}")
        await ctx.reply(embed=success_embed("Role Removed", f"Removed {role.mention} from {member.mention}."))

    @commands.group(name="roles", aliases=["roletools"], invoke_without_command=True)
    @commands.guild_only()
    async def role(self, ctx, member: discord.Member = None, *, role_query: str = None):
        """List all roles, or give a role using a mention, ID, or partial role name."""
        if not member and not role_query:
            return await self._send_role_list(ctx)
        if not ctx.author.guild_permissions.manage_roles:
            return await ctx.reply(embed=error_embed("Missing Permissions", "You need **Manage Roles** to give roles."))
        if not ctx.guild.me.guild_permissions.manage_roles:
            return await ctx.reply(embed=error_embed("Missing Permissions", "I need **Manage Roles** to give roles."))
        await self._give_role(ctx, member, role_query)

    @role.command(name="give", aliases=["add", "grant"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_give(self, ctx, member: discord.Member = None, *, role_query: str = None):
        await self._give_role(ctx, member, role_query)

    @commands.command(name="giverole", aliases=["addrole", "rolegive"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def giverole(self, ctx, member: discord.Member = None, *, role_query: str = None):
        """Give a role by partial name."""
        await self._give_role(ctx, member, role_query)

    @role.command(name="remove", aliases=["take", "revoke"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_remove(self, ctx, member: discord.Member = None, *, role_query: str = None):
        await self._remove_role(ctx, member, role_query)

    @commands.command(name="removerole", aliases=["takerole"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def removerole(self, ctx, member: discord.Member = None, *, role_query: str = None):
        """Remove a role by partial name."""
        await self._remove_role(ctx, member, role_query)

    def _split_role_and_value(self, payload):
        if not payload or "|" not in payload:
            return None, None
        left, right = payload.split("|", 1)
        return left.strip(), right.strip()

    @role.command(name="name", aliases=["rename"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_name(self, ctx, *, payload: str = None):
        """Rename a role. Usage: ,roles name staff | Staff Team"""
        role_query, new_name = self._split_role_and_value(payload)
        if not role_query or not new_name:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}roles name <role> | <new name>`"))
        if len(new_name) > 100:
            return await ctx.reply(embed=error_embed("Name Too Long", "Role names must be 100 characters or less."))

        role = await self._resolve_role(ctx, role_query)
        if not role:
            return
        allowed, reason = self._can_use_role(ctx, role)
        if not allowed:
            return await ctx.reply(embed=error_embed("Cannot Edit Role", reason))

        old_name = role.name
        await role.edit(name=new_name, reason=f"Role renamed by {ctx.author}")
        await ctx.reply(embed=success_embed("Role Renamed", f"`{old_name}` is now {role.mention}."))

    def _split_last_word(self, payload):
        if not payload:
            return None, None
        parts = payload.rsplit(" ", 1)
        if len(parts) != 2:
            return None, None
        return parts[0].strip(), parts[1].strip()

    @role.command(name="color", aliases=["colour"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_color(self, ctx, *, payload: str = None):
        """Change a role color by partial role name."""
        role_query, color = self._split_last_word(payload)
        if not role_query or not color:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}roles color <role> <#hex|name|reset>`"))

        value = parse_color_value(color)
        if value is None:
            return await ctx.reply(embed=error_embed("Invalid Color", "Use a hex color like `#ff66aa`, a color name, or `reset`."))

        role = await self._resolve_role(ctx, role_query)
        if not role:
            return
        allowed, reason = self._can_use_role(ctx, role)
        if not allowed:
            return await ctx.reply(embed=error_embed("Cannot Edit Role", reason))

        await role.edit(colour=discord.Color(value), reason=f"Role color changed by {ctx.author}")
        await ctx.reply(embed=success_embed("Role Color Updated", f"{role.mention} color set to `#{value:06X}`."))

    @role.command(name="hoist")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_hoist(self, ctx, *, payload: str = None):
        """Toggle whether a role is shown separately."""
        role_query, state = self._split_last_word(payload)
        await self._edit_role_bool(ctx, role_query, state, "hoist")

    @role.command(name="mentionable")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_mentionable(self, ctx, *, payload: str = None):
        """Toggle whether anyone can mention a role."""
        role_query, state = self._split_last_word(payload)
        await self._edit_role_bool(ctx, role_query, state, "mentionable")

    async def _edit_role_bool(self, ctx, role_query, state, field):
        if not role_query or state is None:
            return await ctx.reply(embed=error_embed("Usage", f"`{self._prefix(ctx)}roles {field} <role> <on/off>`"))
        value = parse_on_off(state)
        if value is None:
            return await ctx.reply(embed=error_embed("Invalid State", "Use `on` or `off`."))
        role = await self._resolve_role(ctx, role_query)
        if not role:
            return
        allowed, reason = self._can_use_role(ctx, role)
        if not allowed:
            return await ctx.reply(embed=error_embed("Cannot Edit Role", reason))
        await role.edit(**{field: value}, reason=f"Role {field} changed by {ctx.author}")
        await ctx.reply(embed=success_embed("Role Updated", f"{role.mention} `{field}` is now `{state.lower()}`."))

    @role.command(name="edit")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_edit(self, ctx, *, payload: str = None):
        """Edit role fields. Example: ,roleedit staff Staff Team #ff66aa"""
        usage = (
            f"`{self._prefix(ctx)}roleedit <role> <new name> <#hex>`\n"
            f"`{self._prefix(ctx)}roles edit <role> --name <name> --color <hex> --hoist on --mentionable off`"
        )
        if not payload:
            return await ctx.reply(
                embed=error_embed("Usage", usage)
            )

        updates = {}
        notes = []
        if "--" in payload:
            role_query, raw_flags = payload.split("--", 1)
            role = await self._resolve_role(ctx, role_query.strip())
            if not role:
                return

            tokens = ("--" + raw_flags).split("--")
            for token in tokens:
                token = token.strip()
                if not token:
                    continue
                key, _, value = token.partition(" ")
                key = key.lower()
                value = value.strip()
                if key in {"name", "rename"} and value:
                    if len(value) > 100:
                        return await ctx.reply(embed=error_embed("Name Too Long", "Role names must be 100 characters or less."))
                    updates["name"] = value
                    notes.append(f"name -> `{value}`")
                elif key in {"color", "colour"} and value:
                    parsed = parse_color_value(value)
                    if parsed is None:
                        return await ctx.reply(embed=error_embed("Invalid Color", f"`{value}` is not a valid color."))
                    updates["colour"] = discord.Color(parsed)
                    notes.append(f"color -> `#{parsed:06X}`")
                elif key in {"hoist", "mentionable"} and value:
                    parsed = parse_on_off(value)
                    if parsed is None:
                        return await ctx.reply(embed=error_embed("Invalid State", f"`{key}` must be on or off."))
                    updates[key] = parsed
                    notes.append(f"{key} -> `{value.lower()}`")
                else:
                    return await ctx.reply(embed=error_embed("Unknown Edit", f"I do not know how to edit `{key}`."))
        else:
            role_pool = [role for role in ctx.guild.roles if role != ctx.guild.default_role]
            role, new_name, color, parse_error = parse_natural_role_edit(role_pool, payload)
            if parse_error == "ambiguous":
                return await ctx.reply(embed=error_embed("Multiple Roles Matched", "Use more of the current role name, or use a role mention/ID."))
            if parse_error:
                return await ctx.reply(embed=error_embed("Usage", usage))

            if new_name:
                if len(new_name) > 100:
                    return await ctx.reply(embed=error_embed("Name Too Long", "Role names must be 100 characters or less."))
                updates["name"] = new_name
                notes.append(f"name -> `{new_name}`")
            if color is not None:
                parsed = parse_color_value(color)
                updates["colour"] = discord.Color(parsed)
                notes.append(f"color -> `#{parsed:06X}`")

        allowed, reason = self._can_use_role(ctx, role)
        if not allowed:
            return await ctx.reply(embed=error_embed("Cannot Edit Role", reason))

        if not updates:
            return await ctx.reply(embed=error_embed("No Changes", usage))

        await role.edit(reason=f"Role edited by {ctx.author}", **updates)
        await ctx.reply(embed=success_embed("Role Edited", f"{role.mention}\n" + "\n".join(notes)))

    @commands.command(name="roleedit", aliases=["editrole"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def roleedit_alias(self, ctx, *, payload: str = None):
        """Alias for ,roles edit."""
        await self.role_edit.callback(self, ctx, payload=payload)

    @commands.group(name="channel", aliases=["channels"], invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_group(self, ctx):
        """Manage text channels by category."""
        prefix = self._prefix(ctx)
        usage = (
            f"`{prefix}channel create <category> <name>`\n"
            f"`{prefix}channel delete <category> <#channel>`\n"
            f"`{prefix}renamechannel [#channel] <new name>`\n"
            f"`{prefix}public [#channel]`"
        )
        await ctx.reply(embed=info_embed("Channel Tools", usage))

    @channel_group.command(name="create", aliases=["add", "new"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_create(self, ctx, category: discord.CategoryChannel = None, *, name: str = None):
        """Create a text channel inside a category."""
        await self._create_channel_in_category(ctx, category, name)

    @commands.command(name="createchannel", aliases=["chcreate", "ccreate"])
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def createchannel_alias(self, ctx, category: discord.CategoryChannel = None, *, name: str = None):
        """Create a text channel inside a category."""
        await self._create_channel_in_category(ctx, category, name)

    @channel_group.command(name="delete", aliases=["remove", "del"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_delete(self, ctx, category: discord.CategoryChannel = None, channel: discord.TextChannel = None):
        """Delete a channel only if it is inside the provided category."""
        await self._delete_channel_in_category(ctx, category, channel)

    @commands.command(name="deletechannelincat", aliases=["chdelete", "cdelete"])
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def deletechannelincat_alias(self, ctx, category: discord.CategoryChannel = None, channel: discord.TextChannel = None):
        """Delete a channel only if it is inside the provided category."""
        await self._delete_channel_in_category(ctx, category, channel)

    @commands.command(name="private", aliases=["priv"])
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def private(self, ctx, channel: discord.TextChannel = None, *members: discord.Member):
        """Make a channel private to you, the bot, and optional members."""
        channel = channel or ctx.channel
        allowed_members = list(dict.fromkeys([ctx.author, ctx.guild.me, *members]))

        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        }
        for member in allowed_members:
            overwrites[member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )

        try:
            await channel.edit(overwrites={**channel.overwrites, **overwrites}, reason=f"Made private by {ctx.author}")
            visible = ", ".join(member.mention for member in allowed_members if member != ctx.guild.me)
            await ctx.reply(embed=success_embed("Channel Private", f"{channel.mention} is now private for {visible}."))
        except Exception as exc:
            await ctx.reply(embed=error_embed("Private Failed", f"Could not update channel permissions: {exc}"))

    @commands.command(name="public", aliases=["pub", "unprivate"])
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def public(self, ctx, channel: discord.TextChannel = None):
        """Make a channel visible to @everyone again."""
        channel = channel or ctx.channel
        try:
            await channel.set_permissions(
                ctx.guild.default_role,
                view_channel=None,
                reason=f"Made public by {ctx.author}",
            )
            await ctx.reply(embed=success_embed("Channel Public", f"{channel.mention} is visible to @everyone again."))
        except Exception as exc:
            await ctx.reply(embed=error_embed("Public Failed", f"Could not update channel permissions: {exc}"))

    @commands.command(name="renamechannel", aliases=["channelrename", "chrename", "crename"])
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def renamechannel(self, ctx, channel: discord.TextChannel = None, *, name: str = None):
        """Rename a text channel."""
        await self._rename_channel(ctx, channel, name)

    @channel_group.command(name="rename", aliases=["name"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_rename(self, ctx, channel: discord.TextChannel = None, *, name: str = None):
        """Rename a text channel."""
        await self._rename_channel(ctx, channel, name)

    @commands.command(name="delete", aliases=["delchannel", "deletechannel"])
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def delete_channel(self, ctx, channel: discord.TextChannel = None):
        """Delete a channel after a typed confirmation."""
        channel = channel or ctx.channel
        prompt = await ctx.reply(
            embed=error_embed(
                "Confirm Channel Delete",
                f"This will permanently delete {channel.mention}.\nType `confirm` within 20 seconds to delete it, or `cancel` to stop.",
            )
        )

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel and message.content.lower() in {"confirm", "cancel"}

        try:
            reply = await self.bot.wait_for("message", timeout=20, check=check)
        except asyncio.TimeoutError:
            return await prompt.edit(embed=info_embed("Delete Cancelled", "No confirmation received."))

        if reply.content.lower() == "cancel":
            return await prompt.edit(embed=info_embed("Delete Cancelled", "Channel deletion cancelled."))

        try:
            await channel.delete(reason=f"Deleted by {ctx.author}")
        except Exception as exc:
            await ctx.send(embed=error_embed("Delete Failed", f"Could not delete channel: {exc}"))


async def setup(bot):
    await bot.add_cog(RoleChannelTools(bot))
