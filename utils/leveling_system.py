"""
Pokemon Leveling System
Handles EXP, level-ups, and stat progression
"""
import random

# Level requirements (EXP needed to reach each level)
def exp_for_level(level: int) -> int:
    """Calculate EXP required to reach a level"""
    # Formula: level^3 for exponential growth
    return level ** 3

def calculate_level(exp: int) -> int:
    """Calculate level from total EXP"""
    level = 1
    while level < 100:  # Max level 100
        if exp < exp_for_level(level + 1):
            break
        level += 1
    return level

def exp_to_next_level(current_exp: int, current_level: int) -> int:
    """Calculate EXP needed for next level"""
    if current_level >= 100:
        return 0
    return exp_for_level(current_level + 1) - current_exp

def award_exp(pokemon_data: dict, exp_gained: int) -> dict:
    """
    Award EXP to a Pokemon and handle level-ups
    
    Args:
        pokemon_data: Pokemon dictionary with stats
        exp_gained: Amount of EXP to award
    
    Returns:
        dict with 'leveled_up' (bool), 'new_level' (int), 'stat_gains' (dict)
    """
    # Normalize: ensure 'stats' dict exists (DB returns flat keys like 'hp', 'attack')
    if 'stats' not in pokemon_data:
        pokemon_data['stats'] = {
            'hp': pokemon_data.get('hp', 100),
            'attack': pokemon_data.get('attack', 50),
            'defense': pokemon_data.get('defense', 50),
            'speed': pokemon_data.get('speed', 50),
        }
    
    old_exp = pokemon_data.get('exp', 0)
    old_level = pokemon_data.get('level', 1)
    
    # Add EXP
    new_exp = old_exp + exp_gained
    pokemon_data['exp'] = new_exp
    
    # Calculate new level
    new_level = calculate_level(new_exp)
    
    result = {
        'leveled_up': new_level > old_level,
        'new_level': new_level,
        'old_level': old_level,
        'stat_gains': {}
    }
    
    # Handle level-ups
    if new_level > old_level:
        pokemon_data['level'] = new_level
        
        # Calculate stat gains (5-10 per stat per level)
        levels_gained = new_level - old_level
        
        for stat in ['hp', 'attack', 'defense', 'speed']:
            old_stat = pokemon_data['stats'][stat]
            gain_per_level = random.randint(5, 10)
            total_gain = gain_per_level * levels_gained
            pokemon_data['stats'][stat] = old_stat + total_gain
            result['stat_gains'][stat] = total_gain
    
    # Sync stats dict back to flat keys so _save_catch() picks them up
    for stat in ['hp', 'attack', 'defense', 'speed']:
        pokemon_data[stat] = pokemon_data['stats'][stat]
    
    return result

def get_battle_exp_reward(winner_level: int, loser_level: int) -> int:
    """
    Calculate EXP reward for winning a battle
    
    Args:
        winner_level: Winner's Pokemon level
        loser_level: Loser's Pokemon level
    
    Returns:
        EXP amount (50-100 base, scaled by level difference)
    """
    base_exp = random.randint(50, 100)
    
    # Bonus for defeating higher level opponents
    level_diff = loser_level - winner_level
    if level_diff > 0:
        bonus = level_diff * 10
        base_exp += bonus
    
    return max(base_exp, 30)  # Minimum 30 EXP

def get_training_exp_reward() -> int:
    """Get EXP reward for training (lower than battles)"""
    return random.randint(10, 30)
