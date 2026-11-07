import discord
import discord.ui as ui
from discord.ext import commands
import random
import asyncio
from utils.economy_db import economy_db
from utils.economy_embeds import *
from config import COLORS, ECONOMY, OWNER_IDS

class EconomyGames(commands.Cog):
    """🎮 Casino & Gambling Games - Test your luck!"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Card deck
        self.card_values = {
            'A': 11, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
            '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10
        }
        self.card_suits = ['♠️', '♥️', '♣️', '♦️']

    async def cog_command_error(self, ctx, error):
        """Catch all errors so nothing fails silently."""
        if isinstance(error, commands.CommandInvokeError):
            error = error.original
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument,
                               commands.CommandOnCooldown)):
            await ctx.send(f"{ECONOMY_EMOJIS['fail']} {error}")
            return
        print(f"[EconomyGames Error] {ctx.command}: {type(error).__name__}: {error}")
        try:
            await ctx.send(
                embed=create_economy_embed(
                    title=f"{ECONOMY_EMOJIS['fail']} Something went wrong",
                    description="An unexpected error occurred. Please try again.",
                    color=COLORS['error']
                )
            )
        except Exception:
            pass

    def validate_bet(self, ctx, bet, user_data):
        """Validate if user can place bet"""
        if user_data is None:
            return False, f"{ECONOMY_EMOJIS['fail']} Could not connect to the economy database! Try again later."
        if bet <= 0:
            return False, f"{ECONOMY_EMOJIS['fail']} Bet must be positive!"
        max_bet = ECONOMY.get('max_bet', 500000)
        if bet > max_bet:
            return False, f"{ECONOMY_EMOJIS['fail']} Maximum bet is 💎 **{max_bet:,}**!"
        if bet > user_data['wallet']:
            return False, f"{ECONOMY_EMOJIS['fail']} You don't have enough money! You have {format_currency(user_data['wallet'])}"
        return True, None

    # ==================== EFFECT HELPERS ====================

    # Non-game effects that should NOT trigger bet caps or be consumed per game
    NON_GAME_EFFECTS = {'bank_expansion', 'rob_protection', 'reward_boost'}

    def get_user_effects(self, user_id):
        """Get all active effects for a user and return them as a dict by type.
        Returns only game-relevant effects (excludes bank_expansion, rob_protection, etc.)."""
        effects = economy_db.get_active_effects(user_id)
        effect_map = {}
        for e in effects:
            etype = e['effect_type']
            if etype not in effect_map and etype not in self.NON_GAME_EFFECTS:
                effect_map[etype] = e
        return effect_map

    def apply_multiplier_effects(self, user_id, winnings, bet, effects):
        """Apply multiplier and double_stakes effects to winnings.
        Returns (adjusted_winnings, effect_texts) and consumes uses."""
        adjusted = winnings
        texts = []

        # Multiplier boost (1.5x winnings)
        if 'multiplier' in effects:
            eff = effects['multiplier']
            mult = float(eff['effect_value'])
            adjusted = int(adjusted * mult)
            texts.append(f"⚡ **Multiplier Boost** ({mult}x)")
            economy_db.consume_effect_use(eff['id'])

        # Double down (2x winnings AND 2x losses)
        if 'double_stakes' in effects:
            eff = effects['double_stakes']
            mult = float(eff['effect_value'])
            adjusted = int(adjusted * mult)
            texts.append(f"🎯 **Double Down** ({mult}x)")
            economy_db.consume_effect_use(eff['id'])

        return adjusted, texts

    def apply_loss_effects(self, user_id, bet, effects):
        """Apply loss protection / double_stakes to losses.
        Returns (adjusted_loss, refund_amount, effect_texts) and consumes uses."""
        loss = bet
        refund = 0
        texts = []

        # Double down increases losses too
        if 'double_stakes' in effects:
            eff = effects['double_stakes']
            mult = float(eff['effect_value'])
            loss = int(loss * mult)
            texts.append(f"🎯 **Double Down** ({mult}x loss)")
            economy_db.consume_effect_use(eff['id'])

        # Safety net refunds 50% of losses
        if 'loss_protection' in effects:
            eff = effects['loss_protection']
            refund_pct = float(eff['effect_value'])
            refund = int(loss * refund_pct)
            texts.append(f"🪂 **Safety Net** (refunded {format_currency(refund)})")
            economy_db.consume_effect_use(eff['id'])

        # Consume multiplier boost use even on loss (it's a per-game item)
        if 'multiplier' in effects:
            eff = effects['multiplier']
            economy_db.consume_effect_use(eff['id'])

        return loss, refund, texts

    def check_luck_boost(self, effects):
        """Check if luck boost is active, return bonus chance (e.g. 0.10)."""
        if 'luck_boost' in effects:
            eff = effects['luck_boost']
            economy_db.consume_effect_use(eff['id'])
            return float(eff['effect_value'])
        return 0.0

    # ==================== BLACKJACK ====================
    
    @commands.command(name='blackjack', aliases=['bj'])
    async def blackjack(self, ctx, bet: int):
        """🃏 Play blackjack against the dealer"""
        # Owners bypass the cooldown
        if ctx.author.id not in OWNER_IDS:
            cooldown = economy_db.check_cooldown(str(ctx.author.id), 'blackjack')
            if cooldown > 0:
                return await ctx.send(embed=cooldown_embed('blackjack', cooldown))
        
        user_data = economy_db.get_user(str(ctx.author.id))
        
        # Validate bet (also handles None user_data)
        valid, error = self.validate_bet(ctx, bet, user_data)
        if not valid:
            return await ctx.send(error)
        
        # Get active effects
        user_id = str(ctx.author.id)
        effects = self.get_user_effects(user_id)
        
        
        
        # Deduct bet
        economy_db.update_balance(user_id, -bet, 0)
        
        # Create deck and deal cards
        def deal_card():
            rank = random.choice(list(self.card_values.keys()))
            suit = random.choice(self.card_suits)
            return {'rank': rank, 'suit': suit, 'display': f"{rank}{suit}"}
        
        def calculate_hand(hand):
            total = sum(self.card_values[card['rank']] for card in hand)
            aces = sum(1 for card in hand if card['rank'] == 'A')
            
            while total > 21 and aces > 0:
                total -= 10
                aces -= 1
            
            return total
        
        player_hand = [deal_card(), deal_card()]
        dealer_hand = [deal_card(), deal_card()]
        
        player_total = calculate_hand(player_hand)
        dealer_total = calculate_hand(dealer_hand)
        
        # Card counter effect — show dealer's hidden card
        dealer_peek = ""
        if 'blackjack_peek' in effects:
            eff = effects['blackjack_peek']
            dealer_peek = f"\n🃏 *Card Counter active — Dealer's hidden card: {dealer_hand[1]['display']}*"
            economy_db.consume_effect_use(eff['id'])
        
        # Check for immediate blackjack
        if player_total == 21:
            winnings = int(bet * 2.5)
            winnings, win_texts = self.apply_multiplier_effects(user_id, winnings, bet, effects)
            economy_db.update_balance(user_id, winnings, 0)
            economy_db.log_transaction(user_id, 'game_win', winnings - bet, 'Blackjack!')
            
            effect_line = ""
            if win_texts:
                effect_line = f"\n{' | '.join(win_texts)}"
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['cards']} BLACKJACK!",
                description=f"**Your Hand:** {' '.join(c['display'] for c in player_hand)} = **21**\n**Dealer:** {dealer_hand[0]['display']} ??\n\n{ECONOMY_EMOJIS['success']} Blackjack! Won: {format_currency(winnings)} (2.5x){effect_line}",
                color=RARITY_COLORS['legendary']
            )
            return await ctx.send(embed=embed)
        
        # Button-based game loop (avoids Manage Messages permission dependency)
        class BlackjackView(ui.View):
            def __init__(self, author):
                super().__init__(timeout=30)
                self.author = author
                self.action = None  # 'hit' or 'stand'

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user != self.author:
                    await interaction.response.send_message("This isn't your game!", ephemeral=True)
                    return False
                return True

            @ui.button(label='Hit', style=discord.ButtonStyle.success, emoji='✅')
            async def hit_button(self, interaction: discord.Interaction, button: ui.Button):
                self.action = 'hit'
                self.stop()
                await interaction.response.defer()

            @ui.button(label='Stand', style=discord.ButtonStyle.danger, emoji='❌')
            async def stand_button(self, interaction: discord.Interaction, button: ui.Button):
                self.action = 'stand'
                self.stop()
                await interaction.response.defer()

        # Show initial hand with buttons
        view = BlackjackView(ctx.author)
        embed = create_economy_embed(
            title=f"{ECONOMY_EMOJIS['cards']} Blackjack",
            description=f"**Your Hand:** {' '.join(c['display'] for c in player_hand)} = **{player_total}**\n**Dealer:** {dealer_hand[0]['display']} ??{dealer_peek}\n\nClick **Hit** to draw a card or **Stand** to stop.",
            color=COLORS['primary']
        )

        msg = await ctx.send(embed=embed, view=view)

        while player_total < 21:
            # Wait for button press or timeout
            timed_out = await view.wait()  # True = timed out, False = stopped

            if timed_out or view.action == 'stand':
                # Auto-stand on timeout or explicit stand
                break

            if view.action == 'hit':
                # Hit
                player_hand.append(deal_card())
                player_total = calculate_hand(player_hand)

                if player_total > 21:
                    # Bust — show dealer's hand too so the owner can see
                    # Dealer plays out their hand even on bust for transparency
                    while dealer_total < 17:
                        dealer_hand.append(deal_card())
                        dealer_total = calculate_hand(dealer_hand)
                    dealer_display = ' '.join(c['display'] for c in dealer_hand)

                    _, refund, loss_texts = self.apply_loss_effects(user_id, bet, effects)
                    if refund > 0:
                        economy_db.update_balance(user_id, refund, 0)

                    economy_db.log_transaction(user_id, 'game_loss', bet, 'Blackjack bust')

                    effect_line = ""
                    if loss_texts:
                        effect_line = f"\n{' | '.join(loss_texts)}"

                    bust_embed = create_economy_embed(
                        title=f"{ECONOMY_EMOJIS['cards']} Blackjack - Bust!",
                        description=(
                            f"**Your Hand:** {' '.join(c['display'] for c in player_hand)} = **{player_total}**\n"
                            f"**Dealer:** {dealer_display} = **{dealer_total}**\n\n"
                            f"{ECONOMY_EMOJIS['fail']} Bust! Lost: {format_currency(bet)}{effect_line}"
                        ),
                        color=COLORS['error']
                    )
                    economy_db.set_cooldown(user_id, 'blackjack', 3)
                    return await msg.edit(embed=bust_embed, view=None)

                if player_total == 21:
                    # Auto-stand at 21
                    break

                # Update embed and reset view for next action
                view = BlackjackView(ctx.author)
                hit_embed = create_economy_embed(
                    title=f"{ECONOMY_EMOJIS['cards']} Blackjack",
                    description=f"**Your Hand:** {' '.join(c['display'] for c in player_hand)} = **{player_total}**\n**Dealer:** {dealer_hand[0]['display']} ??{dealer_peek}\n\nClick **Hit** to draw a card or **Stand** to stop.",
                    color=COLORS['primary']
                )
                await msg.edit(embed=hit_embed, view=view)
        
        # Dealer's turn
        while dealer_total < 17:
            dealer_hand.append(deal_card())
            dealer_total = calculate_hand(dealer_hand)
        
        # Determine winner
        dealer_display = ' '.join(c['display'] for c in dealer_hand)
        
        if dealer_total > 21 or player_total > dealer_total:
            # Player wins
            winnings = bet * 2
            winnings, win_texts = self.apply_multiplier_effects(user_id, winnings, bet, effects)
            economy_db.update_balance(user_id, winnings, 0)
            economy_db.log_transaction(user_id, 'game_win', winnings - bet, 'Blackjack win')
            
            effect_line = ""
            if win_texts:
                effect_line = f"\n{' | '.join(win_texts)}"
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['cards']} Blackjack - You Win!",
                description=f"**Your Hand:** {' '.join(c['display'] for c in player_hand)} = **{player_total}**\n**Dealer:** {dealer_display} = **{dealer_total}**\n\n{ECONOMY_EMOJIS['success']} Won: {format_currency(winnings)} (2x){effect_line}",
                color=COLORS['success']
            )
        elif player_total == dealer_total:
            # Push (tie) — consume effects without benefit
            if 'multiplier' in effects:
                economy_db.consume_effect_use(effects['multiplier']['id'])
            if 'double_stakes' in effects:
                economy_db.consume_effect_use(effects['double_stakes']['id'])
            if 'loss_protection' in effects:
                economy_db.consume_effect_use(effects['loss_protection']['id'])
            
            economy_db.update_balance(user_id, bet, 0)
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['cards']} Blackjack - Push",
                description=f"**Your Hand:** {' '.join(c['display'] for c in player_hand)} = **{player_total}**\n**Dealer:** {dealer_display} = **{dealer_total}**\n\n{ECONOMY_EMOJIS['info']} Tie! Bet returned.",
                color=COLORS['secondary']
            )
        else:
            # Dealer wins — apply loss effects
            _, refund, loss_texts = self.apply_loss_effects(user_id, bet, effects)
            if refund > 0:
                economy_db.update_balance(user_id, refund, 0)
            
            economy_db.log_transaction(user_id, 'game_loss', bet, 'Blackjack loss')
            
            effect_line = ""
            if loss_texts:
                effect_line = f"\n{' | '.join(loss_texts)}"
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['cards']} Blackjack - Dealer Wins",
                description=f"**Your Hand:** {' '.join(c['display'] for c in player_hand)} = **{player_total}**\n**Dealer:** {dealer_display} = **{dealer_total}**\n\n{ECONOMY_EMOJIS['fail']} Lost: {format_currency(bet)}{effect_line}",
                color=COLORS['error']
            )
        
        # Set cooldown (3 seconds)
        economy_db.set_cooldown(user_id, 'blackjack', 3)
        await msg.edit(embed=embed)
    
    # ==================== DICE GAME ====================
    
    @commands.command(name='dice')
    async def dice(self, ctx, bet: int, prediction: int):
        """🎲 Roll 2 dice and predict the sum (2-12)"""
        # Owners bypass the cooldown
        if ctx.author.id not in OWNER_IDS:
            cooldown = economy_db.check_cooldown(str(ctx.author.id), 'dice')
            if cooldown > 0:
                return await ctx.send(embed=cooldown_embed('dice', cooldown))
        
        user_data = economy_db.get_user(str(ctx.author.id))
        
        # Validate bet (also handles None user_data)
        valid, error = self.validate_bet(ctx, bet, user_data)
        if not valid:
            return await ctx.send(error)
        
        if not 2 <= prediction <= 12:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Prediction must be between 2 and 12!")
        
        # Get active effects
        user_id = str(ctx.author.id)
        effects = self.get_user_effects(user_id)
        
        
        
        # Deduct bet
        economy_db.update_balance(user_id, -bet, 0)
        
        # Animated rolling (skipped for bot owners)
        roll_msg = await ctx.send(embed=create_economy_embed(
            title=f"{ECONOMY_EMOJIS['dice']} Dice Roll",
            description=f"🎲 🎲\n\n{ECONOMY_EMOJIS['loading']} Rolling...",
            color=COLORS['primary']
        ))

        import config as _cfg
        if ctx.author.id not in _cfg.OWNER_IDS:
            await asyncio.sleep(1.5)
        
        # Roll dice
        dice1 = random.randint(1, 6)
        dice2 = random.randint(1, 6)
        total = dice1 + dice2
        
        # Loaded dice effect — only guarantees common roll (7, 2x payout)
        if 'dice_guarantee' in effects:
            eff = effects['dice_guarantee']
            if prediction == 7:
                # Only works on the most common roll (2x payout)
                total = 7
                dice1 = 3
                dice2 = 4
            # Always consume the use, even if prediction wasn't 7
            economy_db.consume_effect_use(eff['id'])
        
        # Calculate multiplier based on rarity (middle numbers are more common)
        multipliers = {2: 10, 3: 7, 4: 5, 5: 3, 6: 2, 7: 2, 8: 2, 9: 3, 10: 5, 11: 7, 12: 10}
        multiplier = multipliers[prediction]
        
        # Check win
        if total == prediction:
            winnings = bet * multiplier
            winnings, win_texts = self.apply_multiplier_effects(user_id, winnings, bet, effects)
            economy_db.update_balance(user_id, winnings, 0)
            economy_db.log_transaction(user_id, 'game_win', winnings - bet, f'Dice win ({multiplier}x)')
            
            effect_line = ""
            if win_texts:
                effect_line = f"\n{' | '.join(win_texts)}"
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['dice']} Dice Roll - WIN!",
                description=f"🎲 **{dice1}** + 🎲 **{dice2}** = **{total}**\n\nYou predicted: **{prediction}**\n{ECONOMY_EMOJIS['success']} Won: {format_currency(winnings)} ({multiplier}x){effect_line}",
                color=COLORS['success']
            )
        else:
            # Apply loss effects
            _, refund, loss_texts = self.apply_loss_effects(user_id, bet, effects)
            if refund > 0:
                economy_db.update_balance(user_id, refund, 0)
            
            economy_db.log_transaction(user_id, 'game_loss', bet, 'Dice loss')
            
            effect_line = ""
            if loss_texts:
                effect_line = f"\n{' | '.join(loss_texts)}"
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['dice']} Dice Roll - Lost",
                description=f"🎲 **{dice1}** + 🎲 **{dice2}** = **{total}**\n\nYou predicted: **{prediction}**\n{ECONOMY_EMOJIS['fail']} Lost: {format_currency(bet)}{effect_line}",
                color=COLORS['error']
            )
        
        # Consume luck boost if active (already consumed in helpers above)
        # Set cooldown (3 seconds)
        economy_db.set_cooldown(user_id, 'dice', 3)
        await roll_msg.edit(embed=embed)
    
    # ==================== COINFLIP ====================
    
    @commands.command(name='flip', aliases=['coinflip', 'cf'])
    async def coinflip(self, ctx, bet: int, choice: str):
        """💰 Flip a coin (heads/tails)"""
        # Owners bypass the cooldown
        if ctx.author.id not in OWNER_IDS:
            cooldown = economy_db.check_cooldown(str(ctx.author.id), 'coinflip')
            if cooldown > 0:
                return await ctx.send(embed=cooldown_embed('coinflip', cooldown))
        
        user_data = economy_db.get_user(str(ctx.author.id))
        
        # Validate bet (also handles None user_data)
        valid, error = self.validate_bet(ctx, bet, user_data)
        if not valid:
            return await ctx.send(error)
        
        choice = choice.lower()
        if choice not in ['heads', 'tails', 'h', 't']:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Choose `heads` or `tails`!")
        
        # Normalize choice
        if choice in ['h', 'heads']:
            choice = 'heads'
        else:
            choice = 'tails'
        
        # Get active effects
        user_id = str(ctx.author.id)
        effects = self.get_user_effects(user_id)
        luck_bonus = self.check_luck_boost(effects)
        
        
        
        # Deduct bet
        economy_db.update_balance(user_id, -bet, 0)
        
        # Animated flip (skipped for bot owners)
        flip_msg = await ctx.send(embed=create_economy_embed(
            title=f"{ECONOMY_EMOJIS['coin']} Coin Flip",
            description=f"{ECONOMY_EMOJIS['loading']} Flipping...",
            color=COLORS['primary']
        ))

        import config as _cfg
        if ctx.author.id not in _cfg.OWNER_IDS:
            await asyncio.sleep(1.5)
        
        # Flip result — luck boost increases win chance
        # Base: 50/50. With luck_boost of 0.10 → 60/40
        win_chance = 0.5 + luck_bonus
        won = random.random() < win_chance
        result = choice if won else ('tails' if choice == 'heads' else 'heads')
        
        if won:
            winnings = bet * 2
            winnings, win_texts = self.apply_multiplier_effects(user_id, winnings, bet, effects)
            economy_db.update_balance(user_id, winnings, 0)
            economy_db.log_transaction(user_id, 'game_win', winnings - bet, 'Coinflip win')
            
            effect_line = ""
            if win_texts:
                effect_line = f"\n{' | '.join(win_texts)}"
            if luck_bonus > 0:
                effect_line += f"\n🍀 **Luck Potion** active"
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['coin']} Coin Flip - WIN!",
                description=f"Result: **{result.capitalize()}**\nYou chose: **{choice.capitalize()}**\n\n{ECONOMY_EMOJIS['success']} Won: {format_currency(winnings)} (2x){effect_line}",
                color=COLORS['success']
            )
        else:
            # Apply loss effects
            _, refund, loss_texts = self.apply_loss_effects(user_id, bet, effects)
            if refund > 0:
                economy_db.update_balance(user_id, refund, 0)
            
            economy_db.log_transaction(user_id, 'game_loss', bet, 'Coinflip loss')
            
            effect_line = ""
            if loss_texts:
                effect_line = f"\n{' | '.join(loss_texts)}"
            if luck_bonus > 0:
                effect_line += f"\n🍀 **Luck Potion** active (unlucky!)"
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['coin']} Coin Flip - Lost",
                description=f"Result: **{result.capitalize()}**\nYou chose: **{choice.capitalize()}**\n\n{ECONOMY_EMOJIS['fail']} Lost: {format_currency(bet)}{effect_line}",
                color=COLORS['error']
            )
        
        # Set cooldown (3 seconds)
        economy_db.set_cooldown(user_id, 'coinflip', 3)
        await flip_msg.edit(embed=embed)
    
    # ==================== ROULETTE ====================
    
    @commands.command(name='roulette')
    async def roulette(self, ctx, bet: int, choice: str):
        """🎯 Spin the roulette wheel (red/black/green/number)"""
        # Owners bypass the cooldown
        if ctx.author.id not in OWNER_IDS:
            cooldown = economy_db.check_cooldown(str(ctx.author.id), 'roulette')
            if cooldown > 0:
                return await ctx.send(embed=cooldown_embed('roulette', cooldown))
        
        user_data = economy_db.get_user(str(ctx.author.id))
        
        # Validate bet (also handles None user_data)
        valid, error = self.validate_bet(ctx, bet, user_data)
        if not valid:
            return await ctx.send(error)
        
        choice = choice.lower()
        
        # Get active effects
        user_id = str(ctx.author.id)
        effects = self.get_user_effects(user_id)
        luck_bonus = self.check_luck_boost(effects)
        
        
        
        # Deduct bet
        economy_db.update_balance(user_id, -bet, 0)
        
        # Roulette numbers
        red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
        
        # Animated spin (skipped for bot owners)
        spin_msg = await ctx.send(embed=create_economy_embed(
            title=f"{ECONOMY_EMOJIS['wheel']} Roulette",
            description=f"{ECONOMY_EMOJIS['loading']} Spinning the wheel...",
            color=COLORS['primary']
        ))

        import config as _cfg
        if ctx.author.id not in _cfg.OWNER_IDS:
            await asyncio.sleep(2)
        
        # Spin result — luck boost gives slight edge on color bets
        number = random.randint(0, 36)
        
        # With luck boost, re-roll once if lost (simulates better odds)
        if luck_bonus > 0 and random.random() < luck_bonus:
            number = random.randint(0, 36)
        
        if number == 0:
            color_result = 'green'
        elif number in red_numbers:
            color_result = 'red'
        else:
            color_result = 'black'
        
        # Check win
        won = False
        multiplier = 0
        
        if choice == color_result:
            if choice == 'green':
                multiplier = 50
            else:
                multiplier = 2
            won = True
        elif choice.isdigit() and int(choice) == number:
            multiplier = 35
            won = True
        
        if won:
            winnings = bet * multiplier
            winnings, win_texts = self.apply_multiplier_effects(user_id, winnings, bet, effects)
            economy_db.update_balance(user_id, winnings, 0)
            economy_db.log_transaction(user_id, 'game_win', winnings - bet, f'Roulette win ({multiplier}x)')
            
            effect_line = ""
            if win_texts:
                effect_line = f"\n{' | '.join(win_texts)}"
            if luck_bonus > 0:
                effect_line += f"\n🍀 **Luck Potion** active"
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['target']} Roulette - WIN!",
                description=f"Ball landed on: **{number} ({color_result})**\nYou bet: **{choice}**\n\n{ECONOMY_EMOJIS['success']} Won: {format_currency(winnings)} ({multiplier}x){effect_line}",
                color=COLORS['success']
            )
        else:
            # Apply loss effects
            _, refund, loss_texts = self.apply_loss_effects(user_id, bet, effects)
            if refund > 0:
                economy_db.update_balance(user_id, refund, 0)
            
            economy_db.log_transaction(user_id, 'game_loss', bet, 'Roulette loss')
            
            effect_line = ""
            if loss_texts:
                effect_line = f"\n{' | '.join(loss_texts)}"
            if luck_bonus > 0:
                effect_line += f"\n🍀 **Luck Potion** active (unlucky!)"
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['target']} Roulette - Lost",
                description=f"Ball landed on: **{number} ({color_result})**\nYou bet: **{choice}**\n\n{ECONOMY_EMOJIS['fail']} Lost: {format_currency(bet)}{effect_line}",
                color=COLORS['error']
            )
        
        # Set cooldown (3 seconds)
        economy_db.set_cooldown(user_id, 'roulette', 3)
        await spin_msg.edit(embed=embed)

async def setup(bot):
    await bot.add_cog(EconomyGames(bot))
