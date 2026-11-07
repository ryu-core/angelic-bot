"""
Roleplay Commands Cog
Fun interaction commands with GIF animations
Multi-source GIF fetching: waifu.pics → nekos.best → otakugifs.xyz → static fallbacks
"""

import discord
from discord.ext import commands
import random
import aiohttp
from utils.embeds import create_embed
import config


# ─── GIF Source Mappings ───────────────────────────────────────────────────────

# Source 1 — waifu.pics  (returns {"url": "..."})
WAIFU_PICS = {
    'kiss':     'https://api.waifu.pics/sfw/kiss',
    'hug':      'https://api.waifu.pics/sfw/hug',
    'pat':      'https://api.waifu.pics/sfw/pat',
    'cry':      'https://api.waifu.pics/sfw/cry',
    'slap':     'https://api.waifu.pics/sfw/slap',
    'dance':    'https://api.waifu.pics/sfw/dance',
    'cuddle':   'https://api.waifu.pics/sfw/cuddle',
    'poke':     'https://api.waifu.pics/sfw/poke',
    'bite':     'https://api.waifu.pics/sfw/bite',
    'wave':     'https://api.waifu.pics/sfw/wave',
    'smile':    'https://api.waifu.pics/sfw/smile',
    'wink':     'https://api.waifu.pics/sfw/wink',
    'bonk':     'https://api.waifu.pics/sfw/bonk',
    'highfive': 'https://api.waifu.pics/sfw/highfive',
    'sleep':    'https://api.waifu.pics/sfw/sleepy',
    'nom':      'https://api.waifu.pics/sfw/nom',
    'blush':    'https://api.waifu.pics/sfw/blush',
    'smug':     'https://api.waifu.pics/sfw/smug',
    'happy':    'https://api.waifu.pics/sfw/happy',
    'bully':    'https://api.waifu.pics/sfw/bully',
    'kick':     'https://api.waifu.pics/sfw/kick',
    'kill':     'https://api.waifu.pics/sfw/kill',
    'stare':    'https://api.waifu.pics/sfw/stare',
    'nuzzle':   'https://api.waifu.pics/sfw/nuzzle',
    'lick':     'https://api.waifu.pics/sfw/lick',
    'punch':    'https://api.waifu.pics/sfw/punch',
    'tickle':   'https://api.waifu.pics/sfw/tickle',
    'hold':     'https://api.waifu.pics/sfw/hold',
    'laugh':    'https://api.waifu.pics/sfw/happy',
    'shout':    'https://api.waifu.pics/sfw/yeet',
    'drool':    'https://api.waifu.pics/sfw/nom',
    'airkiss':  'https://api.waifu.pics/sfw/kiss',
    'sad':      'https://api.waifu.pics/sfw/cry',
    'facepalm': 'https://api.waifu.pics/sfw/facepalm',
    'confused': 'https://api.waifu.pics/sfw/confused',
    'carry':    'https://api.waifu.pics/sfw/hug',
    'throw':    'https://api.waifu.pics/sfw/yeet',
}

# Source 2 — nekos.best  (returns {"results": [{"url": "..."}]})
NEKOS_BEST = {
    'kiss':     'https://nekos.best/api/v2/kiss',
    'hug':      'https://nekos.best/api/v2/hug',
    'pat':      'https://nekos.best/api/v2/pat',
    'cry':      'https://nekos.best/api/v2/cry',
    'slap':     'https://nekos.best/api/v2/slap',
    'laugh':    'https://nekos.best/api/v2/laugh',
    'cuddle':   'https://nekos.best/api/v2/cuddle',
    'poke':     'https://nekos.best/api/v2/poke',
    'bite':     'https://nekos.best/api/v2/bite',
    'wave':     'https://nekos.best/api/v2/wave',
    'smile':    'https://nekos.best/api/v2/smile',
    'wink':     'https://nekos.best/api/v2/wink',
    'highfive': 'https://nekos.best/api/v2/highfive',
    'sleep':    'https://nekos.best/api/v2/sleep',
    'nuzzle':   'https://nekos.best/api/v2/nuzzle',
    'blush':    'https://nekos.best/api/v2/blush',
    'nom':      'https://nekos.best/api/v2/nom',
    'bully':    'https://nekos.best/api/v2/bully',
    'kick':     'https://nekos.best/api/v2/kick',
    'punch':    'https://nekos.best/api/v2/punch',
    'smug':     'https://nekos.best/api/v2/smug',
    'happy':    'https://nekos.best/api/v2/happy',
    'sad':      'https://nekos.best/api/v2/sad',
    'facepalm': 'https://nekos.best/api/v2/facepalm',
    'confused': 'https://nekos.best/api/v2/confused',
    'tickle':   'https://nekos.best/api/v2/tickle',
    'lick':     'https://nekos.best/api/v2/lick',
    'stare':    'https://nekos.best/api/v2/stare',
    'dance':    'https://nekos.best/api/v2/dance',
    'bonk':     'https://nekos.best/api/v2/bonk',
    'kill':     'https://nekos.best/api/v2/shoot',     # closest match
    'shout':    'https://nekos.best/api/v2/angry',
    'drool':    'https://nekos.best/api/v2/nom',
    'airkiss':  'https://nekos.best/api/v2/kiss',
    'carry':    'https://nekos.best/api/v2/hug',
    'throw':    'https://nekos.best/api/v2/angry',
    'hold':     'https://nekos.best/api/v2/hug',
}

