"""
Multiplayer Games — TicTacToe, Word Game, Trivia, Connect Four
Button-based interactive games with leaderboards
"""
import discord
from discord.ext import commands
from discord.ui import View, Button, Select
from utils.embeds import success_embed, error_embed, info_embed
import config
import asyncio
import random
import aiohttp
import html


# ─── EXPANDED WORD LIST WITH HINTS (200+ words) ───
WORD_HINTS = {
    # Technology & Computing
    'python': 'Programming language or large snake',
    'discord': 'Popular chat platform for gamers',
    'keyboard': 'Input device with keys for typing',
    'monitor': 'Display screen for computers',
    'algorithm': 'Step-by-step problem-solving procedure',
    'computer': 'Electronic device for processing data',
    'internet': 'Global network of computers',
    'database': 'Organized collection of data',
    'function': 'Reusable block of code',
    'variable': 'Container for storing data values',
    'software': 'Programs and applications for computers',
    'hardware': 'Physical computer components',
    'generate': 'Create or produce',
    'download': 'Transfer data from internet to device',
    'wireless': 'Communication without physical connection',
    'graphics': 'Visual images or designs',
    'terminal': 'Text-based interface for commands',
    'password': 'Secret string used for authentication',
    'protocol': 'Set of rules for data transmission',
    'compiler': 'Program that translates code',
    'robotics': 'Science of designing robots',
    'debugger': 'Tool for finding code errors',
    'ethernet': 'Wired network technology',
    'firmware': 'Software embedded in hardware',
    'encoding': 'Converting data to a specific format',
    'datatype': 'Classification of data in programming',
    'platform': 'System that runs applications',
    'notebook': 'Book for writing notes or a portable computer',
    'template': 'Reusable pattern or blueprint',

    # Animals & Nature
    'elephant': 'Largest land animal with a trunk',
    'jellyfish': 'Gelatinous sea creature',
    'kangaroo': 'Australian hopping marsupial',
    'dinosaur': 'Extinct prehistoric reptile',
    'mountain': 'Large natural elevation',
    'nitrogen': 'Chemical element, gas in air',
    'squirrel': 'Small bushy-tailed rodent',
    'flamingo': 'Pink wading bird',
    'mushroom': 'Fungus with a cap and stem',
    'scorpion': 'Arachnid with a venomous tail',
    'crocodile': 'Large aquatic reptile',
    'chameleon': 'Lizard that changes color',
    'butterfly': 'Insect with colorful wings',
    'porcupine': 'Rodent covered in quills',
    'starfish': 'Sea creature shaped like a star',
    'tortoise': 'Slow-moving shelled reptile',
    'predator': 'Animal that hunts other animals',
    'penguin': 'Flightless bird from Antarctica',
    'dolphin': 'Intelligent marine mammal',
    'leopard': 'Spotted big cat',
    'gorilla': 'Largest living primate',
    'hamster': 'Small furry pet rodent',
    'antelope': 'Swift grassland animal',
    'platypus': 'Egg-laying mammal with a bill',
    'parakeet': 'Small colorful parrot',
    'sparrow': 'Common small brown bird',
    'ecosystem': 'Community of living organisms',
    'blizzard': 'Severe snowstorm with high winds',
    'volcanic': 'Related to volcanoes',
    'asteroid': 'Small rocky body in space',
    'waterfall': 'Cascade of falling water',
    'avalanche': 'Mass of snow sliding down mountain',
    'tropical': 'Related to warm equatorial regions',
    'wildfire': 'Uncontrolled fire in nature',

    # Food & Drink
    'sandwich': 'Food with filling between bread slices',
    'broccoli': 'Green tree-shaped vegetable',
    'smoothie': 'Blended fruit drink',
    'pancakes': 'Flat breakfast cakes',
    'espresso': 'Strong concentrated coffee',
    'cinnamon': 'Sweet aromatic spice',
    'avocado': 'Creamy green fruit',
    'spaghetti': 'Long thin pasta',
    'pineapple': 'Tropical spiky fruit',
    'blueberry': 'Small blue fruit',
    'chocolate': 'Sweet brown confection',
    'croissant': 'Flaky French pastry',
    'hamburger': 'Ground meat in a bun',
    'lemonade': 'Sweet lemon drink',
    'barbeque': 'Outdoor cooking over fire',
    'mushroom': 'Fungus with a cap and stem',

    # Places & Geography
    'paradise': 'Perfect or ideal place',
    'universe': 'All existing matter and space',
    'vacation': 'Time off for leisure',
    'railroad': 'Track for trains',
    'building': 'Constructed structure',
    'hospital': 'Medical care facility',
    'bookstore': 'Shop that sells books',
    'cathedral': 'Large important church',
    'continent': 'Large landmass on Earth',
    'peninsula': 'Land surrounded by water on three sides',
    'apartment': 'Living unit in a building',
    'gymnasium': 'Room for physical exercise',
    'boulevard': 'Wide tree-lined street',
    'skyscraper': 'Very tall building',
    'landscape': 'Visible features of an area',

    # Objects & Things
    'umbrella': 'Device for protection from rain',
    'envelope': 'Paper container for letters',
    'backpack': 'Bag carried on shoulders',
    'calendar': 'System for organizing days',
    'treasure': 'Valuable hidden wealth',
    'xylophone': 'Musical percussion instrument',
    'telescope': 'Instrument for viewing distant objects',
    'headphone': 'Audio device worn on ears',
    'furniture': 'Movable items in a room',
    'suitcase': 'Travel bag for clothes',
    'necklace': 'Jewelry worn around the neck',
    'champion': 'Winner or title holder',
    'scissors': 'Cutting tool with blades',
    'trampoline': 'Bouncing surface on a frame',
    'binocular': 'Device for seeing far away',
    'fireworks': 'Explosive pyrotechnic displays',
    'chandelier': 'Hanging light fixture',
    'hourglass': 'Time-measuring sand device',
    'blueprint': 'Technical drawing or plan',

    # Concepts & Abstract
    'abstract': 'Theoretical or not concrete',
    'birthday': 'Annual celebration of birth',
    'football': 'Popular team sport with a ball',
    'illusion': 'False perception or deception',
    'language': 'System of communication',
    'overflow': 'Exceed capacity or limits',
    'question': 'Inquiry or query',
    'spectrum': 'Range of colors or values',
    'absolute': 'Complete or total',
    'dialogue': 'Conversation between people',
    'exchange': 'Trade or swap items',
    'feedback': 'Response or reaction',
    'creative': 'Having ability to create',
    'strategy': 'Plan of action to achieve goals',
    'momentum': 'Force of moving objects',
    'ambition': 'Strong desire to achieve',
    'patience': 'Ability to wait calmly',
    'obstacle': 'Something blocking the way',
    'sympathy': 'Understanding of others feelings',
    'conflict': 'Serious disagreement or fight',
    'progress': 'Forward movement or development',
    'behavior': 'Way someone acts or conducts',
    'attitude': 'Settled way of thinking',
    'decision': 'Choice made after thinking',
    'evidence': 'Available facts or proof',
    'ignorance': 'Lack of knowledge',
    'priority': 'Something more important',
    'prophecy': 'Prediction of the future',
    'scenario': 'Possible sequence of events',

    # Sports & Activities
    'yachting': 'Sailing recreational boats',
    'swimming': 'Moving through water using body',
    'climbing': 'Going up using hands and feet',
    'baseball': 'Team sport with bat and ball',
    'lacrosse': 'Team sport with a netted stick',
    'marathon': 'Long-distance running race',
    'archery': 'Shooting arrows at targets',
    'gymnastics': 'Physical exercises and routines',
    'wrestling': 'Combat sport of grappling',
    'surfboard': 'Board for riding ocean waves',
    'parachute': 'Device for slow descent from sky',
    'snowboard': 'Board for sliding on snow',
    'exercise': 'Physical activity for fitness',

    # Science & Education
    'evolution': 'Gradual change over time',
    'chemistry': 'Study of substances and reactions',
    'molecule': 'Smallest unit of a compound',
    'bacteria': 'Single-celled microorganisms',
    'magnetic': 'Having properties of a magnet',
    'skeleton': 'Framework of bones in body',
    'electron': 'Negatively charged particle',
    'radiation': 'Energy emitted as waves',
    'telescope': 'Instrument for viewing distant objects',
    'discovery': 'Finding something new',
    'professor': 'University teacher',
    'research': 'Systematic investigation',
    'equation': 'Mathematical statement of equality',
    'organism': 'Individual living thing',
    'photosynthesis': 'Plants converting light to energy',
    'microscope': 'Instrument for viewing tiny objects',

    # History & Culture
    'zeppelin': 'Large rigid airship',
    'carnival': 'Festive celebration with rides',
    'mythology': 'Collection of myths',
    'tradition': 'Customs passed through generations',
    'gladiator': 'Ancient Roman fighter',
    'adventure': 'Exciting experience',
    'invention': 'New device or creation',
    'sculpture': 'Three-dimensional artwork',
    'orchestra': 'Large group of musicians',

    # Misc
    'detective': 'Person who investigates crimes',
    'volunteer': 'Person who works without pay',
    'passenger': 'Traveler in a vehicle',
    'dangerous': 'Involving risk or harm',
    'permanent': 'Lasting forever',
    'beautiful': 'Very pleasing to look at',
    'wonderful': 'Extremely good or remarkable',
    'invisible': 'Cannot be seen',
    'knowledge': 'Information gained through experience',
    'important': 'Of great significance',
    'different': 'Not the same',
    'community': 'Group of people living together',
    'education': 'Process of learning',
    'emergency': 'Serious unexpected situation',
    'happiness': 'State of being happy',
    'marketing': 'Promoting and selling products',
    'nutrition': 'Process of providing food',
    'president': 'Head of state or organization',
    'recommend': 'Suggest as good or suitable',
    'telephone': 'Device for voice communication',
    'transport': 'Moving people or goods',
    'navigator': 'Person who directs course',
    'labyrinth': 'Complex maze',
    'signature': 'Handwritten name',
    'companion': 'Person who accompanies another',
    'thunderstorm': 'Storm with thunder and lightning',
}

