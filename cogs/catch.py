"""
Catch Cog — Universal User Catch System
Catch users across all servers, build teams, and battle!
"""
import discord
from discord.ext import commands
from discord.ui import Button, View, Select
from datetime import datetime, UTC
import random
import os
import asyncio
import sys
import config
import traceback
from utils.embeds import success_embed, error_embed, info_embed

from utils.rarity_system import get_rarity_from_member, get_rarity_info, calculate_stats, RARITY_TIERS
from utils.battle_system import BattleState, BattleView, TYPE_MOVES, DIVINE_MOVES, CELESTIAL_MOVES, create_stat_bar, TYPE_EMOJIS
from utils.card_display import format_card_display, format_userdex_pages

# Add database directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'database'))
from models import Database, CaughtPokemon, BattleTeam, db as _db

# Ensure tables exist
_db.create_tables()

# ============================================================================
# DATABASE HELPER FUNCTIONS (replacing JSON file operations)
# ============================================================================

def _get_user_catches(owner_id):
    """Get all catches for a specific user from database"""
    session = _db.get_session()
    try:
        catches = session.query(CaughtPokemon).filter_by(owner_id=owner_id).all()
        # Convert to dict format — key by DB instance id so duplicate caught_ids
        # (same user caught/traded multiple times) are all preserved
        result = {}
        for catch in catches:
            result[str(catch.id)] = {
                'id': catch.id,                    # DB instance primary key (unique per catch)
                'caught_id': catch.caught_id,      # The Discord user ID who was caught
                'name': catch.name,
                'rarity': catch.rarity,
                'rarity_score': catch.rarity_score,
                'type': catch.pokemon_type,
                'level': catch.level,
                'hp': catch.hp,
                'attack': catch.attack,
                'defense': catch.defense,
                'speed': catch.speed,
                'exp': catch.exp,
                'moves': catch.moves,
                'caught_at': catch.caught_at.isoformat() if catch.caught_at else None
            }
        return result
    finally:
        session.close()

def _get_specific_catch(owner_id, caught_id):
    """Get a specific catch from database"""
    session = _db.get_session()
    try:
        catch = session.query(CaughtPokemon).filter_by(
            owner_id=owner_id,
            caught_id=caught_id
        ).first()
        
        if not catch:
            return None
        
        return {
            'name': catch.name,
            'rarity': catch.rarity,
            'rarity_score': catch.rarity_score,
            'type': catch.pokemon_type,
            'level': catch.level,
            'hp': catch.hp,
            'attack': catch.attack,
            'defense': catch.defense,
            'speed': catch.speed,
            'exp': catch.exp,
            'moves': catch.moves,
            'caught_at': catch.caught_at.isoformat() if catch.caught_at else None
        }
    finally:
        session.close()

def _save_catch(owner_id, caught_id, catch_data):
    """Save a catch to database - Robust Version"""
    session = _db.get_session()
    try:
        # Check if already exists
        existing = session.query(CaughtPokemon).filter_by(
            owner_id=owner_id,
            caught_id=caught_id
        ).first()
        
        if existing:
            # Update existing
            existing.name = catch_data.get('name', existing.name)
            existing.rarity = catch_data.get('rarity', existing.rarity)
            existing.rarity_score = catch_data.get('rarity_score', existing.rarity_score)
            existing.pokemon_type = catch_data.get('type', existing.pokemon_type)
            existing.level = catch_data.get('level', existing.level)
            existing.hp = catch_data.get('hp', existing.hp)
            existing.attack = catch_data.get('attack', existing.attack)
            existing.defense = catch_data.get('defense', existing.defense)
            existing.speed = catch_data.get('speed', existing.speed)
            existing.exp = catch_data.get('exp', existing.exp)
            existing.moves = catch_data.get('moves', existing.moves)
        else:
            # Create new
            new_catch = CaughtPokemon(
                owner_id=owner_id,
                caught_id=caught_id,
                name=catch_data.get('name', 'Unknown'),
                rarity=catch_data.get('rarity', 'Common'),
                rarity_score=catch_data.get('rarity_score', 0),
                pokemon_type=catch_data.get('type', 'Normal'),
                level=catch_data.get('level', 1),
                hp=catch_data.get('hp', 100),
                attack=catch_data.get('attack', 50),
                defense=catch_data.get('defense', 50),
                speed=catch_data.get('speed', 50),
                exp=catch_data.get('exp', 0),
                moves=catch_data.get('moves', [])
            )
            session.add(new_catch)
        
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"Error saving catch: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()

def _delete_catch(owner_id, caught_id, catch_id=None):
    """Delete a catch from database"""
    session = _db.get_session()
    try:
        query = session.query(CaughtPokemon).filter_by(
            owner_id=owner_id,
            caught_id=caught_id
        )
        if catch_id is not None:
            query = query.filter_by(id=catch_id)

        # Lock and revalidate ownership in the deleting transaction. This
        # prevents a release confirmed by the old owner from deleting a catch
        # after a concurrent trade has transferred it to somebody else.
        catch = query.order_by(CaughtPokemon.id).with_for_update().first()
        if catch:
            session.delete(catch)
            deleted = 1
        else:
            deleted = 0
        session.commit()
        return deleted > 0
    except Exception as e:
        session.rollback()
        print(f"Error deleting catch: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()

def _get_user_team(user_id):
    """Get user's battle team from database"""
    session = _db.get_session()
    try:
        team = session.query(BattleTeam).filter_by(user_id=user_id).first()
        
        if not team:
            return {}
        
        result = {}
        if team.slot1_id:
            catch = session.query(CaughtPokemon).filter_by(id=team.slot1_id).first()
            if catch:
                result['slot1'] = str(catch.caught_id)
        
        if team.slot2_id:
            catch = session.query(CaughtPokemon).filter_by(id=team.slot2_id).first()
            if catch:
                result['slot2'] = str(catch.caught_id)
        
        if team.slot3_id:
            catch = session.query(CaughtPokemon).filter_by(id=team.slot3_id).first()
            if catch:
                result['slot3'] = str(catch.caught_id)
        
        return result
    finally:
        session.close()

def _save_user_team(user_id, team_data):
    """Save user's battle team to database"""
    session = _db.get_session()
    try:
        team = session.query(BattleTeam).filter_by(user_id=user_id).first()
        
        # Get Pokemon IDs from caught_id values
        slot1_id = None
        slot2_id = None
        slot3_id = None
        
        if 'slot1' in team_data and team_data['slot1']:
            catch = session.query(CaughtPokemon).filter_by(
                owner_id=user_id,
                caught_id=int(team_data['slot1'])
            ).first()
            if catch:
                slot1_id = catch.id
        
        if 'slot2' in team_data and team_data['slot2']:
            catch = session.query(CaughtPokemon).filter_by(
                owner_id=user_id,
                caught_id=int(team_data['slot2'])
            ).first()
            if catch:
                slot2_id = catch.id
        
        if 'slot3' in team_data and team_data['slot3']:
            catch = session.query(CaughtPokemon).filter_by(
                owner_id=user_id,
                caught_id=int(team_data['slot3'])
            ).first()
            if catch:
                slot3_id = catch.id
        
        if team:
            # Update existing team
            team.slot1_id = slot1_id
            team.slot2_id = slot2_id
            team.slot3_id = slot3_id
            team.updated_at = datetime.now(UTC)
        else:
            # Create new team
            team = BattleTeam(
                user_id=user_id,
                slot1_id=slot1_id,
                slot2_id=slot2_id,
                slot3_id=slot3_id
            )
            session.add(team)
        
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"Error saving team: {e}")
        return False
    finally:
        session.close()

