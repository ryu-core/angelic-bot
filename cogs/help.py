"""Interactive, self-updating command help.

The command list is generated from Discord.py's live command registries.  This
keeps help in sync when commands or subcommands are added in another cog.
"""

from dataclasses import dataclass
from typing import Iterable

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Select, View

import config
from cogs.gf import GF_ID


COMMANDS_PER_PAGE = 8


def get_server_prefix(bot, guild_id: int | None) -> str:
    if guild_id and hasattr(bot, "prefix_cache") and guild_id in bot.prefix_cache:
        return bot.prefix_cache[guild_id]
    return config.PREFIX


# There must be at most 24 visible categories because a Discord select supports
# 25 options and Overview occupies one of them.
CATEGORY_META = {
    "moderation": ("Moderation", "🛡️", "Moderation, roles, and channel controls"),
    "games": ("Games", "🎮", "Multiplayer, solo, and casino games"),
    "catch": ("Catch System", "🎯", "Catch, trade, train, and battle"),
    "economy": ("Economy", "💰", "Balances, rewards, banking, and shops"),
    "fun": ("Fun & Roleplay", "🎉", "Roleplay reactions and social commands"),
    "marriage": ("Marriage", "💍", "Marriage, adoption, and family trees"),
    "search": ("Search", "🔍", "Image search and fact checking"),
    "utility": ("Utility", "⚙️", "Information and everyday tools"),
    "message_stats": ("Message Stats", "📊", "Message counters and leaderboards"),
    "invites": ("Invites", "🎟️", "Invite tracking, rewards, and goals"),
    "confessions": ("Confessions", "🔒", "Anonymous confessions and filters"),
    "ai_chat": ("AI Chat", "🤖", "AI channels and premium questions"),
    "translation": ("Translation", "🌐", "Translation and language monitoring"),
    "crypto": ("Crypto", "📈", "Prices, trends, and portfolios"),
    "premium": ("Premium", "👑", "Premium and restricted commands"),
    "booster": ("Boosters", "💎", "Boost announcements and booster roles"),
    "therapy": ("Therapy", "🫂", "Private support session tools"),
    "security": ("Security", "🛡️", "AntiNuke and server protection"),
    "tickets": ("Ticket Sorting", "📂", "Automatic ticket organization"),
    "music": ("Music & Voice", "🎵", "Music playback and voice tools"),
    "giveaways": ("Giveaways", "🎁", "Giveaway creation and requirements"),
    "setup": ("Server Setup", "🔧", "Welcome, roles, prefixes, and automation"),
    "staff": ("Staff Tools", "📋", "Staff supervision and server logs"),
}


COG_CATEGORIES = {
    "AFK": "utility",
    "AIChat": "ai_chat",
    "AntiNuke": "security",
    "AutoQuote": "utility",
    "AutoRoles": "setup",
    "BleedCommands": "utility",
    "Booster": "booster",
    "BumpReminder": "setup",
    "Catch": "catch",
    "ConfessionManager": "confessions",
    "Crypto": "crypto",
    "Economy": "economy",
    "EconomyGames": "games",
    "EmbedBuilder": "utility",
    "Games": "games",
    "General": "utility",
    "GF": "premium",
    "Giveaways": "giveaways",
    "Help": "utility",
    "InviteManager": "invites",
    "Marriage": "marriage",
    "MessageStats": "message_stats",
    "Moderation": "moderation",
    "MultiplayerGames": "games",
    "Music": "music",
    "Notes": "utility",
    "Owner": "premium",
    "PrefixManager": "setup",
    "PremiumCommands": "premium",
    "PrivateVC": "music",
    "RoleChannelTools": "moderation",
    "Roleplay": "fun",
    "Search": "search",
    "StaffSupervision": "staff",
    "TherapySessions": "therapy",
    "TicketSort": "tickets",
    "TranslationMonitor": "translation",
    "Transparency": "staff",
    "TTSCommands": "music",
    "Utility": "utility",
    "UwULock": "security",
    "WelcomeSystem": "setup",
}


# A few broad cogs contain commands that clearly belong in another category.
COMMAND_CATEGORIES = {
    "nuke": "security",
    "softban": "moderation",
    "hardban": "moderation",
    "tempban": "moderation",
    "massban": "moderation",
    "deleteemoji": "moderation",
    "stripstaff": "moderation",
    "roleall": "moderation",
    "unroleall": "moderation",
    "ship": "fun",
    "quotemsg": "fun",
    "translate": "translation",
}


@dataclass(frozen=True)
class HelpEntry:
    key: str
    category: str
    name: str
    usage: str
    description: str
    aliases: tuple[str, ...] = ()
    command: object | None = None
    is_slash: bool = False


def _cog_name(command) -> str:
    name = getattr(command, "cog_name", None)
    if name:
        return name
    binding = getattr(command, "binding", None)
    return binding.__class__.__name__ if binding is not None else ""


