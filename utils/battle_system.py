"""
Battle System for Catch
Turn-based 3v3 battles with dramatic visuals and fast-paced combat
"""
import discord
from discord.ui import Button, View, Select
import random
import asyncio
from typing import Dict, List, Optional
import config

# Type advantages (attacker -> defender)
TYPE_ADVANTAGES = {
    'Fire': ['Grass', 'Ice', 'Steel'],
    'Water': ['Fire', 'Ground', 'Rock'],
    'Grass': ['Water', 'Ground', 'Rock'],
    'Electric': ['Water', 'Flying'],
    'Psychic': ['Fighting', 'Poison'],
    'Dark': ['Psychic', 'Ghost'],
    'Ghost': ['Psychic', 'Ghost'],
    'Dragon': ['Dragon'],
    'Fairy': ['Fighting', 'Dragon', 'Dark'],
    'Ice': ['Grass', 'Ground', 'Flying', 'Dragon'],
    'Fighting': ['Normal', 'Ice', 'Rock', 'Dark', 'Steel'],
    'Poison': ['Grass', 'Fairy'],
    'Steel': ['Ice', 'Rock', 'Fairy'],
    'Ground': ['Fire', 'Electric', 'Poison', 'Rock', 'Steel'],
    'Rock': ['Fire', 'Ice', 'Flying'],
    'Flying': ['Grass', 'Fighting'],
}

# Moves for each type (4 moves per type)
TYPE_MOVES = {
    'Fire': ['Flamethrower', 'Fire Blast', 'Ember', 'Heat Wave'],
    'Water': ['Hydro Pump', 'Surf', 'Water Gun', 'Aqua Tail'],
    'Grass': ['Solar Beam', 'Leaf Blade', 'Vine Whip', 'Energy Ball'],
    'Electric': ['Thunderbolt', 'Thunder', 'Shock Wave', 'Volt Tackle'],
    'Psychic': ['Psychic', 'Psybeam', 'Confusion', 'Future Sight'],
    'Dark': ['Dark Pulse', 'Night Slash', 'Crunch', 'Foul Play'],
    'Ghost': ['Shadow Ball', 'Hex', 'Lick', 'Phantom Force'],
    'Dragon': ['Dragon Claw', 'Outrage', 'Dragon Pulse', 'Draco Meteor'],
    'Fairy': ['Moonblast', 'Dazzling Gleam', 'Play Rough', 'Disarming Voice'],
    'Ice': ['Ice Beam', 'Blizzard', 'Ice Shard', 'Freeze Shock'],
    'Fighting': ['Close Combat', 'Brick Break', 'Karate Chop', 'Focus Blast'],
    'Poison': ['Sludge Bomb', 'Poison Jab', 'Toxic', 'Venoshock'],
    'Steel': ['Iron Head', 'Flash Cannon', 'Metal Claw', 'Steel Beam'],
    'Ground': ['Earthquake', 'Earth Power', 'Dig', 'Mud Shot'],
    'Rock': ['Rock Slide', 'Stone Edge', 'Rock Throw', 'Power Gem'],
    'Flying': ['Air Slash', 'Brave Bird', 'Wing Attack', 'Hurricane'],
}

# Divine moves (owner-exclusive)
DIVINE_MOVES = ['Divine Wrath', 'Celestial Strike', 'Omega Beam', "God's Judgment"]

# Celestial moves (co-owner-exclusive)
CELESTIAL_MOVES = ['Lunar Eclipse', 'Starfall Barrage', 'Void Rift', 'Cosmic Judgment']

# ═══ Type emoji mapping ═══
TYPE_EMOJIS = {
    'Fire': '🔥', 'Water': '💧', 'Grass': '🌿', 'Electric': '⚡',
    'Psychic': '🔮', 'Dark': '🌑', 'Ghost': '👻', 'Dragon': '🐉',
    'Fairy': '✨', 'Ice': '❄️', 'Fighting': '🥊', 'Poison': '☠️',
    'Steel': '⚙️', 'Ground': '🌍', 'Rock': '🪨', 'Flying': '🦅',
    'Normal': '⭐',
}