# User types
_TYPES = [
    "Fire", "Water", "Grass", "Electric", "Psychic",
    "Dark", "Ghost", "Dragon", "Fairy", "Ice",
    "Fighting", "Poison", "Steel", "Ground", "Rock", "Flying"
]

# ============================================================================
# USERDEX PAGINATION VIEW
# ============================================================================

class UserdexView(View):
    """Paginated view for userdex with full navigation."""

    def __init__(self, pages: list, author: discord.Member):
        super().__init__(timeout=120)
        self.pages = pages
        self.current_page = 0
        self.author = author
        self.message = None
        self._update_buttons()

    def _update_buttons(self):
        is_first = self.current_page == 0
        is_last = self.current_page >= len(self.pages) - 1
        self.first_btn.disabled = is_first
        self.prev_btn.disabled = is_first
        self.next_btn.disabled = is_last
        self.last_btn.disabled = is_last
        self.page_btn.label = f"{self.current_page + 1}/{len(self.pages)}"

    async def _check_author(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your userdex!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label='<<', style=discord.ButtonStyle.primary)
    async def first_btn(self, interaction: discord.Interaction, button: Button):
        if not await self._check_author(interaction):
            return
        self.current_page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label='<', style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: Button):
        if not await self._check_author(interaction):
            return
        self.current_page = max(0, self.current_page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label='1/1', style=discord.ButtonStyle.secondary, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

    @discord.ui.button(label='>', style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: Button):
        if not await self._check_author(interaction):
            return
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label='>>', style=discord.ButtonStyle.primary)
    async def last_btn(self, interaction: discord.Interaction, button: Button):
        if not await self._check_author(interaction):
            return
        self.current_page = len(self.pages) - 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass



class ReleaseConfirmView(discord.ui.View):
    def __init__(self, ctx, member, fail_embed):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.member = member
        self.fail_embed = fail_embed
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Release", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        success = _delete_catch(self.ctx.author.id, self.member.id)
        
        if success:
            embed = success_embed(
                "User Released!",
                f"**{self.member.display_name}** has been released back to the wild!\n"
                f"You can catch them again with `{config.PREFIX}throwball {self.member.mention}`"
            )
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.edit_message(embed=self.fail_embed, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        embed = info_embed("Release Cancelled", f"**{self.member.display_name}** remains in your collection.")
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

class Catch(commands.Cog):
    """Catch users! Build teams and battle!"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx):
        """Remove cooldowns for bot owners."""
        if ctx.author.id in config.OWNER_IDS:
            ctx.command.reset_cooldown(ctx)


    # ──────────────────────────── throwball ────────────────────────────
    @commands.command(name="throwball", aliases=["catch"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def throwball(self, ctx, member: discord.Member = None):
        """Throw a ball at a user — rarity-based catch chance!

        Usage: ,throwball @user
        """
        if not member:
            return await ctx.reply(embed=error_embed(
                "Missing Target",
                f"Usage: `{config.PREFIX}throwball @user`",
            ))

        if member.bot:
            return await ctx.reply(embed=error_embed(
                "Can't Catch Bots", "Nice try — bots are immune!"
            ))

        if member.id == ctx.author.id:
            return await ctx.reply(embed=error_embed(
                "Self Catch?", "You can't throw a ball at yourself!"
            ))

        # Check if already caught (universal check using database)
        existing_catch = _get_specific_catch(ctx.author.id, member.id)
        
        if existing_catch:
            return await ctx.reply(embed=error_embed(
                "Already Caught!",
                f"You've already caught **{member.display_name}**!\n"
                f"Use `{config.PREFIX}inspect {member.mention}` to view their stats."
            ))

        # Catch rate: 90% for owners, 80% for co-owners, rarity-based for everyone else
        if ctx.author.id in config.OWNER_IDS:
            catch_rate = 0.90  # 90% for bot owners
        elif ctx.author.id in config.CO_OWNER_IDS:
            catch_rate = 0.80  # 80% for co-owners
        else:
            # Rarity-based catch rates — rarer users are harder to catch
            rarity = get_rarity_from_member(member)
            rarity_catch_rates = {
                'Common': 0.30,     # 30%
                'Rare': 0.20,       # 20%
                'Epic': 0.12,       # 12%
                'Legendary': 0.08,  # 8%
                'Mythic': 0.05,     # 5%
                'Celestial': 0.04,  # 4% (co-owner targets)
                'Divine': 0.02,     # 2% (owner targets)
            }
            catch_rate = rarity_catch_rates.get(rarity, 0.15)
        
        caught = random.random() < catch_rate

        # ── Multi-phase catch animation ──
        THROW_MSGS = [
            f"💫 **{ctx.author.display_name}** winds up and hurls a ball at **{member.display_name}**!",
            f"🌟 **{ctx.author.display_name}** launches a ball straight at **{member.display_name}**!",
            f"⚡ **{ctx.author.display_name}** throws with incredible force at **{member.display_name}**!",
        ]
        WIGGLE_MSGS = ['🔴 *...wiggle...*', '🟡 *...wiggle...*', '🟢 *...wiggle...*']
        MISS_FLAVOR = [
            f"😤 **{member.display_name}** spotted the ball and sidestepped at the last second!",
            f"💨 A sudden gust of wind knocked the ball off course!",
            f"🤸 **{member.display_name}** does a backflip and dodges completely!",
            f"✋ **{member.display_name}** caught your ball and threw it back at you!",
            f"🏃 **{member.display_name}** sprinted away at lightning speed!",
            f"🛡️ **{member.display_name}** blocked the ball with their bare hands!",
            f"🪞 The ball bounced off **{member.display_name}**'s sheer aura!",
            f"😎 **{member.display_name}** casually stepped aside like it was nothing!",
        ]

        # Phase 1: Throw
        throw_embed = discord.Embed(
            title="🎯 Throwing Ball...",
            description=random.choice(THROW_MSGS),
            color=0xf1c40f
        )
        throw_embed.set_thumbnail(url=member.display_avatar.url)
        throw_msg = await ctx.reply(embed=throw_embed)

        await asyncio.sleep(1.2)

        # Phase 2: Wiggle (1-3 times)
        num_wiggles = random.randint(1, 3)
        wiggle_text = random.choice(THROW_MSGS)
        for i in range(num_wiggles):
            wiggle_text += f"\n{WIGGLE_MSGS[i]}"
            wiggle_embed = discord.Embed(
                title="🎯 Catching...",
                description=wiggle_text,
                color=0xf39c12
            )
            wiggle_embed.set_thumbnail(url=member.display_avatar.url)
            await throw_msg.edit(embed=wiggle_embed)
            await asyncio.sleep(1.0)

        if not caught:
            miss_embed = discord.Embed(
                title="💨 Escaped!",
                description=random.choice(MISS_FLAVOR),
                color=config.COLORS['error'],
            )
            miss_embed.set_thumbnail(url=member.display_avatar.url)
            miss_embed.set_footer(text="Better luck next time...")
            return await throw_msg.edit(embed=miss_embed)

        # ---- Generate User Stats ----
        # Determine rarity based on role
        rarity = get_rarity_from_member(member)
        rarity_info = get_rarity_info(rarity)
        
        # Base stats
        account_age = (datetime.now(UTC) - member.created_at).days
        base_hp = min(999, 100 + account_age)
        base_attack = random.randint(30, 120)
        base_defense = random.randint(20, 100)
        base_speed = random.randint(10, 110)
        
        # Apply rarity multiplier
        final_stats = calculate_stats(base_hp, base_attack, base_defense, base_speed, rarity)
        
        # Assign type and moves
        pokemon_type = random.choice(_TYPES)
        
        # Divine rarity gets special moves
        if rarity == 'Divine':
            moves = DIVINE_MOVES
        elif rarity == 'Celestial':
            moves = CELESTIAL_MOVES
        else:
            moves = TYPE_MOVES.get(pokemon_type, ["Tackle", "Scratch", "Pound", "Quick Attack"])

        # Create card embed with stat bars
        card_embed = discord.Embed(
            title=f"{rarity_info['emoji']} ✨ CAUGHT! — {member.display_name}",
            description=(
                f"*A wild **{rarity} {member.display_name}** was caught by {ctx.author.mention}!*\n\n"
                f"```\n"
                f"╔══════════════════════════╗\n"
                f"║  {member.display_name[:20]:^24}  ║\n"
                f"╚══════════════════════════╝\n"
                f"```"
            ),
            color=rarity_info['color'],
        )
        card_embed.set_thumbnail(url=member.display_avatar.url)
        card_embed.add_field(name="Rarity", value=f"{rarity_info['emoji']} `{rarity}`", inline=True)
        card_embed.add_field(name="Type", value=f"{TYPE_EMOJIS.get(pokemon_type, '⭐')} `{pokemon_type}`", inline=True)
        card_embed.add_field(name="Level", value="`1`", inline=True)
        card_embed.add_field(
            name="📊 Stats",
            value=(
                f"```\n"
                f"❤️ HP  {create_stat_bar(final_stats['hp'])}\n"
                f"⚔️ ATK {create_stat_bar(final_stats['attack'])}\n"
                f"🛡️ DEF {create_stat_bar(final_stats['defense'])}\n"
                f"⚡ SPD {create_stat_bar(final_stats['speed'])}\n"
                f"```"
            ),
            inline=False
        )
        card_embed.add_field(name="🎯 Moves", value=" • ".join([f"`{m}`" for m in moves[:4]]), inline=False)
        card_embed.set_footer(text=f"Account age: {account_age} days • xiel Catch")

        # Show the card embed immediately — don't block on DB write
        await throw_msg.edit(embed=card_embed)

        # Persist card to database in the background (non-blocking)
        catch_data = {
            'name': member.display_name,
            'rarity': rarity,
            'rarity_score': rarity_info.get('score', 0),
            'type': pokemon_type,
            'hp': final_stats['hp'],
            'attack': final_stats['attack'],
            'defense': final_stats['defense'],
            'speed': final_stats['speed'],
            'moves': moves[:4],
            'level': 1,
            'exp': 0
        }
        asyncio.create_task(asyncio.to_thread(_save_catch, ctx.author.id, member.id, catch_data))

    @throwball.error
    async def throwball_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(embed=error_embed(
                "Cooldown",
                f"You can throw again in **{int(error.retry_after)}s**.",
            ))

    # ──────────────────────────── userdex ──────────────────────────────
    @commands.command(name="userdex", aliases=["pokedex", "cards", "collection"])
    async def userdex(self, ctx, member: discord.Member = None):
        """View your (or someone's) universal user collection

        Usage: ,userdex [@user]
        """
        target = member or ctx.author
        caught_pokemon = _get_user_catches(target.id)

        if not caught_pokemon:
            return await ctx.reply(embed=info_embed(
                "Empty Userdex",
                f"{'You have' if target == ctx.author else f'{target.display_name} has'} "
                f"not caught anyone yet!\nUse `{config.PREFIX}throwball @user` to start.",
            ))

        # Convert to list format for display function
        # Each value dict already contains 'id' (instance PK) and 'caught_id' (Discord user ID)
        catches_list = list(caught_pokemon.values())

        # Get paginated embeds
        pages = format_userdex_pages(catches_list, target, self.bot)

        if len(pages) == 1:
            return await ctx.reply(embed=pages[0])

        # Multi-page: use interactive view
        view = UserdexView(pages, ctx.author)
        view.message = await ctx.reply(embed=pages[0], view=view)

    # ──────────────────────────── gameinfo ──────────────────────────────
    @commands.command(name="gameinfo", aliases=["catchinfo", "howtoplay"])
    async def gameinfo(self, ctx):
        """Learn how the User Catch System works

        Usage: ,gameinfo
        """
        embed = discord.Embed(
            title="🎮 User Catch System - Complete Guide",
            description=(
                "Catch users, build teams, battle, and level up!\n\n"
                "**📋 All Commands:**\n"
            ),
            color=0xFFD700
        )
        
        embed.add_field(
            name="🎯 Core Commands",
            value=(
                f"`{config.PREFIX}throwball @user` - Catch a user (rarity-based rate, 90% for owners)\n"
                f"`{config.PREFIX}userdex [@user]` - View collection\n"
                f"`{config.PREFIX}inspect @user` - View detailed stats\n"
                f"`{config.PREFIX}release @user` - Release a caught user\n"
                f"`{config.PREFIX}gameinfo` - Show this guide"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚔️ Battle Commands",
            value=(
                f"`{config.PREFIX}team` - View your battle team\n"
                f"`{config.PREFIX}setteam @u1 @u2 @u3` - Set 3v3 team\n"
                f"`{config.PREFIX}battle @user` - Challenge to battle\n"
                f"`{config.PREFIX}train @user` - Train for EXP (1hr cooldown)"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔄 Trading Commands",
            value=(
                f"`{config.PREFIX}trade @user` - Start a trade\n"
                f"`{config.PREFIX}offer @user` - Offer a caught user\n"
                f"`{config.PREFIX}unoffer @user` - Remove offer\n"
                f"`{config.PREFIX}confirm` - Confirm trade (both must confirm)\n"
                f"`{config.PREFIX}canceltrade` - Cancel active trade"
            ),
            inline=False
        )
        
        embed.add_field(
            name="✨ Rarity Tiers",
            value=(
                "⚪ **Common** - 1.0x stats\n"
                "🟢 **Rare** - 1.2x stats\n"
                "🟣 **Epic** - 1.4x stats\n"
                "🟡 **Legendary** - 1.6x stats\n"
                "🔴 **Mythic** - 1.8x stats\n"
                "✨ **Divine** - 2.5x stats (Owner Only!)"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📈 Leveling & Battles",
            value=(
                "• Train: 10-30 EXP (1hr cooldown)\n"
                "• Battles: 50-100 EXP\n"
                "• Level up: +5-10 all stats\n"
                "• Max level: 100\n"
                "• Type advantages matter!\n"
                "• Visual health bars"
            ),
            inline=True
        )
        
        # Only show owner commands to bot owners
        if ctx.author.id in config.OWNER_IDS:
            embed.add_field(
                name="🔐 Owner Commands",
                value=(
                    f"`{config.PREFIX}stealuser @user @caught` - Steal from collection\n"
                    f"`{config.PREFIX}deletepokemon @user @caught` - Delete from collection"
                ),
                inline=False
            )
        
        embed.set_footer(text="Catch rates: 30% Common | 20% Rare | 12% Epic | 8% Legendary | 5% Mythic | 90% Owners")
        
        await ctx.reply(embed=embed)

    # ──────────────────────────── inspect ──────────────────────────────
    @commands.command(name="inspect", aliases=["view", "pokestats"])
    async def inspect(self, ctx, member: discord.Member = None):
        """View detailed stats of a caught user

        Usage: ,inspect @user
        """
        if not member:
            return await ctx.reply(embed=error_embed(
                "Missing Target",
                f"Usage: `{config.PREFIX}inspect @user`",
            ))

        try:
            data = _get_specific_catch(ctx.author.id, member.id)

            if not data:
                return await ctx.reply(embed=error_embed(
                    "Not Caught",
                    f"You haven't caught **{member.display_name}** yet!\n"
                    f"Use `{config.PREFIX}throwball {member.mention}` to catch them."
                ))
            rarity = data.get('rarity', 'Common')
            rarity_info = get_rarity_info(rarity)

            # Use professional card display
            embed = format_card_display(data, member, rarity_info)
            
            await ctx.reply(embed=embed)
        except Exception as e:
            print(f"Inspect Logic Error: {e}")
            await ctx.reply(embed=error_embed("Error", f"An unexpected error occurred: {e}"))

    @inspect.error
    async def inspect_error(self, ctx, error):
        if isinstance(error, commands.MemberNotFound):
            await ctx.reply(embed=error_embed(
                "User Not Found",
                f"Could not find a user with that ID/Name in this server."
            ))
        elif isinstance(error, commands.BadArgument):
            await ctx.reply(embed=error_embed(
                "Invalid Argument",
                f"Please provide a valid user mention or ID.\nUsage: `{config.PREFIX}inspect @user`"
            ))
        else:
            print(f"Inspect Error: {error}")

    # ──────────────────────────── release ──────────────────────────────
    @commands.command(name="release", aliases=["free"])
    async def release(self, ctx, member: discord.Member = None):
        """Release a caught user back to the wild
        
        Usage: ,release @user
        """
        if not member:
            return await ctx.reply(embed=error_embed(
                "Missing Target",
                f"Usage: `{config.PREFIX}release @user`",
            ))

        data = _get_specific_catch(ctx.author.id, member.id)

        if not data:
            return await ctx.reply(embed=error_embed(
                "Not Caught",
                f"You haven't caught **{member.display_name}** yet!"
            ))

        # Confirmation step
        fail_embed = error_embed("Release Failed", "An error occurred while trying to release this user.")
        view = ReleaseConfirmView(ctx, member, fail_embed)
        
        embed = discord.Embed(
            title="⚠️ Release Confirmation",
            description=(
                f"Are you sure you want to release **{member.display_name}**?\n"
                "This action cannot be undone and you will lose this caught user forever."
            ),
            color=config.COLORS['warning']
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        view.message = await ctx.reply(embed=embed, view=view)

    # ──────────────────────────── team ──────────────────────────────
    @commands.command(name="team", aliases=["myteam"])
    async def team(self, ctx):
        """View your current battle team

        Usage: ,team
        """
        team_data = _get_user_team(ctx.author.id)

        if not team_data:
            return await ctx.reply(embed=info_embed(
                "No Team Set",
                f"You haven't set up a battle team yet!\n"
                f"Use `{config.PREFIX}setteam @user1 @user2 @user3` to create your team."
            ))

        embed = discord.Embed(
            title=f"⚔️ {ctx.author.display_name}'s Battle Team",
            description="Your 3v3 battle team:",
            color=config.COLORS['primary']
        )

        for i in range(1, 4):
            slot_key = f"slot{i}"
            if slot_key in team_data:
                caught_id = int(team_data[slot_key])
                data = _get_specific_catch(ctx.author.id, caught_id)
                if data:
                    rarity_emoji = RARITY_TIERS[data.get('rarity', 'Common')]['emoji']
                    embed.add_field(
                        name=f"{i}. {rarity_emoji} {data.get('name', 'Unknown')}",
                        value=f"Lv.{data.get('level', 1)} {data.get('type', 'Normal')} • HP: {data.get('hp', 0)}",
                        inline=False
                    )

        await ctx.reply(embed=embed)

    # ──────────────────────────── setteam ──────────────────────────────
    @commands.command(name="setteam", aliases=["buildteam"])
    async def setteam(self, ctx, member1: discord.Member = None, member2: discord.Member = None, member3: discord.Member = None):
        """Set your 3v3 battle team

        Usage: ,setteam @user1 @user2 @user3
        """
        if not all([member1, member2, member3]):
            return await ctx.reply(embed=error_embed(
                "Invalid Team",
                f"You need to specify 3 users!\n"
                f"Usage: `{config.PREFIX}setteam @user1 @user2 @user3`"
            ))

        # Validate all are caught
        team_members = [member1, member2, member3]
        team_data = {}
        
        for i, member in enumerate(team_members, 1):
            data = _get_specific_catch(ctx.author.id, member.id)
            if not data:
                return await ctx.reply(embed=error_embed(
                    "User Not Caught",
                    f"You haven't caught **{member.display_name}** yet!\n"
                    f"Catch them first with `{config.PREFIX}throwball {member.mention}`"
                ))
            team_data[f"slot{i}"] = str(member.id)

        # Save team
        _save_user_team(ctx.author.id, team_data)

        # Show confirmation
        embed = discord.Embed(
            title="✅ Team Set!",
            description="Your battle team has been configured:",
            color=config.COLORS['success']
        )

        for i in range(1, 4):
            slot_key = f"slot{i}"
            if slot_key in team_data:
                caught_id = int(team_data[slot_key])
                data = _get_specific_catch(ctx.author.id, caught_id)
                if data:
                    rarity_emoji = RARITY_TIERS[data.get('rarity', 'Common')]['emoji']
                    embed.add_field(
                        name=f"{i}. {rarity_emoji} {data.get('name', 'Unknown')}",
                        value=f"Lv.{data.get('level', 1)} {data.get('type', 'Normal')}",
                        inline=True
                    )

        await ctx.reply(embed=embed)

    # ──────────────────────────── battle ──────────────────────────────
    @commands.command(name="battle", aliases=["fight", "duel"])
    async def battle(self, ctx, opponent: discord.Member = None):
        """Challenge someone to a 3v3 battle!

        Usage: ,battle @user
        """
        if not opponent:
            return await ctx.reply(embed=error_embed(
                "Missing Opponent",
                f"Usage: `{config.PREFIX}battle @user`"
            ))

        if opponent.id == ctx.author.id:
            return await ctx.reply(embed=error_embed(
                "Self Battle?",
                "You can't battle yourself!"
            ))

        if opponent.bot:
            return await ctx.reply(embed=error_embed(
                "Can't Battle Bots",
                "Bots don't participate in battles!"
            ))

        # Check both players have teams
        p1_team_data = _get_user_team(ctx.author.id)
        p2_team_data = _get_user_team(opponent.id)

        if not p1_team_data:
            return await ctx.reply(embed=error_embed(
                "No Team",
                f"You need to set up your team first!\n"
                f"Use `{config.PREFIX}setteam @user1 @user2 @user3`"
            ))

        if not p2_team_data:
            return await ctx.reply(embed=error_embed(
                "Opponent Has No Team",
                f"**{opponent.display_name}** hasn't set up their team yet!"
            ))

        # Load both teams
        p1_team = []
        p2_team = []

        for i in range(1, 4):
            slot_key = f"slot{i}"
            if slot_key in p1_team_data:
                data = _get_specific_catch(ctx.author.id, int(p1_team_data[slot_key]))
                if data:
                    p1_team.append(data)
            
            if slot_key in p2_team_data:
                data = _get_specific_catch(opponent.id, int(p2_team_data[slot_key]))
                if data:
                    p2_team.append(data)

        if len(p1_team) < 3 or len(p2_team) < 3:
            return await ctx.reply(embed=error_embed(
                "Invalid Team",
                "Both players need 3 valid users in their team!"
            ))

        # Start battle
        battle_state = BattleState(
            ctx.author.id, p1_team,
            opponent.id, p2_team,
            p1_name=ctx.author.display_name,
            p2_name=opponent.display_name
        )
        embed = battle_state.create_battle_embed()
        view = BattleView(battle_state)

        await ctx.reply(embed=embed, view=view)


    # ──────────────────────────── TRADING SYSTEM ──────────────────────────────
    
    # Active trades: {(user1_id, user2_id): {trade_data}}
    active_trades = {}
    
    @commands.command(name="trade")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def trade(self, ctx, partner: discord.Member = None):
        """Initiate a user trade with another user (mutual trading only!)
        
        Usage: ,trade @user
        """
        if not partner or partner.bot or partner == ctx.author:
            return await ctx.reply(embed=error_embed(
                "Invalid Partner",
                f"Usage: `{config.PREFIX}trade @user`\nYou can't trade with yourself or bots!"
            ))
        
        # Check if either user has an active trade
        for (u1, u2) in list(self.active_trades.keys()):
            if ctx.author.id in (u1, u2) or partner.id in (u1, u2):
                return await ctx.reply(embed=error_embed(
                    "Trade in Progress",
                    "One of you already has an active trade! Complete or cancel it first."
                ))
        
        # Create trade
        trade_key = tuple(sorted([ctx.author.id, partner.id]))
        trade_state = {
            'initiator': ctx.author.id,
            'partner': partner.id,
            'user1_offers': [],
            'user2_offers': [],
            'user1_confirmed': False,
            'user2_confirmed': False,
            'started_at': datetime.now(),
            'channel_id': ctx.channel.id
        }
        self.active_trades[trade_key] = trade_state
        
        embed = discord.Embed(
            title="🔄 Trade Initiated!",
            description=(
                f"{ctx.author.mention} wants to trade with {partner.mention}!\n\n"
                f"**How to trade:**\n"
                f"• `{config.PREFIX}offer @user` - Offer a caught user\n"
                f"• `{config.PREFIX}unoffer @user` - Remove offer\n"
                f"• `{config.PREFIX}confirm` - Confirm trade (both must confirm)\n"
                f"• `{config.PREFIX}canceltrade` - Cancel trade\n\n"
                "⚠️ **Both users MUST offer at least 1 caught user!**\n"
                "Trade expires in 2 minutes."
            ),
            color=0x3498db
        )
        
        await ctx.reply(embed=embed)
        
        # Auto-cancel after 2 minutes
        await asyncio.sleep(120)
        # Only expire the trade created by this command. The same pair may
        # have completed it and opened a newer trade before this timer wakes.
        if self.active_trades.get(trade_key) is trade_state:
            self.active_trades.pop(trade_key, None)
            try:
                await ctx.send(embed=info_embed("Trade Expired", "The trade timed out."))
            except:
                pass
    
    @commands.command(name="offer")
    async def offer(self, ctx, pokemon: discord.Member = None):
        """Offer a caught user in an active trade
        
        Usage: ,offer @user
        """
        if not pokemon:
            return await ctx.reply(embed=error_embed(
                "Missing User",
                f"Usage: `{config.PREFIX}offer @user`"
            ))
        
        # Find active trade
        trade_key = None
        for key in self.active_trades.keys():
            if ctx.author.id in key:
                trade_key = key
                break
        
        if not trade_key:
            return await ctx.reply(embed=error_embed(
                "No Active Trade",
                f"You don't have an active trade! Start one with `{config.PREFIX}trade @user`"
            ))
        
        trade = self.active_trades[trade_key]
        offer_list = 'user1_offers' if ctx.author.id == trade_key[0] else 'user2_offers'
        
        # Check if user owns this Pokemon (unoffered duplicate instance)
        session = _db.get_session()
        try:
            catches = session.query(CaughtPokemon).filter_by(
                owner_id=ctx.author.id,
                caught_id=pokemon.id
            ).all()
            
            offered_ids = [int(x) for x in trade[offer_list]]
            available_catch = None
            for c in catches:
                if c.id not in offered_ids:
                    available_catch = c
                    break
            
            if not available_catch:
                if catches:
                    return await ctx.reply(embed=error_embed(
                        "Already Offered",
                        f"You've already offered all your copies of **{pokemon.display_name}**!"
                    ))
                else:
                    return await ctx.reply(embed=error_embed(
                        "Not Owned",
                        f"You don't own **{pokemon.display_name}**!"
                    ))
            
            if len(trade[offer_list]) >= 3:
                return await ctx.reply(embed=error_embed(
                    "Max Offers",
                    "You can only offer up to 3 users per trade!"
                ))
            
            # Add unique database row ID as string
            trade[offer_list].append(str(available_catch.id))
        finally:
            session.close()
        
        # Reset confirmations
        trade['user1_confirmed'] = False
        trade['user2_confirmed'] = False
        
        await self._show_trade_preview(ctx, trade_key)
    
    @commands.command(name="unoffer")
    async def unoffer(self, ctx, pokemon: discord.Member = None):
        """Remove a caught user from your trade offer
        
        Usage: ,unoffer @user
        """
        if not pokemon:
            return await ctx.reply(embed=error_embed(
                "Missing User",
                f"Usage: `{config.PREFIX}unoffer @user`"
            ))
        
        # Find active trade
        trade_key = None
        for key in self.active_trades.keys():
            if ctx.author.id in key:
                trade_key = key
                break
        
        if not trade_key:
            return await ctx.reply(embed=error_embed(
                "No Active Trade",
                "You don't have an active trade!"
            ))
        
        trade = self.active_trades[trade_key]
        offer_list = 'user1_offers' if ctx.author.id == trade_key[0] else 'user2_offers'
        
        session = _db.get_session()
        try:
            offered_instance_to_remove = None
            for offered_str_id in trade[offer_list]:
                c = session.query(CaughtPokemon).filter_by(id=int(offered_str_id)).first()
                if c and c.caught_id == pokemon.id:
                    offered_instance_to_remove = offered_str_id
                    break
            
            if not offered_instance_to_remove:
                return await ctx.reply(embed=error_embed(
                    "Not Offered",
                    f"You haven't offered **{pokemon.display_name}**!"
                ))
            
            trade[offer_list].remove(offered_instance_to_remove)
        finally:
            session.close()
        
        # Reset confirmations
        trade['user1_confirmed'] = False
        trade['user2_confirmed'] = False
        
        await self._show_trade_preview(ctx, trade_key)
    
    @commands.command(name="confirm")
    async def confirm_trade(self, ctx):
        """Confirm your side of the trade
        
        Usage: ,confirm
        """
        # Find active trade
        trade_key = None
        for key in self.active_trades.keys():
            if ctx.author.id in key:
                trade_key = key
                break
        
        if not trade_key:
            return await ctx.reply(embed=error_embed(
                "No Active Trade",
                "You don't have an active trade!"
            ))
        
        trade = self.active_trades[trade_key]
        
        # Check both sides have offers
        if not trade['user1_offers'] or not trade['user2_offers']:
            return await ctx.reply(embed=error_embed(
                "Empty Offers",
                "⚠️ **Both users must offer at least 1 caught user!**\nNo one-sided trades allowed."
            ))
        
        # Set confirmation
        if ctx.author.id == trade_key[0]:
            trade['user1_confirmed'] = True
        else:
            trade['user2_confirmed'] = True
        
        # Check if both confirmed
        if trade['user1_confirmed'] and trade['user2_confirmed']:
            await self._execute_trade(ctx, trade_key)
        else:
            await ctx.reply(embed=info_embed(
                "Confirmed!",
                f"{ctx.author.mention} confirmed! Waiting for the other user..."
            ))
    
    @commands.command(name="canceltrade")
    async def cancel_trade(self, ctx):
        """Cancel your active trade
        
        Usage: ,canceltrade
        """
        # Find and remove active trade
        trade_key = None
        for key in self.active_trades.keys():
            if ctx.author.id in key:
                trade_key = key
                break
        
        if not trade_key:
            return await ctx.reply(embed=error_embed(
                "No Active Trade",
                "You don't have an active trade!"
            ))
        
        del self.active_trades[trade_key]
        await ctx.reply(embed=success_embed(
            "Trade Cancelled",
            "The trade has been cancelled."
        ))
    
    async def _show_trade_preview(self, ctx, trade_key):
        """Show current trade preview"""
        trade = self.active_trades[trade_key]
        
        user1 = self.bot.get_user(trade_key[0])
        user2 = self.bot.get_user(trade_key[1])
        
        session = _db.get_session()
        try:
            # Get Pokemon names
            user1_pokemon = []
            for pid in trade['user1_offers']:
                c = session.query(CaughtPokemon).filter_by(id=int(pid)).first()
                if c:
                    p = self.bot.get_user(c.caught_id)
                    name = p.display_name if p else f"User#{c.caught_id}"
                    user1_pokemon.append(f"{name} (Lv.{c.level} {c.rarity})")
                else:
                    user1_pokemon.append(f"Unknown Catch #{pid}")
            
            user2_pokemon = []
            for pid in trade['user2_offers']:
                c = session.query(CaughtPokemon).filter_by(id=int(pid)).first()
                if c:
                    p = self.bot.get_user(c.caught_id)
                    name = p.display_name if p else f"User#{c.caught_id}"
                    user2_pokemon.append(f"{name} (Lv.{c.level} {c.rarity})")
                else:
                    user2_pokemon.append(f"Unknown Catch #{pid}")
        finally:
            session.close()
        
        embed = discord.Embed(
            title="🔄 Trade Preview",
            description=(
                f"**{user1.display_name}'s Offers:**\n"
                f"{chr(10).join(['• ' + p for p in user1_pokemon]) if user1_pokemon else '*(none)*'}\n\n"
                f"**{user2.display_name}'s Offers:**\n"
                f"{chr(10).join(['• ' + p for p in user2_pokemon]) if user2_pokemon else '*(none)*'}\n\n"
                f"✅ {user1.display_name}: {'Confirmed' if trade['user1_confirmed'] else 'Not confirmed'}\n"
                f"✅ {user2.display_name}: {'Confirmed' if trade['user2_confirmed'] else 'Not confirmed'}\n\n"
                f"Use `{config.PREFIX}confirm` to confirm when ready!"
            ),
            color=0x3498db
        )
        
        channel = self.bot.get_channel(trade['channel_id'])
        if channel:
            await channel.send(embed=embed)
    
    async def _execute_trade(self, ctx, trade_key):
        """Execute the trade swap atomically after revalidating every offer."""
        trade = self.active_trades.get(trade_key)
        if not trade:
            return

        try:
            user1_offer_ids = [int(db_id) for db_id in trade['user1_offers']]
            user2_offer_ids = [int(db_id) for db_id in trade['user2_offers']]
        except (KeyError, TypeError, ValueError):
            self.active_trades.pop(trade_key, None)
            return await ctx.send(embed=error_embed(
                "Trade Cancelled",
                "The trade offers were no longer valid. No Pokemon were moved."
            ))

        all_offer_ids = user1_offer_ids + user2_offer_ids
        if (not user1_offer_ids or not user2_offer_ids or
                len(set(all_offer_ids)) != len(all_offer_ids)):
            self.active_trades.pop(trade_key, None)
            return await ctx.send(embed=error_embed(
                "Trade Cancelled",
                "The trade offers were no longer valid. No Pokemon were moved."
            ))
        
        session = _db.get_session()
        try:
            # Lock every offered row in one transaction. If a release or
            # another trade changed an offer, the ownership check below sees
            # the committed result before anything is transferred.
            locked_catches = (
                session.query(CaughtPokemon)
                .filter(CaughtPokemon.id.in_(all_offer_ids))
                .order_by(CaughtPokemon.id)
                .with_for_update()
                .all()
            )
            catches_by_id = {catch.id: catch for catch in locked_catches}

            offers_are_current = (
                len(locked_catches) == len(all_offer_ids) and
                all(
                    db_id in catches_by_id and
                    catches_by_id[db_id].owner_id == trade_key[0]
                    for db_id in user1_offer_ids
                ) and
                all(
                    db_id in catches_by_id and
                    catches_by_id[db_id].owner_id == trade_key[1]
                    for db_id in user2_offer_ids
                )
            )
            if not offers_are_current:
                session.rollback()
                self.active_trades.pop(trade_key, None)
                return await ctx.send(embed=error_embed(
                    "Trade Cancelled",
                    "One or more offered Pokemon is missing or changed owners. "
                    "No Pokemon were moved."
                ))

            for db_id in user1_offer_ids:
                catches_by_id[db_id].owner_id = trade_key[1]
            for db_id in user2_offer_ids:
                catches_by_id[db_id].owner_id = trade_key[0]
            
            session.commit()
        except Exception as e:
            session.rollback()
            self.active_trades.pop(trade_key, None)
            print(f"Error executing trade: {e}")
            traceback.print_exc()
            return await ctx.send(embed=error_embed(
                "Trade Error",
                "An error occurred while executing the trade database update. "
                "No Pokemon were moved."
            ))
        finally:
            session.close()
        
        # Remove trade
        self.active_trades.pop(trade_key, None)
        
        user1 = self.bot.get_user(trade_key[0])
        user2 = self.bot.get_user(trade_key[1])
        
        embed = discord.Embed(
            title="✅ Trade Complete!",
            description=(
                f"{user1.mention} and {user2.mention} successfully traded Pokemon!\n\n"
                f"**{user1.display_name} received:** {len(trade['user2_offers'])} Pokemon\n"
                f"**{user2.display_name} received:** {len(trade['user1_offers'])} Pokemon"
            ),
            color=0x2ecc71
        )
        
        await ctx.send(embed=embed)


    # ──────────────────────────── TRAINING & LEVELING ──────────────────────────────
    
    @commands.command(name="train")
    async def train(self, ctx, pokemon: discord.Member = None):
        """Train a caught user to gain EXP (1 hour cooldown)
        
        Usage: ,train @user
        """
        if not pokemon:
            return await ctx.reply(embed=error_embed(
                "Missing User",
                f"Usage: `{config.PREFIX}train @user`\n"
                "Train one of your caught users to gain EXP!"
            ))
        
        # Check ownership
        pokemon_data = _get_specific_catch(ctx.author.id, pokemon.id)
        
        if not pokemon_data:
            return await ctx.reply(embed=error_embed(
                "Not Owned",
                f"You don't own **{pokemon.display_name}**!"
            ))
        
        from utils.leveling_system import award_exp, get_training_exp_reward, exp_to_next_level
        
        # Award training EXP (10-30)
        exp_gained = get_training_exp_reward()
        result = award_exp(pokemon_data, exp_gained)
        
        # Save updated data
        _save_catch(ctx.author.id, pokemon.id, pokemon_data)
        
        # Build response
        embed = discord.Embed(
            title="🏋️ Training Complete!",
            description=f"**{pokemon.display_name}** gained **{exp_gained} EXP** from training!",
            color=0x3498db
        )
        
        if result['leveled_up']:
            # Level up!
            embed.color = 0xf1c40f
            embed.title = "⭐ LEVEL UP!"
            embed.description = (
                f"**{pokemon.display_name}** leveled up!\n"
                f"**Level {result['old_level']} → {result['new_level']}**\n\n"
                f"**Stat Gains:**\n"
                f"❤️ HP: +{result['stat_gains']['hp']}\n"
                f"⚔️ ATK: +{result['stat_gains']['attack']}\n"
                f"🛡️ DEF: +{result['stat_gains']['defense']}\n"
                f"⚡ SPD: +{result['stat_gains']['speed']}"
            )
        else:
            # Show progress
            current_level = pokemon_data['level']
            exp_needed = exp_to_next_level(pokemon_data['exp'], current_level)
            embed.add_field(
                name="Progress",
                value=f"Level {current_level} | {exp_needed} EXP to next level",
                inline=False
            )
        
        await ctx.reply(embed=embed)
    
    @train.error
    async def train_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            minutes = int(error.retry_after // 60)
            seconds = int(error.retry_after % 60)
            await ctx.reply(embed=error_embed(
                "Training Cooldown",
                f"You can train again in **{minutes}m {seconds}s**."
            ))


    # ──────────────────────────── OWNER COMMANDS ──────────────────────────────
    
    @commands.command(name="stealuser", aliases=["stealpokemon"])
    async def steal_pokemon(self, ctx, target: discord.Member = None, pokemon: discord.Member = None):
        """[OWNER ONLY] Steal a caught user from any user
        
        Usage: ,stealuser @user @caughtuser
        """
        if ctx.author.id not in config.OWNER_IDS:
             return await ctx.reply(embed=error_embed("Permission Denied", "This command is for bot owners only."))

        if not target or not pokemon:
            return await ctx.reply(embed=error_embed(
                "Missing Arguments",
                f"Usage: `{config.PREFIX}stealuser @user @caughtuser`\n"
                "Steal a caught user from a user's collection."
            ))
        
        # Check if target owns this user (using database)
        pokemon_data = _get_specific_catch(target.id, pokemon.id)
        
        if not pokemon_data:
            return await ctx.reply(embed=error_embed(
                "Not Found",
                f"**{target.display_name}** doesn't own **{pokemon.display_name}**!"
            ))
        
        # Steal: remove from target, add to owner
        _delete_catch(target.id, pokemon.id)
        _save_catch(ctx.author.id, pokemon.id, pokemon_data)
        
        embed = discord.Embed(
            title="🔥 User Stolen!",
            description=(
                f"**{ctx.author.display_name}** stole **{pokemon.display_name}** "
                f"from **{target.display_name}**!\n\n"
                f"Rarity: {pokemon_data.get('rarity', 'Unknown')}"
            ),
            color=0xe74c3c
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="deletepokemon", aliases=["delpoke"])
    async def delete_pokemon(self, ctx, target: discord.Member = None, pokemon: discord.Member = None):
        """[OWNER ONLY] Delete a caught user from any user's collection
        
        Usage: ,deletepokemon @user @caughtuser
        """
        if ctx.author.id not in config.OWNER_IDS:
             return await ctx.reply(embed=error_embed("Permission Denied", "This command is for bot owners only."))

        if not target or not pokemon:
            return await ctx.reply(embed=error_embed(
                "Missing Arguments",
                f"Usage: `{config.PREFIX}deletepokemon @user @caughtuser`\n"
                "Remove a caught user from a user's collection."
            ))
        
        # Check if target owns this user (using database)
        pokemon_data = _get_specific_catch(target.id, pokemon.id)
        
        if not pokemon_data:
            return await ctx.reply(embed=error_embed(
                "Not Found",
                f"**{target.display_name}** doesn't own **{pokemon.display_name}**!"
            ))
        
        # Delete from database
        _delete_catch(target.id, pokemon.id)
        
        embed = discord.Embed(
            title="🗑️ User Deleted!",
            description=(
                f"Removed **{pokemon.display_name}** ({pokemon_data.get('rarity', 'Unknown')}) "
                f"from **{target.display_name}**'s collection."
            ),
            color=0x95a5a6
        )
        
        await ctx.reply(embed=embed)

    @commands.command(name="giveuser", aliases=["givepoke", "gift", "give"])
    async def give_user(self, ctx, target: discord.Member = None, pokemon: discord.Member = None):
        """[OWNER ONLY] Give any user to someone's collection
        
        Usage: ,giveuser @target @user
        Generates stats automatically.
        """
        if ctx.author.id not in config.OWNER_IDS:
             return await ctx.reply(embed=error_embed("Permission Denied", "This command is for bot owners only."))

        if not target or not pokemon:
            return await ctx.reply(embed=error_embed(
                "Missing Arguments",
                f"Usage: `{config.PREFIX}giveuser @target @user`\n"
                "Gives a user to someone's collection with auto-generated stats."
            ))

        if pokemon.bot:
            return await ctx.reply(embed=error_embed("Can't Give Bots", "Bots can't be added to collections."))

        # Check if target already has this user
        existing = _get_specific_catch(target.id, pokemon.id)
        if existing:
            return await ctx.reply(embed=error_embed(
                "Already Owned",
                f"**{target.display_name}** already has **{pokemon.display_name}**!"
            ))

        # Auto-generate stats
        rarity = get_rarity_from_member(pokemon)
        rarity_info = get_rarity_info(rarity)
        account_age = (datetime.now(UTC) - pokemon.created_at).days
        base_hp = min(999, 100 + account_age)
        base_attack = random.randint(30, 120)
        base_defense = random.randint(20, 100)
        base_speed = random.randint(10, 110)
        final_stats = calculate_stats(base_hp, base_attack, base_defense, base_speed, rarity)
        pokemon_type = random.choice(_TYPES)

        if rarity == 'Divine':
            moves = DIVINE_MOVES
        elif rarity == 'Celestial':
            moves = CELESTIAL_MOVES
        else:
            moves = TYPE_MOVES.get(pokemon_type, ["Tackle", "Scratch", "Pound", "Quick Attack"])

        catch_data = {
            'name': pokemon.display_name,
            'rarity': rarity,
            'rarity_score': rarity_info.get('score', 0),
            'type': pokemon_type,
            'hp': final_stats['hp'],
            'attack': final_stats['attack'],
            'defense': final_stats['defense'],
            'speed': final_stats['speed'],
            'moves': moves[:4],
            'level': 1,
            'exp': 0
        }
        _save_catch(target.id, pokemon.id, catch_data)

        embed = discord.Embed(
            title=f"{rarity_info['emoji']} User Gifted!",
            description=(
                f"**{pokemon.display_name}** ({rarity}) has been added to "
                f"**{target.display_name}**'s collection!"
            ),
            color=rarity_info['color']
        )
        embed.set_thumbnail(url=pokemon.display_avatar.url)
        embed.add_field(name="Rarity", value=f"{rarity_info['emoji']} `{rarity}`", inline=True)
        embed.add_field(name="Type", value=f"`{pokemon_type}`", inline=True)
        embed.add_field(name="Stats", value=(
            f"HP: `{final_stats['hp']}` | ATK: `{final_stats['attack']}` | "
            f"DEF: `{final_stats['defense']}` | SPD: `{final_stats['speed']}`"
        ), inline=False)
        embed.set_footer(text=f"Gifted by {ctx.author.display_name}")
        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Catch(bot))