def _category_for(command) -> str:
    simple_name = getattr(command, "name", "").lower()
    return COMMAND_CATEGORIES.get(simple_name, COG_CATEGORIES.get(_cog_name(command), "utility"))


def _visible_to(command, user_id: int) -> bool:
    if getattr(command, "hidden", False):
        return False
    cog_name = _cog_name(command)
    if cog_name == "Owner" and user_id not in config.OWNER_IDS:
        return False
    if cog_name in {"GF", "UwULock"} and user_id != GF_ID and user_id not in config.OWNER_IDS:
        return False
    return True


def _one_line(value: str | None, fallback: str) -> str:
    text = " ".join((value or "").strip().split())
    return (text or fallback)[:180]


def _walk_app_commands(bot, guild_id: int | None = None) -> Iterable[app_commands.Command | app_commands.Group]:
    """Walk the application-command tree without relying on a library version."""
    guild = discord.Object(id=guild_id) if guild_id else None
    stack = list(bot.tree.get_commands(guild=guild))
    while stack:
        command = stack.pop(0)
        yield command
        if isinstance(command, app_commands.Group):
            stack[0:0] = list(command.commands)


def collect_help_entries(bot, user_id: int, prefix: str,
                         guild_id: int | None = None) -> list[HelpEntry]:
    entries: list[HelpEntry] = []
    seen: set[str] = set()

    for command in bot.walk_commands():
        if not _visible_to(command, user_id):
            continue
        qualified = command.qualified_name
        signature = f" {command.signature}" if command.signature else ""
        key = f"prefix:{qualified.lower()}"
        seen.add(key)
        entries.append(HelpEntry(
            key=key,
            category=_category_for(command),
            name=qualified,
            usage=f"{prefix}{qualified}{signature}",
            description=_one_line(command.short_doc, "No description provided."),
            aliases=tuple(command.aliases),
            command=command,
        ))

    for command in _walk_app_commands(bot, guild_id):
        if isinstance(command, app_commands.Group) or not _visible_to(command, user_id):
            continue
        qualified = command.qualified_name
        key = f"slash:{qualified.lower()}"
        # Hybrid commands are already represented by their prefix form.
        if f"prefix:{qualified.lower()}" in seen:
            continue
        entries.append(HelpEntry(
            key=key,
            category=_category_for(command),
            name=qualified,
            usage=f"/{qualified}",
            description=_one_line(command.description, "No description provided."),
            command=command,
            is_slash=True,
        ))

    return sorted(entries, key=lambda entry: (entry.category, entry.name.lower(), entry.is_slash))


