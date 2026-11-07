from __future__ import annotations

from discord import Object, app_commands


COG_CATEGORIES = {
    "AFK": "Utility", "AIChat": "AI Chat", "AntiNuke": "Security", "AutoQuote": "Utility",
    "AutoRoles": "Server Setup", "BleedCommands": "Utility", "Booster": "Boosters",
    "BumpReminder": "Server Setup", "Catch": "Catch System", "ConfessionManager": "Confessions",
    "Crypto": "Crypto", "Economy": "Economy", "EconomyGames": "Games", "EmbedBuilder": "Utility",
    "Games": "Games", "General": "Utility", "GF": "Premium", "Giveaways": "Giveaways",
    "Help": "Utility", "InviteManager": "Invites", "Marriage": "Marriage", "MessageStats": "Message Stats",
    "Moderation": "Moderation", "MultiplayerGames": "Games", "Music": "Music & Voice",
    "Notes": "Utility", "Owner": "Owner", "PrefixManager": "Server Setup", "PremiumCommands": "Premium",
    "PrivateVC": "Music & Voice", "RoleChannelTools": "Moderation", "Roleplay": "Fun & Roleplay",
    "Search": "Search", "StaffSupervision": "Staff Tools", "TherapySessions": "Therapy",
    "TicketSort": "Ticket Sorting", "TranslationMonitor": "Translation", "Transparency": "Staff Tools",
    "TTSCommands": "Music & Voice", "Utility": "Utility", "UwULock": "Security", "WelcomeSystem": "Server Setup",
}
COMMAND_CATEGORIES = {
    "nuke": "Security", "softban": "Moderation", "hardban": "Moderation", "tempban": "Moderation",
    "massban": "Moderation", "ship": "Fun & Roleplay", "quotemsg": "Fun & Roleplay", "translate": "Translation",
}


def _one_line(value: str | None, name: str) -> str:
    text = " ".join((value or "").strip().split())
    return (text or f"Run the {name} command.")[:180]


def _app_commands(bot):
    roots = list(bot.tree.get_commands())
    if bot.guilds:
        roots.extend(bot.tree.get_commands(guild=Object(id=bot.guilds[0].id)))
    stack = roots
    seen = set()
    while stack:
        command = stack.pop(0)
        key = (command.qualified_name.lower(), command.__class__, getattr(command, "type", None))
        if key in seen:
            continue
        seen.add(key)
        yield command
        if isinstance(command, app_commands.Group):
            stack[0:0] = list(command.commands)


def _cog_name(command) -> str:
    name = getattr(command, "cog_name", None)
    if name:
        return name
    binding = getattr(command, "binding", None)
    return binding.__class__.__name__ if binding is not None else ""


def _category(command) -> str:
    return COMMAND_CATEGORIES.get(command.name.lower(), COG_CATEGORIES.get(_cog_name(command), "Utility"))


def _visible(command, user_id: str, config) -> bool:
    if getattr(command, "hidden", False):
        return False
    cog_name = _cog_name(command)
    if cog_name == "Owner" and user_id not in config.owners:
        return False
    return cog_name not in {"GF", "UwULock"} or user_id in config.owners


def command_registry(bot, user_id: str, config, prefix: str = ",") -> list[dict]:
    commands = []
    seen = set()
    for command in bot.walk_commands():
        if not _visible(command, user_id, config):
            continue
        qualified = command.qualified_name
        signature = f" {command.signature}" if command.signature else ""
        key = f"prefix:{qualified.lower()}"
        seen.add(key)
        category = _category(command)
        commands.append({
            "id": key, "name": qualified, "aliases": list(command.aliases),
            "syntax": f"{prefix}{qualified}{signature}", "category": category,
            "description": _one_line(command.short_doc, qualified),
            "source": command.callback.__module__.replace(".", "/") + ".py",
            "kind": "prefix", "premium": category == "Premium", "restricted": category in {"Premium", "Owner"},
        })
    for command in _app_commands(bot):
        if isinstance(command, app_commands.Group) or not _visible(command, user_id, config):
            continue
        qualified = command.qualified_name
        key = f"slash:{qualified.lower()}"
        if f"prefix:{qualified.lower()}" in seen:
            continue
        category = _category(command)
        commands.append({
            "id": key, "name": qualified, "aliases": [], "syntax": f"/{qualified}", "category": category,
            "description": _one_line(command.description, qualified), "source": "discord/app_commands",
            "kind": "slash", "premium": category == "Premium", "restricted": category in {"Premium", "Owner"},
        })
    return sorted(commands, key=lambda item: (item["category"], item["name"].lower(), item["kind"]))