# Source 3 — otakugifs.xyz  (returns {"link": "..."})
OTAKU_GIFS = {
    'kiss':     'https://api.otakugifs.xyz/gif?reaction=kiss',
    'hug':      'https://api.otakugifs.xyz/gif?reaction=hug',
    'pat':      'https://api.otakugifs.xyz/gif?reaction=pat',
    'cry':      'https://api.otakugifs.xyz/gif?reaction=cry',
    'slap':     'https://api.otakugifs.xyz/gif?reaction=slap',
    'laugh':    'https://api.otakugifs.xyz/gif?reaction=laugh',
    'cuddle':   'https://api.otakugifs.xyz/gif?reaction=cuddle',
    'poke':     'https://api.otakugifs.xyz/gif?reaction=poke',
    'bite':     'https://api.otakugifs.xyz/gif?reaction=bite',
    'wave':     'https://api.otakugifs.xyz/gif?reaction=wave',
    'smile':    'https://api.otakugifs.xyz/gif?reaction=smile',
    'wink':     'https://api.otakugifs.xyz/gif?reaction=wink',
    'bonk':     'https://api.otakugifs.xyz/gif?reaction=bonk',
    'sleep':    'https://api.otakugifs.xyz/gif?reaction=sleep',
    'nuzzle':   'https://api.otakugifs.xyz/gif?reaction=nuzzle',
    'blush':    'https://api.otakugifs.xyz/gif?reaction=blush',
    'dance':    'https://api.otakugifs.xyz/gif?reaction=dance',
    'happy':    'https://api.otakugifs.xyz/gif?reaction=happy',
    'sad':      'https://api.otakugifs.xyz/gif?reaction=sad',
    'smug':     'https://api.otakugifs.xyz/gif?reaction=smug',
    'confused': 'https://api.otakugifs.xyz/gif?reaction=confused',
    'facepalm': 'https://api.otakugifs.xyz/gif?reaction=facepalm',
    'tickle':   'https://api.otakugifs.xyz/gif?reaction=tickle',
    'lick':     'https://api.otakugifs.xyz/gif?reaction=lick',
    'stare':    'https://api.otakugifs.xyz/gif?reaction=stare',
    'punch':    'https://api.otakugifs.xyz/gif?reaction=punch',
    'kick':     'https://api.otakugifs.xyz/gif?reaction=kick',
    'kill':     'https://api.otakugifs.xyz/gif?reaction=shoot',
    'shout':    'https://api.otakugifs.xyz/gif?reaction=angry',
    'highfive': 'https://api.otakugifs.xyz/gif?reaction=highfive',
    'drool':    'https://api.otakugifs.xyz/gif?reaction=drool',
    'airkiss':  'https://api.otakugifs.xyz/gif?reaction=kiss',
    'carry':    'https://api.otakugifs.xyz/gif?reaction=hug',
    'throw':    'https://api.otakugifs.xyz/gif?reaction=throw',
    'hold':     'https://api.otakugifs.xyz/gif?reaction=hug',
    'nom':      'https://api.otakugifs.xyz/gif?reaction=nom',
    'bully':    'https://api.otakugifs.xyz/gif?reaction=bully',
}

