import re


NAMED_COLORS = {
    "black": 0x000000,
    "white": 0xFFFFFF,
    "red": 0xE74C3C,
    "orange": 0xE67E22,
    "yellow": 0xF1C40F,
    "green": 0x2ECC71,
    "blue": 0x3498DB,
    "purple": 0x9B59B6,
    "pink": 0xFF5CA8,
    "gray": 0x95A5A6,
    "grey": 0x95A5A6,
    "gold": 0xF1C40F,
    "aqua": 0x1ABC9C,
    "teal": 0x1ABC9C,
}


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def normalize_role_query(value):
    query = str(value or "").strip()
    mention = re.fullmatch(r"<@&(\d+)>", query)
    if mention:
        return mention.group(1)
    return query


def role_search_score(role, query):
    query = normalize_role_query(query)
    query_norm = normalize_text(query)
    if not query_norm:
        return None

    role_id = str(getattr(role, "id", ""))
    role_name = normalize_text(getattr(role, "name", ""))
    compact_role = role_name.replace(" ", "")
    compact_query = query_norm.replace(" ", "")
    initials = "".join(part[0] for part in role_name.split() if part)

    if query_norm == role_id:
        return 0
    if role_name == query_norm:
        return 1
    if compact_role == compact_query:
        return 2
    if initials and initials == compact_query:
        return 3
    if role_name.startswith(query_norm):
        return 4
    if compact_role.startswith(compact_query):
        return 5
    if any(part.startswith(query_norm) for part in role_name.split()):
        return 6
    if query_norm in role_name:
        return 7
    if compact_query in compact_role:
        return 8
    return None


def find_role_matches(roles, query, limit=5):
    matches = []
    for role in roles:
        score = role_search_score(role, query)
        if score is not None:
            matches.append((score, getattr(role, "position", 0) * -1, getattr(role, "name", ""), role))
    matches.sort(key=lambda item: (item[0], item[1], item[2].lower()))
    return [item[3] for item in matches[:limit]]


def is_exact_role_match(role, query):
    query = normalize_role_query(query)
    query_norm = normalize_text(query)
    role_id = str(getattr(role, "id", ""))
    role_name = normalize_text(getattr(role, "name", ""))
    return query_norm in {
        role_id,
        role_name,
        role_name.replace(" ", ""),
        "".join(part[0] for part in role_name.split() if part),
    }


def parse_natural_role_edit(roles, payload):
    """Parse: <existing role> <new name> [color], resolving the role from the left."""
    tokens = str(payload or "").strip().split()
    if not tokens:
        return None, None, None, "empty"

    color = None
    if parse_color_value(tokens[-1]) is not None:
        color = tokens.pop()

    if not tokens:
        return None, None, color, "missing_role"

    saw_ambiguous = False
    for split_at in range(len(tokens), 0, -1):
        role_query = " ".join(tokens[:split_at])
        new_name = " ".join(tokens[split_at:]).strip() or None
        matches = find_role_matches(roles, role_query, limit=6)
        if not matches:
            continue

        exact_matches = [role for role in matches if is_exact_role_match(role, role_query)]
        if len(exact_matches) == 1:
            return exact_matches[0], new_name, color, None

        if len(matches) == 1 and (new_name or color is not None):
            return matches[0], new_name, color, None

        saw_ambiguous = True

    return None, None, color, "ambiguous" if saw_ambiguous else "not_found"


def parse_color_value(value):
    raw = str(value or "").strip().lower()
    if not raw:
        return None

    if raw in {"none", "default", "reset"}:
        return 0
    if raw in NAMED_COLORS:
        return NAMED_COLORS[raw]

    if raw.startswith("#"):
        raw = raw[1:]
    elif raw.startswith("0x"):
        raw = raw[2:]

    if len(raw) == 3 and re.fullmatch(r"[0-9a-f]{3}", raw):
        raw = "".join(char * 2 for char in raw)

    if re.fullmatch(r"[0-9a-f]{6}", raw):
        return int(raw, 16)

    return None


def parse_on_off(value):
    raw = str(value or "").strip().lower()
    if raw in {"on", "yes", "true", "enable", "enabled", "1"}:
        return True
    if raw in {"off", "no", "false", "disable", "disabled", "0"}:
        return False
    return None
