import discord
from discord.ext import commands
from utils.embeds import success_embed, error_embed
from utils.economy_db import economy_db
from utils.ship_generator import ShipImageGenerator
import config
import random

class Games(commands.Cog):
    """Fun game commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='rps', aliases=['rockpaperscissors'])
    async def rps(self, ctx, choice: str = ""):
        """Play Rock Paper Scissors"""
        if not choice or choice.lower() not in ['rock', 'paper', 'scissors', 'r', 'p', 's']:
            return await ctx.reply(embed=error_embed('Invalid Choice', f'Usage: `{config.PREFIX}rps <rock|paper|scissors>`'))
        
        choices = ['rock', 'paper', 'scissors']
        choice_map = {'r': 'rock', 'p': 'paper', 's': 'scissors'}
        
        user_choice = choice_map.get(choice.lower(), choice.lower())
        bot_choice = random.choice(choices)
        
        emoji_map = {'rock': '🪨', 'paper': '📄', 'scissors': '✂️'}
        
        # Determine winner
        if user_choice == bot_choice:
            result = "It's a tie!"
            color = config.COLORS['secondary']
        elif (
            (user_choice == 'rock' and bot_choice == 'scissors') or
            (user_choice == 'paper' and bot_choice == 'rock') or
            (user_choice == 'scissors' and bot_choice == 'paper')
        ):
            result = f"{config.EMOJIS['success']} You win!"
            color = config.COLORS['success']
        else:
            result = f"{config.EMOJIS['error']} You lose!"
            color = config.COLORS['error']
        
        embed = discord.Embed(
            title=f"{config.EMOJIS['game']} Rock Paper Scissors",
            description=f"You chose {emoji_map[user_choice]} **{user_choice.title()}**\nI chose {emoji_map[bot_choice]} **{bot_choice.title()}**\n\n{result}",
            color=color
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name='8ball', aliases=['eightball'])
    async def eightball(self, ctx, *, question=None):
        """Ask the magic 8ball a question"""
        if not question:
            return await ctx.reply(embed=error_embed('No Question', f'Usage: `{config.PREFIX}8ball <question>`'))
        
        responses = {
            'yes': [
                'It is certain.', 'It is decidedly so.', 'Without a doubt.',
                'Yes - definitely.', 'You may rely on it.', 'As I see it, yes.',
                'Most likely.', 'Outlook good.', 'Yes.', 'Signs point to yes.'
            ],
            'maybe': [
                'Reply hazy, try again.', 'Ask again later.', 'Better not tell you now.',
                'Cannot predict now.', 'Concentrate and ask again.'
            ],
            'no': [
                "Don't count on it.", 'My reply is no.', 'My sources say no.',
                'Outlook not so good.', 'Very doubtful.'
            ]
        }
        
        category = random.choice(list(responses.keys()))
        answer = random.choice(responses[category])
        
        color_map = {'yes': config.COLORS['success'], 'maybe': config.COLORS['secondary'], 'no': config.COLORS['error']}
        
        embed = discord.Embed(
            title='🎱 Magic 8-Ball',
            color=color_map[category]
        )
        embed.add_field(name='Question', value=question, inline=False)
        embed.add_field(name='Answer', value=answer, inline=False)
        
        await ctx.reply(embed=embed)
    
    @commands.command(name='mines', aliases=['minesweeper'])
    async def mines(self, ctx, bet: str = "", grid_size: int = 3):
        """Play Minesweeper game with economy bet
        
        Usage: ,mines <bet> [grid_size]
        Grid sizes: 3 (easy), 4 (medium), 5 (hard)
        """
        if not bet:
            return await ctx.reply(embed=error_embed('Missing Bet', f'Usage: `{config.PREFIX}mines <bet> [3|4|5]`\nExample: `{config.PREFIX}mines 500 3`'))
        
        # Parse bet amount
        try:
            bet_amount = int(bet.replace(',', ''))
        except ValueError:
            if bet.lower() == 'all':
                data = economy_db.get_user(str(ctx.author.id))
                if not data:
                    return await ctx.reply(embed=error_embed('Error', 'Could not fetch your balance.'))
                bet_amount = data['wallet']
            else:
                return await ctx.reply(embed=error_embed('Invalid Bet', 'Please enter a valid number or `all`.'))
        
        if bet_amount <= 0:
            return await ctx.reply(embed=error_embed('Invalid Bet', 'Bet must be a positive amount.'))
        
        # Enforce max bet
        max_bet = config.ECONOMY.get('max_bet', 500000)
        if bet_amount > max_bet:
            return await ctx.reply(embed=error_embed('Bet Too High', f'Maximum bet is 💎 **{max_bet:,}**!'))
        
        # Check balance
        data = economy_db.get_user(str(ctx.author.id))
        if not data:
            return await ctx.reply(embed=error_embed('Error', 'Could not fetch your balance.'))
        if data['wallet'] < bet_amount:
            return await ctx.reply(embed=error_embed('Insufficient Funds', f'You only have 💎 **{data["wallet"]:,}** in your wallet.'))
        
        if grid_size not in [3, 4, 5]:
            return await ctx.reply(embed=error_embed('Invalid Size', f'Choose grid size: 3 (easy), 4 (medium), or 5 (hard)\nUsage: `{config.PREFIX}mines <bet> [3|4|5]`'))
        
        # Deduct bet
        economy_db.update_balance(str(ctx.author.id), -bet_amount, 0)
        
        # Define mine count based on difficulty
        mine_counts = {3: 2, 4: 4, 5: 6}
        num_mines = mine_counts[grid_size]
        
        # Create grid with mines
        total_cells = grid_size * grid_size
        mine_positions = random.sample(range(total_cells), num_mines)
        safe_cells = total_cells - num_mines
        
        # Track game state
        revealed = set()
        game_over = False
        cashed_out = False
        
        class MinesView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)  # pyre-ignore[28]
                self.message = None
                
                # Create grid buttons
                for i in range(total_cells):
                    row_num = i // grid_size
                    button = discord.ui.Button(
                        style=discord.ButtonStyle.secondary,
                        label='❔',
                        row=row_num if grid_size <= 4 else min(row_num, 3),
                        custom_id=f'cell_{i}'
                    )
                    button.callback = self.create_callback(i)
                    self.add_item(button)
                
                # Add Cash Out button (last row)
                cashout_row = min(grid_size, 4)
                cashout_btn = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    label=f'Cash Out (💎 0)',
                    custom_id='cashout',
                    row=cashout_row,
                    disabled=True
                )
                cashout_btn.callback = self.cashout_callback
                self.add_item(cashout_btn)
            
            def get_multiplier(self):
                """Calculate multiplier based on revealed cells and mine count"""
                # More mines = higher risk = higher multiplier per safe cell
                raw_per_cell: float = 0.2 + (num_mines * 0.1)
                per_cell = round(raw_per_cell, 2)
                raw_multiplier: float = 1.0 + len(revealed) * per_cell
                return round(raw_multiplier, 2)
            
            def get_winnings(self):
                """Calculate current winnings"""
                return int(bet_amount * self.get_multiplier())
            
            def update_cashout_label(self):
                """Update the cashout button label with current winnings"""
                for item in self.children:
                    if item.custom_id == 'cashout':
                        winnings = self.get_winnings()
                        item.label = f'Cash Out (💎 {winnings:,})'
                        item.disabled = len(revealed) == 0
                        break
            
            async def cashout_callback(self, interaction: discord.Interaction):
                nonlocal game_over, cashed_out
                
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message('This is not your game!', ephemeral=True)
                
                if game_over or cashed_out:
                    return await interaction.response.send_message('Game is already over!', ephemeral=True)
                
                if len(revealed) == 0:
                    return await interaction.response.send_message('Reveal at least one cell first!', ephemeral=True)
                
                cashed_out = True
                game_over = True
                winnings = self.get_winnings()
                profit = winnings - bet_amount
                
                # Award winnings
                economy_db.update_balance(str(ctx.author.id), winnings, 0)
                
                # Disable all buttons
                for i, item in enumerate(self.children):
                    if item.custom_id and item.custom_id.startswith('cell_'):
                        idx = int(item.custom_id.split('_')[1])
                        if idx in mine_positions:
                            item.label = '💣'
                            item.style = discord.ButtonStyle.danger
                    item.disabled = True
                
                embed = discord.Embed(
                    title=f'{config.EMOJIS["success"]} Minesweeper - Cashed Out!',
                    description=(
                        f'💎 **You cashed out!**\n'
                        f'**Bet:** 💎 {bet_amount:,}\n'
                        f'**Multiplier:** {self.get_multiplier()}x\n'
                        f'**Winnings:** 💎 {winnings:,} (+{profit:,})'
                    ),
                    color=config.COLORS['success']
                )
                await interaction.response.edit_message(embed=embed, view=self)
            
            def create_callback(self, index):
                async def button_callback(interaction: discord.Interaction):
                    nonlocal game_over
                    
                    if interaction.user.id != ctx.author.id:
                        return await interaction.response.send_message('This is not your game!', ephemeral=True)
                    
                    if game_over or cashed_out:
                        return await interaction.response.send_message('Game is already over!', ephemeral=True)
                    
                    if index in revealed:
                        return await interaction.response.send_message('Already revealed!', ephemeral=True)
                    
                    revealed.add(index)
                    
                    # Check if mine
                    if index in mine_positions:
                        game_over = True
                        # Reveal all mines
                        for i, item in enumerate(self.children):
                            if item.custom_id and item.custom_id.startswith('cell_'):
                                idx = int(item.custom_id.split('_')[1])
                                if idx in mine_positions:
                                    item.label = '💣'
                                    item.style = discord.ButtonStyle.danger
                                elif idx in revealed:
                                    item.label = '💎'
                                    item.style = discord.ButtonStyle.success
                            item.disabled = True
                        
                        embed = discord.Embed(
                            title=f'{config.EMOJIS["error"]} Minesweeper - Game Over!',
                            description=(
                                f'\U0001f4a5 You hit a mine!\n'
                                f'**Bet Lost:** 💎 {bet_amount:,}\n'
                                f'**Score:** {len(revealed) - 1}/{safe_cells}'
                            ),
                            color=config.COLORS['error']
                        )
                        await interaction.response.edit_message(embed=embed, view=self)
                    else:
                        # Safe cell
                        for item in self.children:
                            if item.custom_id == f'cell_{index}':
                                item.label = '💎'
                                item.style = discord.ButtonStyle.success
                                item.disabled = True
                        
                        # Update cashout button
                        self.update_cashout_label()
                        
                        # Check win condition — all safe cells found
                        if len(revealed) == safe_cells:
                            game_over = True
                            winnings = self.get_winnings()
                            profit = winnings - bet_amount
                            economy_db.update_balance(str(ctx.author.id), winnings, 0)
                            
                            for item in self.children:
                                item.disabled = True
                            
                            embed = discord.Embed(
                                title=f'{config.EMOJIS["success"]} Minesweeper - You Win!',
                                description=(
                                    f'{config.EMOJIS["crown"]} **All safe cells found!**\n'
                                    f'**Bet:** 💎 {bet_amount:,}\n'
                                    f'**Multiplier:** {self.get_multiplier()}x (MAX)\n'
                                    f'**Winnings:** 💎 {winnings:,} (+{profit:,})'
                                ),
                                color=config.COLORS['success']
                            )
                            await interaction.response.edit_message(embed=embed, view=self)
                        else:
                            embed = discord.Embed(
                                title=f'{config.EMOJIS["game"]} Minesweeper',
                                description=(
                                    f'**Bet:** 💎 {bet_amount:,}\n'
                                    f'**Grid:** {grid_size}x{grid_size} | **Mines:** {num_mines}\n'
                                    f'**Multiplier:** {self.get_multiplier()}x\n'
                                    f'**Progress:** {len(revealed)}/{safe_cells}\n\n'
                                    f'Click cells to reveal. Cash out anytime!'
                                ),
                                color=config.COLORS['primary']
                            )
                            await interaction.response.edit_message(embed=embed, view=self)
                
                return button_callback
            
            async def on_timeout(self):
                nonlocal game_over
                if not game_over and not cashed_out and len(revealed) > 0:
                    # Auto-cashout on timeout
                    winnings = self.get_winnings()
                    economy_db.update_balance(str(ctx.author.id), winnings, 0)
                elif not game_over and not cashed_out:
                    # Refund if no cells were revealed
                    economy_db.update_balance(str(ctx.author.id), bet_amount, 0)
                game_over = True
        
        view = MinesView()
        embed = discord.Embed(
            title=f'{config.EMOJIS["game"]} Minesweeper',
            description=(
                f'**Bet:** 💎 {bet_amount:,}\n'
                f'**Grid:** {grid_size}x{grid_size} | **Mines:** {num_mines}\n'
                f'**Multiplier:** 1.0x\n'
                f'**Progress:** 0/{safe_cells}\n\n'
                f'Click cells to reveal them. Cash out anytime!'
            ),
            color=config.COLORS['primary']
        )
        await ctx.reply(embed=embed, view=view)
    
    @commands.command(name='ship')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ship(self, ctx, user1: discord.Member = None, user2: discord.Member = None):
        """Calculate compatibility between two users"""
        # Owners bypass the cooldown
        if ctx.author.id in config.OWNER_IDS:
            ctx.command.reset_cooldown(ctx)
        # If no users provided, ship author with random member
        if not user1 and not user2:
            members = [m for m in ctx.guild.members if not m.bot and m != ctx.author]
            if members:
                user1 = ctx.author
                user2 = random.choice(members)
            else:
                return await ctx.reply(embed=error_embed('No Members', 'Not enough members to ship!'))
        
        # If only one user provided, ship with author
        elif not user2:
            user2 = user1
            user1 = ctx.author
        
        # Don't allow shipping with bots
        if user1.bot or user2.bot:
            return await ctx.reply(embed=error_embed('Invalid Users', 'Cannot ship with bots!'))
        
        # Send "generating" message
        async with ctx.typing():
            try:
                # Generate image
                generator = ShipImageGenerator()
                image_bytes = await generator.generate(
                    avatar1_url=str(user1.display_avatar.url),
                    avatar2_url=str(user2.display_avatar.url),
                    username1=user1.name,
                    username2=user2.name,
                    user1_id=user1.id,
                    user2_id=user2.id
                )
                
                # Send image
                file = discord.File(image_bytes, filename="ship.png")
                await ctx.send(file=file)
                
            except Exception as e:
                await ctx.reply(embed=error_embed('Ship Failed', f'Could not generate ship image: {str(e)}'))
    
    @ship.error
    async def ship_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(embed=error_embed(
                'Cooldown',
                f'You can use this command again in {error.retry_after:.1f} seconds!'
            ))
    
    @commands.command(name='quotemsg', aliases=['qm'])
    async def quotemsg(self, ctx):
        """Quote a message and create a beautiful quote image"""
        # Check if replying to a message
        if not ctx.message.reference:
            return await ctx.reply(embed=error_embed('No Message', 'Reply to a message to quote it!\\nExample: Reply to any message and type `,quote`'))
        
        try:
            # Get the referenced message
            referenced_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            
            if not referenced_msg.content:
                return await ctx.reply(embed=error_embed('Empty Message', 'Cannot quote an empty message or image-only message.'))
            
            # Send loading message
            loading_msg = await ctx.reply(embed=success_embed(
                'Generating Quote',
                f'{config.EMOJIS["loading"]} Creating beautiful quote image...'
            ))
            
            # Generate quote image with stunning graphics
            from PIL import Image, ImageDraw, ImageFont, ImageFilter
            import aiohttp
            import io
            from datetime import datetime
            
            # Image dimensions - MUCH LARGER for readability
            width = 1600
            padding = 100
            
            # Estimate height based on text length
            text_length = len(referenced_msg.content)
            estimated_lines = max(4, min(text_length // 30, 20))
            height = 600 + (estimated_lines * 65)
            
            # Create base image
            img = Image.new('RGB', (width, height), color=(20, 20, 30))
            draw = ImageDraw.Draw(img)
            
            # Create beautiful gradient background (purple to blue)
            for y in range(height):
                # Gradient from deep purple to blue
                r = int(124 + (14 - 124) * (y / height))
                g = int(58 + (233 - 58) * (y / height))
                b = int(237 + (246 - 237) * (y / height))
                draw.line([(0, y), (width, y)], fill=(r, g, b))
            
            # Add decorative corner elements
            corner_size = 80
            corner_color = (255, 255, 255, 100)
            
            # Top-left corner decoration
            draw.arc([30, 30, 30 + corner_size, 30 + corner_size], start=180, end=270, fill=(255, 255, 255), width=4)
            
            # Top-right corner decoration
            draw.arc([width - 30 - corner_size, 30, width - 30, 30 + corner_size], start=270, end=360, fill=(255, 255, 255), width=4)
            
            # Bottom-left corner decoration
            draw.arc([30, height - 30 - corner_size, 30 + corner_size, height - 30], start=90, end=180, fill=(255, 255, 255), width=4)
            
            # Bottom-right corner decoration
            draw.arc([width - 30 - corner_size, height - 30 - corner_size,  width - 30, height - 30], start=0, end=90, fill=(255, 255, 255), width=4)
            
            # Try to load fonts - MUCH BIGGER for readability
            try:
                quote_font = ImageFont.truetype('arial.ttf', 56)
                author_font = ImageFont.truetype('arialbd.ttf', 38)
                username_font = ImageFont.truetype('arial.ttf', 32)
                date_font = ImageFont.truetype('arial.ttf', 28)
            except:
                try:
                    quote_font = ImageFont.truetype('calibri.ttf', 56)
                    author_font = ImageFont.truetype('calibrib.ttf', 38)
                    username_font = ImageFont.truetype('calibri.ttf', 24)
                    date_font = ImageFont.truetype('calibri.ttf', 20)
                except:
                    quote_font = ImageFont.load_default()
                    author_font = ImageFont.load_default()
                    username_font = ImageFont.load_default()
                    date_font = ImageFont.load_default()
            
            # Download and process author's avatar
            avatar_url = str(referenced_msg.author.display_avatar.url)
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as resp:
                    avatar_data = await resp.read()
                    avatar_img = Image.open(io.BytesIO(avatar_data)).convert('RGBA')
                    
                    # Make avatar much larger for visibility
                    avatar_size = 200
                    avatar_img = avatar_img.resize((avatar_size, avatar_size))
                    
                    # Create circular mask
                    mask = Image.new('L', (avatar_size, avatar_size), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                    
                    # Create avatar with white border and shadow effect
                    avatar_pos_x = padding
                    avatar_pos_y = padding + 30
                    
                    # Draw shadow/border
                    for offset in range(10, 0, -1):
                        shadow_alpha = int(90 - offset * 7)
                        shadow_layer = Image.new('RGBA', (avatar_size + offset*2, avatar_size + offset*2), (255, 255, 255, shadow_alpha))
                        shadow_mask = Image.new('L', (avatar_size + offset*2, avatar_size + offset*2), 0)
                        shadow_mask_draw = ImageDraw.Draw(shadow_mask)
                        shadow_mask_draw.ellipse((0, 0, avatar_size + offset*2, avatar_size + offset*2), fill=shadow_alpha)
                        
                        temp_img = Image.new('RGBA', img.size, (0, 0, 0, 0))
                        temp_img.paste(shadow_layer, (avatar_pos_x - offset, avatar_pos_y - offset), shadow_mask)
                        img = Image.alpha_composite(img.convert('RGBA'), temp_img).convert('RGB')
                    
                    # Paste avatar
                    temp_img = Image.new('RGBA', img.size, (0, 0, 0, 0))
                    temp_img.paste(avatar_img, (avatar_pos_x, avatar_pos_y), mask)
                    img = Image.alpha_composite(img.convert('RGBA'), temp_img).convert('RGB')
                    
                    # Draw white border around avatar
                    draw = ImageDraw.Draw(img)
                    border_width = 5
                    draw.ellipse([avatar_pos_x - border_width, avatar_pos_y - border_width, 
                                  avatar_pos_x + avatar_size + border_width, avatar_pos_y + avatar_size + border_width], 
                                 outline=(255, 255, 255), width=border_width)
            
            # Calculate text start position
            text_start_x = avatar_pos_x + avatar_size + 60
            text_start_y = avatar_pos_y + 30
            
            # Draw quote mark decoration
            quote_mark_font_size = 100
            try:
                quote_mark_font = ImageFont.truetype('arial.ttf', quote_mark_font_size)
            except:
                quote_mark_font = quote_font
                
            draw.text((text_start_x - 15, text_start_y - 40), '"', fill=(255, 255, 255, 150), font=quote_mark_font)
            
            # Word wrap the message text
            text = referenced_msg.content
            max_width = width - text_start_x - padding - 60
            
            words = text.split()
            lines = []
            current_line = ""
            
            for word in words:
                test_line = current_line + word + " "
                # Better width calculation for larger font
                test_width = len(test_line) * 28
                if test_width > max_width:
                    if current_line:
                        lines.append(current_line.strip())
                    current_line = word + " "
                else:
                    current_line = test_line
            
            if current_line:
                lines.append(current_line.strip())
            
            # Draw text with shadow effect
            y_text = text_start_y
            line_spacing = 65  # Increased spacing for readability
            
            import itertools
            for line in itertools.islice(lines, 15):  # Limit to 15 lines
                # Draw shadow
                draw.text((text_start_x + 2, y_text + 2), line, fill=(0, 0, 0, 100), font=quote_font)
                # Draw main text
                draw.text((text_start_x, y_text), line, fill=(255, 255, 255), font=quote_font)
                y_text += line_spacing
            
            # Draw closing quote mark
            draw.text((text_start_x + max_width - 40, y_text - line_spacing - 10), '"', 
                     fill=(255, 255, 255, 150), font=quote_mark_font)
            
            # Draw author section with background panel
            author_section_y = y_text + 30
            panel_padding = 20
            
            # Draw author name with icon
            author_name = f"— {referenced_msg.author.display_name}"
            draw.text((text_start_x + 2, author_section_y + 2), author_name, fill=(0, 0, 0, 120), font=author_font)
            draw.text((text_start_x, author_section_y), author_name, fill=(255, 255, 255), font=author_font)
            
            # Draw username (tag)
            username_text = f"@{referenced_msg.author.name}"
            draw.text((text_start_x, author_section_y + 38), username_text, fill=(220, 220, 255), font=username_font)
            
            # Draw date
            date_text = referenced_msg.created_at.strftime('%B %d, %Y at %I:%M %p')
            draw.text((text_start_x, author_section_y + 68), date_text, fill=(200, 200, 220), font=date_font)
            
            # Add watermark/branding (subtle)
            watermark_text = "xiel"
            draw.text((width - padding - 150, height - 40), watermark_text, fill=(255, 255, 255, 80), font=date_font)
            
            # Save to bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG', quality=95)
            img_bytes.seek(0)
            
            # Send image
            file = discord.File(img_bytes, filename='quote.png')
            await loading_msg.delete()
            await ctx.reply(file=file)
            
        except Exception as e:
            try:
                await loading_msg.delete()
            except:
                pass
            await ctx.reply(embed=error_embed('Quote Failed', f'Could not create quote: {str(e)}'))

async def setup(bot):
    await bot.add_cog(Games(bot))