BLACKTEA_WORDS = sorted(set(WORD_HINTS.keys()) | {
    "ability", "absence", "academy", "account", "accident", "advance",
    "airplane", "analysis", "ancient", "another", "anything", "arrival",
    "article", "average", "balance", "battery", "because", "bedroom",
    "biology", "blanket", "cabinet", "captain", "careful", "central",
    "century", "certain", "chapter", "climate", "college", "command",
    "company", "compare", "complex", "concert", "contest", "control",
    "courage", "crystal", "culture", "current", "diamond", "digital",
    "distant", "drawing", "dynamic", "eastern", "economy", "edition",
    "elastic", "element", "emotion", "evening", "example", "factory",
    "failure", "fashion", "feature", "fiction", "formula", "freedom",
    "gallery", "general", "genuine", "gravity", "healthy", "history",
    "holiday", "imagine", "include", "journey", "justice", "kitchen",
    "library", "machine", "manager", "measure", "medical", "meeting",
    "message", "mission", "morning", "mystery", "natural", "network",
    "nothing", "observe", "officer", "opinion", "package", "pattern",
    "perfect", "picture", "plastic", "popular", "prepare", "private",
    "problem", "process", "promise", "quality", "regular", "respect",
    "science", "section", "service", "silence", "similar", "society",
    "special", "station", "student", "subject", "success", "support",
    "surface", "teacher", "therapy", "thought", "traffic", "uniform",
    "village", "weather", "western", "whisper", "without", "written",
})