# ═══ Dramatic hit flavor text ═══
CRIT_FLAVOR = [
    "💥 **CRITICAL HIT!** The blow is devastating!",
    "⚡ **CRITICAL!** A bone-crushing strike!",
    "🔥 **CRITICAL HIT!** Pure destruction!",
    "💀 **CRITICAL!** An earth-shattering impact!",
]

ATTACK_FLAVOR = [
    "The attack lands cleanly!",
    "A solid hit!",
    "The strike connects!",
    "Direct hit!",
    "Right on target!",
]

DODGE_FLAVOR = [
    "🌀 **DODGED!** They saw it coming and evaded!",
    "💨 **MISS!** The target vanished at the last second!",
    "🛡️ **EVADED!** Quick reflexes saved the day!",
]

SUPER_EFFECTIVE = [
    "⚡ **Super effective!** The arena shakes!",
    "💥 **Super effective!** A massive blow!",
    "🔥 **Super effective!** Devastating damage!",
]

NOT_EFFECTIVE = [
    "🛡️ Not very effective... the attack barely scratches!",
    "💫 Not very effective... they shrug it off!",
]

FAINT_FLAVOR = [
    "💀 **{name}** crumbles to the ground... **FAINTED!**",
    "☠️ **{name}** can't take anymore... **DOWN!**",
    "💫 **{name}** collapses! **OUT OF THE FIGHT!**",
]


def create_health_bar(current_hp: int, max_hp: int, length: int = 10) -> str:
    """Create a sleek ASCII health bar"""
    percentage = current_hp / max_hp if max_hp > 0 else 0
    filled = int(length * percentage)
    empty = length - filled

    if percentage > 0.5:
        fill = '▰'
    elif percentage > 0.2:
        fill = '▰'
    else:
        fill = '▰'

    bar = f"`{fill * filled}{'▱' * empty}` {current_hp}/{max_hp}"

    if percentage > 0.5:
        return f"💚 {bar}"
    elif percentage > 0.2:
        return f"💛 {bar}"
    else:
        return f"❤️ {bar}"


def create_stat_bar(value: int, max_val: int = 999, length: int = 8) -> str:
    """Create a compact stat bar for cards"""
    filled = max(1, int(length * (value / max_val)))
    empty = length - filled
    return f"{'█' * filled}{'░' * empty} {value}"


def create_team_status(team: list) -> str:
    """Show alive/fainted status of full team"""
    icons = []
    for p in team:
        if p['current_hp'] > 0:
            icons.append('🟢')
        else:
            icons.append('🔴')
    return ''.join(icons)


def calculate_damage(attacker: dict, defender: dict, move_power: int) -> tuple:
    """Calculate damage with crits, dodges, and type advantages"""
    # Dodge chance (5%)
    if random.random() < 0.05:
        return 0, 1.0, 'dodge'

    # Increased damage formula for shorter battles (~4-6 turns)
    base_damage = (attacker['attack'] * move_power * 8) / defender['defense']

    # Type advantage multiplier
    multiplier = 1.0
    attacker_type = attacker.get('type', 'Normal')
    defender_type = defender.get('type', 'Normal')

    if defender_type in TYPE_ADVANTAGES.get(attacker_type, []):
        multiplier = 1.5
    elif attacker_type in TYPE_ADVANTAGES.get(defender_type, []):
        multiplier = 0.5

    # Critical hit (10% chance, 2x damage)
    is_crit = random.random() < 0.10
    crit_mult = 2.0 if is_crit else 1.0

    # Random variance (0.85 - 1.0)
    variance = random.uniform(0.85, 1.0)

    final_damage = int(base_damage * multiplier * crit_mult * variance)
    hit_type = 'crit' if is_crit else 'normal'
    return max(1, final_damage), multiplier, hit_type


