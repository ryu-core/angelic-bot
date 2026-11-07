import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import random
from datetime import datetime
from utils.economy_db import economy_db
from utils.economy_embeds import *
from config import COLORS, EMOJIS, OWNER_IDS

class Economy(commands.Cog):
    """💎 Economy System - Earn, spend, and manage your virtual currency"""
    
    def __init__(self, bot):
        self.bot = bot
        self.loan_reminder_task.start()
        
        # Work job definitions: (name, emoji, min_pay, max_pay, scenarios)
        self.work_jobs = [
            {
                'name': 'Shopkeeper',
                'emoji': '🏪',
                'min': 10000,
                'max': 28000,
                'scenarios': [
                    'You restocked the shelves and upsold premium products.',
                    'A rush of customers came in and you handled them like a pro.',
                    'You negotiated bulk deals and brought in massive revenue.',
                    'You rearranged the store layout and sales skyrocketed.',
                ]
            },
            {
                'name': 'Chef',
                'emoji': '👨‍🍳',
                'min': 12000,
                'max': 32000,
                'scenarios': [
                    'You cooked a 5-course meal for a celebrity and they tipped generously.',
                    'Your secret recipe went viral and the restaurant was fully booked.',
                    'You catered a high-profile event and earned a massive bonus.',
                    'You created a new fusion dish that won an online food contest.',
                ]
            },
            {
                'name': 'Hairstylist',
                'emoji': '✂️',
                'min': 10000,
                'max': 25000,
                'scenarios': [
                    'You gave an influencer a makeover and they posted it to 1M followers.',
                    'Your salon was packed all day and tips were rolling in.',
                    'You won a local hair competition and got prize money.',
                    'A celebrity visit brought a surge of new bookings and tips.',
                ]
            },
            {
                'name': 'Hacker',
                'emoji': '💻',
                'min': 20000,
                'max': 50000,
                'scenarios': [
                    'You found a critical bug in a startup\'s system and claimed the bounty.',
                    'A company hired you for a penetration test — zero traces left.',
                    'You bypassed 3 layers of security for a CTF and won first place.',
                    'Your exploit report earned you a hefty bug bounty payout.',
                ]
            },
            {
                'name': 'Streamer',
                'emoji': '🎮',
                'min': 15000,
                'max': 40000,
                'scenarios': [
                    'You hit 10,000 viewers during your stream and subs poured in.',
                    'A top donation train kept your stream going for 12 hours straight.',
                    'A clip of your stream went viral and you gained 50k new followers.',
                    'You partnered with a sponsor and received an advance payment.',
                ]
            },
            {
                'name': 'Lawyer',
                'emoji': '⚖️',
                'min': 18000,
                'max': 45000,
                'scenarios': [
                    'You won a complex case in court and got a massive retainer fee.',
                    'Your sharp arguments saved your client millions — great cut for you.',
                    'You negotiated an out-of-court settlement and pocketed the commission.',
                    'A high-profile client paid premium rates for your expertise.',
                ]
            },
            {
                'name': 'Doctor',
                'emoji': '👨‍⚕️',
                'min': 20000,
                'max': 48000,
                'scenarios': [
                    'You performed a complex surgery and the hospital gave you a bonus.',
                    'Your diagnosis saved a life and the family sent a large gift.',
                    'You treated VIP patients at a private clinic for top-dollar rates.',
                    'You consulted on a rare case and received an expert witness fee.',
                ]
            },
            {
                'name': 'Musician',
                'emoji': '🎸',
                'min': 12000,
                'max': 38000,
                'scenarios': [
                    'You performed at a sold-out concert and received royalties.',
                    'Your track got featured in a movie soundtrack — big payday.',
                    'You beat-dropped at a festival and went viral on social media.',
                    'A label offered you a session fee for recording an album.',
                ]
            },
            {
                'name': 'Crypto Trader',
                'emoji': '💹',
                'min': 15000,
                'max': 50000,
                'scenarios': [
                    'You called the dip perfectly and flipped a 3x gain.',
                    'Your trade bot executed a perfect arbitrage opportunity.',
                    'You shorted the top and covered at the perfect moment.',
                    'A memecoin you bought early pumped 500% — you cashed out in time.',
                ]
            },
            {
                'name': 'Mechanic',
                'emoji': '🔧',
                'min': 10000,
                'max': 27000,
                'scenarios': [
                    'You fixed a luxury car and the owner tipped massively.',
                    'Your garage was booked solid and overtime pay kicked in.',
                    'You sourced rare parts for a client and charged a premium.',
                    'You repaired an exotic vehicle and got a glowing referral bonus.',
                ]
            },
        ]

    async def cog_command_error(self, ctx, error):
        """Global economy error handler — prevents silent failures."""
        # Unwrap command invoke errors
        if isinstance(error, commands.CommandInvokeError):
            error = error.original
        # Ignore user-facing errors (bad argument, missing arg, etc)
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument,
                               commands.MemberNotFound, commands.UserNotFound,
                               commands.CommandOnCooldown)):
            return
        print(f"[Economy Error] {ctx.command}: {type(error).__name__}: {error}")
        try:
            await ctx.send(
                embed=create_economy_embed(
                    title=f"{ECONOMY_EMOJIS['fail']} Something went wrong",
                    description=f"An unexpected error occurred. Please try again.",
                    color=COLORS['error']
                )
            )
        except Exception:
            pass
    
    # ==================== BALANCE & BANKING ====================
    
    @commands.command(name='balance', aliases=['bal', 'money'])
    async def balance(self, ctx, member: discord.Member = None):
        """💰 Check your balance or someone else's"""
        user = member or ctx.author
        
        # Get user data
        user_data = economy_db.get_user(str(user.id))
        
        if not user_data:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Could not fetch balance!")
        
        wallet = user_data['wallet']
        bank = user_data['bank']
        total = wallet + bank
        
        # Calculate dynamic bank limit (base + bank_expansion effects)
        bank_limit = 100000
        bank_effects = economy_db.get_active_effects(str(user.id), 'bank_expansion')
        for eff in bank_effects:
            bank_limit += int(eff.get('effect_value', 0))
        
        embed = balance_embed(user, wallet, bank, total, bank_limit)
        await ctx.send(embed=embed)
    
    @commands.command(name='deposit', aliases=['dep'])
    async def deposit(self, ctx, amount: str):
        """🏦 Deposit money to your bank"""
        user_data = economy_db.get_user(str(ctx.author.id))
        if not user_data:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Could not connect to the economy database! Try again later.")
        wallet = user_data['wallet']
        bank = user_data['bank']
        
        # Calculate dynamic bank limit (base + bank notes used)
        bank_limit = 100000
        bank_effects = economy_db.get_active_effects(str(ctx.author.id), 'bank_expansion')
        for eff in bank_effects:
            bank_limit += int(eff.get('effect_value', 0))
        remaining_space = max(0, bank_limit - bank)
        
        # Parse amount
        if amount.lower() in ['all', 'max']:
            amount = min(wallet, remaining_space)
        else:
            try:
                amount = int(amount)
            except:
                return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Invalid amount!")
        
        # Validation
        if amount <= 0:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Amount must be positive! Your bank may be full.")
        
        if amount > wallet:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} You don't have that much in your wallet!")
        
        if bank + amount > bank_limit:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Bank limit reached! Max: {format_currency(bank_limit)}\n{ECONOMY_EMOJIS['info']} Buy a 📜 **Bank Note** from the shop to increase your limit!")
        
        # Update balance
        economy_db.update_balance(str(ctx.author.id), -amount, amount)
        
        embed = create_economy_embed(
            title=f"{ECONOMY_EMOJIS['bank']} Deposit Successful",
            description=f"Deposited {format_currency(amount)} to your bank",
            color=COLORS['success'],
            user=ctx.author
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='withdraw', aliases=['with'])
    async def withdraw(self, ctx, amount: str):
        """💰 Withdraw money from your bank"""
        user_data = economy_db.get_user(str(ctx.author.id))
        if not user_data:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Could not connect to the economy database! Try again later.")
        bank = user_data['bank']
        
        # Parse amount
        if amount.lower() in ['all', 'max']:
            amount = bank
        else:
            try:
                amount = int(amount)
            except:
                return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Invalid amount!")
        
        # Validation
        if amount <= 0:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Amount must be positive!")
        
        if amount > bank:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} You don't have that much in your bank!")
        
        # Update balance
        economy_db.update_balance(str(ctx.author.id), amount, -amount)
        
        embed = create_economy_embed(
            title=f"{ECONOMY_EMOJIS['wallet']} Withdrawal Successful",
            description=f"Withdrew {format_currency(amount)} to your wallet",
            color=COLORS['success'],
            user=ctx.author
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='pay', aliases=['transfer'])
    async def pay(self, ctx, member: discord.Member, amount: int):
        """💸 Pay another user (requires receiver acceptance)"""
        # Validation
        if member == ctx.author:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} You cannot pay yourself!")
        
        if member.bot:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} You cannot pay bots!")
        
        if amount <= 0:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Amount must be positive!")
        
        # Check sender balance
        sender_data = economy_db.get_user(str(ctx.author.id))
        if not sender_data:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Could not connect to the economy database! Try again later.")
        if sender_data['wallet'] < amount:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} You don't have enough money in your wallet!")
        
        # Create accept/decline view
        class PayConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.result = None
                self._state = 'pending'
                self._state_lock = asyncio.Lock()

            async def _already_processed(self, interaction):
                await interaction.response.send_message(
                    f"{ECONOMY_EMOJIS['fail']} This payment request has already been processed.",
                    ephemeral=True
                )
            
            @discord.ui.button(label='Accept', style=discord.ButtonStyle.green, emoji='✅')
            async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != member.id:
                    return await interaction.response.send_message(
                        f"{ECONOMY_EMOJIS['fail']} Only {member.mention} can accept this payment!",
                        ephemeral=True
                    )

                async with self._state_lock:
                    if self._state != 'pending':
                        return await self._already_processed(interaction)
                    # Claim the request before touching the database so a
                    # duplicate interaction cannot execute it twice.
                    self._state = 'processing'

                    success, reason = economy_db.transfer_wallet(
                        str(ctx.author.id),
                        str(member.id),
                        amount,
                        f"Paid {member.name}",
                        f"Received from {ctx.author.name}"
                    )

                    if success:
                        self._state = 'accepted'
                        self.result = True
                        embed = transfer_embed(ctx.author, member, amount)
                    else:
                        self._state = 'failed'
                        self.result = False
                        if reason == 'insufficient_funds':
                            description = (
                                f"{ctx.author.mention} no longer has enough money "
                                f"in their wallet to send {format_currency(amount)}."
                            )
                        else:
                            description = (
                                "The economy database could not complete this payment. "
                                "No funds were moved."
                            )
                        embed = create_economy_embed(
                            title=f"{ECONOMY_EMOJIS['fail']} Payment Failed",
                            description=description,
                            color=COLORS['error']
                        )

                    for child in self.children:
                        child.disabled = True
                    self.stop()
                    await interaction.response.edit_message(embed=embed, view=self)
            
            @discord.ui.button(label='Decline', style=discord.ButtonStyle.red, emoji='❌')
            async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != member.id:
                    return await interaction.response.send_message(
                        f"{ECONOMY_EMOJIS['fail']} Only {member.mention} can decline this payment!",
                        ephemeral=True
                    )

                async with self._state_lock:
                    if self._state != 'pending':
                        return await self._already_processed(interaction)
                    self._state = 'declined'
                    self.result = False
                    self.stop()
                    
                    embed = create_economy_embed(
                        title=f"{ECONOMY_EMOJIS['fail']} Payment Declined",
                        description=f"{member.mention} declined the payment of {format_currency(amount)} from {ctx.author.mention}",
                        color=COLORS['error']
                    )
                    for child in self.children:
                        child.disabled = True
                    await interaction.response.edit_message(embed=embed, view=self)
            
            async def on_timeout(self):
                async with self._state_lock:
                    if self._state == 'pending':
                        self._state = 'expired'
                        self.result = None
                        for child in self.children:
                            child.disabled = True
        
        # Send confirmation request
        confirm_embed = create_economy_embed(
            title=f"{ECONOMY_EMOJIS['wallet']} Payment Request",
            description=f"{ctx.author.mention} wants to pay {member.mention} **{format_currency(amount)}**\n\n{member.mention}, do you accept?",
            color=COLORS['primary'],
            user=ctx.author
        )
        
        view = PayConfirmView()
        msg = await ctx.send(embed=confirm_embed, view=view)
        
        # Wait for response
        await view.wait()
        
        if view.result is None:
            # Timed out
            timeout_embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Payment Expired",
                description=f"Payment of {format_currency(amount)} to {member.mention} expired (no response in 60s)",
                color=COLORS['error']
            )
            for child in view.children:
                child.disabled = True
            await msg.edit(embed=timeout_embed, view=view)
    
    # ==================== EARNING COMMANDS ====================
    
    @commands.command(name='daily')
    async def daily(self, ctx):
        """🎁 Claim your daily reward"""
        # Owners bypass the cooldown
        if ctx.author.id not in OWNER_IDS:
            cooldown = economy_db.check_cooldown(str(ctx.author.id), 'daily')
            if cooldown > 0:
                return await ctx.send(embed=cooldown_embed('daily', cooldown))
        
        # Get user data (ensures account exists)
        user_data = economy_db.get_user(str(ctx.author.id))
        if not user_data:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Could not connect to the economy database! Try again later.")
        
        # Calculate reward with streak bonus
        base_reward = random.randint(500, 1000)
        streak = (user_data.get('daily_streak') or 0) + 1
        streak_bonus = min(streak * 50, 500)  # Max 500 bonus
        total_reward = base_reward + streak_bonus
        
        # Update balance, streak, and cooldown atomically via add_earnings + set_cooldown
        economy_db.add_earnings(str(ctx.author.id), total_reward)
        economy_db.set_cooldown(str(ctx.author.id), 'daily', 86400)  # 24 hours

        # Update streak separately (simple UPDATE)
        economy_db._exec(
            "UPDATE economy_users SET daily_streak = %s WHERE user_id = %s",
            (streak, str(ctx.author.id)),
            commit=True
        )
        
        # Log transaction
        economy_db.log_transaction(str(ctx.author.id), 'earn', total_reward, 'Daily reward')
        
        embed = daily_embed(ctx.author, total_reward, streak)
        await ctx.send(embed=embed)
    
    @commands.command(name='weekly')
    async def weekly(self, ctx):
        """📆 Claim your weekly reward"""
        # Owners bypass the cooldown
        if ctx.author.id not in OWNER_IDS:
            cooldown = economy_db.check_cooldown(str(ctx.author.id), 'weekly')
            if cooldown > 0:
                return await ctx.send(embed=cooldown_embed('weekly', cooldown))
        
        reward = 5000
        
        # Ensure user account exists before adding earnings
        economy_db.get_user(str(ctx.author.id))
        
        # Update balance
        economy_db.add_earnings(str(ctx.author.id), reward)
        economy_db.set_cooldown(str(ctx.author.id), 'weekly', 604800)  # 7 days
        economy_db.log_transaction(str(ctx.author.id), 'earn', reward, 'Weekly reward')
        
        embed = create_economy_embed(
            title=f"{ECONOMY_EMOJIS['weekly']} Weekly Reward Claimed!",
            description=f"{ECONOMY_EMOJIS['success']} You received {format_currency(reward)}",
            color=COLORS['success'],
            user=ctx.author
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='work')
    async def work(self, ctx):
        """⚒️ Work a shift to earn big money — choose your job!"""
        # Owners bypass the cooldown entirely
        if ctx.author.id not in OWNER_IDS:
            cooldown = economy_db.check_cooldown(str(ctx.author.id), 'work')
            if cooldown > 0:
                return await ctx.send(embed=cooldown_embed('work', cooldown))


        # Pick 4 random unique jobs to offer
        job_choices = random.sample(self.work_jobs, min(4, len(self.work_jobs)))

        # Build the selection embed
        select_embed = discord.Embed(
            title='⚒️ Pick Your Shift',
            description=(
                f'Hey {ctx.author.mention}, choose a job below to start your shift!\n'
                f'Each job pays differently — pick wisely.\n\n'
                + '\n'.join(
                    f'{job["emoji"]} **{job["name"]}** — 💎 {job["min"]:,} – {job["max"]:,}'
                    for job in job_choices
                )
            ),
            color=COLORS['primary']
        )
        select_embed.set_footer(
            text=f'You have 30 seconds to pick • Cooldown: 1 hour',
            icon_url=ctx.author.display_avatar.url
        )

        # Build buttons
        class JobSelectView(discord.ui.View):
            def __init__(self_v):
                super().__init__(timeout=30)
                self_v.chosen_job = None
                for job in job_choices:
                    btn = discord.ui.Button(
                        label=job['name'],
                        emoji=job['emoji'],
                        style=discord.ButtonStyle.secondary,
                        custom_id=job['name']
                    )
                    btn.callback = self_v._make_callback(job)
                    self_v.add_item(btn)

            def _make_callback(self_v, job):
                async def callback(interaction: discord.Interaction):
                    if interaction.user.id != ctx.author.id:
                        return await interaction.response.send_message(
                            f"{ECONOMY_EMOJIS['fail']} This isn't your work shift!",
                            ephemeral=True
                        )
                    self_v.chosen_job = job
                    # Disable all buttons
                    for child in self_v.children:
                        child.disabled = True
                        if isinstance(child, discord.ui.Button):
                            child.style = (
                                discord.ButtonStyle.success
                                if child.custom_id == job['name']
                                else discord.ButtonStyle.secondary
                            )
                    self_v.stop()
                    await interaction.response.defer()
                return callback

            async def on_timeout(self_v):
                for child in self_v.children:
                    child.disabled = True

        view = JobSelectView()
        msg = await ctx.send(embed=select_embed, view=view)
        await view.wait()

        # Timed out with no selection
        if view.chosen_job is None:
            timeout_embed = discord.Embed(
                title=f"{ECONOMY_EMOJIS['fail']} Shift Expired",
                description="You didn't pick a job in time. Your shift was given to someone else!",
                color=COLORS['error']
            )
            timeout_embed.set_footer(text='No cooldown applied since you didn\'t work.')
            for child in view.children:
                child.disabled = True
            return await msg.edit(embed=timeout_embed, view=view)

        # Job selected — compute pay
        job = view.chosen_job
        earnings = random.randint(job['min'], job['max'])
        scenario = random.choice(job['scenarios'])

        # Apply reward boost if active
        boost_effects = economy_db.get_active_effects(str(ctx.author.id), 'reward_boost')
        boosted = False
        if boost_effects:
            boost_mult = float(boost_effects[0].get('effect_value', 1.0))
            boosted_earnings = int(earnings * boost_mult)
            bonus = boosted_earnings - earnings
            earnings = boosted_earnings
            boosted = True

        # Ensure user account exists
        economy_db.get_user(str(ctx.author.id))

        # Update balance & cooldown
        economy_db.add_earnings(str(ctx.author.id), earnings)
        economy_db.set_cooldown(str(ctx.author.id), 'work', 3600)  # 1 hour
        economy_db.log_transaction(str(ctx.author.id), 'earn', earnings, f'Worked as {job["name"]}')

        # Result embed
        result_embed = discord.Embed(
            title=f"{job['emoji']} Shift Complete — {job['name']}",
            description=f'*{scenario}*',
            color=COLORS['success']
        )
        result_embed.add_field(
            name=f"{ECONOMY_EMOJIS['gem']} Earned",
            value=format_currency(earnings),
            inline=True
        )
        result_embed.add_field(
            name=f"{ECONOMY_EMOJIS['clock']} Next Shift",
            value='In **1 hour**',
            inline=True
        )
        if boosted:
            result_embed.add_field(
                name=f"{ECONOMY_EMOJIS['star']} Reward Boost Active",
                value=f'+{format_currency(bonus)} bonus applied!',
                inline=False
            )
        result_embed.set_footer(
            text=f'Shift completed by {ctx.author.name}',
            icon_url=ctx.author.display_avatar.url
        )
        result_embed.set_thumbnail(url=ctx.author.display_avatar.url)

        # Disable buttons and update message
        await msg.edit(embed=result_embed, view=view)
    
    @commands.command(name='crime')
    async def crime(self, ctx):
        """🔪 Commit a crime (risky!)"""
        # Check cooldown
        cooldown = economy_db.check_cooldown(str(ctx.author.id), 'crime')
        if cooldown > 0:
            return await ctx.send(embed=cooldown_embed('crime', cooldown))
        
        # 40% success rate
        success = random.random() < 0.4
        
        if success:
            reward = random.randint(1000, 5000)
            economy_db.add_earnings(str(ctx.author.id), reward)
            economy_db.log_transaction(str(ctx.author.id), 'earn', reward, 'Successful crime')
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['success']} Crime Successful!",
                description=f"You got away with {format_currency(reward)}!",
                color=COLORS['success'],
                user=ctx.author
            )
        else:
            penalty = random.randint(500, 2000)
            user_data = economy_db.get_user(str(ctx.author.id))
            if not user_data:
                return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Database error! Try again.")
            
            # Can't go negative
            actual_penalty = min(penalty, user_data['wallet'])
            
            economy_db.update_balance(str(ctx.author.id), -actual_penalty, 0)
            economy_db.log_transaction(str(ctx.author.id), 'spend', actual_penalty, 'Failed crime penalty')
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Crime Failed!",
                description=f"You got caught and paid a fine of {format_currency(actual_penalty)}!",
                color=COLORS['error'],
                user=ctx.author
            )
        
        economy_db.set_cooldown(str(ctx.author.id), 'crime', 7200)  # 2 hours
        await ctx.send(embed=embed)
    
    @commands.command(name='rob')
    async def rob(self, ctx, member: discord.Member):
        """💰 Rob another user (risky!)"""
        # Check cooldown
        cooldown = economy_db.check_cooldown(str(ctx.author.id), 'rob')
        if cooldown > 0:
            return await ctx.send(embed=cooldown_embed('rob', cooldown))
        
        # Validation
        if member == ctx.author:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} You cannot rob yourself!")
        
        if member.bot:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} You cannot rob bots!")
        
        # Get target data
        target_data = economy_db.get_user(str(member.id))
        if not target_data:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Could not fetch target's data! Try again.")
        target_wallet = target_data['wallet']
        
        # Check if target has enough money
        if target_wallet < 500:
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Cannot Rob",
                description=f"{member.mention} doesn't have enough money to rob! (Minimum: {format_currency(500)})",
                color=COLORS['error'],
                user=ctx.author
            ))
        
        # Check if target has rob protection
        if economy_db.has_rob_protection(str(member.id)):
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['shield']} Target Protected",
                description=f"{member.mention} has an active Rob Shield! You cannot rob them right now.",
                color=COLORS['error'],
                user=ctx.author
            ))
        
        # Get robber data
        robber_data = economy_db.get_user(str(ctx.author.id))
        if not robber_data:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Could not fetch your data! Try again.")
        
        # 40% success rate
        success = random.random() < 0.4
        
        if success:
            # Calculate stolen amount (10-30% of target's wallet)
            steal_percentage = random.uniform(0.1, 0.3)
            stolen_amount = int(target_wallet * steal_percentage)
            stolen_amount = max(100, min(stolen_amount, 5000))  # Between 100 and 5000
            
            # Transfer money
            economy_db.update_balance(str(member.id), -stolen_amount, 0)
            economy_db.update_balance(str(ctx.author.id), stolen_amount, 0)
            
            # Log transactions
            economy_db.log_transaction(str(ctx.author.id), 'earn', stolen_amount, f'Robbed {member.name}')
            economy_db.log_transaction(str(member.id), 'spend', stolen_amount, f'Robbed by {ctx.author.name}')
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['success']} Robbery Successful!",
                description=f"You successfully robbed {member.mention} and stole {format_currency(stolen_amount)}!\n\n{ECONOMY_EMOJIS['info']} Their bank money is safe!",
                color=COLORS['success'],
                user=ctx.author
            )
            
            # Notify target
            try:
                target_embed = create_economy_embed(
                    title=f"{ECONOMY_EMOJIS['warning']} You Were Robbed!",
                    description=f"{ctx.author.mention} robbed you and stole {format_currency(stolen_amount)}!\n\n{ECONOMY_EMOJIS['info']} Tip: Keep your money in the bank to protect it!",
                    color=COLORS['error']
                )
                await member.send(embed=target_embed)
            except:
                pass  # User has DMs disabled
        else:
            # Failed robbery - pay penalty
            penalty = random.randint(500, 2000)
            actual_penalty = min(penalty, robber_data['wallet'])
            
            economy_db.update_balance(str(ctx.author.id), -actual_penalty, 0)
            economy_db.log_transaction(str(ctx.author.id), 'spend', actual_penalty, 'Failed robbery penalty')
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Robbery Failed!",
                description=f"You got caught trying to rob {member.mention}!\n\n{ECONOMY_EMOJIS['down']} You paid a fine of {format_currency(actual_penalty)}",
                color=COLORS['error'],
                user=ctx.author
            )
        
        # Set cooldown (1 hour)
        economy_db.set_cooldown(str(ctx.author.id), 'rob', 3600)
        await ctx.send(embed=embed)
    
    # ==================== SHOP & INVENTORY ====================
    
    @commands.command(name='shop')
    async def shop(self, ctx):
        """🛒 Browse the shop"""
        from utils.shop_items import get_all_items
        all_items = get_all_items()

        if not all_items:
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['gem']} Shop",
                description=f"{ECONOMY_EMOJIS['info']} The shop is currently empty!",
                color=COLORS['primary']
            )
            return await ctx.send(embed=embed)

        # Build items list from Python dict (always available)
        items = list(all_items.values())
        per_page = 6
        total_pages = (len(items) + per_page - 1) // per_page

        # If only 1 page, no need for buttons
        if total_pages <= 1:
            embed = shop_embed(items, 1, 1)
            return await ctx.send(embed=embed)

        # Paginated view for multiple pages
        class ShopPaginationView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)
                self.current_page = 1
                self.update_buttons()

            def update_buttons(self):
                self.prev_btn.disabled = self.current_page <= 1
                self.next_btn.disabled = self.current_page >= total_pages

            def get_page_items(self):
                start = (self.current_page - 1) * per_page
                end = start + per_page
                return items[start:end]

            @discord.ui.button(label='◀ Previous', style=discord.ButtonStyle.secondary, custom_id='shop_prev')
            async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("This isn't your shop menu!", ephemeral=True)
                self.current_page -= 1
                self.update_buttons()
                embed = shop_embed(self.get_page_items(), self.current_page, total_pages)
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label='Next ▶', style=discord.ButtonStyle.secondary, custom_id='shop_next')
            async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("This isn't your shop menu!", ephemeral=True)
                self.current_page += 1
                self.update_buttons()
                embed = shop_embed(self.get_page_items(), self.current_page, total_pages)
                await interaction.response.edit_message(embed=embed, view=self)

            async def on_timeout(self):
                for child in self.children:
                    child.disabled = True

        view = ShopPaginationView()
        embed = shop_embed(view.get_page_items(), 1, total_pages)
        msg = await ctx.send(embed=embed, view=view)

        # Disable buttons after timeout
        await view.wait()
        for child in view.children:
            child.disabled = True
        try:
            await msg.edit(view=view)
        except:
            pass
    
    @commands.command(name='buy', aliases=['purchase'])
    async def buy(self, ctx, *, item_name: str):
        """💳 Buy an item from the shop"""
        from utils.shop_items import get_item_by_name
        
        # Get item data
        item_data = get_item_by_name(item_name)
        
        if not item_data:
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Item Not Found",
                description=f"Could not find item: **{item_name}**\nUse `,shop` to see available items.",
                color=COLORS['error'],
                user=ctx.author
            ))
        
        # Check user balance
        user_data = economy_db.get_user(str(ctx.author.id))
        if not user_data:
            return await ctx.send(f"{ECONOMY_EMOJIS['fail']} Could not connect to the economy database! Try again later.")
        price = item_data['price']
        
        if user_data['wallet'] < price:
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Insufficient Funds",
                description=f"You need {format_currency(price)} to buy **{item_data['item_name']}**\nYou have: {format_currency(user_data['wallet'])}",
                color=COLORS['error'],
                user=ctx.author
            ))
        
        # Purchase item
        economy_db.update_balance(str(ctx.author.id), -price, 0)
        economy_db.log_transaction(str(ctx.author.id), 'shop_buy', price, f"Bought {item_data['item_name']}")
        
        # Bank Note: auto-activate on purchase (no need for separate ,use step)
        if item_data.get('effect_type') == 'bank_expansion':
            user_id = str(ctx.author.id)
            effect_value = item_data['effect_value']
            existing = economy_db.get_active_effects(user_id, 'bank_expansion')
            if existing:
                old_value = int(existing[0].get('effect_value', 0))
                new_value = old_value + int(effect_value)
                economy_db._exec(
                    "UPDATE economy_active_effects SET effect_value = %s WHERE id = %s",
                    (new_value, existing[0]['id']),
                    commit=True
                )
                total_expansion = new_value
            else:
                economy_db.add_effect(
                    user_id, 'bank_expansion', effect_value,
                    uses_remaining=-1, duration_seconds=-1,
                    item_id=item_data['item_id']
                )
                total_expansion = int(effect_value)
            
            new_bank_limit = 100000 + total_expansion
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['success']} Bank Note Applied!",
                description=(
                    f"You bought and activated {item_data['emoji']} **{item_data['item_name']}** for {format_currency(price)}\n\n"
                    f"🏦 Bank limit increased by **{format_currency(int(effect_value))}**\n"
                    f"📊 New bank limit: **{format_currency(new_bank_limit)}**"
                ),
                color=COLORS['success'],
                user=ctx.author
            )
        else:
            # Normal items: add to inventory, require ,use to activate
            economy_db.add_item(str(ctx.author.id), item_data['item_id'], 1)
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['success']} Purchase Successful!",
                description=f"You bought {item_data['emoji']} **{item_data['item_name']}** for {format_currency(price)}\n\n{ECONOMY_EMOJIS['info']} Use `,use {item_data['item_name']}` to activate it!",
                color=COLORS['success'],
                user=ctx.author
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='use', aliases=['activate'])
    async def use_item(self, ctx, *, item_name: str):
        """✨ Use an item from your inventory"""
        from utils.shop_items import get_item_by_name

        # Get item data from Python dict
        item_data = get_item_by_name(item_name)

        if not item_data:
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Item Not Found",
                description=f"Could not find item: **{item_name}**\nUse `,shop` to see available items.",
                color=COLORS['error'],
                user=ctx.author
            ))

        # Check inventory directly from DB (no guild join needed)
        user_id = str(ctx.author.id)
        inv_row = economy_db._exec(
            "SELECT quantity FROM economy_inventory WHERE user_id = %s AND item_id = %s",
            (user_id, item_data['item_id']),
            fetchone=True
        )

        if not inv_row or inv_row['quantity'] <= 0:
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Item Not Owned",
                description=f"You don't have **{item_data['item_name']}** in your inventory!\nBuy it first with `,buy {item_data['item_name']}`",
                color=COLORS['error'],
                user=ctx.author
            ))

        # Check if effect is already active (for non-stackable items)
        if not item_data.get('stackable', False):
            existing_effects = economy_db.get_active_effects(user_id, item_data['effect_type'])
            if existing_effects:
                return await ctx.send(embed=create_economy_embed(
                    title=f"{ECONOMY_EMOJIS['warning']} Effect Already Active",
                    description=f"You already have an active **{item_data['item_name']}** effect!",
                    color=COLORS['error'],
                    user=ctx.author
                ))

        # Enforce max 2 active game effects at a time
        # Passive/utility effects don't count toward the limit
        NON_GAME_EFFECTS = {'bank_expansion', 'rob_protection', 'reward_boost'}
        if item_data['effect_type'] not in NON_GAME_EFFECTS:
            all_effects = economy_db.get_active_effects(user_id)
            game_effects = [e for e in all_effects if e['effect_type'] not in NON_GAME_EFFECTS]
            if len(game_effects) >= 2:
                return await ctx.send(embed=create_economy_embed(
                    title=f"{ECONOMY_EMOJIS['warning']} Too Many Effects",
                    description=f"You can only have **2 game effects** active at a time!\nWait for your current effects to expire or be used up before activating more.\n\nUse `,effects` to see your active effects.",
                    color=COLORS['error'],
                    user=ctx.author
                ))

        # Remove item from inventory FIRST
        economy_db.remove_item(user_id, item_data['item_id'], 1)

        # Activate item effect
        effect_type = item_data['effect_type']
        effect_value = item_data['effect_value']
        duration = item_data['effect_duration']

        if duration == -1:  # Permanent effect (like bank note)
            # For bank_expansion: consolidate into a single effect row
            if effect_type == 'bank_expansion':
                existing = economy_db.get_active_effects(user_id, 'bank_expansion')
                if existing:
                    # Update existing effect value instead of adding a new row
                    old_value = int(existing[0].get('effect_value', 0))
                    new_value = old_value + int(effect_value)
                    economy_db._exec(
                        "UPDATE economy_active_effects SET effect_value = %s WHERE id = %s",
                        (new_value, existing[0]['id']),
                        commit=True
                    )
                    duration_text = f"Bank limit +{format_currency(int(effect_value))} (Total: +{format_currency(new_value)})"
                else:
                    economy_db.add_effect(
                        user_id, effect_type, effect_value,
                        uses_remaining=-1, duration_seconds=-1,
                        item_id=item_data['item_id']
                    )
                    duration_text = f"Bank limit +{format_currency(int(effect_value))}"
            else:
                economy_db.add_effect(
                    user_id, effect_type, effect_value,
                    uses_remaining=-1, duration_seconds=-1,
                    item_id=item_data['item_id']
                )
                duration_text = "Permanent"
        elif isinstance(duration, int) and duration > 100:  # Time-based (seconds)
            economy_db.add_effect(
                user_id, effect_type, effect_value,
                uses_remaining=-1, duration_seconds=duration,
                item_id=item_data['item_id']
            )
            duration_text = format_time(duration)
        else:  # Use-based (small number = number of uses)
            economy_db.add_effect(
                user_id, effect_type, effect_value,
                uses_remaining=duration, duration_seconds=-1,
                item_id=item_data['item_id']
            )
            duration_text = f"{duration} uses"

        embed = create_economy_embed(
            title=f"{ECONOMY_EMOJIS['success']} Item Activated!",
            description=(
                f"{item_data['emoji']} **{item_data['item_name']}** is now active!\n\n"
                f"{ECONOMY_EMOJIS['info']} Effect: {item_data['description']}\n"
                f"{ECONOMY_EMOJIS['clock']} Duration: {duration_text}"
            ),
            color=COLORS['success'],
            user=ctx.author
        )

        await ctx.send(embed=embed)
    
    @commands.command(name='inventory', aliases=['inv'])
    async def inventory(self, ctx, member: discord.Member = None):
        """🎒 View your inventory"""
        from utils.shop_items import get_item
        user = member or ctx.author

        # Get raw inventory rows (no guild join dependency)
        raw_items = economy_db._exec(
            "SELECT item_id, quantity, purchased_at FROM economy_inventory WHERE user_id = %s AND quantity > 0 ORDER BY purchased_at DESC",
            (str(user.id),),
            fetchall=True
        ) or []

        # Enrich each row with item info from Python SHOP_ITEMS dict
        enriched = []
        for row in raw_items:
            info = get_item(row['item_id'])
            if info:
                enriched.append({
                    'item_id': row['item_id'],
                    'item_name': info['item_name'],
                    'emoji': info['emoji'],
                    'description': info['description'],
                    'quantity': row['quantity'],
                    'item_type': info['item_type'],
                    'price': info['price'],
                })
            else:
                enriched.append({
                    'item_id': row['item_id'],
                    'item_name': row['item_id'].replace('_', ' ').title(),
                    'emoji': '❓',
                    'description': 'Unknown item',
                    'quantity': row['quantity'],
                    'item_type': 'unknown',
                    'price': 0,
                })

        embed = inventory_embed(user, enriched)
        await ctx.send(embed=embed)
    
    @commands.command(name='effects', aliases=['buffs', 'active'])
    async def effects(self, ctx):
        """✨ View your active item effects"""
        # Clean up expired effects first
        economy_db.remove_expired_effects(str(ctx.author.id))
        
        # Get active effects
        effects = economy_db.get_active_effects(str(ctx.author.id))
        
        embed = create_economy_embed(
            title=f"{ECONOMY_EMOJIS['star']} Active Effects",
            color=COLORS['primary'],
            user=ctx.author
        )
        
        if not effects:
            embed.description = f"{ECONOMY_EMOJIS['info']} You don't have any active effects!\n\nUse `,shop` to browse items and `,use <item>` to activate them."
        else:
            from utils.shop_items import get_item
            from datetime import datetime
            
            description = ""
            for effect in effects:
                item_data = get_item(effect.get('item_id', ''))
                emoji = item_data['emoji'] if item_data else '✨'
                effect_name = item_data['item_name'] if item_data else effect['effect_type'].replace('_', ' ').title()
                
                # Calculate remaining time/uses
                if effect['uses_remaining'] > 0:
                    remaining = f"{effect['uses_remaining']} uses left"
                elif effect['expires_at'] > 0:
                    current_time = int(datetime.now().timestamp())
                    time_left = effect['expires_at'] - current_time
                    remaining = f"{format_time(time_left)} remaining"
                else:
                    remaining = "Permanent"
                
                description += f"{emoji} **{effect_name}**\n{ECONOMY_EMOJIS['info']} {remaining}\n\n"
            
            embed.description = description
        
        await ctx.send(embed=embed)
    
    # ==================== LEADERBOARD ====================
    
    @commands.command(name='leaderboard', aliases=['lb', 'top', 'rich'])
    async def leaderboard(self, ctx):
        """🏆 View the richest members"""
        top_users = economy_db.get_leaderboard( 10)
        
        if not top_users:
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['crown']} Leaderboard",
                description=f"{ECONOMY_EMOJIS['info']} No data available yet!",
                color=COLORS['primary']
            )
            return await ctx.send(embed=embed)
        
        embed = leaderboard_embed(ctx.guild, top_users)
        await ctx.send(embed=embed)
    
    # ==================== OWNER ONLY COMMANDS ====================
    
    @commands.command(name='addmoney', aliases=['addbal', 'give$'])
    async def addmoney(self, ctx, member: discord.Member = None, amount: int = None):
        """👑 [OWNER] Add money to a user's wallet"""
        try:
            import config
            
            # Check if user is owner
            if ctx.author.id not in config.OWNER_IDS:
                return await ctx.send(embed=create_economy_embed(
                    title=f"{ECONOMY_EMOJIS['fail']} Permission Denied",
                    description=f"This command is only available to bot owners!\nYour ID: `{ctx.author.id}`\nOwner IDs: `{config.OWNER_IDS}`",
                    color=COLORS['error']
                ))
            
            if not member:
                return await ctx.send(embed=create_economy_embed(
                    title=f"{ECONOMY_EMOJIS['fail']} Missing Member",
                    description=f"Usage: `{PREFIX}addmoney @member <amount>`",
                    color=COLORS['error']
                ))
            
            if not amount or amount <= 0:
                return await ctx.send(embed=create_economy_embed(
                    title=f"{ECONOMY_EMOJIS['fail']} Invalid Amount",
                    description="Amount must be a positive number!",
                    color=COLORS['error']
                ))
            
            # Add money to user's wallet
            economy_db.update_balance(str(member.id), amount, 0)
            economy_db.log_transaction(str(member.id), 'admin_add', amount, f'Admin added by {ctx.author.name}')
            
            embed = create_economy_embed(
                title=f"{ECONOMY_EMOJIS['success']} Money Added",
                description=f"Added {format_currency(amount)} to {member.mention}'s wallet!",
                color=COLORS['success']
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Error in addmoney command: {str(e)}\nPlease check the command usage: `,addmoney @member <amount>`")
    
    
    @commands.command(name='removemoney', aliases=['removebal', 'take$'])
    async def removemoney(self, ctx, member: discord.Member, amount: int):
        """👑 [OWNER] Remove money from a user's wallet"""
        import config
        
        if ctx.author.id not in config.OWNER_IDS:
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Permission Denied",
                description="This command is only available to bot owners!",
                color=COLORS['error']
            ))
        
        if amount <= 0:
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Invalid Amount",
                description="Amount must be positive!",
                color=COLORS['error']
            ))
        
        # Remove money (can go negative)
        economy_db.update_balance(str(member.id), -amount, 0)
        economy_db.log_transaction(str(member.id), 'admin_remove', amount, f'Admin removed by {ctx.author.name}')
        
        embed = create_economy_embed(
            title=f"{ECONOMY_EMOJIS['success']} Money Removed",
            description=f"Removed {format_currency(amount)} from {member.mention}'s wallet!",
            color=COLORS['success']
        )
        await ctx.send(embed=embed)
    
    @commands.command(name='setmoney', aliases=['setbal', 'set$'])
    async def setmoney(self, ctx, member: discord.Member, wallet: int = None, bank: int = None):
        """👑 [OWNER] Set a user's balance

        Usage:
        ,setmoney @user 5000 - Set wallet to 5000
        ,setmoney @user 5000 10000 - Set wallet to 5000 and bank to 10000
        """
        import config
        
        if ctx.author.id not in config.OWNER_IDS:
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Permission Denied",
                description="This command is only available to bot owners!",
                color=COLORS['error']
            ))
        
        if wallet is None:
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Invalid Usage",
                description=f"Usage: `,setmoney @user <wallet> [bank]`\nExample: `,setmoney @user 5000 10000`",
                color=COLORS['error']
            ))
        
        # Set balance directly
        economy_db.set_balance(str(member.id), wallet, bank if bank is not None else 0)
        economy_db.log_transaction(str(member.id), 'admin_set', 0, f'Balance set by {ctx.author.name}')
        
        description = f"Set {member.mention}'s balance:\n"
        description += f"💰 Wallet: {format_currency(wallet)}\n"
        if bank is not None:
            description += f"🏦 Bank: {format_currency(bank)}"
        
        embed = create_economy_embed(
            title=f"{ECONOMY_EMOJIS['success']} Balance Set",
            description=description,
            color=COLORS['success']
        )
        await ctx.send(embed=embed)
    
    @commands.command(name='reseteconomy', aliases=['resetuser', 'eco_reset'])
    async def reseteconomy(self, ctx, member: discord.Member):
        """👑 [OWNER] Reset a user's economy data"""
        import config
        
        if ctx.author.id not in config.OWNER_IDS:
            return await ctx.send(embed=create_economy_embed(
                title=f"{ECONOMY_EMOJIS['fail']} Permission Denied",
                description="This command is only available to bot owners!",
                color=COLORS['error']
            ))
        
        # Reset to starting balance (wallet=1000, bank=0, all stats cleared)
        economy_db.set_balance(str(member.id), 1000, 0, reset_stats=True)
        economy_db.log_transaction(str(member.id), 'admin_remove', 0, f'Economy reset by {ctx.author.name}')
        
        embed = create_economy_embed(
            title=f"{ECONOMY_EMOJIS['success']} Economy Reset",
            description=f"Reset {member.mention}'s economy to starting balance (💎 **1,000** wallet, **0** bank, all stats cleared)!",
            color=COLORS['success']
        )
        await ctx.send(embed=embed)

    def cog_unload(self):
        self.loan_reminder_task.cancel()

    # ==================== LOAN SYSTEM ====================

    @tasks.loop(hours=2)
    async def loan_reminder_task(self):
        """Every 2 hours: ping overdue borrowers (7+ days), auto-deduct penalty at 14 days"""
        try:
            overdue = economy_db.get_all_overdue_loans()
            import time
            now = int(time.time())

            for loan in overdue:
                user_id = int(loan['user_id'])
                loan_id = loan['id']
                days_overdue = (now - loan['taken_at']) // 86400
                ping_count = loan.get('ping_count', 0)
                last_ping = loan.get('last_ping_at', 0)

                # Throttle: only ping if it's been at least 2 hours since last ping
                if now - last_ping < 7200:
                    continue

                user = self.bot.get_user(user_id)

                guild = None
                guild_name = 'a server'

                # --- 14+ days overdue: apply 25% bank penalty ---
                if days_overdue >= 14:
                    penalty = int(loan['total_remaining'] * 0.25)
                    deducted, bank_left = economy_db.apply_loan_penalty(loan_id, penalty)
                    economy_db.update_loan_ping(loan_id, ping_count + 1)

                    if user:
                        try:
                            penalty_embed = discord.Embed(
                                title="⚠️ Loan Penalty Applied!",
                                description=(
                                    f"Your loan of **{loan['amount']:,} 💎** "
                                    f"is **{days_overdue} days overdue**!\n\n"
                                    f"**Penalty (25%):** `{penalty:,}` gems auto-deducted from your bank.\n"
                                    f"**Deducted:** `{deducted:,}` gems\n"
                                    f"**Bank remaining:** `{bank_left:,}` gems\n\n"
                                    f"Use `,payloan <amount>` to pay your debt!"
                                ),
                                color=0xFF0000
                            )
                            penalty_embed.set_footer(text="Pay your loan on time to avoid penalties!")
                            await user.send(embed=penalty_embed)
                        except Exception:
                            pass
                    continue

                # --- 7+ days overdue: ping in DM ---
                if days_overdue >= 7:
                    economy_db.update_loan_ping(loan_id, ping_count + 1)
                    if user:
                        try:
                            reminder_embed = discord.Embed(
                                title="🔔 Loan Payment Overdue!",
                                description=(
                                    f"Hey {user.mention}! Your loan is overdue!\n\n"
                                    f"💰 **Borrowed:** `{loan['amount']:,}` gems\n"
                                    f"📉 **Remaining:** `{loan['total_remaining']:,}` gems\n"
                                    f"⏰ **Days overdue:** `{days_overdue}`\n"
                                    f"💳 **Daily payment:** `{loan['daily_payment']:,}` gems\n\n"
                                    f"Use `,payloan <amount>` to make a payment!\n"
                                    f"⚠️ After 14 days, **25% penalty** will be auto-deducted from your bank!"
                                ),
                                color=0xFFA500
                            )
                            reminder_embed.set_footer(text=f"Ping #{ping_count + 1} • Reminders sent every 2 hours")
                            await user.send(embed=reminder_embed)
                        except Exception:
                            pass
        except Exception as e:
            print(f"[LoanReminder] Error: {e}")

    @loan_reminder_task.before_loop
    async def before_loan_reminder(self):
        await self.bot.wait_until_ready()

    @commands.command(name='loan', aliases=['takeloan', 'borrow'])
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def loan(self, ctx, amount: str = None):
        """Take a loan from the bank (max 500,000 gems)"""
        # get_user auto-creates the account if it doesn't exist
        economy_db.get_user(str(ctx.author.id))

        if not amount:
            embed = discord.Embed(
                title="🏦 Loan System",
                description=(
                    "Borrow gems from the bank and pay them back over time!\n\n"
                    "**Rules:**\n"
                    "• Max loan: `500,000` 💎\n"
                    "• Tax: `10%` on top of the loan\n"
                    "• Daily suggestion: `total ÷ 30`\n"
                    "• Only **1 active loan** at a time\n"
                    "• After 7 days overdue: DM reminders every 2hrs\n"
                    "• After 14 days overdue: 25% auto-deducted from bank\n\n"
                    f"**Usage:** `,loan <amount>`"
                ),
                color=COLORS.get('primary', 0x9b59b6)
            )
            return await ctx.reply(embed=embed)

        # Parse amount
        try:
            amount_clean = amount.replace(',', '').replace('k', '000').replace('K', '000')
            loan_amount = int(float(amount_clean))
        except ValueError:
            return await ctx.reply(embed=discord.Embed(
                title="❌ Invalid Amount",
                description="Please enter a valid number. Example: `,loan 50000`",
                color=COLORS.get('error', 0xe74c3c)
            ))

        if loan_amount <= 0:
            return await ctx.reply(embed=discord.Embed(
                title="❌ Invalid Amount",
                description="Loan amount must be greater than 0!",
                color=COLORS.get('error', 0xe74c3c)
            ))

        if loan_amount > 500000:
            return await ctx.reply(embed=discord.Embed(
                title="❌ Amount Too High",
                description=f"Maximum loan amount is **500,000 💎**! You requested `{loan_amount:,}`.",
                color=COLORS.get('error', 0xe74c3c)
            ))

        success, result = economy_db.take_loan(str(ctx.author.id), loan_amount)

        if not success:
            return await ctx.reply(embed=discord.Embed(
                title="❌ Loan Denied",
                description=str(result),
                color=COLORS.get('error', 0xe74c3c)
            ))

        embed = discord.Embed(
            title="🏦 Loan Approved!",
            description=f"**{loan_amount:,} 💎** has been added to your wallet!",
            color=COLORS.get('success', 0x2ecc71)
        )
        embed.add_field(name="💰 Borrowed", value=f"`{result['amount']:,}` 💎", inline=True)
        embed.add_field(name="💸 Tax (10%)", value=f"`{result['tax']:,}` 💎", inline=True)
        embed.add_field(name="📊 Total to Repay", value=f"`{result['total_with_tax']:,}` 💎", inline=True)
        embed.add_field(name="📅 Suggested Daily Payment", value=f"`{result['daily_payment']:,}` 💎/day", inline=True)
        embed.add_field(
            name="⚠️ Reminders",
            value="After 7 days overdue: DM reminders every 2hrs\nAfter 14 days: 25% bank penalty",
            inline=False
        )
        embed.set_footer(text="Use ,payloan <amount> to make payments • ,loanstatus to check balance")
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.command(name='payloan', aliases=['repaylloan', 'repayloan', 'loanpay'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def payloan(self, ctx, amount: str = None):
        """Pay back your active loan"""
        if not amount:
            return await ctx.reply(embed=discord.Embed(
                title="❌ Missing Amount",
                description="Usage: `,payloan <amount>` — Pay gems from your wallet toward your loan.",
                color=COLORS.get('error', 0xe74c3c)
            ))

        try:
            amount_clean = amount.replace(',', '').replace('k', '000').replace('K', '000')
            pay_amount = int(float(amount_clean))
        except ValueError:
            return await ctx.reply(embed=discord.Embed(
                title="❌ Invalid Amount",
                description="Please enter a valid number.",
                color=COLORS.get('error', 0xe74c3c)
            ))

        if pay_amount <= 0:
            return await ctx.reply(embed=discord.Embed(
                title="❌ Invalid Amount",
                description="Payment must be greater than 0!",
                color=COLORS.get('error', 0xe74c3c)
            ))

        success, msg, data = economy_db.pay_loan(str(ctx.author.id), pay_amount)

        if not success:
            return await ctx.reply(embed=discord.Embed(
                title="❌ Payment Failed",
                description=str(msg),
                color=COLORS.get('error', 0xe74c3c)
            ))

        if msg == 'paid_off':
            embed = discord.Embed(
                title="🎉 Loan Fully Paid Off!",
                description=(
                    f"Congratulations {ctx.author.mention}! You've fully repaid your loan!\n\n"
                    f"**Paid:** `{data['paid']:,}` 💎\n"
                    f"**Remaining:** `0` 💎 ✅\n\n"
                    "You can now take a new loan anytime!"
                ),
                color=COLORS.get('success', 0x2ecc71)
            )
        else:
            embed = discord.Embed(
                title="✅ Payment Made!",
                description=f"Successfully paid `{data['paid']:,}` 💎 toward your loan!",
                color=COLORS.get('success', 0x2ecc71)
            )
            embed.add_field(name="💸 Paid", value=f"`{data['paid']:,}` 💎", inline=True)
            embed.add_field(name="📉 Remaining", value=f"`{data['remaining']:,}` 💎", inline=True)
            embed.set_footer(text="Use ,loanstatus to see full loan details")

        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.command(name='loanstatus', aliases=['myloan', 'loaninfo', 'loan-status'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def loanstatus(self, ctx):
        """Check your current loan status"""
        import time
        loan = economy_db.get_active_loan(str(ctx.author.id))

        if not loan:
            embed = discord.Embed(
                title="🏦 No Active Loan",
                description=(
                    "You don't have an active loan!\n\n"
                    f"Use `,loan <amount>` to borrow up to **500,000 💎**."
                ),
                color=COLORS.get('primary', 0x9b59b6)
            )
            return await ctx.reply(embed=embed)

        now = int(time.time())
        taken_ago = now - loan['taken_at']
        days_borrowed = taken_ago // 86400
        days_overdue = max(0, (now - loan['next_due_at']) // 86400)
        percent_paid = round((1 - loan['total_remaining'] / loan['total_with_tax']) * 100, 1)
        status_icon = "🟢" if days_overdue == 0 else ("🟡" if days_overdue < 7 else "🔴")
        overdue_text = f"**{days_overdue} days overdue** ⚠️" if days_overdue > 0 else "On track ✅"

        embed = discord.Embed(
            title=f"{status_icon} Your Loan Status",
            color=COLORS.get('error', 0xe74c3c) if days_overdue >= 7 else COLORS.get('primary', 0x9b59b6)
        )
        embed.add_field(name="💰 Original Amount", value=f"`{loan['amount']:,}` 💎", inline=True)
        embed.add_field(name="📊 Total with Tax", value=f"`{loan['total_with_tax']:,}` 💎", inline=True)
        embed.add_field(name="📉 Remaining", value=f"`{loan['total_remaining']:,}` 💎", inline=True)
        embed.add_field(name="📅 Daily Suggestion", value=f"`{loan['daily_payment']:,}` 💎/day", inline=True)
        embed.add_field(name="📆 Days Borrowed", value=f"`{days_borrowed}` days", inline=True)
        embed.add_field(name="⏰ Status", value=overdue_text, inline=True)
        embed.add_field(
            name="📊 Progress",
            value=f"{'█' * int(percent_paid // 10)}{'░' * (10 - int(percent_paid // 10))} {percent_paid}% paid",
            inline=False
        )
        if days_overdue >= 7:
            embed.add_field(
                name="⚠️ Warning",
                value=f"You've received `{loan.get('ping_count', 0)}` reminder(s). Penalty auto-deduction starts at 14 days!",
                inline=False
            )
        embed.set_footer(text="Use ,payloan <amount> to make a payment")
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Economy(bot))