BLACKTEA_PROMPTS = sorted({
    word[i:i + size]
    for word in BLACKTEA_WORDS
    for size in (2, 3)
    for i in range(len(word) - size + 1)
    if word[i:i + size].isalpha()
})


# ─── TIC TAC TOE ───
class TTTButton(Button):
    def __init__(self, x, y):
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        view: TTTView = self.view
        if interaction.user.id != view.current_player.id:
            return await interaction.response.send_message("Not your turn!", ephemeral=True)
        self.disabled = True
        if view.current_player == view.player_x:
            self.style = discord.ButtonStyle.danger
            self.label = 'X'
            self.emoji = None
            view.board[self.y][self.x] = 'X'
        else:
            self.style = discord.ButtonStyle.primary
            self.label = 'O'
            self.emoji = None
            view.board[self.y][self.x] = 'O'

        winner = view.check_winner()
        if winner:
            for child in view.children:
                child.disabled = True
            view.stop()
            embed = discord.Embed(title="🎮 Tic Tac Toe",
                description=f"🏆 **{view.current_player.display_name}** wins!",
                color=0x2ecc71)
            return await interaction.response.edit_message(embed=embed, view=view)

        if view.is_full():
            for child in view.children:
                child.disabled = True
            view.stop()
            embed = discord.Embed(title="🎮 Tic Tac Toe",
                description="🤝 It's a **draw**!", color=0xf39c12)
            return await interaction.response.edit_message(embed=embed, view=view)

        # Switch turns
        view.current_player = view.player_o if view.current_player == view.player_x else view.player_x
        symbol = 'O' if view.current_player == view.player_o else 'X'
        embed = discord.Embed(title="🎮 Tic Tac Toe",
            description=f"**{view.current_player.display_name}**'s turn ({symbol})",
            color=config.COLORS['primary'])
        embed.set_footer(text=f"{view.player_x.display_name} (X) vs {view.player_o.display_name} (O)")
        await interaction.response.edit_message(embed=embed, view=view)


