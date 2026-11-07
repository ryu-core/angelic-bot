# Premium Economy Embeds with Animations
import discord
from config import COLORS, EMOJIS
from datetime import timedelta

# Premium Emoji Set for Economy
ECONOMY_EMOJIS = {
    # Currency
    'gem': '💎',
    'coin': '💰',
    'money_bag': '💵',
    'bank': '🏦',
    'wallet': '👛',
    
    # Status & Progress
    'success': '✨',
    'fail': '💥',
    'warning': '⚠️',
    'info': 'ℹ️',
    'loading': '⏳',
    'streak': '⚡',
    'fire': '🔥',
    'star': '⭐',
    'clock': '🕐',
    
    # Games
    'slots': '🎰',
    'dice': '🎲',
    'cards': '🃏',
    'target': '🎯',
    'rocket': '🚀',
    'wheel': '🎡',
    
    # Items & Rarity
    'shield': '🛡️',
    'sword': '⚔️',
    'potion': '🧪',
    'crown': '👑',
    'legendary': '🌟',
    'epic': '💫',
    'rare': '⭐',
    'common': '🔸',
    
    # Arrows & Direction
    'up': '📈',
    'down': '📉',
    'right': '➡️',
    'rising': '↗️',
    'falling': '↘️',
    
    # Medals
    'first': '🥇',
    'second': '🥈',
    'third': '🥉',
    
    # Work & Daily
    'work': '⚒️',
    'daily': '📅',
    'weekly': '📆',
    'gift': '🎁',
}

# Rarity Colors
RARITY_COLORS = {
    'legendary': 0xFFD700,  # Gold
    'epic': 0x9b59b6,       # Purple
    'rare': 0x3498db,       # Blue
    'common': 0x95a5a6,     # Gray
}

def format_currency(amount, emoji='💎'):
    """Format currency with commas and emoji"""
    return f"{emoji} **{amount:,}**"

def create_progress_bar(current, maximum, length=10, filled='▰', empty='▱'):
    """Create an animated progress bar"""
    if maximum == 0:
        percentage = 0
    else:
        percentage = current / maximum
    
    filled_length = int(length * percentage)
    bar = filled * filled_length + empty * (length - filled_length)
    percent = int(percentage * 100)
    
    return f"{bar} {percent}%"

def format_time(seconds):
    """Format seconds into readable time"""
    if seconds <= 0:
        return "Ready!"
    
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 and days == 0:
        parts.append(f"{secs}s")
    
    return " ".join(parts)

def create_economy_embed(title, description="", color=None, user=None):
    """Create a premium economy embed"""
    if color is None:
        color = COLORS['primary']
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )
    
    if user:
        embed.set_footer(text=f"Requested by {user.name}", icon_url=user.display_avatar.url)
    
    return embed

def balance_embed(user, wallet, bank, total, bank_limit=100000):
    """Create balance display embed"""
    embed = create_economy_embed(
        title=f"{ECONOMY_EMOJIS['wallet']} {user.name}'s Balance",
        color=COLORS['primary'],
        user=user
    )
    
    embed.add_field(
        name=f"{ECONOMY_EMOJIS['money_bag']} Wallet",
        value=format_currency(wallet),
        inline=True
    )
    
    embed.add_field(
        name=f"{ECONOMY_EMOJIS['bank']} Bank",
        value=format_currency(bank),
        inline=True
    )
    
    embed.add_field(
        name=f"{ECONOMY_EMOJIS['gem']} Net Worth",
        value=format_currency(total),
        inline=True
    )
    
    # Add progress bar for bank capacity
    bank_progress = create_progress_bar(bank, bank_limit)
    embed.add_field(
        name=f"{ECONOMY_EMOJIS['shield']} Bank Capacity",
        value=f"{bank_progress}\n{format_currency(bank)}/{format_currency(bank_limit)}",
        inline=False
    )
    
    embed.set_thumbnail(url=user.display_avatar.url)
    
    return embed

def daily_embed(user, amount, streak):
    """Create daily reward embed"""
    embed = create_economy_embed(
        title=f"{ECONOMY_EMOJIS['gift']} Daily Reward Claimed!",
        description=f"{ECONOMY_EMOJIS['success']} You received {format_currency(amount)}",
        color=COLORS['success'],
        user=user
    )
    
    if streak > 1:
        embed.add_field(
            name=f"{ECONOMY_EMOJIS['streak']} Streak Bonus",
            value=f"**{streak}** day streak! {ECONOMY_EMOJIS['fire']}",
            inline=False
        )
    
    embed.set_thumbnail(url="https://em-content.zobj.net/thumbs/120/twitter/322/gift_1f381.png")
    
    return embed

