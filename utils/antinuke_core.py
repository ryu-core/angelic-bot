from copy import deepcopy


VALID_PUNISHMENTS = {"ban", "kick", "strip", "stripstaff", "timeout", "warn"}

DEFAULT_MODULES = {
    "ban": {
        "enabled": False,
        "threshold": 3,
        "punishment": "ban",
        "command_detection": True,
        "label": "member bans",
    },
    "kick": {
        "enabled": False,
        "threshold": 3,
        "punishment": "ban",
        "command_detection": True,
        "label": "member kicks",
    },
    "channel": {
        "enabled": False,
        "threshold": 3,
        "punishment": "ban",
        "command_detection": True,
        "label": "channel create/delete",
    },
    "role": {
        "enabled": False,
        "threshold": 3,
        "punishment": "ban",
        "command_detection": True,
        "label": "role create/delete",
    },
    "webhook": {
        "enabled": False,
        "threshold": 5,
        "punishment": "ban",
        "command_detection": False,
        "label": "webhook creates",
    },
    "botadd": {
        "enabled": False,
        "threshold": 1,
        "punishment": "ban",
        "command_detection": False,
        "label": "bot additions",
    },
    "emoji": {
        "enabled": False,
        "threshold": 3,
        "punishment": "ban",
        "command_detection": False,
        "label": "emoji deletes",
    },
    "vanity": {
        "enabled": False,
        "threshold": 1,
        "punishment": "ban",
        "command_detection": False,
        "label": "vanity changes",
    },
    "guild": {
        "enabled": False,
        "threshold": 3,
        "punishment": "ban",
        "command_detection": False,
        "label": "server updates",
    },
    "adminrole": {
        "enabled": False,
        "threshold": 1,
        "punishment": "ban",
        "command_detection": False,
        "label": "admin role grants",
    },
}

MODULE_ALIASES = {
    "bans": "ban",
    "memberban": "ban",
    "member_ban": "ban",
    "kicks": "kick",
    "memberkick": "kick",
    "member_kick": "kick",
    "channels": "channel",
    "channel_create": "channel",
    "channel_delete": "channel",
    "channelcreate": "channel",
    "channeldelete": "channel",
    "roles": "role",
    "role_create": "role",
    "role_delete": "role",
    "rolecreate": "role",
    "roledelete": "role",
    "webhooks": "webhook",
    "webhook_create": "webhook",
    "webhookcreate": "webhook",
    "bot": "botadd",
    "bots": "botadd",
    "bot_add": "botadd",
    "botadd": "botadd",
    "emojis": "emoji",
    "emoji_delete": "emoji",
    "emojidelete": "emoji",
    "vanity_url": "vanity",
    "server": "guild",
    "serverupdate": "guild",
    "guild_update": "guild",
    "guildupdate": "guild",
    "admin": "adminrole",
    "adminrole": "adminrole",
    "admin_role": "adminrole",
    "admin_role_grant": "adminrole",
    "adminrolegrant": "adminrole",
}

LEGACY_THRESHOLD_TO_MODULE = {
    "ban": "ban",
    "kick": "kick",
    "channel_delete": "channel",
    "role_delete": "role",
    "webhook_create": "webhook",
    "bot_add": "botadd",
    "admin_role_grant": "adminrole",
    "guild_update": "guild",
    "vanity": "vanity",
}

COMMAND_MODULE_MAP = {
    "ban": "ban",
    "b": "ban",
    "tempban": "ban",
    "softban": "ban",
    "hardban": "ban",
    "massban": "ban",
    "kick": "kick",
    "k": "kick",
    "nuke": "channel",
    "roleall": "role",
    "unroleall": "role",
    "stripstaff": "role",
}


def normalize_module(value):
    if value is None:
        return None
    key = str(value).lower().replace("-", "_")
    key = key.replace(" ", "_")
    if key in DEFAULT_MODULES:
        return key
    return MODULE_ALIASES.get(key)


def clamp_threshold(value, default=1):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(20, number))


def parse_bool(value):
    if value is None:
        return None
    key = str(value).lower()
    if key in {"on", "enable", "enabled", "true", "yes", "y", "1"}:
        return True
    if key in {"off", "disable", "disabled", "false", "no", "n", "0"}:
        return False
    return None