class TTTView(View):
    def __init__(self, player_x, player_o):
        super().__init__(timeout=120)
        self.player_x = player_x
        self.player_o = player_o
        self.current_player = player_x
        self.board = [[None]*3 for _ in range(3)]
        for y in range(3):
            for x in range(3):
                self.add_item(TTTButton(x, y))

    def check_winner(self):
        b = self.board
        # Rows, cols, diags
        for i in range(3):
            if b[i][0] == b[i][1] == b[i][2] and b[i][0]:
                return b[i][0]
            if b[0][i] == b[1][i] == b[2][i] and b[0][i]:
                return b[0][i]
        if b[0][0] == b[1][1] == b[2][2] and b[0][0]:
            return b[0][0]
        if b[0][2] == b[1][1] == b[2][0] and b[0][2]:
            return b[0][2]
        return None

    def is_full(self):
        return all(self.board[y][x] is not None for y in range(3) for x in range(3))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# ─── CONNECT FOUR ───
class C4Button(Button):
    def __init__(self, col):
        # Discord limits 5 buttons per row, so split 7 columns across 2 rows
        super().__init__(style=discord.ButtonStyle.secondary, label=str(col+1), row=0 if col < 5 else 1)
        self.col = col

    async def callback(self, interaction: discord.Interaction):
        view: C4View = self.view
        if interaction.user.id != view.current_player.id:
            return await interaction.response.send_message("Not your turn!", ephemeral=True)

        # Find lowest empty row in column
        row = -1
        for r in range(5, -1, -1):
            if view.board[r][self.col] == '⚫':
                row = r
                break
        if row == -1:
            return await interaction.response.send_message("Column full!", ephemeral=True)

        piece = '🔴' if view.current_player == view.p1 else '🟡'
        view.board[row][self.col] = piece

        # Check if column is now full
        if view.board[0][self.col] != '⚫':
            self.disabled = True

        winner = view.check_winner()
        board_str = view.render_board()

        if winner:
            for child in view.children:
                child.disabled = True
            view.stop()
            embed = discord.Embed(title="🎮 Connect Four",
                description=f"{board_str}\n\n🏆 **{view.current_player.display_name}** wins!",
                color=0x2ecc71)
            return await interaction.response.edit_message(embed=embed, view=view)

        if view.is_full():
            for child in view.children:
                child.disabled = True
            view.stop()
            embed = discord.Embed(title="🎮 Connect Four",
                description=f"{board_str}\n\n🤝 It's a **draw**!", color=0xf39c12)
            return await interaction.response.edit_message(embed=embed, view=view)

        view.current_player = view.p2 if view.current_player == view.p1 else view.p1
        piece_next = '🔴' if view.current_player == view.p1 else '🟡'
        embed = discord.Embed(title="🎮 Connect Four",
            description=f"{board_str}\n\n**{view.current_player.display_name}**'s turn ({piece_next})",
            color=config.COLORS['primary'])
        await interaction.response.edit_message(embed=embed, view=view)