# Source 4 — reliable static fallbacks (always available)
STATIC_FALLBACKS = {
    'kiss': [
        'https://media.tenor.com/HRYCKFEzHwcAAAAC/anime-kiss.gif',
        'https://media.tenor.com/8V6sBRExjdEAAAAC/kiss-anime.gif',
    ],
    'hug': [
        'https://media.tenor.com/cbGLaFAEWSAAAAAC/anime-hug.gif',
        'https://media.tenor.com/3hAs6r_vXlUAAAAC/anime-hug.gif',
    ],
    'pat': [
        'https://media.tenor.com/PPmNkNHPdRkAAAAC/anime-headpat.gif',
        'https://media.tenor.com/4bYFpFMXeE0AAAAC/kawaii-pat.gif',
    ],
    'cry': [
        'https://media.tenor.com/ZVbBJahrVSUAAAAC/anime-cry.gif',
        'https://media.tenor.com/vrmFv_xYQy4AAAAC/crying-anime.gif',
    ],
    'slap': [
        'https://media.tenor.com/NoZHjkHiI5kAAAAC/slap-anime.gif',
        'https://media.tenor.com/4B54ISCF4PoAAAAC/anime-slap.gif',
    ],
    'dance': [
        'https://media.tenor.com/ZobJlmBFd8IAAAAC/anime-dance.gif',
        'https://media.tenor.com/9kXjPGPLBdAAAAAC/anime-dance.gif',
    ],
    'kill': [
        'https://media.tenor.com/GcuTrFe4HHIAAAAC/anime-sword.gif',
        'https://media.tenor.com/UJSJgJI4pJkAAAAC/anime-fight.gif',
        'https://media.tenor.com/q5VIv9JjBkMAAAAC/anime-fight.gif',
    ],
    'cuddle': [
        'https://media.tenor.com/h8mWy0b1R1MAAAAC/anime-cuddle.gif',
    ],
    'poke': [
        'https://media.tenor.com/E_Ot9ghK0gcAAAAC/poke-anime.gif',
    ],
    'bite': [
        'https://media.tenor.com/vCVVqlSZ_I8AAAAC/anime-bite.gif',
    ],
    'wave': [
        'https://media.tenor.com/h4hP-jjBi-UAAAAC/wave-anime.gif',
    ],
    'smile': [
        'https://media.tenor.com/AeZAYUCL_bcAAAAC/anime-smile.gif',
    ],
    'wink': [
        'https://media.tenor.com/GtXFzqOVt0IAAAAC/wink-anime.gif',
    ],
    'bonk': [
        'https://media.tenor.com/ZhMHcbkn-ZIAAAAC/bonk-anime.gif',
    ],
    'highfive': [
        'https://media.tenor.com/l8-W_Z3TbzsAAAAC/anime-high-five.gif',
    ],
    'sleep': [
        'https://media.tenor.com/gd_2bw8bS3cAAAAC/anime-sleep.gif',
        'https://media.tenor.com/w2bPv42EwnwAAAAC/anime-sleeping.gif',
    ],
    'laugh': [
        'https://media.tenor.com/K3lmRkTdVD8AAAAC/anime-laugh.gif',
    ],
    'blush': [
        'https://media.tenor.com/pMnXfKpSsuoAAAAC/anime-blush.gif',
    ],
    'nuzzle': [
        'https://media.tenor.com/NZbgr8gMdscAAAAC/anime-nuzzle.gif',
    ],
    'stare': [
        'https://media.tenor.com/gKt6U9t_LvQAAAAC/anime-stare.gif',
    ],
    'punch': [
        'https://media.tenor.com/tUk3ZJ7aVjgAAAAC/anime-punch.gif',
    ],
    'tickle': [
        'https://media.tenor.com/INb6NRTMITcAAAAC/anime-tickle.gif',
    ],
    'lick': [
        'https://media.tenor.com/0D_-Sgu6GLUAAAAC/anime-lick.gif',
    ],
    'smug': [
        'https://media.tenor.com/VopRQAhEfKAAAAAC/smug-anime.gif',
    ],
    'facepalm': [
        'https://media.tenor.com/WS3X1iLBq_QAAAAC/facepalm-anime.gif',
    ],
    'confused': [
        'https://media.tenor.com/pPYMGH5Mw_AAAAAC/anime-confused.gif',
    ],
    'happy': [
        'https://media.tenor.com/OUqFQFIfvBkAAAAC/anime-happy.gif',
    ],
    'sad': [
        'https://media.tenor.com/vrmFv_xYQy4AAAAC/crying-anime.gif',
    ],
    'shout': [
        'https://media.tenor.com/BrS5JKQTZ1EAAAAC/anime-angry.gif',
    ],
    'drool': [
        'https://media.tenor.com/nKVSG0_fmR0AAAAC/anime-drool.gif',
    ],
    'bully': [
        'https://media.tenor.com/NoZHjkHiI5kAAAAC/slap-anime.gif',
    ],
    'nom': [
        'https://media.tenor.com/LDX7cKFXPMIAAAAC/anime-nom.gif',
    ],
    'carry': [
        'https://media.tenor.com/cbGLaFAEWSAAAAAC/anime-hug.gif',
    ],
    'throw': [
        'https://media.tenor.com/BrS5JKQTZ1EAAAAC/anime-angry.gif',
    ],
    'hold': [
        'https://media.tenor.com/h8mWy0b1R1MAAAAC/anime-cuddle.gif',
    ],
    'kick': [
        'https://media.tenor.com/tUk3ZJ7aVjgAAAAC/anime-punch.gif',
    ],
    'airkiss': [
        'https://media.tenor.com/HRYCKFEzHwcAAAAC/anime-kiss.gif',
    ],
}


