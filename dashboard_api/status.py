from __future__ import annotations

from datetime import UTC, datetime


def status_payload(bot) -> dict:
    started_at = getattr(bot, "start_time", None)
    if not isinstance(started_at, datetime):
        uptime = 0
    else:
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        uptime = max(0, int((datetime.now(UTC) - started_at).total_seconds()))
    guilds = list(bot.guilds)
    return {
        "online": bot.is_ready() and not bot.is_closed(),
        "latency": max(0, round(bot.latency * 1000)) if bot.is_ready() else None,
        "guilds": len(guilds),
        "users": sum(guild.member_count or 0 for guild in guilds),
        "commandCount": len(list(bot.walk_commands())) + len(bot.tree.get_commands()),
        "commandsRun": max(0, int(getattr(bot, "commands_executed", 0))),
        "uptime": uptime,
        "updatedAt": datetime.now(UTC).isoformat(),
    }


def guild_snapshot(bot) -> list[dict]:
    return [{
        "id": str(guild.id),
        "name": guild.name,
        "icon": str(guild.icon.url) if guild.icon else None,
        "ownerId": str(guild.owner_id),
        "memberCount": guild.member_count or 0,
    } for guild in bot.guilds]
