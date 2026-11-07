"""Side-effect-free application configuration.

This module may be imported by cogs, utilities, tests, and the executable entry
point without constructing a Discord client or running application startup.
"""

import os

from dotenv import load_dotenv


load_dotenv()


def _parse_id_list(name):
    """Parse a comma-separated environment variable into valid integer IDs."""
    result = []
    for raw_value in os.getenv(name, '').split(','):
        value = raw_value.strip()
        if value.isdigit():
            result.append(int(value))
    return result


TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('PREFIX', ',')

OWNER_IDS = _parse_id_list('OWNER_IDS')
CO_OWNER_IDS = [
    co_owner_id
    for co_owner_id in _parse_id_list('CO_OWNER_IDS')
    if co_owner_id not in OWNER_IDS
]

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
SERPER_API_KEY = os.getenv('SERPER_API_KEY')

COLORS = {
    'primary': int(os.getenv('PRIMARY_COLOR', '0x9b59b6'), 16),
    'secondary': int(os.getenv('SECONDARY_COLOR', '0x3498db'), 16),
    'success': int(os.getenv('SUCCESS_COLOR', '0x2ecc71'), 16),
    'error': int(os.getenv('ERROR_COLOR', '0xe74c3c'), 16),
    'warning': int(os.getenv('WARNING_COLOR', '0xf39c12'), 16),
}

EMOJIS = {
    'success': '<:check:1470801900705419417>',
    'error': '<:cross:1470801974948794409>',
    'warning': '<:warn:1470802511865581579>',
    'loading': '<:loading:1470802096050802698>',
    'info': '<:info:1470802169903976479>',
    'ban': '<:ban:1470802583219077273>',
    'kick': '<:kick:1470802648897818761>',
    'mute': '<:mute:1470802745165349150>',
    'lock': '<:lock:1470802824928690237>',
    'unlock': '<:unlock:1470794585252036729>',
    'jail': '<:jail:1470802942742364363>',
    'shield': '<:shield:1470803015891026024>',
    'search': '<:search:1470803174884376679>',
    'clock': '<:clock:1470803263216550071>',
    'pin': '<:pin:1470803374831308871>',
    'log': '<:log:1470803471333855445>',
    'settings': '<:settings:1470803557182869567>',
    'game': '<:game:1470803841569259756>',
    'chat': '<:game:1470803841569259756>',
    'crown': '<:crown:1470803758039695420>',
    'gem': '<:gem:1470803642318717105>',
    'quote': '<:quote:1470804032263028859>',
    'role': '<:settings:1470803557182869567>',
    'mine': '<:game:1470803841569259756>',
    'sleep': '<:SleepyFurina:1470801292334203004>',
}

RATE_LIMITS = {
    'chatgpt': 3,
    'commands': 5,
}

ECONOMY = {
    'currency_name': 'Gems',
    'currency_emoji': '<:gem:1470803642318717105>',
    'starting_balance': 1000,
    'daily_reward': (500, 1000),
    'weekly_reward': 5000,
    'work_reward': (100, 300),
    'crime_reward': (1000, 5000),
    'crime_penalty': (500, 2000),
    'bank_limit': 100000,
    'max_bet': 500000,
}

ECONOMY_EMOJIS = {
    'gem': '<:gem:1470803642318717105>',
    'coin': '<:gem:1470803642318717105>',
    'wallet': '<:gem:1470803642318717105>',
    'bank': '<:lock:1470802824928690237>',
    'up': '<:check:1470801900705419417>',
    'down': '<:cross:1470801974948794409>',
    'slot': '<:game:1470803841569259756>',
    'dice': '<:game:1470803841569259756>',
    'cards': '<:game:1470803841569259756>',
    'fire': '<:crown:1470803758039695420>',
    'star': '<:crown:1470803758039695420>',
    'first': '<:crown:1470803758039695420>',
    'second': '<:gem:1470803642318717105>',
    'third': '<:shield:1470803015891026024>',
}

__all__ = [
    'TOKEN', 'PREFIX', 'OWNER_IDS', 'CO_OWNER_IDS',
    'OPENAI_API_KEY', 'GOOGLE_API_KEY', 'GOOGLE_SEARCH_ENGINE_ID', 'SERPER_API_KEY',
    'COLORS', 'EMOJIS', 'RATE_LIMITS', 'ECONOMY', 'ECONOMY_EMOJIS',
]
