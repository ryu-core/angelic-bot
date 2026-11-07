# Shop Items Configuration and Effects System
from datetime import datetime, timedelta

# Unique Shop Items Catalog
SHOP_ITEMS = {
    'multiplier_boost': {
        'item_id': 'multiplier_boost',
        'item_name': 'Multiplier Boost',
        'description': '1.25x winnings for next game',
        'price': 10000,
        'emoji': '⚡',
        'item_type': 'booster',
        'effect_type': 'multiplier',
        'effect_value': 1.25,
        'effect_duration': 1,  # 1 game
        'stackable': False
    },
    'rob_shield': {
        'item_id': 'rob_shield',
        'item_name': 'Rob Shield',
        'description': 'Protects from robbery for 24 hours',
        'price': 10000,
        'emoji': '🛡️',
        'item_type': 'consumable',
        'effect_type': 'rob_protection',
        'effect_value': 1,
        'effect_duration': 86400,  # 24 hours in seconds
        'stackable': False
    },
    'bank_note': {
        'item_id': 'bank_note',
        'item_name': 'Bank Note',
        'description': 'Increases bank limit by 50,000',
        'price': 25000,
        'emoji': '📜',
        'item_type': 'consumable',
        'effect_type': 'bank_expansion',
        'effect_value': 50000,
        'effect_duration': -1,  # Permanent
        'stackable': True
    },
    'gem_magnet': {
        'item_id': 'gem_magnet',
        'item_name': 'Gem Magnet',
        'description': '+20% daily/weekly rewards for 7 days',
        'price': 20000,
        'emoji': '🧲',
        'item_type': 'booster',
        'effect_type': 'reward_boost',
        'effect_value': 0.20,  # 20% boost
        'effect_duration': 604800,  # 7 days in seconds
        'stackable': False
    },
    'loaded_dice': {
        'item_id': 'loaded_dice',
        'item_name': 'Loaded Dice',
        'description': 'Guarantees dice win on common roll (7) — single use',
        'price': 25000,
        'emoji': '🎲',
        'item_type': 'consumable',
        'effect_type': 'dice_guarantee',
        'effect_value': 1,
        'effect_duration': 1,  # 1 game
        'stackable': False
    },
    'card_counter': {
        'item_id': 'card_counter',
        'item_name': 'Card Counter',
        'description': "Shows dealer's hidden card in blackjack",
        'price': 15000,
        'emoji': '🃏',
        'item_type': 'consumable',
        'effect_type': 'blackjack_peek',
        'effect_value': 1,
        'effect_duration': 1,  # 1 game
        'stackable': False
    },
    'slot_hack': {
        'item_id': 'slot_hack',
        'item_name': 'Slot Hack',
        'description': 'Reroll slots once per game',
        'price': 12000,
        'emoji': '💻',
        'item_type': 'consumable',
        'effect_type': 'slot_reroll',
        'effect_value': 1,
        'effect_duration': 1,  # 1 game
        'stackable': False
    },
    'double_down': {
        'item_id': 'double_down',
        'item_name': 'Double Down',
        'description': '2x winnings but also 2x losses (3 games)',
        'price': 12000,
        'emoji': '🎯',
        'item_type': 'booster',
        'effect_type': 'double_stakes',
        'effect_value': 2.0,
        'effect_duration': 3,  # 3 games
        'stackable': False
    },
    'safety_net': {
        'item_id': 'safety_net',
        'item_name': 'Safety Net',
        'description': 'Refund 30% of losses for next 3 games',
        'price': 15000,
        'emoji': '🪂',
        'item_type': 'booster',
        'effect_type': 'loss_protection',
        'effect_value': 0.30,  # 30% refund
        'effect_duration': 3,  # 3 games
        'stackable': False
    }
}

def get_all_items():
    """Get all shop items"""
    return SHOP_ITEMS

def get_item(item_id):
    """Get specific item by ID"""
    return SHOP_ITEMS.get(item_id)

def get_item_by_name(item_name):
    """Get item by name (case-insensitive)"""
    item_name_lower = item_name.lower().replace(' ', '_')
    
    for item_id, item_data in SHOP_ITEMS.items():
        if item_id == item_name_lower or item_data['item_name'].lower() == item_name.lower():
            return item_data
    
    return None

def initialize_shop_items(economy_db, guild_id):
    """Initialize shop with default items for a guild"""
    try:
        timestamp = int(datetime.now().timestamp())

        for item_id, item_data in SHOP_ITEMS.items():
            economy_db._exec("""
                INSERT IGNORE INTO economy_shop
                (guild_id, item_id, item_name, description, price, emoji, item_type, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                guild_id,
                item_data['item_id'],
                item_data['item_name'],
                item_data['description'],
                item_data['price'],
                item_data['emoji'],
                item_data['item_type'],
                timestamp
            ), commit=True)

        return True

    except Exception as e:
        print(f"Error initializing shop items: {e}")
        return False

