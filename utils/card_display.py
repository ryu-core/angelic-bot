"""
Card Display Utilities
Professional Pokemon-style card formatting — clean & premium userdex design
"""
import discord
from datetime import datetime, timezone
import math

# ─── Stat Bar ─────────────────────────────────────────────────────────────────

def create_stat_bar(value: int, max_value: int, length: int = 10) -> str:
    """Create a visual stat bar"""
    if max_value <= 0:
        return "░" * length
    filled = min(length, int((value / max_value) * length))
    return "█" * filled + "░" * (length - filled)


# ─── Inspect Card ─────────────────────────────────────────────────────────────

def format_card_display(pokemon_data: dict, member: discord.Member, rarity_info: dict) -> discord.Embed:
    """
    Create a professional card display for inspect command.
    """
    rarity = pokemon_data['rarity']
    stats = pokemon_data.get('stats', {
        'hp': pokemon_data.get('hp', 0),
        'attack': pokemon_data.get('attack', 0),
        'defense': pokemon_data.get('defense', 0),
        'speed': pokemon_data.get('speed', 0)
    })

    header = f"{rarity_info['emoji']} **{rarity.upper()}** — {member.display_name}"
    type_line = f"🔥 Type: `{pokemon_data['type']}` │ Level: `{pokemon_data.get('level', 1)}`"

    max_stat = max(stats.get('hp', 1), stats.get('attack', 1), stats.get('defense', 1), stats.get('speed', 1), 1)
    hp_bar  = create_stat_bar(stats.get('hp', 0), max_stat, 12)
    atk_bar = create_stat_bar(stats.get('attack', 0), max_stat, 12)
    def_bar = create_stat_bar(stats.get('defense', 0), max_stat, 12)
    spd_bar = create_stat_bar(stats.get('speed', 0), max_stat, 12)

    stats_display = (
        f"❤️ **HP**  `{hp_bar}` {stats.get('hp', 0)}\n"
        f"⚔️ **ATK** `{atk_bar}` {stats.get('attack', 0)}\n"
        f"🛡️ **DEF** `{def_bar}` {stats.get('defense', 0)}\n"
        f"⚡ **SPD** `{spd_bar}` {stats.get('speed', 0)}"
    )

    moves_list = "\n".join([f"• {move}" for move in pokemon_data.get('moves', [])])

    if pokemon_data.get('caught_at'):
        try:
            caught_at = datetime.fromisoformat(pokemon_data['caught_at'])
            if caught_at.tzinfo is None:
                caught_at = caught_at.replace(tzinfo=timezone.utc)
            time_diff = datetime.now(timezone.utc) - caught_at
            if time_diff.days > 0:
                time_str = f"{time_diff.days}d ago"
            elif time_diff.seconds >= 3600:
                time_str = f"{time_diff.seconds // 3600}h ago"
            else:
                time_str = f"{time_diff.seconds // 60}m ago"
        except (ValueError, TypeError):
            time_str = "Unknown"
    else:
        time_str = "Unknown"

    embed = discord.Embed(
        title=header,
        color=rarity_info.get('color', 0xFFD700)
    )
    embed.description = f"{type_line}\n\n{stats_display}"
    embed.add_field(name="💥 Moves", value=moves_list or "No moves", inline=True)
    embed.add_field(
        name="📊 Info",
        value=(
            f"**Rarity Score:** {pokemon_data.get('rarity_score', 0)}\n"
            f"**EXP:** {pokemon_data.get('exp', 0)}\n"
            f"**Caught:** {time_str}"
        ),
        inline=True
    )

    if rarity == 'Divine':
        embed.set_footer(text="✨ DIVINE RARITY — OWNER EXCLUSIVE ✨")
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)

    return embed


# ─── Userdex Pages ────────────────────────────────────────────────────────────

USERS_PER_PAGE = 6

_RARITY_ORDER = ['Divine', 'Celestial', 'Mythic', 'Legendary', 'Epic', 'Rare', 'Common']

_RARITY_COLORS = {
    'Divine':    0xFFD700,
    'Celestial': 0xE0B0FF,
    'Mythic':    0xFF4444,
    'Legendary': 0xFFAA00,
    'Epic':      0xAA00FF,
    'Rare':      0x00AAFF,
    'Common':    0xAAAAAA,
}

_RARITY_BADGES = {
    'Divine':    '✨',
    'Celestial': '🌌',
    'Mythic':    '🔴',
    'Legendary': '🟡',
    'Epic':      '🟣',
    'Rare':      '🔵',
    'Common':    '⚪',
}


def _time_ago(iso_str: str) -> str:
    """Convert ISO timestamp to short relative time string."""
    if not iso_str:
        return "?"
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - dt
        if diff.days >= 365:
            return f"{diff.days // 365}y"
        if diff.days >= 30:
            return f"{diff.days // 30}mo"
        if diff.days > 0:
            return f"{diff.days}d"
        if diff.seconds >= 3600:
            return f"{diff.seconds // 3600}h"
        return f"{diff.seconds // 60}m"
    except Exception:
        return "?"