class BattleView(View):
    """Interactive battle view with dynamic buttons (no static custom_id)"""

    def __init__(self, battle_state: 'BattleState', timeout=180):
        super().__init__(timeout=timeout)
        self.battle_state = battle_state
        self._build_buttons()

    def _build_buttons(self):
        """Build move buttons for the current player"""
        self.clear_items()

        current = self.battle_state.get_current_pokemon()
        if not current:
            return

        # Move buttons — styled by move position
        moves = current.get('moves', [])
        styles = [
            discord.ButtonStyle.primary,
            discord.ButtonStyle.primary,
            discord.ButtonStyle.success,
            discord.ButtonStyle.success,
        ]

        for i, move in enumerate(moves[:4]):
            btn = Button(
                label=f"⚔️ {move}",
                style=styles[i],
                row=0 if i < 2 else 1
            )
            btn.callback = self._make_move_cb(i)
            self.add_item(btn)

        # Switch button
        switch_btn = Button(label="🔄 Switch", style=discord.ButtonStyle.secondary, row=2)
        switch_btn.callback = self._switch_cb
        self.add_item(switch_btn)

        # Flee button
        flee_btn = Button(label="🏃 Flee", style=discord.ButtonStyle.danger, row=2)
        flee_btn.callback = self._flee_cb
        self.add_item(flee_btn)

    def _make_move_cb(self, move_index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.battle_state.current_turn_user_id:
                return await interaction.response.send_message("❌ It's not your turn!", ephemeral=True)
            await self.battle_state.execute_move(interaction, move_index)
        return callback

    async def _switch_cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.battle_state.current_turn_user_id:
            return await interaction.response.send_message("❌ It's not your turn!", ephemeral=True)
        await self.battle_state.switch_pokemon(interaction)

    async def _flee_cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.battle_state.current_turn_user_id:
            return await interaction.response.send_message("❌ It's not your turn!", ephemeral=True)
        await self.battle_state.flee(interaction)


class BattleState:
    """Manages battle state and logic with dramatic presentation"""

    def __init__(self, player1_id: int, player1_team: List[dict],
                 player2_id: int, player2_team: List[dict],
                 p1_name: str = "Player 1", p2_name: str = "Player 2"):
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.p1_name = p1_name
        self.p2_name = p2_name
        self.player1_team = [p.copy() for p in player1_team]
        self.player2_team = [p.copy() for p in player2_team]

        for pokemon in self.player1_team + self.player2_team:
            pokemon['current_hp'] = pokemon['hp']
            pokemon['total_damage'] = 0  # Track for MVP

        self.player1_active = 0
        self.player2_active = 0

        # Speed determines first turn
        p1_speed = self.player1_team[0]['speed']
        p2_speed = self.player2_team[0]['speed']
        self.current_turn = 1 if p1_speed >= p2_speed else 2

        self.battle_log = []
        self.winner = None
        self.turn_count = 0

    @property
    def current_turn_user_id(self):
        return self.player1_id if self.current_turn == 1 else self.player2_id

    @property
    def current_player_name(self):
        return self.p1_name if self.current_turn == 1 else self.p2_name

    def get_current_pokemon(self):
        if self.current_turn == 1:
            return self.player1_team[self.player1_active]
        return self.player2_team[self.player2_active]

    def get_opponent_pokemon(self):
        if self.current_turn == 1:
            return self.player2_team[self.player2_active]
        return self.player1_team[self.player1_active]

    async def execute_move(self, interaction: discord.Interaction, move_index: int):
        """Execute a move with dramatic effects"""
        self.turn_count += 1
        attacker = self.get_current_pokemon()
        defender = self.get_opponent_pokemon()

        move_name = attacker['moves'][move_index]
        move_power = 50 + (move_index * 15)  # 50, 65, 80, 95

        damage, multiplier, hit_type = calculate_damage(attacker, defender, move_power)

        type_emoji = TYPE_EMOJIS.get(attacker.get('type', 'Normal'), '⭐')

        # Build action log
        if hit_type == 'dodge':
            log_entry = f"{type_emoji} **{attacker['name']}** used **{move_name}**!\n" + random.choice(DODGE_FLAVOR)
        else:
            defender['current_hp'] = max(0, defender['current_hp'] - damage)
            attacker['total_damage'] = attacker.get('total_damage', 0) + damage

            log_entry = f"{type_emoji} **{attacker['name']}** used **{move_name}**!"

            if hit_type == 'crit':
                log_entry += f"\n{random.choice(CRIT_FLAVOR)} **-{damage}** HP!"
            else:
                log_entry += f"\n{random.choice(ATTACK_FLAVOR)} **-{damage}** HP"

            if multiplier > 1.0:
                log_entry += f"\n{random.choice(SUPER_EFFECTIVE)}"
            elif multiplier < 1.0:
                log_entry += f"\n{random.choice(NOT_EFFECTIVE)}"

        self.battle_log = [log_entry]  # Only show last action

        # Check if defender fainted
        if defender['current_hp'] <= 0:
            self.battle_log.append(random.choice(FAINT_FLAVOR).format(name=defender['name']))
            await self.handle_faint(interaction)
        else:
            self.current_turn = 2 if self.current_turn == 1 else 1
            await self.update_battle_display(interaction)

    async def handle_faint(self, interaction: discord.Interaction):
        """Handle pokemon fainting — auto-switch to next alive"""
        if self.current_turn == 1:
            # Player 2's pokemon fainted
            next_p = None
            for i, p in enumerate(self.player2_team):
                if p['current_hp'] > 0:
                    self.player2_active = i
                    next_p = p
                    break
            if not next_p:
                self.winner = self.player1_id
                await self.end_battle(interaction)
                return
            self.battle_log.append(f"🔵 **{self.p2_name}** sends out **{next_p['name']}**!")
        else:
            next_p = None
            for i, p in enumerate(self.player1_team):
                if p['current_hp'] > 0:
                    self.player1_active = i
                    next_p = p
                    break
            if not next_p:
                self.winner = self.player2_id
                await self.end_battle(interaction)
                return
            self.battle_log.append(f"🔴 **{self.p1_name}** sends out **{next_p['name']}**!")

        self.current_turn = 2 if self.current_turn == 1 else 1
        await self.update_battle_display(interaction)

    async def switch_pokemon(self, interaction: discord.Interaction):
        """Switch to next available pokemon"""
        if self.current_turn == 1:
            team = self.player1_team
            active = self.player1_active
        else:
            team = self.player2_team
            active = self.player2_active

        available = [i for i, p in enumerate(team) if p['current_hp'] > 0 and i != active]

        if not available:
            return await interaction.response.send_message("❌ No other fighters available!", ephemeral=True)

        # Switch to first available
        new_idx = available[0]
        if self.current_turn == 1:
            self.player1_active = new_idx
        else:
            self.player2_active = new_idx

        name = team[new_idx]['name']
        icon = '🔴' if self.current_turn == 1 else '🔵'
        self.battle_log = [f"{icon} **{self.current_player_name}** switched to **{name}**!"]

        self.current_turn = 2 if self.current_turn == 1 else 1
        await self.update_battle_display(interaction)

    async def flee(self, interaction: discord.Interaction):
        """Flee from battle"""
        self.winner = self.player2_id if self.current_turn == 1 else self.player1_id
        fleeing = self.current_player_name
        self.battle_log = [f"🏃 **{fleeing}** fled from battle!"]
        await self.end_battle(interaction)

    async def update_battle_display(self, interaction: discord.Interaction):
        embed = self.create_battle_embed()
        view = BattleView(self)
        await interaction.response.edit_message(embed=embed, view=view)

    async def end_battle(self, interaction: discord.Interaction):
        """Dramatic win screen with MVP"""
        from utils.leveling_system import award_exp, get_battle_exp_reward

        winner_name = self.p1_name if self.winner == self.player1_id else self.p2_name
        loser_name = self.p2_name if self.winner == self.player1_id else self.p1_name

        embed = discord.Embed(
            title="🏆 BATTLE OVER!",
            color=0xFFD700
        )

        # Winner announcement
        embed.description = (
            f"```ansi\n\u001b[1;33m{'═' * 30}\n"
            f"  🎉 {winner_name.upper()} WINS! 🎉\n"
            f"{'═' * 30}\u001b[0m\n```\n"
            f"**{winner_name}** defeated **{loser_name}** in **{self.turn_count}** turns!"
        )

        # Find MVP (highest damage dealer from winner's team)
        winner_team = self.player1_team if self.winner == self.player1_id else self.player2_team
        loser_team = self.player2_team if self.winner == self.player1_id else self.player1_team

        mvp = max(winner_team, key=lambda p: p.get('total_damage', 0))
        mvp_dmg = mvp.get('total_damage', 0)

        embed.add_field(
            name="⭐ MVP",
            value=f"**{mvp['name']}** — dealt **{mvp_dmg}** total damage!",
            inline=False
        )

        # Battle log
        if self.battle_log:
            embed.add_field(
                name="📜 Final Action",
                value="\n".join(self.battle_log[-3:]),
                inline=False
            )

        # EXP and Rewards
        reward_gems = random.randint(100, 300)
        exp_rewards = []
        level_ups = []

        for pokemon in winner_team:
            avg_loser_level = sum(p.get('level', 1) for p in loser_team) // len(loser_team)
            exp_gained = get_battle_exp_reward(pokemon.get('level', 1), avg_loser_level)
            result = award_exp(pokemon, exp_gained)
            exp_rewards.append(f"`{pokemon['name']}` → +{exp_gained} EXP")
            if result['leveled_up']:
                level_ups.append(f"🌟 **{pokemon['name']}** leveled up to **Lv.{result['new_level']}**!")

        rewards_text = f"💎 **{reward_gems} Gems**\n" + " • ".join(exp_rewards)
        if level_ups:
            rewards_text += "\n\n" + "\n".join(level_ups)

        embed.add_field(name="🎁 Rewards", value=rewards_text, inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

    def create_battle_embed(self) -> discord.Embed:
        """Create the dramatic battle display"""
        p1 = self.player1_team[self.player1_active]
        p2 = self.player2_team[self.player2_active]

        t1e = TYPE_EMOJIS.get(p1.get('type', 'Normal'), '⭐')
        t2e = TYPE_EMOJIS.get(p2.get('type', 'Normal'), '⭐')

        # Team status icons
        p1_status = create_team_status(self.player1_team)
        p2_status = create_team_status(self.player2_team)

        # Build embed
        is_p1_turn = self.current_turn == 1
        turn_color = 0xe74c3c if is_p1_turn else 0x3498db

        embed = discord.Embed(
            title=f"⚔️ BATTLE — {self.p1_name} vs {self.p2_name}",
            color=turn_color
        )

        # Player 1 side
        p1_hp = create_health_bar(p1['current_hp'], p1['hp'])
        p1_arrow = "▶️ " if is_p1_turn else ""
        embed.add_field(
            name=f"{p1_arrow}🔴 {self.p1_name}'s {p1['name']} {t1e}",
            value=(
                f"{p1_hp}\n"
                f"⚔️ `{p1['attack']}` 🛡️ `{p1['defense']}` ⚡ `{p1['speed']}`\n"
                f"Team: {p1_status}"
            ),
            inline=False
        )

        # VS separator
        embed.add_field(name="━━━━ ⚡ VS ⚡ ━━━━", value="\u200b", inline=False)

        # Player 2 side
        p2_hp = create_health_bar(p2['current_hp'], p2['hp'])
        p2_arrow = "▶️ " if not is_p1_turn else ""
        embed.add_field(
            name=f"{p2_arrow}🔵 {self.p2_name}'s {p2['name']} {t2e}",
            value=(
                f"{p2_hp}\n"
                f"⚔️ `{p2['attack']}` 🛡️ `{p2['defense']}` ⚡ `{p2['speed']}`\n"
                f"Team: {p2_status}"
            ),
            inline=False
        )

        # Action log
        if self.battle_log:
            embed.add_field(
                name="📜 Action",
                value="\n".join(self.battle_log[-3:]),
                inline=False
            )

        # Turn indicator
        turn_name = self.current_player_name
        turn_icon = '🔴' if is_p1_turn else '🔵'
        embed.set_footer(text=f"{turn_icon} {turn_name}'s turn — Choose your move! • Turn {self.turn_count + 1}")

        return embed
