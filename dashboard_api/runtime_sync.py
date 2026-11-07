from __future__ import annotations

from datetime import UTC, datetime


def sync_prefix(bot, guild_id: str, prefix: str, updated_by: str = "0") -> None:
    numeric_guild_id = int(guild_id)
    numeric_user_id = int(updated_by) if str(updated_by).isdigit() else 0
    if not hasattr(bot, "prefix_cache"):
        bot.prefix_cache = {}
    bot.prefix_cache[numeric_guild_id] = prefix

    prefix_cog = bot.get_cog("PrefixManager")
    if prefix_cog is None or not hasattr(prefix_cog, "db"):
        return
    from database.models import ServerPrefix

    session = prefix_cog.db.get_session()
    try:
        record = session.query(ServerPrefix).filter_by(server_id=numeric_guild_id).first()
        if record:
            record.prefix = prefix
            record.set_by = numeric_user_id
            record.set_at = datetime.now(UTC).replace(tzinfo=None)
        else:
            session.add(ServerPrefix(server_id=numeric_guild_id, prefix=prefix, set_by=numeric_user_id))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def sync_alias_add(guild_id: str, alias: dict, updated_by: str) -> None:
    from utils.database import settings_db

    if settings_db:
        settings_db.add_alias(guild_id, alias["name"], alias["command"], updated_by)


def sync_alias_delete(guild_id: str, name: str) -> None:
    from utils.database import settings_db

    if settings_db:
        settings_db.remove_alias(guild_id, name)


def sync_security(guild_id: str, anti_nuke: dict | None, access: dict | None) -> None:
    from utils.antinuke_core import merge_config
    from utils.database import settings_db

    if not settings_db:
        return

    if anti_nuke is not None:
        current = settings_db.get_setting("antinuke_v3", guild_id, "config", None)
        runtime = merge_config(current)
        runtime["log_channel_id"] = anti_nuke.get("logChannelId") or None
        master_enabled = bool(anti_nuke.get("enabled"))
        for name, module in anti_nuke.get("modules", {}).items():
            if name not in runtime["modules"]:
                continue
            runtime["modules"][name].update({
                "enabled": master_enabled and bool(module.get("enabled")),
                "threshold": int(module.get("threshold", 3)),
                "punishment": module.get("punishment", "strip"),
            })
        settings_db.set_setting("antinuke_v3", guild_id, "config", runtime)

    if access is not None:
        desired = {
            str(user_id): role
            for key, role in (("admins", "admin"), ("whitelist", "whitelisted"), ("trust", "trusted"))
            for user_id in access.get(key, [])
        }
        existing = {
            str(entry["user_id"]): entry["role"]
            for entry in settings_db.get_all_antinuke_whitelisted(guild_id)
        }
        for user_id in existing.keys() - desired.keys():
            settings_db.remove_antinuke_whitelist(guild_id, user_id)
        for user_id, role in desired.items():
            if existing.get(user_id) != role:
                settings_db.add_antinuke_whitelist(guild_id, user_id, role=role)


def sync_settings_document(bot, document: dict) -> None:
    guild_id = str(document.get("guildId", ""))
    if not guild_id.isdigit():
        return
    updated_by = str(document.get("updatedBy") or "0")
    if document.get("prefix"):
        sync_prefix(bot, guild_id, document["prefix"], updated_by)
    sync_security(guild_id, document.get("antiNuke"), document.get("access"))
    for alias in document.get("aliases", []):
        sync_alias_add(guild_id, alias, updated_by)


def normalize_premium_name(command_name: str) -> str | None:
    from utils.premium import normalize_premium_command

    return normalize_premium_command(command_name)


def sync_premium_grant(user_id: str, guild_id: str, command_name: str, granted_by: str) -> None:
    from utils.premium import grant_premium

    grant_premium(int(user_id), int(guild_id), command_name, int(granted_by))


def sync_premium_revoke(user_id: str, guild_id: str, command_name: str) -> None:
    from utils.premium import revoke_premium

    revoke_premium(int(user_id), int(guild_id), command_name)


def sync_profile_grant(user_id: str, guild_id: str, granted_by: str) -> None:
    from database.models import BotProfileAccess
    from utils.premium import _db

    session = _db.get_session()
    try:
        existing = session.query(BotProfileAccess).filter_by(
            user_id=int(user_id), server_id=int(guild_id)
        ).first()
        if not existing:
            session.add(BotProfileAccess(
                user_id=int(user_id), server_id=int(guild_id), granted_by=int(granted_by)
            ))
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def sync_profile_revoke(user_id: str, guild_id: str) -> None:
    from database.models import BotProfileAccess
    from utils.premium import _db

    session = _db.get_session()
    try:
        session.query(BotProfileAccess).filter_by(
            user_id=int(user_id), server_id=int(guild_id)
        ).delete()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def sync_global_ban(bot, user_id: str, reason: str, banned_by: str) -> None:
    from database.models import GlobalBan

    owner_cog = bot.get_cog("Owner")
    if owner_cog is None or not hasattr(owner_cog, "db"):
        return
    session = owner_cog.db.get_session()
    try:
        record = session.query(GlobalBan).filter_by(user_id=int(user_id)).first()
        if record:
            record.reason = reason
            record.banned_by = int(banned_by)
        else:
            session.add(GlobalBan(
                user_id=int(user_id), username=None, reason=reason, banned_by=int(banned_by)
            ))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def sync_global_unban(bot, user_id: str) -> None:
    from database.models import GlobalBan

    owner_cog = bot.get_cog("Owner")
    if owner_cog is None or not hasattr(owner_cog, "db"):
        return
    session = owner_cog.db.get_session()
    try:
        session.query(GlobalBan).filter_by(user_id=int(user_id)).delete()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