class Roleplay(commands.Cog):
    """Roleplay and interaction commands with multi-source GIF support"""

    def __init__(self, bot):
        self.bot = bot

    # ─── Core GIF Fetcher ─────────────────────────────────────────────────────

    async def _try_waifu_pics(self, session: aiohttp.ClientSession, action: str):
        """Attempt to fetch a GIF from waifu.pics. Returns (url, 'waifu.pics') or None."""
        endpoint = WAIFU_PICS.get(action)
        if not endpoint:
            return None
        try:
            async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    url = data.get('url')
                    if url:
                        return url, 'waifu.pics'
        except Exception as e:
            print(f"[RP] waifu.pics failed for '{action}': {e}")
        return None

    async def _try_nekos_best(self, session: aiohttp.ClientSession, action: str):
        """Attempt to fetch a GIF from nekos.best. Returns (url, 'nekos.best') or None."""
        endpoint = NEKOS_BEST.get(action)
        if not endpoint:
            return None
        try:
            async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    results = data.get('results', [])
                    if results:
                        url = results[0].get('url')
                        if url:
                            return url, 'nekos.best'
        except Exception as e:
            print(f"[RP] nekos.best failed for '{action}': {e}")
        return None

    async def _try_otaku_gifs(self, session: aiohttp.ClientSession, action: str):
        """Attempt to fetch a GIF from otakugifs.xyz. Returns (url, 'otakugifs') or None."""
        endpoint = OTAKU_GIFS.get(action)
        if not endpoint:
            return None
        try:
            async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    url = data.get('link') or data.get('url')
                    if url:
                        return url, 'otakugifs.xyz'
        except Exception as e:
            print(f"[RP] otakugifs.xyz failed for '{action}': {e}")
        return None

    async def get_gif(self, action: str):
        """
        Fetch a GIF URL from multiple sources in priority order:
          1. waifu.pics
          2. nekos.best
          3. otakugifs.xyz
          4. static curated fallbacks

        Returns (gif_url: str, source: str) or (None, None).
        """
        async with aiohttp.ClientSession() as session:
            result = await self._try_waifu_pics(session, action)
            if result:
                return result

            result = await self._try_nekos_best(session, action)
            if result:
                return result

            result = await self._try_otaku_gifs(session, action)
            if result:
                return result

        # Static fallback (no HTTP needed)
        fallbacks = STATIC_FALLBACKS.get(action)
        if fallbacks:
            return random.choice(fallbacks), 'static'

        return None, None

    # ─── Embed Builder ────────────────────────────────────────────────────────

    def build_embed(self, description: str, color: int, gif_url: str,
                    source: str, footer_text: str, author: discord.Member):
        """Build a standardised roleplay embed with GIF + source-aware footer."""
        embed = discord.Embed(description=description, color=color)
        if gif_url:
            embed.set_image(url=gif_url)
        src_label = f' | GIF: {source}' if source and source != 'static' else ''
        embed.set_footer(
            text=f'{footer_text}{src_label}',
            icon_url=author.display_avatar.url
        )
        return embed

    # ══════════════════════════════════════════════════════════════════════════
    # ─── Commands ─────────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    # ── Kiss ──────────────────────────────────────────────────────────────────
    @commands.command(name='kiss')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def kiss(self, ctx, member: discord.Member = None):
        """Kiss someone special! 💋\n\nUsage: ,kiss @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Kiss?',
                description=f'Mention someone to kiss!\n**Usage:** `{config.PREFIX}kiss @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Self Love? 💕',
                description="You can't kiss yourself, silly!"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Awkward...', description="Bots don't appreciate kisses!"
            ))

        gif_url, source = await self.get_gif('kiss')
        embed = self.build_embed(
            f"💋 **{ctx.author.mention} kissed {member.mention}!**",
            0xff69b4, gif_url, source,
            f"Mwah! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Hug ───────────────────────────────────────────────────────────────────
    @commands.command(name='hug')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def hug(self, ctx, member: discord.Member = None):
        """Give someone a warm hug! 🤗\n\nUsage: ,hug @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Hug?',
                description=f'Mention someone to hug!\n**Usage:** `{config.PREFIX}hug @user`'
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Beep Boop 🤖', description="Bots appreciate the gesture, but try hugging a real person!"
            ))

        if member.id == ctx.author.id:
            gif_url, source = await self.get_gif('cry')
            embed = self.build_embed(
                f"🤗 **{ctx.author.mention} hugged themselves... They need a friend!**",
                0x3498db, gif_url, source,
                "Don't worry, we all need hugs sometimes!", ctx.author
            )
            return await ctx.send(embed=embed)

        gif_url, source = await self.get_gif('hug')
        embed = self.build_embed(
            f"🤗 **{ctx.author.mention} hugged {member.mention}!**",
            0x3498db, gif_url, source,
            f"Warm hugs ♥ | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Pat ───────────────────────────────────────────────────────────────────
    @commands.command(name='pat')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def pat(self, ctx, member: discord.Member = None):
        """Pat someone's head! 👋\n\nUsage: ,pat @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Pat?',
                description=f'Mention someone to pat!\n**Usage:** `{config.PREFIX}pat @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Hmm...', description="Patting yourself is a bit awkward!"
            ))

        gif_url, source = await self.get_gif('pat')
        if member.bot:
            embed = self.build_embed(
                f"👋 **{ctx.author.mention} patted me! Thanks!** 💙",
                0x9b59b6, gif_url, source,
                "Beep boop! I appreciate it!", ctx.author
            )
        else:
            embed = self.build_embed(
                f"👋 **{ctx.author.mention} patted {member.mention}'s head!**",
                0x9b59b6, gif_url, source,
                f"Good job! | Requested by {ctx.author.name}", ctx.author
            )
        await ctx.send(embed=embed)

    # ── Cry ───────────────────────────────────────────────────────────────────
    @commands.command(name='cry')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def cry(self, ctx, *, reason: str = None):
        """Express your sadness 😢\n\nUsage: ,cry [reason]"""
        gif_url, source = await self.get_gif('cry')
        desc = f"😢 **{ctx.author.mention} is crying!**"
        if reason:
            desc += f"\n*Reason:* {reason}"
        embed = self.build_embed(desc, 0x3498db, gif_url, source,
                                 "There, there... It'll be okay!", ctx.author)
        await ctx.send(embed=embed)

    # ── Slap ──────────────────────────────────────────────────────────────────
    @commands.command(name='slap')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slap(self, ctx, member: discord.Member = None):
        """Slap someone! 👋💥\n\nUsage: ,slap @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Slap?',
                description=f'Mention someone to slap!\n**Usage:** `{config.PREFIX}slap @user`'
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Protected! 🛡️', description="You can't slap bots! We have shields!"
            ))

        gif_url, source = await self.get_gif('slap')
        if member.id == ctx.author.id:
            embed = self.build_embed(
                f"💥 **{ctx.author.mention} slapped themselves! Ouch!**",
                0xe74c3c, gif_url, source, "Why would you do that?!", ctx.author
            )
        else:
            embed = self.build_embed(
                f"💥 **{ctx.author.mention} slapped {member.mention}!**\n*That's gotta hurt!*",
                0xe74c3c, gif_url, source,
                f"Ouch! | Requested by {ctx.author.name}", ctx.author
            )
        await ctx.send(embed=embed)

    # ── Shout ─────────────────────────────────────────────────────────────────
    @commands.command(name='shout', aliases=['yell', 'scream'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def shout(self, ctx, *, message: str = None):
        """Shout something out loud! 📢\n\nUsage: ,shout [message]"""
        gif_url, source = await self.get_gif('shout')
        text = f'"{message.upper()}"' if message else '"AAAAHHHHH!!!"'
        embed = self.build_embed(
            f"📢 **{ctx.author.mention} is shouting!**\n\n**{text}**",
            0xf39c12, gif_url, source,
            f"Loud noises! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Dance ─────────────────────────────────────────────────────────────────
    @commands.command(name='dance')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def dance(self, ctx):
        """Dance like nobody's watching! 💃\n\nUsage: ,dance"""
        gif_url, source = await self.get_gif('dance')
        embed = self.build_embed(
            f"💃 **{ctx.author.mention} is dancing!**",
            0xe67e22, gif_url, source,
            f"Let's groove! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Drool ─────────────────────────────────────────────────────────────────
    @commands.command(name='drool')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def drool(self, ctx, *, thing: str = None):
        """Drool over something! 🤤\n\nUsage: ,drool [thing]"""
        gif_url, source = await self.get_gif('drool')
        desc = f"🤤 **{ctx.author.mention} is drooling over {thing}!**" if thing else \
               f"🤤 **{ctx.author.mention} is drooling!**"
        embed = self.build_embed(desc, 0x3498db, gif_url, source,
                                 f"So tasty! | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Air Kiss ──────────────────────────────────────────────────────────────
    @commands.command(name='airkiss', aliases=['blowkiss'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def airkiss(self, ctx, member: discord.Member = None):
        """Blow a kiss to someone! 😘\n\nUsage: ,airkiss [@user]"""
        gif_url, source = await self.get_gif('airkiss')
        if member:
            if member.id == ctx.author.id:
                desc = f"😘 **{ctx.author.mention} blew a kiss to themselves! Self-love!**"
            else:
                desc = f"😘 **{ctx.author.mention} blew a kiss to {member.mention}!**"
        else:
            desc = f"😘 **{ctx.author.mention} blew a kiss! Catch it!**"
        embed = self.build_embed(desc, 0xff69b4, gif_url, source,
                                 f"Mwah! | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Laugh ─────────────────────────────────────────────────────────────────
    @commands.command(name='laugh', aliases=['lol'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def laugh(self, ctx, *, reason: str = None):
        """Laugh out loud! 😂\n\nUsage: ,laugh [reason]"""
        gif_url, source = await self.get_gif('laugh')
        desc = f"😂 **{ctx.author.mention} is laughing! HAHAHA!**"
        if reason:
            desc = f"😂 **{ctx.author.mention} is laughing!**\n*Reason:* {reason}"
        embed = self.build_embed(desc, 0xf1c40f, gif_url, source,
                                 f"That's hilarious! | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Kill ──────────────────────────────────────────────────────────────────
    @commands.command(name='kill')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def kill(self, ctx, member: discord.Member = None):
        """Playfully 'kill' someone! ⚔️\n\nUsage: ,kill @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Kill?',
                description=f"Mention someone to kill!\n**Usage:** `{config.PREFIX}kill @user`\n*Don't worry, it's just roleplay!* 😅"
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Wait, what?! 😰',
                description="You can't kill yourself! Need someone to talk to?"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Immortal! 🤖', description="Bots are immortal! You can't kill us!"
            ))

        gif_url, source = await self.get_gif('kill')
        embed = self.build_embed(
            f"⚔️ **{ctx.author.mention} killed {member.mention}!**\n*RIP* 💀",
            0x8e44ad, gif_url, source,
            f"Just roleplay! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Cuddle ────────────────────────────────────────────────────────────────
    @commands.command(name='cuddle')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def cuddle(self, ctx, member: discord.Member = None):
        """Cuddle with someone! 🥰\n\nUsage: ,cuddle @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Cuddle?',
                description=f'Mention someone to cuddle!\n**Usage:** `{config.PREFIX}cuddle @user`'
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Aww! 🤖', description="Bots would love to cuddle, but we're made of code!"
            ))

        gif_url, source = await self.get_gif('cuddle')
        if member.id == ctx.author.id:
            embed = self.build_embed(
                f"🥰 **{ctx.author.mention} cuddled themselves... They need company!**",
                0xe91e63, gif_url, source, "You deserve cuddles too!", ctx.author
            )
        else:
            embed = self.build_embed(
                f"🥰 **{ctx.author.mention} is cuddling with {member.mention}!**",
                0xe91e63, gif_url, source,
                f"So cozy! | Requested by {ctx.author.name}", ctx.author
            )
        await ctx.send(embed=embed)

    # ── Poke ──────────────────────────────────────────────────────────────────
    @commands.command(name='poke')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def poke(self, ctx, member: discord.Member = None):
        """Poke someone! 👉\n\nUsage: ,poke @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Poke?',
                description=f'Mention someone to poke!\n**Usage:** `{config.PREFIX}poke @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Poking Yourself?', description="That's a bit weird!"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Beep Boop! 🤖', description="Bots don't feel pokes!"
            ))

        gif_url, source = await self.get_gif('poke')
        embed = self.build_embed(
            f"👉 **{ctx.author.mention} poked {member.mention}!**\n*Hey! Pay attention!*",
            0x3498db, gif_url, source,
            f"Poke poke! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Bite ──────────────────────────────────────────────────────────────────
    @commands.command(name='bite')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def bite(self, ctx, member: discord.Member = None):
        """Bite someone! 😬\n\nUsage: ,bite @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Bite?',
                description=f'Mention someone to bite!\n**Usage:** `{config.PREFIX}bite @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Ouch!', description="Biting yourself hurts!"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Metal Teeth! 🤖', description="Bots are made of metal! You'll break your teeth!"
            ))

        gif_url, source = await self.get_gif('bite')
        embed = self.build_embed(
            f"😬 **{ctx.author.mention} bit {member.mention}!**\n*Nom nom!*",
            0xe74c3c, gif_url, source,
            f"That's gonna leave a mark! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Wave ──────────────────────────────────────────────────────────────────
    @commands.command(name='wave')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def wave(self, ctx, member: discord.Member = None):
        """Wave at someone! 👋\n\nUsage: ,wave [@user]"""
        gif_url, source = await self.get_gif('wave')
        if member:
            if member.id == ctx.author.id:
                desc = f"👋 **{ctx.author.mention} waved at themselves! Lonely?**"
            elif member.bot:
                desc = f"👋 **{ctx.author.mention} waved at {member.mention}! *waves back* 🤖**"
            else:
                desc = f"👋 **{ctx.author.mention} waved at {member.mention}!**"
        else:
            desc = f"👋 **{ctx.author.mention} is waving! Hello everyone!**"
        embed = self.build_embed(desc, 0xf39c12, gif_url, source,
                                 f"Hello there! | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Smile ─────────────────────────────────────────────────────────────────
    @commands.command(name='smile')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def smile(self, ctx):
        """Show your beautiful smile! 😊\n\nUsage: ,smile"""
        gif_url, source = await self.get_gif('smile')
        embed = self.build_embed(
            f"😊 **{ctx.author.mention} is smiling!**\n*What a beautiful smile!*",
            0xf1c40f, gif_url, source,
            f"Keep smiling! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Wink ──────────────────────────────────────────────────────────────────
    @commands.command(name='wink')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def wink(self, ctx, member: discord.Member = None):
        """Wink at someone! 😉\n\nUsage: ,wink [@user]"""
        gif_url, source = await self.get_gif('wink')
        if member:
            if member.id == ctx.author.id:
                desc = f"😉 **{ctx.author.mention} winked at themselves! Confident!**"
            elif member.bot:
                desc = f"😉 **{ctx.author.mention} winked at {member.mention}! *winks back* 🤖**"
            else:
                desc = f"😉 **{ctx.author.mention} winked at {member.mention}!**"
        else:
            desc = f"😉 **{ctx.author.mention} winked!**"
        embed = self.build_embed(desc, 0xff69b4, gif_url, source,
                                 f"Smooth! | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Bonk ──────────────────────────────────────────────────────────────────
    @commands.command(name='bonk')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def bonk(self, ctx, member: discord.Member = None):
        """Bonk someone! 🔨\n\nUsage: ,bonk @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Bonk?',
                description=f'Mention someone to bonk!\n**Usage:** `{config.PREFIX}bonk @user`'
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Protected! 🛡️', description="You can't bonk bots! We have shields!"
            ))

        gif_url, source = await self.get_gif('bonk')
        if member.id == ctx.author.id:
            embed = self.build_embed(
                f"🔨 **{ctx.author.mention} bonked themselves! Self-bonk!**",
                0xe67e22, gif_url, source, "Why would you do that?!", ctx.author
            )
        else:
            embed = self.build_embed(
                f"🔨 **{ctx.author.mention} bonked {member.mention}!**\n*Go to horny jail!*",
                0xe67e22, gif_url, source,
                f"BONK! | Requested by {ctx.author.name}", ctx.author
            )
        await ctx.send(embed=embed)

    # ── High Five ─────────────────────────────────────────────────────────────
    @commands.command(name='highfive', aliases=['hi5'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def highfive(self, ctx, member: discord.Member = None):
        """Give someone a high five! ✋\n\nUsage: ,highfive @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to High Five?',
                description=f'Mention someone to high five!\n**Usage:** `{config.PREFIX}highfive @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Forever Alone?', description="You can't high five yourself!"
            ))

        gif_url, source = await self.get_gif('highfive')
        if member.bot:
            embed = self.build_embed(
                f"✋ **{ctx.author.mention} high fived me! *high fives back* 🤖**",
                0x2ecc71, gif_url, source, "Nice!", ctx.author
            )
        else:
            embed = self.build_embed(
                f"✋ **{ctx.author.mention} high fived {member.mention}!**\n*Nice teamwork!*",
                0x2ecc71, gif_url, source,
                f"Up top! | Requested by {ctx.author.name}", ctx.author
            )
        await ctx.send(embed=embed)

    # ── Sleep ─────────────────────────────────────────────────────────────────
    @commands.command(name='sleep', aliases=['sleepy'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def sleep(self, ctx):
        """Go to sleep! 😴\n\nUsage: ,sleep"""
        gif_url, source = await self.get_gif('sleep')
        embed = self.build_embed(
            f"😴 **{ctx.author.mention} is going to sleep!**\n*Good night! Sweet dreams!*",
            0x5865f2, gif_url, source,
            f"Sleep tight! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ══════════════════════════════════════════════════════════════════════════
    # ─── NEW Commands ─────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    # ── Nuzzle ────────────────────────────────────────────────────────────────
    @commands.command(name='nuzzle')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def nuzzle(self, ctx, member: discord.Member = None):
        """Nuzzle someone affectionately! 🥺\n\nUsage: ,nuzzle @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Nuzzle?',
                description=f'Mention someone to nuzzle!\n**Usage:** `{config.PREFIX}nuzzle @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Hmm...', description="You can't nuzzle yourself!"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Metal Frame! 🤖', description="Bots are too hard to nuzzle!"
            ))

        gif_url, source = await self.get_gif('nuzzle')
        embed = self.build_embed(
            f"🥺 **{ctx.author.mention} nuzzled {member.mention}!**\n*So soft and warm!*",
            0xff69b4, gif_url, source,
            f"Aww! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Stare ─────────────────────────────────────────────────────────────────
    @commands.command(name='stare')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def stare(self, ctx, member: discord.Member = None):
        """Stare intensely at someone! 👀\n\nUsage: ,stare [@user]"""
        gif_url, source = await self.get_gif('stare')
        if member:
            if member.id == ctx.author.id:
                desc = f"👀 **{ctx.author.mention} is staring at themselves in the mirror...**"
            elif member.bot:
                desc = f"👀 **{ctx.author.mention} is staring at {member.mention}... creepy!**"
            else:
                desc = f"👀 **{ctx.author.mention} is staring intensely at {member.mention}!**"
        else:
            desc = f"👀 **{ctx.author.mention} is staring into the void...**"
        embed = self.build_embed(desc, 0x2c3e50, gif_url, source,
                                 f"Intense... | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Blush ─────────────────────────────────────────────────────────────────
    @commands.command(name='blush')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def blush(self, ctx, member: discord.Member = None):
        """Blush at someone! 😳\n\nUsage: ,blush [@user]"""
        gif_url, source = await self.get_gif('blush')
        if member:
            if member.id == ctx.author.id:
                desc = f"😳 **{ctx.author.mention} is blushing at themselves! Narcissist!**"
            else:
                desc = f"😳 **{ctx.author.mention} is blushing because of {member.mention}!**"
        else:
            desc = f"😳 **{ctx.author.mention} is blushing!** *So cute!*"
        embed = self.build_embed(desc, 0xff6b9d, gif_url, source,
                                 f"How adorable! | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Nom ───────────────────────────────────────────────────────────────────
    @commands.command(name='nom', aliases=['chomp', 'munch'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def nom(self, ctx, member: discord.Member = None):
        """Nom on someone or something! 😋\n\nUsage: ,nom [@user]"""
        gif_url, source = await self.get_gif('nom')
        if member:
            if member.id == ctx.author.id:
                desc = f"😋 **{ctx.author.mention} is nomming on themselves... interesting choice.**"
            else:
                desc = f"😋 **{ctx.author.mention} is nomming on {member.mention}!**\n*Nom nom nom!*"
        else:
            desc = f"😋 **{ctx.author.mention} is nomming on something!** *Delicious!*"
        embed = self.build_embed(desc, 0xf39c12, gif_url, source,
                                 f"Nom nom! | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Punch ─────────────────────────────────────────────────────────────────
    @commands.command(name='punch')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def punch(self, ctx, member: discord.Member = None):
        """Punch someone! 👊\n\nUsage: ,punch @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Punch?',
                description=f'Mention someone to punch!\n**Usage:** `{config.PREFIX}punch @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Stop! 🛑', description="Punching yourself is not okay!"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Ow! 🤖', description="You'll hurt your fist on my metal body!"
            ))

        gif_url, source = await self.get_gif('punch')
        embed = self.build_embed(
            f"👊 **{ctx.author.mention} punched {member.mention}!**\n*POW! Right in the face!*",
            0xc0392b, gif_url, source,
            f"Ouch! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Throw ─────────────────────────────────────────────────────────────────
    @commands.command(name='throw')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def throw(self, ctx, member: discord.Member = None, *, obj: str = 'something'):
        """Throw something at someone! 🎯\n\nUsage: ,throw @user [object]"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Throw at Who?',
                description=f'Mention someone to throw at!\n**Usage:** `{config.PREFIX}throw @user [object]`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='??', description="You can't throw things at yourself!"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Dodged! 🤖', description="Bots have perfect reaction time. Dodged!"
            ))

        gif_url, source = await self.get_gif('throw')
        embed = self.build_embed(
            f"🎯 **{ctx.author.mention} threw {obj} at {member.mention}!**",
            0xe67e22, gif_url, source,
            f"Direct hit! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Lick ──────────────────────────────────────────────────────────────────
    @commands.command(name='lick')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def lick(self, ctx, member: discord.Member = None):
        """Lick someone! 👅\n\nUsage: ,lick @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Lick?',
                description=f'Mention someone to lick!\n**Usage:** `{config.PREFIX}lick @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Weird...', description="Licking yourself is... a choice."
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Gross! 🤖', description="I taste like plastic and circuits!"
            ))

        gif_url, source = await self.get_gif('lick')
        embed = self.build_embed(
            f"👅 **{ctx.author.mention} licked {member.mention}!**\n*Eww! Or... aww?*",
            0x9b59b6, gif_url, source,
            f"That's... something. | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Tickle ────────────────────────────────────────────────────────────────
    @commands.command(name='tickle')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def tickle(self, ctx, member: discord.Member = None):
        """Tickle someone! 🤣\n\nUsage: ,tickle @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Tickle?',
                description=f'Mention someone to tickle!\n**Usage:** `{config.PREFIX}tickle @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Flexible!', description="Tickling yourself barely works!"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='No Tickle! 🤖', description="Bots aren't ticklish. *bzzt*"
            ))

        gif_url, source = await self.get_gif('tickle')
        embed = self.build_embed(
            f"🤣 **{ctx.author.mention} is tickling {member.mention}!**\n*Hahaha stop stop stop!*",
            0xf1c40f, gif_url, source,
            f"Hehehe! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Bully ─────────────────────────────────────────────────────────────────
    @commands.command(name='bully')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def bully(self, ctx, member: discord.Member = None):
        """Bully someone (playfully)! 😤\n\nUsage: ,bully @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Who to Bully?',
                description=f'Mention someone to bully!\n**Usage:** `{config.PREFIX}bully @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Self Bully?', description="Are you ok buddy?"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Not Today! 🤖', description="You can't bully an AI. I have no feelings!"
            ))

        gif_url, source = await self.get_gif('bully')
        embed = self.build_embed(
            f"😤 **{ctx.author.mention} is bullying {member.mention}!**\n*Why must you hurt them like this?!*",
            0xe74c3c, gif_url, source,
            f"Meanie! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Hold ──────────────────────────────────────────────────────────────────
    @commands.command(name='hold', aliases=['holdhand', 'holdhands'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def hold(self, ctx, member: discord.Member = None):
        """Hold someone's hand! 🤝\n\nUsage: ,hold @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Hold Who?',
                description=f'Mention someone to hold hands with!\n**Usage:** `{config.PREFIX}hold @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Lonely? 🥺', description="You can't hold your own hand!"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='No Hands! 🤖', description="Bots don't have hands... well, not real ones!"
            ))

        gif_url, source = await self.get_gif('hold')
        embed = self.build_embed(
            f"🤝 **{ctx.author.mention} is holding {member.mention}'s hand!**\n*How wholesome!*",
            0x2ecc71, gif_url, source,
            f"So sweet! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Carry ─────────────────────────────────────────────────────────────────
    @commands.command(name='carry')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def carry(self, ctx, member: discord.Member = None):
        """Carry someone! 💪\n\nUsage: ,carry @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Carry Who?',
                description=f'Mention someone to carry!\n**Usage:** `{config.PREFIX}carry @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Impossible!', description="You can't carry yourself!"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Too Heavy! 🤖', description="Servers weigh like, 400kg. I'm not portable!"
            ))

        gif_url, source = await self.get_gif('carry')
        embed = self.build_embed(
            f"💪 **{ctx.author.mention} is carrying {member.mention}!**\n*Legs? Who needs legs?*",
            0x3498db, gif_url, source,
            f"So strong! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)

    # ── Smug ──────────────────────────────────────────────────────────────────
    @commands.command(name='smug')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def smug(self, ctx, member: discord.Member = None):
        """Show off your smug face! 😏\n\nUsage: ,smug [@user]"""
        gif_url, source = await self.get_gif('smug')
        if member:
            if member.id == ctx.author.id:
                desc = f"😏 **{ctx.author.mention} is being smug at themselves!**"
            else:
                desc = f"😏 **{ctx.author.mention} is being smug at {member.mention}!**\n*You can't beat me!*"
        else:
            desc = f"😏 **{ctx.author.mention} is being smug!**\n*Look at this confident person!*"
        embed = self.build_embed(desc, 0x8e44ad, gif_url, source,
                                 f"So smug! | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Facepalm ──────────────────────────────────────────────────────────────
    @commands.command(name='facepalm', aliases=['fp'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def facepalm(self, ctx, member: discord.Member = None):
        """Facepalm at someone's actions! 🤦\n\nUsage: ,facepalm [@user]"""
        gif_url, source = await self.get_gif('facepalm')
        if member:
            if member.id == ctx.author.id:
                desc = f"🤦 **{ctx.author.mention} facepalmed at themselves.** *What did you do?!*"
            elif member.bot:
                desc = f"🤦 **{ctx.author.mention} facepalmed because of {member.mention}!** *The bot did something weird again!*"
            else:
                desc = f"🤦 **{ctx.author.mention} facepalmed because of {member.mention}!** *Why?!*"
        else:
            desc = f"🤦 **{ctx.author.mention} is facepalming!** *The audacity...*"
        embed = self.build_embed(desc, 0x95a5a6, gif_url, source,
                                 f"I can't even... | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Confused ──────────────────────────────────────────────────────────────
    @commands.command(name='confused', aliases=['huh', 'what'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def confused(self, ctx, member: discord.Member = None):
        """Express confusion! 😕\n\nUsage: ,confused [@user]"""
        gif_url, source = await self.get_gif('confused')
        if member:
            if member.id == ctx.author.id:
                desc = f"😕 **{ctx.author.mention} is confused about themselves!** *An existential crisis!*"
            else:
                desc = f"😕 **{ctx.author.mention} is confused by {member.mention}!** *What just happened?*"
        else:
            desc = f"😕 **{ctx.author.mention} is confused!** *Wait... what?*"
        embed = self.build_embed(desc, 0xbdc3c7, gif_url, source,
                                 f"Huh?? | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Happy ─────────────────────────────────────────────────────────────────
    @commands.command(name='happy', aliases=['yay', 'woohoo'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def happy(self, ctx, *, reason: str = None):
        """Express happiness! 🎉\n\nUsage: ,happy [reason]"""
        gif_url, source = await self.get_gif('happy')
        desc = f"🎉 **{ctx.author.mention} is super happy!**"
        if reason:
            desc += f"\n*Because:* {reason}"
        embed = self.build_embed(desc, 0x27ae60, gif_url, source,
                                 f"Yayyy! | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Sad ───────────────────────────────────────────────────────────────────
    @commands.command(name='sad')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def sad(self, ctx, *, reason: str = None):
        """Express sadness 😞\n\nUsage: ,sad [reason]"""
        gif_url, source = await self.get_gif('sad')
        desc = f"😞 **{ctx.author.mention} is feeling sad...**"
        if reason:
            desc += f"\n*Reason:* {reason}"
        embed = self.build_embed(desc, 0x7f8c8d, gif_url, source,
                                 f"Aww... it'll get better! | Requested by {ctx.author.name}", ctx.author)
        await ctx.send(embed=embed)

    # ── Kick ──────────────────────────────────────────────────────────────────
    @commands.command(name='rpkick', aliases=['rkick'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def rpkick(self, ctx, member: discord.Member = None):
        """Playfully kick someone! 🦵\n\nUsage: ,rpkick @user"""
        if not member:
            return await ctx.reply(embed=create_embed(
                'error', title='Kick Who?',
                description=f'Mention someone to kick!\n**Usage:** `{config.PREFIX}rpkick @user`'
            ))
        if member.id == ctx.author.id:
            return await ctx.reply(embed=create_embed(
                'error', title='Oops!', description="You can't kick yourself!"
            ))
        if member.bot:
            return await ctx.reply(embed=create_embed(
                'error', title='Titanium Shins! 🤖', description="You'd only hurt yourself!"
            ))

        gif_url, source = await self.get_gif('kick')
        embed = self.build_embed(
            f"🦵 **{ctx.author.mention} kicked {member.mention}!**\n*Ooof!*",
            0xe74c3c, gif_url, source,
            f"KAPOW! | Requested by {ctx.author.name}", ctx.author
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Roleplay(bot))