class C4View(View):
    def __init__(self, p1, p2):
        super().__init__(timeout=180)
        self.p1 = p1
        self.p2 = p2
        self.current_player = p1
        self.board = [['⚫']*7 for _ in range(6)]
        for col in range(7):
            self.add_item(C4Button(col))

    def render_board(self):
        return '\n'.join(''.join(row) for row in self.board)

    def check_winner(self):
        b = self.board
        for r in range(6):
            for c in range(7):
                if b[r][c] == '⚫':
                    continue
                p = b[r][c]
                # Horizontal
                if c+3 < 7 and all(b[r][c+i] == p for i in range(4)):
                    return p
                # Vertical
                if r+3 < 6 and all(b[r+i][c] == p for i in range(4)):
                    return p
                # Diagonal down-right
                if r+3 < 6 and c+3 < 7 and all(b[r+i][c+i] == p for i in range(4)):
                    return p
                # Diagonal up-right
                if r-3 >= 0 and c+3 < 7 and all(b[r-i][c+i] == p for i in range(4)):
                    return p
        return None

    def is_full(self):
        return all(self.board[0][c] != '⚫' for c in range(7))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class MultiplayerGames(commands.Cog):
    """Multiplayer games with interactive buttons"""

    def __init__(self, bot):
        self.bot = bot
        self.active_word_games = {}  # {channel_id: {'word': str, 'hints_used': int}}
        self.active_blacktea_games = set()
        # Track used words per channel to avoid repeats across games
        self.used_words_history = {}  # {channel_id: set(words)}

    @property
    def qualified_name(self):
        return "Games"

    # ─── TIC TAC TOE ───
    @commands.command(name='ttt', aliases=['tictactoe'])
    async def tictactoe(self, ctx, opponent: discord.Member = None):
        """Play Tic Tac Toe against another member"""
        if not opponent:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}ttt <@user>`'))
        if opponent.bot:
            return await ctx.reply(embed=error_embed('Error', "Can't play against bots!"))
        if opponent == ctx.author:
            return await ctx.reply(embed=error_embed('Error', "Can't play against yourself!"))

        # Ask for acceptance
        ask = discord.Embed(title="🎮 Tic Tac Toe Challenge",
            description=f"{opponent.mention}, {ctx.author.mention} challenges you!\nReact ✅ to accept.",
            color=config.COLORS['primary'])
        msg = await ctx.send(embed=ask)
        await msg.add_reaction('✅')
        def check(r, u):
            return u == opponent and str(r.emoji) == '✅' and r.message.id == msg.id
        try:
            await self.bot.wait_for('reaction_add', check=check, timeout=30)
        except asyncio.TimeoutError:
            return await msg.edit(embed=error_embed('Declined', f'{opponent.display_name} did not accept.'))

        view = TTTView(ctx.author, opponent)
        embed = discord.Embed(title="🎮 Tic Tac Toe",
            description=f"**{ctx.author.display_name}**'s turn (X)",
            color=config.COLORS['primary'])
        embed.set_footer(text=f"{ctx.author.display_name} (X) vs {opponent.display_name} (O)")
        await msg.edit(embed=embed, view=view)

    # ─── CONNECT FOUR ───
    @commands.command(name='c4', aliases=['connectfour', 'connect4'])
    async def connectfour(self, ctx, opponent: discord.Member = None):
        """Play Connect Four against another member"""
        if not opponent:
            return await ctx.reply(embed=error_embed('Usage', f'`{config.PREFIX}c4 <@user>`'))
        if opponent.bot or opponent == ctx.author:
            return await ctx.reply(embed=error_embed('Error', "Invalid opponent."))

        ask = discord.Embed(title="🎮 Connect Four Challenge",
            description=f"{opponent.mention}, {ctx.author.mention} challenges you!\nReact ✅ to accept.",
            color=config.COLORS['primary'])
        msg = await ctx.send(embed=ask)
        await msg.add_reaction('✅')
        def check(r, u):
            return u == opponent and str(r.emoji) == '✅' and r.message.id == msg.id
        try:
            await self.bot.wait_for('reaction_add', check=check, timeout=30)
        except asyncio.TimeoutError:
            return await msg.edit(embed=error_embed('Declined', f'{opponent.display_name} did not accept.'))

        view = C4View(ctx.author, opponent)
        board = view.render_board()
        embed = discord.Embed(title="🎮 Connect Four",
            description=f"{board}\n\n**{ctx.author.display_name}**'s turn (🔴)",
            color=config.COLORS['primary'])
        await msg.edit(embed=embed, view=view)

    # ─── WORD GAME (with no-repeat logic) ───
    @commands.command(name='wordgame', aliases=['wg', 'wordstart'])
    async def wordgame(self, ctx, rounds: int = 5):
        """Start a word scramble game (min 3 players)
        
        React to join, then unscramble words!
        Leaderboard shown at the end.
        """
        rounds = min(rounds, 15)
        # Join phase
        join_embed = discord.Embed(title="🔤 Word Game — Join Now!",
            description=f"React ✅ to join! (min 3 players)\nRounds: **{rounds}**\nStarting in 20 seconds...",
            color=0x3498db)
        msg = await ctx.send(embed=join_embed)
        await msg.add_reaction('✅')
        await asyncio.sleep(20)
        msg = await ctx.channel.fetch_message(msg.id)
        players = set()
        for reaction in msg.reactions:
            if str(reaction.emoji) == '✅':
                async for user in reaction.users():
                    if not user.bot:
                        players.add(user)
        if len(players) < 3:
            return await msg.edit(embed=error_embed('Not Enough Players',
                f'Need at least 3 players. Only {len(players)} joined.'))

        # Build word pool — exclude previously used words in this channel
        all_words = list(WORD_HINTS.keys())
        channel_id = ctx.channel.id

        if channel_id not in self.used_words_history:
            self.used_words_history[channel_id] = set()

        # Get available (unused) words
        available = [w for w in all_words if w not in self.used_words_history[channel_id]]

        # If we've exhausted all words, reset the pool
        if len(available) < rounds:
            self.used_words_history[channel_id] = set()
            available = list(all_words)

        random.shuffle(available)
        words = available[:rounds + 5]  # Grab extra in case

        scores = {p.id: 0 for p in players}
        player_names = {p.id: p.display_name for p in players}

        for rnd in range(1, rounds + 1):
            if not words:
                break
            word = words.pop()
            # Track this word as used
            self.used_words_history[channel_id].add(word)

            scrambled = ''.join(random.sample(word, len(word)))
            while scrambled == word:
                scrambled = ''.join(random.sample(word, len(word)))

            # Store active game data for hint system
            self.active_word_games[ctx.channel.id] = {'word': word, 'hints_used': 0}
            
            round_embed = discord.Embed(title=f"🔤 Round {rnd}/{rounds}",
                description=f"Unscramble: **`{scrambled.upper()}`**\n\nType your answer!\nUse `,hint` for help!",
                color=0x3498db)
            await ctx.send(embed=round_embed)

            def check(m):
                return m.author.id in scores and m.channel == ctx.channel and m.content.lower() == word.lower()
            try:
                answer = await self.bot.wait_for('message', check=check, timeout=20)
                scores[answer.author.id] += 1
                await ctx.send(embed=success_embed('Correct!',
                    f'🎉 **{answer.author.display_name}** got it! The word was **{word}**.'))
            except asyncio.TimeoutError:
                await ctx.send(embed=info_embed('Time Up', f'The word was **{word}**.'))
            
            # Clear active game data after round
            if ctx.channel.id in self.active_word_games:
                del self.active_word_games[ctx.channel.id]

            if rnd < rounds:
                await asyncio.sleep(3)

        # Leaderboard
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        lb = '\n'.join(f"{'🥇🥈🥉'[i] if i < 3 else '🏅'} **{player_names[uid]}** — {s} point{'s' if s != 1 else ''}"
                       for i, (uid, s) in enumerate(sorted_scores) if s > 0)
        if not lb:
            lb = "No one scored any points!"
        final = discord.Embed(title="🏆 Word Game — Final Results",
            description=lb, color=0xf1c40f)
        await ctx.send(embed=final)

    # ─── BLACKTEA ───
    @commands.command(name='blacktea', aliases=['bt'])
    async def blacktea(self, ctx, lives: int = 2):
        """Start a Bleed-style Blacktea elimination game.

        Players take turns typing a valid word that contains the shown letters.
        Missing a turn costs a life. Last player standing wins.
        """
        if ctx.channel.id in self.active_blacktea_games:
            return await ctx.reply(embed=error_embed('Game Running', 'A Blacktea game is already running in this channel.'))

        lives = max(1, min(lives, 5))
        join_embed = discord.Embed(
            title="🍵 Blacktea — Join Now!",
            description=(
                "React ✅ to join.\n"
                f"Lives: **{lives}**\n"
                "Need at least **2** players.\n"
                "Starting in **20 seconds**..."
            ),
            color=config.COLORS['primary']
        )
        msg = await ctx.send(embed=join_embed)
        await msg.add_reaction('✅')
        await asyncio.sleep(20)

        try:
            msg = await ctx.channel.fetch_message(msg.id)
        except discord.NotFound:
            return

        players = []
        seen = set()
        for reaction in msg.reactions:
            if str(reaction.emoji) == '✅':
                async for user in reaction.users():
                    if user.bot or user.id in seen:
                        continue
                    seen.add(user.id)
                    players.append(user)

        if len(players) < 2:
            return await msg.edit(embed=error_embed('Not Enough Players', f'Need at least 2 players. Only {len(players)} joined.'))

        self.active_blacktea_games.add(ctx.channel.id)
        random.shuffle(players)
        lives_left = {player.id: lives for player in players}
        used_words = set()
        turn_index = 0
        turn_number = 1

        def alive_players():
            return [player for player in players if lives_left.get(player.id, 0) > 0]

        def pick_prompt():
            usable = [
                prompt for prompt in BLACKTEA_PROMPTS
                if any(prompt in word and word not in used_words for word in BLACKTEA_WORDS)
            ]
            return random.choice(usable or BLACKTEA_PROMPTS)

        def is_valid_answer(content, prompt):
            answer = content.lower().strip()
            if not answer.isalpha() or len(answer) < 3:
                return False
            return prompt in answer and answer in BLACKTEA_WORDS and answer not in used_words

        try:
            start_embed = discord.Embed(
                title="🍵 Blacktea Started",
                description=(
                    "Type a real word containing the shown letters before time runs out.\n"
                    "Repeated words do not count.\n\n"
                    + "\n".join(f"**{player.display_name}** — {'❤' * lives_left[player.id]}" for player in players)
                ),
                color=config.COLORS['primary']
            )
            await msg.edit(embed=start_embed)
            await asyncio.sleep(3)

            while len(alive_players()) > 1 and turn_number <= 120:
                alive = alive_players()
                current = alive[turn_index % len(alive)]
                prompt = pick_prompt()
                valid_remaining = sum(1 for word in BLACKTEA_WORDS if prompt in word and word not in used_words)

                turn_embed = discord.Embed(
                    title=f"🍵 Blacktea — Turn {turn_number}",
                    description=(
                        f"{current.mention}, type a word containing **`{prompt.upper()}`**.\n"
                        "**Time:** 12 seconds\n"
                        f"**Possible words left:** {valid_remaining}\n\n"
                        + "\n".join(
                            f"**{player.display_name}** — {'❤' * lives_left[player.id]}"
                            for player in alive
                        )
                    ),
                    color=config.COLORS['primary']
                )
                await ctx.send(embed=turn_embed)

                def check(message):
                    return (
                        message.channel == ctx.channel
                        and message.author.id == current.id
                        and is_valid_answer(message.content, prompt)
                    )

                try:
                    answer_msg = await self.bot.wait_for('message', check=check, timeout=12)
                    answer = answer_msg.content.lower().strip()
                    used_words.add(answer)
                    await answer_msg.add_reaction('✅')
                    turn_index += 1
                except asyncio.TimeoutError:
                    lives_left[current.id] -= 1
                    if lives_left[current.id] <= 0:
                        await ctx.send(embed=error_embed('Eliminated', f'**{current.display_name}** ran out of lives.'))
                    else:
                        await ctx.send(embed=error_embed('Life Lost', f'**{current.display_name}** lost a life. **{lives_left[current.id]}** left.'))
                        turn_index += 1

                turn_number += 1
                await asyncio.sleep(2)

            winners = alive_players()
            if winners:
                winner = winners[0]
                final_desc = (
                    f"🏆 **{winner.display_name}** wins!\n\n"
                    f"Words used: **{len(used_words)}**\n"
                    f"Survived turns: **{turn_number - 1}**"
                )
            else:
                final_desc = "No one survived."

            final_embed = discord.Embed(
                title="🍵 Blacktea — Final Results",
                description=final_desc,
                color=0xf1c40f
            )
            await ctx.send(embed=final_embed)
        finally:
            self.active_blacktea_games.discard(ctx.channel.id)

    # ─── HINT COMMAND ───
    @commands.command(name='hint')
    async def word_hint(self, ctx):
        """Get a hint for the current word game"""
        if ctx.channel.id not in self.active_word_games:
            return await ctx.send(embed=error_embed('No Active Game', 'There is no word game running in this channel.'))
        
        game_data = self.active_word_games[ctx.channel.id]
        word = game_data['word']
        hints_used = game_data['hints_used']
        
        if hints_used == 0:
            # First hint: definition/category
            hint_text = WORD_HINTS.get(word, 'No hint available')
            game_data['hints_used'] = 1
            await ctx.send(embed=info_embed('💡 Hint 1', hint_text))
        elif hints_used == 1:
            # Second hint: first letter
            game_data['hints_used'] = 2
            await ctx.send(embed=info_embed('💡 Hint 2', f'First letter: **{word[0].upper()}**'))
        elif hints_used == 2:
            # Third hint: last letter
            game_data['hints_used'] = 3
            await ctx.send(embed=info_embed('💡 Hint 3', f'Last letter: **{word[-1].upper()}**'))
        else:
            await ctx.send(embed=error_embed('No More Hints', 'All hints have been used for this round.'))

    # ─── TRIVIA ───
    @commands.command(name='trivia', aliases=['quiz'])
    async def trivia(self, ctx, rounds: int = 5):
        """Start a trivia game (min 2 players)"""
        rounds = min(rounds, 10)
        join_embed = discord.Embed(title="🧠 Trivia — Join Now!",
            description=f"React ✅ to join!\nRounds: **{rounds}**\nStarting in 15 seconds...",
            color=0x9b59b6)
        msg = await ctx.send(embed=join_embed)
        await msg.add_reaction('✅')
        await asyncio.sleep(15)
        msg = await ctx.channel.fetch_message(msg.id)
        players = set()
        for reaction in msg.reactions:
            if str(reaction.emoji) == '✅':
                async for user in reaction.users():
                    if not user.bot:
                        players.add(user)
        if len(players) < 2:
            return await msg.edit(embed=error_embed('Not Enough Players', 'Need at least 2 players.'))

        scores = {p.id: 0 for p in players}
        player_names = {p.id: p.display_name for p in players}

        # Fetch questions from Open Trivia DB with error handling
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://opentdb.com/api.php?amount={rounds}&type=multiple",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return await ctx.send(embed=error_embed('API Error', 
                            f'Trivia API returned status {resp.status}. Try again later.'))
                    data = await resp.json()
        except asyncio.TimeoutError:
            return await ctx.send(embed=error_embed('Timeout', 
                'Trivia API took too long to respond. Try again later.'))
        except aiohttp.ClientError as e:
            return await ctx.send(embed=error_embed('Connection Error', 
                f'Could not connect to trivia API. Try again later.'))
        except Exception as e:
            return await ctx.send(embed=error_embed('Error', 
                f'Unexpected error fetching trivia questions. Try again later.'))

        if data.get('response_code') != 0:
            return await ctx.send(embed=error_embed('Error', 'Not enough trivia questions available.'))

        for rnd, q in enumerate(data['results'], 1):
            question = html.unescape(q['question'])
            correct = html.unescape(q['correct_answer'])
            options = [html.unescape(a) for a in q['incorrect_answers']] + [correct]
            random.shuffle(options)
            letters = ['A', 'B', 'C', 'D']
            correct_letter = letters[options.index(correct)]

            opts_text = '\n'.join(f"**{letters[i]}.** {options[i]}" for i in range(len(options)))
            q_embed = discord.Embed(title=f"🧠 Round {rnd}/{rounds}",
                description=f"**{question}**\n\n{opts_text}\n\nType your answer (A/B/C/D)",
                color=0x9b59b6)
            q_embed.set_footer(text=f"Category: {q['category']} | Difficulty: {q['difficulty'].title()}")
            await ctx.send(embed=q_embed)

            answered = set()
            def check(m):
                return (m.author.id in scores and m.channel == ctx.channel and
                        m.content.upper() in letters and m.author.id not in answered)
            try:
                while True:
                    answer = await self.bot.wait_for('message', check=check, timeout=15)
                    answered.add(answer.author.id)
                    if answer.content.upper() == correct_letter:
                        scores[answer.author.id] += 1
                        await answer.add_reaction('✅')
                    else:
                        await answer.add_reaction('❌')
                    if len(answered) >= len(players):
                        break
            except asyncio.TimeoutError:
                pass

            await ctx.send(embed=info_embed('Answer', f'The correct answer was **{correct_letter}. {correct}**'))
            if rnd < len(data['results']):
                await asyncio.sleep(3)

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        lb = '\n'.join(f"{'🥇🥈🥉'[i] if i < 3 else '🏅'} **{player_names[uid]}** — {s}/{rounds}"
                       for i, (uid, s) in enumerate(sorted_scores))
        final = discord.Embed(title="🏆 Trivia — Final Results",
            description=lb, color=0xf1c40f)
        await ctx.send(embed=final)


async def setup(bot):
    await bot.add_cog(MultiplayerGames(bot))