def format_userdex_pages(catches: list, target: discord.Member, bot) -> list:
    """
    Create clean, premium paginated userdex embeds.

    Each page shows up to USERS_PER_PAGE entries with:
      - Rarity badge + username
      - Type / Level / EXP bar
      - Compact stat summary
      - Caught time

    Args:
        catches: List of catch dicts (each must have 'caught_id', 'rarity', etc.)
        target:  User whose collection we're displaying
        bot:     Bot instance for user lookups

    Returns:
        List of discord.Embed pages
    """
    from utils.rarity_system import RARITY_TIERS

    if not catches:
        return []

    # ── Sort: rarity first, then level desc ───────────────────────────────────
    rarity_priority = {r: i for i, r in enumerate(_RARITY_ORDER)}
    catches.sort(
        key=lambda c: (
            rarity_priority.get(c.get('rarity', 'Common'), 99),
            -c.get('level', 1)
        )
    )

    # ── Aggregate stats ────────────────────────────────────────────────────────
    rarity_counts = {}
    total_power = 0
    for catch in catches:
        r = catch.get('rarity', 'Common')
        rarity_counts[r] = rarity_counts.get(r, 0) + 1
        st = catch.get('stats', {
            'hp': catch.get('hp', 0),
            'attack': catch.get('attack', 0),
            'defense': catch.get('defense', 0),
            'speed': catch.get('speed', 0)
        })
        total_power += st.get('hp', 0) + st.get('attack', 0) + st.get('defense', 0) + st.get('speed', 0)

    # ── Rarity summary bar ─────────────────────────────────────────────────────
    summary_parts = []
    for r in _RARITY_ORDER:
        if r in rarity_counts:
            badge = _RARITY_BADGES.get(r, '⚪')
            summary_parts.append(f"{badge} **{rarity_counts[r]}**")
    summary_line = "  ".join(summary_parts)

    # ── Dominant rarity colour for embed ──────────────────────────────────────
    dominant_rarity = next((r for r in _RARITY_ORDER if r in rarity_counts), 'Common')
    embed_color = _RARITY_COLORS.get(dominant_rarity, 0xAAAAAA)

    # ── Pagination ────────────────────────────────────────────────────────────
    total_pages = max(1, math.ceil(len(catches) / USERS_PER_PAGE))
    pages = []

    for page_num in range(total_pages):
        start = page_num * USERS_PER_PAGE
        end = start + USERS_PER_PAGE
        page_catches = catches[start:end]

        embed = discord.Embed(
            title=f"📖  {target.display_name}'s Collection",
            color=embed_color
        )

        # Header description
        embed.description = (
            f"**{len(catches)}** users caught  •  **{total_power:,}** total power\n"
            f"{summary_line}\n"
            f"{'─' * 34}"
        )

        # ── Per-catch entries ──────────────────────────────────────────────────
        for global_idx, catch in enumerate(page_catches, start + 1):
            caught_id = catch.get('caught_id', '0')
            # Use instance auto-id if available for uniqueness display
            instance_id = catch.get('id', catch.get('caught_id', '?'))

            caught_member = bot.get_user(int(caught_id)) if str(caught_id).isdigit() else None
            display_name = caught_member.display_name if caught_member else f"User#{caught_id}"

            rarity  = catch.get('rarity', 'Common')
            badge   = _RARITY_BADGES.get(rarity, '⚪')
            tier    = RARITY_TIERS.get(rarity, {})
            level   = catch.get('level', 1)
            exp     = catch.get('exp', 0)
            p_type  = catch.get('type', 'Normal')
            time_s  = _time_ago(catch.get('caught_at'))

            st = catch.get('stats', {
                'hp': catch.get('hp', 0),
                'attack': catch.get('attack', 0),
                'defense': catch.get('defense', 0),
                'speed': catch.get('speed', 0)
            })
            hp  = st.get('hp', 0)
            atk = st.get('attack', 0)
            def_ = st.get('defense', 0)
            spd = st.get('speed', 0)
            power = hp + atk + def_ + spd

            # EXP bar (max ~1000 EXP for level 100)
            exp_needed = level * 100
            exp_fill = min(8, int((exp / max(exp_needed, 1)) * 8))
            exp_bar = "▰" * exp_fill + "▱" * (8 - exp_fill)

            # Field: neat, cool and premium layout
            embed.add_field(
                name=f"`#{global_idx:02d}` {badge} **{display_name}** `[Card #{instance_id}]`",
                value=(
                    f"⭐ `Lv.{level}` │ `{rarity}` │ `{p_type}` │ Caught `{time_s} ago`\n"
                    f"❤️ `{hp}`  ⚔️ `{atk}`  🛡️ `{def_}`  ⚡ `{spd}`  •  **`{power}`** PWR\n"
                    f"EXP: `{exp_bar}` `{exp}/{exp_needed}`"
                ),
                inline=False
            )

        # ── Footer & thumbnail ─────────────────────────────────────────────────
        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)

        embed.set_footer(
            text=f"Page {page_num + 1} / {total_pages}  •  ◀ ▶ to navigate  •  ,inspect @user for full card",
            icon_url=target.display_avatar.url if target.display_avatar else None
        )
        pages.append(embed)

    return pages


# ─── Backward-compatible wrapper ─────────────────────────────────────────────

def format_userdex_display(catches: list, target: discord.Member, bot) -> discord.Embed:
    """Returns first page. Use format_userdex_pages() for full pagination."""
    pages = format_userdex_pages(catches, target, bot)
    return pages[0] if pages else discord.Embed(title="Empty Userdex", color=0xFFD700)
