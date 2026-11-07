import time

import discord
from discord.ext import commands

import config
from utils.database import Database
from utils.embeds import error_embed, info_embed, success_embed


notes_db = Database("notes")


class Notes(commands.Cog):
    """Private task notes with optional public webhook display."""

    def __init__(self, bot):
        self.bot = bot

    @property
    def qualified_name(self):
        return "Utility"

    def _blank(self):
        return {"title": "My Notes", "items": []}

    def _get_notes(self, user_id):
        data = notes_db.get(str(user_id), self._blank())
        if not isinstance(data, dict):
            return self._blank()
        data.setdefault("title", "My Notes")
        data.setdefault("items", [])
        return data

    def _save_notes(self, user_id, data):
        notes_db.set(str(user_id), data)

    async def _hide_invocation(self, ctx):
        try:
            await ctx.message.delete()
        except Exception:
            pass

    async def _quiet_reply(self, ctx, embed):
        try:
            message = await ctx.reply(embed=embed, mention_author=False, delete_after=12)
            return message
        except TypeError:
            message = await ctx.reply(embed=embed, mention_author=False)
            try:
                await message.delete(delay=12)
            except Exception:
                pass
            return message

    def _format_notes(self, data, owner):
        items = data.get("items", [])
        if not items:
            description = "No notes yet. Add one with `,notes add <task>`."
        else:
            lines = []
            for index, item in enumerate(items, start=1):
                text = str(item.get("text", "")).strip() or "(empty)"
                if item.get("done"):
                    text = f"~~{text}~~"
                lines.append(f"`{index}.` {text}")
            description = "\n".join(lines)
            if len(description) > 3900:
                description = description[:3890] + "\n...and more"

        done_count = sum(1 for item in items if item.get("done"))
        embed = discord.Embed(
            title=data.get("title") or "My Notes",
            description=description,
            color=config.COLORS.get("primary", 0x9B59B6),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=owner.display_name, icon_url=owner.display_avatar.url)
        embed.set_footer(text=f"{done_count}/{len(items)} done")
        return embed

    async def _dm_notes(self, ctx, data=None, notice="I sent your notes in DM."):
        data = data or self._get_notes(ctx.author.id)
        embed = self._format_notes(data, ctx.author)
        try:
            await ctx.author.send(embed=embed)
            await self._quiet_reply(ctx, success_embed("Notes Sent", notice))
        except discord.Forbidden:
            await self._quiet_reply(ctx, error_embed("DMs Closed", "I could not DM you. Please enable DMs for this server."))

    async def _send_public_webhook(self, ctx, embed):
        perms = ctx.channel.permissions_for(ctx.guild.me)
        if not perms.manage_webhooks:
            return await ctx.reply(embed=error_embed("Missing Permission", "I need Manage Webhooks to display notes publicly."))

        webhook = None
        try:
            webhook = await ctx.channel.create_webhook(name="xiel Notes", reason=f"Public notes display by {ctx.author}")
            await webhook.send(
                embed=embed,
                username=f"{ctx.author.display_name}'s Notes",
                avatar_url=ctx.author.display_avatar.url,
                wait=True,
            )
        finally:
            if webhook:
                try:
                    await webhook.delete(reason="Temporary notes webhook cleanup")
                except Exception:
                    pass

    @commands.group(name="notes", aliases=["note", "todo", "tasks"], invoke_without_command=True)
    @commands.guild_only()
    async def notes(self, ctx):
        """Show your notes privately in DM."""
        await self._hide_invocation(ctx)
        await self._dm_notes(ctx)

    @notes.command(name="add", aliases=["new", "write"])
    async def notes_add(self, ctx, *, text: str = None):
        """Add one or more note points. Separate multiple points with |."""
        await self._hide_invocation(ctx)
        if not text:
            return await self._quiet_reply(ctx, error_embed("Usage", f"`{config.PREFIX}notes add <task>`"))

        parts = [part.strip() for part in text.split("|") if part.strip()]
        if not parts:
            return await self._quiet_reply(ctx, error_embed("Empty Note", "Write at least one task or point."))

        data = self._get_notes(ctx.author.id)
        for part in parts:
            data["items"].append({"text": part[:500], "done": False, "created_at": int(time.time())})
        self._save_notes(ctx.author.id, data)
        await self._dm_notes(ctx, data, f"Added {len(parts)} note point(s).")

    @notes.command(name="done", aliases=["check", "strike", "complete"])
    async def notes_done(self, ctx, number: int = None):
        """Strike off a completed note point."""
        await self._hide_invocation(ctx)
        data = self._get_notes(ctx.author.id)
        if number is None or number < 1 or number > len(data["items"]):
            return await self._quiet_reply(ctx, error_embed("Invalid Point", "Give a valid note number."))
        data["items"][number - 1]["done"] = True
        self._save_notes(ctx.author.id, data)
        await self._dm_notes(ctx, data, f"Marked point {number} as done.")

    @notes.command(name="undo", aliases=["uncheck"])
    async def notes_undo(self, ctx, number: int = None):
        """Un-strike a note point."""
        await self._hide_invocation(ctx)
        data = self._get_notes(ctx.author.id)
        if number is None or number < 1 or number > len(data["items"]):
            return await self._quiet_reply(ctx, error_embed("Invalid Point", "Give a valid note number."))
        data["items"][number - 1]["done"] = False
        self._save_notes(ctx.author.id, data)
        await self._dm_notes(ctx, data, f"Reopened point {number}.")

    @notes.command(name="edit")
    async def notes_edit(self, ctx, number: int = None, *, text: str = None):
        """Edit a note point."""
        await self._hide_invocation(ctx)
        data = self._get_notes(ctx.author.id)
        if number is None or number < 1 or number > len(data["items"]) or not text:
            return await self._quiet_reply(ctx, error_embed("Usage", f"`{config.PREFIX}notes edit <number> <new text>`"))
        data["items"][number - 1]["text"] = text[:500]
        self._save_notes(ctx.author.id, data)
        await self._dm_notes(ctx, data, f"Edited point {number}.")

    @notes.command(name="remove", aliases=["delete", "rm"])
    async def notes_remove(self, ctx, number: int = None):
        """Remove a note point."""
        await self._hide_invocation(ctx)
        data = self._get_notes(ctx.author.id)
        if number is None or number < 1 or number > len(data["items"]):
            return await self._quiet_reply(ctx, error_embed("Invalid Point", "Give a valid note number."))
        removed = data["items"].pop(number - 1)
        self._save_notes(ctx.author.id, data)
        await self._dm_notes(ctx, data, f"Removed: {removed.get('text', 'note')}")

    @notes.command(name="clear", aliases=["wipe"])
    async def notes_clear(self, ctx):
        """Clear all your notes."""
        await self._hide_invocation(ctx)
        self._save_notes(ctx.author.id, self._blank())
        await self._quiet_reply(ctx, success_embed("Notes Cleared", "Your notes are now empty."))

    @notes.command(name="title")
    async def notes_title(self, ctx, *, title: str = None):
        """Set your notes title."""
        await self._hide_invocation(ctx)
        if not title:
            return await self._quiet_reply(ctx, error_embed("Usage", f"`{config.PREFIX}notes title <title>`"))
        data = self._get_notes(ctx.author.id)
        data["title"] = title[:100]
        self._save_notes(ctx.author.id, data)
        await self._dm_notes(ctx, data, "Updated your notes title.")

    @notes.command(name="move")
    async def notes_move(self, ctx, old: int = None, new: int = None):
        """Move a note point to a different position."""
        await self._hide_invocation(ctx)
        data = self._get_notes(ctx.author.id)
        if (
            old is None
            or new is None
            or old < 1
            or new < 1
            or old > len(data["items"])
            or new > len(data["items"])
        ):
            return await self._quiet_reply(ctx, error_embed("Usage", f"`{config.PREFIX}notes move <from> <to>`"))
        item = data["items"].pop(old - 1)
        data["items"].insert(new - 1, item)
        self._save_notes(ctx.author.id, data)
        await self._dm_notes(ctx, data, f"Moved point {old} to {new}.")

    @notes.command(name="public", aliases=["share", "show"])
    async def notes_public(self, ctx):
        """Display your notes publicly using a webhook."""
        data = self._get_notes(ctx.author.id)
        embed = self._format_notes(data, ctx.author)
        await self._send_public_webhook(ctx, embed)

    @notes.command(name="stats", aliases=["progress"])
    async def notes_stats(self, ctx):
        """DM your note completion progress."""
        await self._hide_invocation(ctx)
        data = self._get_notes(ctx.author.id)
        total = len(data["items"])
        done = sum(1 for item in data["items"] if item.get("done"))
        percent = round((done / total) * 100) if total else 0
        await self._quiet_reply(ctx, info_embed("Notes Progress", f"Done: **{done}/{total}** ({percent}%)."))


async def setup(bot):
    await bot.add_cog(Notes(bot))