def cooldown_embed(cooldown_type, remaining_seconds):
    """Create cooldown notification embed"""
    emoji_map = {
        'daily': ECONOMY_EMOJIS['daily'],
        'weekly': ECONOMY_EMOJIS['weekly'],
        'work': ECONOMY_EMOJIS['work'],
        'crime': ECONOMY_EMOJIS['warning'],
        'rob': ECONOMY_EMOJIS['shield'],
        'slots': ECONOMY_EMOJIS['slots'],
        'coinflip': ECONOMY_EMOJIS['coin'],
        'blackjack': ECONOMY_EMOJIS['cards'],
        'dice': ECONOMY_EMOJIS['dice'],
        'roulette': ECONOMY_EMOJIS['wheel']
    }
    
    emoji = emoji_map.get(cooldown_type, ECONOMY_EMOJIS['loading'])
    
    embed = create_economy_embed(
        title=f"{ECONOMY_EMOJIS['loading']} Cooldown Active",
        description=f"{emoji} You already used `{cooldown_type}` recently!\n\n{ECONOMY_EMOJIS['info']} Try again in: **{format_time(remaining_seconds)}**",
        color=COLORS['error']
    )
    
    return embed

def work_embed(user, amount, job_name):
    """Create work reward embed"""
    embed = create_economy_embed(
        title=f"{ECONOMY_EMOJIS['work']} Work Complete!",
        description=f"You worked as a **{job_name}** and earned {format_currency(amount)}",
        color=COLORS['success'],
        user=user
    )
    
    return embed

def shop_embed(items, page=1, total_pages=1):
    """Create shop display embed"""
    embed = create_economy_embed(
        title=f"{ECONOMY_EMOJIS['gem']} Economy Shop",
        description=f"Browse available items below\nPage {page}/{total_pages}",
        color=COLORS['primary']
    )
    
    for item in items:
        rarity_emoji = ECONOMY_EMOJIS.get(item.get('item_type', 'common'), '🔸')
        embed.add_field(
            name=f"{item.get('emoji', '💎')} {item['item_name']}",
            value=f"{item.get('description', 'No description')}\n{ECONOMY_EMOJIS['coin']} Price: **{item['price']:,}**",
            inline=True
        )
    
    embed.set_footer(text=f"Use ,buy <item_name> to purchase")
    
    return embed

def inventory_embed(user, items):
    """Create inventory display embed"""
    embed = create_economy_embed(
        title=f"{ECONOMY_EMOJIS['shield']} {user.name}'s Inventory",
        color=COLORS['primary'],
        user=user
    )
    
    if not items:
        embed.description = f"{ECONOMY_EMOJIS['info']} Your inventory is empty!\nVisit the shop with `,shop`"
        return embed
    
    for item in items[:25]:  # Discord limit: 25 fields
        embed.add_field(
            name=f"{item.get('emoji', '💎')} {item['item_name']} x{item['quantity']}",
            value=f"{item.get('description', 'No description')[:50]}...",
            inline=True
        )
    
    return embed

def leaderboard_embed(guild, top_users):
    """Create leaderboard embed with podium"""
    embed = create_economy_embed(
        title=f"{ECONOMY_EMOJIS['crown']} Economy Leaderboard",
        description=f"Top richest members in **{guild.name}**",
        color=RARITY_COLORS['legendary']
    )
    
    medals = [ECONOMY_EMOJIS['first'], ECONOMY_EMOJIS['second'], ECONOMY_EMOJIS['third']]
    
    leaderboard_text = ""
    for idx, user_data in enumerate(top_users, 1):
        medal = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
        total = user_data['total']
        user_id = user_data['user_id']
        
        leaderboard_text += f"{medal} <@{user_id}> • {format_currency(total)}\n"
    
    embed.description += f"\n\n{leaderboard_text}"
    
    return embed

def game_win_embed(game_name, bet, winnings, multiplier):
    """Create game win embed"""
    profit = winnings - bet
    
    embed = create_economy_embed(
        title=f"{ECONOMY_EMOJIS['success']} You Won!",
        description=f"**{game_name}** • Multiplier: **{multiplier}x**",
        color=COLORS['success']
    )
    
    embed.add_field(name="Bet", value=format_currency(bet), inline=True)
    embed.add_field(name="Winnings", value=format_currency(winnings), inline=True)
    embed.add_field(name="Profit", value=f"{ECONOMY_EMOJIS['up']} {format_currency(profit)}", inline=True)
    
    return embed

def game_loss_embed(game_name, bet):
    """Create game loss embed"""
    embed = create_economy_embed(
        title=f"{ECONOMY_EMOJIS['fail']} You Lost!",
        description=f"**{game_name}**",
        color=COLORS['error']
    )
    
    embed.add_field(name="Lost", value=f"{ECONOMY_EMOJIS['down']} {format_currency(bet)}", inline=False)
    
    return embed

def transfer_embed(sender, receiver, amount):
    """Create transfer confirmation embed"""
    embed = create_economy_embed(
        title=f"{ECONOMY_EMOJIS['success']} Transfer Complete",
        description=f"{sender.mention} sent {format_currency(amount)} to {receiver.mention}",
        color=COLORS['success']
    )
    
    return embed
