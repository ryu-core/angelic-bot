"""
Rarity System for Catch
Classifies caught users into rarity tiers based on legitimate account metrics
Prevents exploitation through alt accounts and fake servers
"""
import discord
from datetime import datetime, timezone

# Rarity tiers with stat multipliers
RARITY_TIERS = {
    'Common': {
        'multiplier': 1.0,
        'emoji': '⚪',
        'color': 0x95a5a6,  # Gray
        'min_score': 0
    },
    'Rare': {
        'multiplier': 1.2,
        'emoji': '🟢',
        'color': 0x2ecc71,  # Green
        'min_score': 100
    },
    'Epic': {
        'multiplier': 1.4,
        'emoji': '🟣',
        'color': 0x9b59b6,  # Purple
        'min_score': 250
    },
    'Legendary': {
        'multiplier': 1.6,
        'emoji': '🟡',
        'color': 0xf1c40f,  # Gold
        'min_score': 500
    },
    'Mythic': {
        'multiplier': 1.8,
        'emoji': '🔴',
        'color': 0xe91e63,  # Pink/Red
        'min_score': 1000
    },
    'Celestial': {
        'multiplier': 2.2,
        'emoji': '🌙',
        'color': 0x7B68EE,  # Medium Slate Blue
        'min_score': 999998  # Co-owner only
    },
    'Divine': {
        'multiplier': 2.5,
        'emoji': '✨',
        'color': 0xFFD700,  # Bright Gold
        'min_score': 999999  # Impossible to reach - owner only
    }
}

def calculate_rarity_score(member: discord.Member) -> int:
    """
    Calculate rarity score based on legitimate account metrics
    Prevents exploitation through alt accounts and fake servers
    
    Scoring factors:
    - Account age (older = rarer)
    - Server count (more mutual servers = rarer)
    - Verification status (verified = bonus)
    - Nitro status (nitro = bonus)
    - Activity indicators (custom status, avatar, banner)
    
    Args:
        member: Discord member object
    
    Returns:
        Rarity score (0-1000+)
    """
    score = 0
    
    # 1. Account Age (0-400 points)
    # Older accounts are harder to fake
    account_age_days = (datetime.now(timezone.utc) - member.created_at).days
    if account_age_days >= 730:  # 2+ years
        score += 400
    elif account_age_days >= 365:  # 1+ year
        score += 300
    elif account_age_days >= 180:  # 6+ months
        score += 200
    elif account_age_days >= 90:  # 3+ months
        score += 100
    elif account_age_days >= 30:  # 1+ month
        score += 50
    # New accounts (<30 days) get 0 points
    
    # 2. Server Membership Duration (0-200 points)
    # How long they've been in THIS server
    if member.joined_at:
        join_age_days = (datetime.now(timezone.utc) - member.joined_at).days
        if join_age_days >= 365:  # 1+ year in server
            score += 200
        elif join_age_days >= 180:  # 6+ months
            score += 150
        elif join_age_days >= 90:  # 3+ months
            score += 100
        elif join_age_days >= 30:  # 1+ month
            score += 50
    
    # 3. Mutual Server Count (0-150 points)
    # More mutual servers = more legitimate
    # Note: This requires the bot to check mutual guilds
    try:
        mutual_guilds = len([g for g in member.mutual_guilds if g.member_count > 10])
        if mutual_guilds >= 20:
            score += 150
        elif mutual_guilds >= 10:
            score += 100
        elif mutual_guilds >= 5:
            score += 50
        elif mutual_guilds >= 2:
            score += 25
    except:
        pass  # If mutual_guilds not available
    
    # 4. Verification Status (0-100 points)
    # System verified badge (not server verification)
    if member.public_flags.verified_bot_developer:
        score += 100
    elif member.public_flags.early_supporter:
        score += 75
    elif member.public_flags.partner:
        score += 100
    elif member.public_flags.staff:
        score += 100
    
    # 5. Nitro Status (0-100 points)
    # Nitro users are more invested in Discord
    if member.premium_since:  # Server booster
        score += 100
    elif member.avatar and member.avatar.is_animated():  # Animated avatar = Nitro
        score += 75
    elif member.banner:  # Banner = Nitro
        score += 75
    
    # 6. Activity Indicators (0-100 points)
    # Custom avatar (not default)
    if member.avatar:
        score += 30
    
    # Custom status or activity
    if member.activity or member.activities:
        score += 20
    
    # Has roles in server (shows engagement)
    non_everyone_roles = [r for r in member.roles if r.name != '@everyone']
    if len(non_everyone_roles) >= 5:
        score += 50
    elif len(non_everyone_roles) >= 3:
        score += 30
    elif len(non_everyone_roles) >= 1:
        score += 10
    
    # 7. Anti-Bot Detection (-500 points)
    # Penalize obvious bot-like patterns
    if member.bot:
        score -= 500  # Bots can't be caught anyway, but just in case
    
    # Suspicious username patterns (all numbers, very short, etc.)
    if member.name.isdigit() or len(member.name) <= 3:
        score -= 50
    
    return max(0, score)  # Ensure non-negative

def get_rarity_from_member(member: discord.Member) -> str:
    """
    Determine rarity tier based on member's rarity score
    Bot owners automatically get Divine rarity
    
    Args:
        member: Discord member object
    
    Returns:
        Rarity tier name (Common, Rare, Epic, Legendary, Mythic, Divine)
    """
    # Import config to check owner IDs
    import config
    
    # Bot owners always get Divine rarity
    if member.id in config.OWNER_IDS:
        return 'Divine'
    
    # Co-owners get Celestial rarity
    if member.id in config.CO_OWNER_IDS:
        return 'Celestial'
    
    score = calculate_rarity_score(member)
    
    # Determine rarity based on score thresholds
    if score >= RARITY_TIERS['Mythic']['min_score']:
        return 'Mythic'
    elif score >= RARITY_TIERS['Legendary']['min_score']:
        return 'Legendary'
    elif score >= RARITY_TIERS['Epic']['min_score']:
        return 'Epic'
    elif score >= RARITY_TIERS['Rare']['min_score']:
        return 'Rare'
    else:
        return 'Common'

def get_rarity_info(rarity: str) -> dict:
    """Get rarity tier information"""
    return RARITY_TIERS.get(rarity, RARITY_TIERS['Common'])

def calculate_stats(base_hp: int, base_attack: int, base_defense: int, base_speed: int, rarity: str) -> dict:
    """
    Calculate final stats based on rarity multiplier
    
    Args:
        base_hp: Base HP value
        base_attack: Base attack value
        base_defense: Base defense value
        base_speed: Base speed value
        rarity: Rarity tier name
    
    Returns:
        Dictionary with final stats
    """
    multiplier = RARITY_TIERS.get(rarity, RARITY_TIERS['Common'])['multiplier']
    
    return {
        'hp': int(base_hp * multiplier),
        'attack': int(base_attack * multiplier),
        'defense': int(base_defense * multiplier),
        'speed': int(base_speed * multiplier)
    }