class HelpDropdown(Select):
    def __init__(self, view: "HelpView"):
        options = [discord.SelectOption(
            label="Overview", value="overview", emoji="🌟",
            description="All command categories", default=view.current_category == "overview",
        )]
        for key in view.available_categories:
            label, emoji, description = CATEGORY_META[key]
            options.append(discord.SelectOption(
                label=label, value=key, emoji=emoji, description=description[:100],
                default=view.current_category == key,
            ))
        super().__init__(placeholder="Select a command category...", options=options,
                         min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: HelpView = self.view
        if not await view.ensure_author(interaction):
            return
        view.current_category = self.values[0]
        view.current_page = 0
        view.refresh_components()
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class PageButton(Button):
    def __init__(self, action: str, emoji: str, row: int = 1):
        super().__init__(style=discord.ButtonStyle.secondary, emoji=emoji, row=row,
                         custom_id=f"help_page_{action}")
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: HelpView = self.view
        if not await view.ensure_author(interaction):
            return
        last = view.page_count - 1
        if self.action == "first":
            view.current_page = 0
        elif self.action == "previous":
            view.current_page = max(0, view.current_page - 1)
        elif self.action == "next":
            view.current_page = min(last, view.current_page + 1)
        elif self.action == "last":
            view.current_page = last
        view.refresh_components()
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class PageIndicator(Button):
    def __init__(self, page: int, pages: int):
        super().__init__(label=f"{page + 1} / {pages}", style=discord.ButtonStyle.secondary,
                         disabled=True, row=1)


class HelpView(View):
    def __init__(self, bot, author_id: int, guild_id: int | None = None,
                 initial_category: str = "overview"):
        super().__init__(timeout=180)
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id
        self.prefix = get_server_prefix(bot, guild_id)
        self.entries = collect_help_entries(bot, author_id, self.prefix, guild_id)
        populated = {entry.category for entry in self.entries}
        self.available_categories = [key for key in CATEGORY_META if key in populated]
        self.current_category = initial_category if initial_category in populated else "overview"
        self.current_page = 0
        self.message = None
        self.refresh_components()

    @property
    def category_entries(self) -> list[HelpEntry]:
        if self.current_category == "overview":
            return []
        return [entry for entry in self.entries if entry.category == self.current_category]

    @property
    def page_count(self) -> int:
        if self.current_category == "overview":
            return max(1, (len(self.available_categories) + 7) // 8)
        return max(1, (len(self.category_entries) + COMMANDS_PER_PAGE - 1) // COMMANDS_PER_PAGE)

    async def ensure_author(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            f"Use your own `{self.prefix}help` command!", ephemeral=True
        )
        return False

    def refresh_components(self):
        self.current_page = min(self.current_page, self.page_count - 1)
        self.clear_items()
        self.add_item(HelpDropdown(self))
        pages = self.page_count
        first = PageButton("first", "⏮️")
        previous = PageButton("previous", "◀️")
        next_button = PageButton("next", "▶️")
        last = PageButton("last", "⏭️")
        first.disabled = previous.disabled = self.current_page == 0
        next_button.disabled = last.disabled = self.current_page >= pages - 1
        self.add_item(first)
        self.add_item(previous)
        self.add_item(PageIndicator(self.current_page, pages))
        self.add_item(next_button)
        self.add_item(last)

    def build_embed(self) -> discord.Embed:
        if self.current_category == "overview":
            start = self.current_page * 8
            keys = self.available_categories[start:start + 8]
            lines = []
            for key in keys:
                label, emoji, description = CATEGORY_META[key]
                count = sum(entry.category == key for entry in self.entries)
                lines.append(f"{emoji} **{label}** — {count} command{'s' if count != 1 else ''}\n{description}")
            embed = discord.Embed(
                title="🌟 xiel — Command Overview",
                description=(
                    f"**{len(self.entries)} commands are currently available to you.**\n"
                    f"Select a category below or use `{self.prefix}help <command>` for details.\n\n"
                    + "\n\n".join(lines)
                ),
                color=config.COLORS.get("primary", 0x9B59B6),
            )
        else:
            label, emoji, description = CATEGORY_META[self.current_category]
            start = self.current_page * COMMANDS_PER_PAGE
            page_entries = self.category_entries[start:start + COMMANDS_PER_PAGE]
            lines = []
            for entry in page_entries:
                aliases = f" · aliases: {', '.join(f'`{alias}`' for alias in entry.aliases)}" if entry.aliases else ""
                lines.append(f"**`{entry.usage}`**{aliases}\n{entry.description}")
            embed = discord.Embed(
                title=f"{emoji} {label} Commands",
                description=f"{description}\n\n" + "\n\n".join(lines),
                color=config.COLORS.get("primary", 0x9B59B6),
            )
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=(
            f"Page {self.current_page + 1}/{self.page_count} • Prefix: {self.prefix} • "
            f"{self.prefix}help <command> for details"
        ))
        return embed

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.HTTPException, discord.NotFound):
                pass


class Help(commands.Cog):
    """Complete interactive command reference."""

    def __init__(self, bot):
        self.bot = bot

    def _find_entry(self, entries: list[HelpEntry], query: str) -> HelpEntry | None:
        query = query.strip().lower().removeprefix("/")
        for entry in entries:
            if entry.name.lower() == query:
                return entry
            if not entry.is_slash and query in (alias.lower() for alias in entry.aliases):
                return entry
        return None

    @commands.command(name="help", aliases=["h", "commands"])
    async def help_command(self, ctx, *, command_name: str | None = None):
        """Browse every available command or inspect one command."""
        guild_id = ctx.guild.id if ctx.guild else None
        prefix = get_server_prefix(self.bot, guild_id)
        entries = collect_help_entries(self.bot, ctx.author.id, prefix, guild_id)

        if command_name:
            category_key = command_name.strip().lower().replace(" ", "_")
            if category_key in CATEGORY_META and any(e.category == category_key for e in entries):
                view = HelpView(self.bot, ctx.author.id, guild_id, category_key)
                view.message = await ctx.reply(embed=view.build_embed(), view=view)
                return

            entry = self._find_entry(entries, command_name)
            if entry is None:
                embed = discord.Embed(
                    title=f"{config.EMOJIS.get('error', '❌')} Command Not Found",
                    description=f"No command called **`{command_name}`** was found.\nUse `{prefix}help` to browse every category.",
                    color=config.COLORS.get("error", 0xE74C3C),
                )
                await ctx.reply(embed=embed)
                return

            aliases = ""
            if entry.aliases:
                aliases = "\n**Aliases:** " + ", ".join(f"`{prefix}{alias}`" for alias in entry.aliases)
            label = CATEGORY_META[entry.category][0]
            embed = discord.Embed(
                title=f"📖 Command: {entry.name}",
                description=f"{entry.description}\n\n**Usage:** `{entry.usage}`{aliases}",
                color=config.COLORS.get("primary", 0x9B59B6),
            )
            embed.set_footer(text=f"Category: {label}")
            await ctx.reply(embed=embed)
            return

        view = HelpView(self.bot, ctx.author.id, guild_id)
        view.message = await ctx.reply(embed=view.build_embed(), view=view)


async def setup(bot):
    await bot.add_cog(Help(bot))