def default_config():
    return {
        "version": 3,
        "log_channel_id": None,
        "modules": deepcopy(DEFAULT_MODULES),
    }


def normalize_module_config(module_config, defaults):
    merged = deepcopy(defaults)
    if not isinstance(module_config, dict):
        return merged

    if "enabled" in module_config:
        parsed = parse_bool(module_config.get("enabled"))
        if parsed is not None:
            merged["enabled"] = parsed
    if "threshold" in module_config:
        merged["threshold"] = clamp_threshold(module_config.get("threshold"), defaults["threshold"])
    if module_config.get("punishment") in VALID_PUNISHMENTS:
        merged["punishment"] = module_config["punishment"]
    if "command_detection" in module_config:
        parsed = parse_bool(module_config.get("command_detection"))
        if parsed is not None:
            merged["command_detection"] = parsed
    return merged


def merge_config(raw):
    config = default_config()
    if not isinstance(raw, dict):
        return config

    if raw.get("log_channel_id"):
        config["log_channel_id"] = raw.get("log_channel_id")

    if isinstance(raw.get("modules"), dict):
        for name, module_config in raw["modules"].items():
            module = normalize_module(name)
            if module:
                config["modules"][module] = normalize_module_config(
                    module_config,
                    config["modules"][module],
                )
        return config

    # Lazy migration for the old v2 shape.
    if "thresholds" in raw or "enabled" in raw:
        enabled = bool(raw.get("enabled", False))
        punishment = raw.get("punishment") if raw.get("punishment") in VALID_PUNISHMENTS else "ban"
        for module in config["modules"]:
            config["modules"][module]["enabled"] = enabled
            config["modules"][module]["punishment"] = punishment

        thresholds = raw.get("thresholds") if isinstance(raw.get("thresholds"), dict) else {}
        for old_key, value in thresholds.items():
            module = LEGACY_THRESHOLD_TO_MODULE.get(old_key)
            if module:
                config["modules"][module]["threshold"] = clamp_threshold(
                    value,
                    config["modules"][module]["threshold"],
                )

        if "bot_add_enabled" in raw:
            parsed = parse_bool(raw.get("bot_add_enabled"))
            if parsed is not None:
                config["modules"]["botadd"]["enabled"] = parsed and enabled
        if "vanity_enabled" in raw:
            parsed = parse_bool(raw.get("vanity_enabled"))
            if parsed is not None:
                config["modules"]["vanity"]["enabled"] = parsed and enabled

    return config


def parse_module_flags(args):
    updates = {}
    errors = []
    args = list(args or [])
    index = 0

    while index < len(args):
        token = str(args[index])
        key = token
        value = None

        if "=" in token and token.startswith("--"):
            key, value = token.split("=", 1)
        elif token.startswith("--") or token in {"-t", "-p", "-c"}:
            if index + 1 >= len(args):
                errors.append(f"missing value for {token}")
                break
            value = args[index + 1]
            index += 1
        else:
            errors.append(f"unknown flag {token}")
            index += 1
            continue

        if key in {"--threshold", "-t"}:
            try:
                number = int(value)
            except (TypeError, ValueError):
                errors.append("threshold must be a number between 1 and 20")
            else:
                if number < 1 or number > 20:
                    errors.append("threshold must be between 1 and 20")
                else:
                    updates["threshold"] = number
        elif key in {"--do", "--punishment", "-p"}:
            punishment = str(value).lower()
            if punishment not in VALID_PUNISHMENTS:
                errors.append("punishment must be ban, kick, strip, stripstaff, timeout, or warn")
            else:
                updates["punishment"] = punishment
        elif key in {"--command", "-c"}:
            parsed = parse_bool(value)
            if parsed is None:
                errors.append("command must be on or off")
            else:
                updates["command_detection"] = parsed
        else:
            errors.append(f"unknown flag {key}")

        index += 1

    return updates, errors


def module_is_enabled(config, module):
    module = normalize_module(module)
    if not module:
        return False
    return bool(config.get("modules", {}).get(module, {}).get("enabled"))


def get_module_config(config, module):
    module = normalize_module(module)
    if not module:
        return None
    return config.get("modules", {}).get(module)
