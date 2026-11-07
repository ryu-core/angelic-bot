import discord
from discord.ext import commands
from discord.ui import View, Button
import asyncio
import requests
import json
import config
from typing import Optional
from utils.booster_check import booster_required


class SearchPaginationView(View):
    """Pagination view for search results"""
    
    def __init__(self, results, query, author, search_info):
        super().__init__(timeout=180)
        self.results = results
        self.query = query
        self.author = author
        self.search_info = search_info
        self.current_page = 0
        self.results_per_page = 5
        self.max_page = (len(results) - 1) // self.results_per_page
        
        self.update_buttons()
    
    def update_buttons(self):
        """Update button states based on current page"""
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.max_page
    
    def create_embed(self):
        """Create embed for current page"""
        embed = discord.Embed(
            title=f"{config.EMOJIS.get('search', '🔍')} Search Results",
            description=f"Showing results for: **{self.query}**",
            color=config.COLORS['primary']
        )
        
        start_idx = self.current_page * self.results_per_page
        end_idx = min(start_idx + self.results_per_page, len(self.results))
        
        for i, result in enumerate(self.results[start_idx:end_idx], start_idx + 1):
            title = result.get('title', 'No Title')
            link = result.get('link', '')
            snippet = result.get('snippet', 'No description available')
            
            if len(snippet) > 150:
                snippet = snippet[:147] + "..."
            
            embed.add_field(
                name=f"{i}. {title}",
                value=f"{snippet}\n[🔗 Visit]({link})",
                inline=False
            )
        
        total_results = self.search_info.get('totalResults', 'Unknown')
        embed.set_footer(
            text=f"Page {self.current_page + 1}/{self.max_page + 1} • Requested by {self.author.name} • Total: {total_results}",
            icon_url=self.author.display_avatar.url
        )
        
        return embed
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, emoji="◀️")
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("Only the command user can use these buttons!", ephemeral=True)
        
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("Only the command user can use these buttons!", ephemeral=True)
        
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class ImagePaginationView(View):
    """Pagination view for image search results"""
    
    def __init__(self, images, query, author):
        super().__init__(timeout=180)
        self.images = images
        self.query = query
        self.author = author
        self.current_index = 0
        
        self.update_buttons()
    
    def update_buttons(self):
        """Update button states based on current index"""
        self.previous_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.images) - 1
    
    def create_embed(self):
        """Create embed for current image"""
        image = self.images[self.current_index]
        image_url = image.get('imageUrl', '')
        title = image.get('title', 'Image Result')
        source = image.get('link', '')
        
        embed = discord.Embed(
            title=f"{config.EMOJIS.get('search', '🖼️')} Image Search Results",
            description=f"**Query:** {self.query}\n**Title:** {title}",
            color=config.COLORS['primary']
        )
        
        embed.set_image(url=image_url)
        
        embed.add_field(
            name="🔗 Source",
            value=f"[Visit Source]({source})",
            inline=False
        )
        
        embed.set_footer(
            text=f"Image {self.current_index + 1}/{len(self.images)} • Requested by {self.author.name}",
            icon_url=self.author.display_avatar.url
        )
        
        return embed
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("Only the command user can use these buttons!", ephemeral=True)
        
        self.current_index -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("Only the command user can use these buttons!", ephemeral=True)
        
        self.current_index += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


# NSFW blocklist — queries containing these are rejected
NSFW_BLOCKLIST = [
    # Core explicit terms
    'nsfw', 'porn', 'porno', 'pornography', 'hentai', 'xxx', 'nude', 'nudes',
    'naked', 'sex', 'sexy', 'sexual', 'sexting',
    # Body parts (explicit context)
    'boobs', 'boob', 'tits', 'titties', 'dick', 'penis', 'vagina', 'pussy',
    'ass', 'butt', 'nipple', 'nipples', 'genitals', 'genital', 'cock',
    'breasts', 'breast', 'cleavage', 'thong', 'bikini',
    # Sexual acts / explicit
    'erotic', 'erotica', 'lewd', 'orgasm', 'fetish', 'bdsm', 'cum',
    'blowjob', 'handjob', 'masturbat', 'intercourse', 'anal',
    'threesome', 'gangbang', 'creampie', 'deepthroat', 'facial',
    'bondage', 'dildo', 'vibrator', 'dominatrix', 'submissive',
    'kinky', 'kink', 'smut', 'explicit',
    # Adult content / rule34
    'rule34', 'r34', 'rule 34', 'onlyfans', 'fansly', 'patreon nsfw',
    'ahegao', 'ecchi', 'futanari', 'yaoi', 'yuri', 'doujin',
    'loli', 'shota',
    # Adult sites
    'xvideos', 'pornhub', 'xnxx', 'xhamster', 'brazzers', 'bangbros',
    'redtube', 'youporn', 'spankbang', 'chaturbate', 'cam girl',
    'camgirl', 'livejasmin', 'stripchat', 'manyvids',
    # Slang / evasion
    'fap', 'milf', 'gilf', 'dilf', 'pawg', 'thicc',
    'strip', 'stripper', 'playboy', 'topless', 'bottomless',
    'upskirt', 'downblouse', 'wardrobe malfunction',
    'hookup', 'hook up', 'escort', 'call girl',
    'suggestive', 'risque', 'provocative',
    'p0rn', 'pr0n', 'p*rn', 'n*de', 'nud3',
    'sext', 'sexualiz',
    # Gore / violence
    'gore', 'gory', 'torture', 'mutilation', 'dismember',
    'beheading', 'decapitat', 'snuff', 'death video',
    'self harm', 'selfharm', 'suicide method',
]

def is_nsfw_query(query: str) -> bool:
    """Check if a query contains NSFW terms"""
    q_lower = query.lower()
    for term in NSFW_BLOCKLIST:
        # Check as whole word or substring
        if term in q_lower:
            return True
    return False


class Search(commands.Cog):
    """Image search and fact-check commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.serper_url = "https://google.serper.dev/search"
        self.serper_images_url = "https://google.serper.dev/images"
        self.headers = {
            'X-API-KEY': config.SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
    
    # Set category for help command
    @property
    def qualified_name(self):
        return "Booster"
    
    # Web Google search command removed; keep image search and factcheck active.
    @commands.cooldown(1, 5, commands.BucketType.user)
    @booster_required()
    async def search(self, ctx, *, query: str):
        """🔍 Search Google for anything (Booster Only 🚀)
        
        Usage: ,search <query>
        Example: ,search Python programming tutorials
        """
        # NSFW filter check
        if is_nsfw_query(query):
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Search Blocked",
                description="🚫 **NSFW content is not allowed!**\n\nThis bot does not permit searching for explicit or inappropriate content.",
                color=config.COLORS['error']
            )
            return await ctx.send(embed=embed)
        
        async with ctx.typing():
            try:
                # Make API request with SafeSearch enabled
                payload = json.dumps({"q": query, "gl": "us", "hl": "en", "safe": "active"})
                response = await asyncio.to_thread(
                    requests.post,
                    self.serper_url,
                    headers=self.headers,
                    data=payload,
                    timeout=10,
                )
                
                if response.status_code != 200:
                    embed = discord.Embed(
                        title=f"{config.EMOJIS['error']} Search Failed",
                        description=f"API returned status code: {response.status_code}",
                        color=config.COLORS['error']
                    )
                    return await ctx.send(embed=embed)
                
                data = response.json()
                
                # Check if we have results
                if 'organic' not in data or len(data['organic']) == 0:
                    embed = discord.Embed(
                        title=f"{config.EMOJIS['search']} No Results Found",
                        description=f"No results found for: **{query}**",
                        color=config.COLORS['error']
                    )
                    return await ctx.send(embed=embed)
                
                # Create pagination view
                view = SearchPaginationView(data['organic'], query, ctx.author, data.get('searchInformation', {}))
                embed = view.create_embed()
                
                await ctx.send(embed=embed, view=view)
                
            except requests.exceptions.Timeout:
                embed = discord.Embed(
                    title=f"{config.EMOJIS['error']} Timeout Error",
                    description="Search request timed out. Please try again.",
                    color=config.COLORS['error']
                )
                await ctx.send(embed=embed)
            except requests.exceptions.RequestException as e:
                embed = discord.Embed(
                    title=f"{config.EMOJIS['error']} Connection Error",
                    description="Failed to connect to search API. Please try again later.",
                    color=config.COLORS['error']
                )
                await ctx.send(embed=embed)
            except Exception as e:
                embed = discord.Embed(
                    title=f"{config.EMOJIS['error']} Error",
                    description=f"An unexpected error occurred: {str(e)}",
                    color=config.COLORS['error']
                )
                await ctx.send(embed=embed)
    
    @commands.command(name='imagesearch', aliases=['images', 'img'])
    @commands.cooldown(1, 5, commands.BucketType.user)
    @booster_required()
    async def image_search(self, ctx, *, query: str):
        """🖼️ Search Google Images (Booster Only 🚀)
        
        Usage: ,imagesearch <query>
        Example: ,imagesearch cute puppies
        """
        # NSFW filter check
        if is_nsfw_query(query):
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Search Blocked",
                description="🚫 **NSFW content is not allowed!**\n\nThis bot does not permit searching for explicit or inappropriate images.",
                color=config.COLORS['error']
            )
            return await ctx.send(embed=embed)
        
        async with ctx.typing():
            try:
                # Make API request with SafeSearch enabled
                payload = json.dumps({"q": query, "gl": "us", "hl": "en", "safe": "active"})
                response = await asyncio.to_thread(
                    requests.post,
                    self.serper_images_url,
                    headers=self.headers,
                    data=payload,
                    timeout=10,
                )
                
                if response.status_code != 200:
                    embed = discord.Embed(
                        title=f"{config.EMOJIS['error']} Search Failed",
                        description=f"API returned status code: {response.status_code}",
                        color=config.COLORS['error']
                    )
                    return await ctx.send(embed=embed)
                
                data = response.json()
                
                # Check if we have results
                if 'images' not in data or len(data['images']) == 0:
                    embed = discord.Embed(
                        title=f"{config.EMOJIS['search']} No Images Found",
                        description=f"No images found for: **{query}**",
                        color=config.COLORS['error']
                    )
                    return await ctx.send(embed=embed)
                
                # Create pagination view
                view = ImagePaginationView(data['images'], query, ctx.author)
                embed = view.create_embed()
                
                await ctx.send(embed=embed, view=view)
                
            except requests.exceptions.Timeout:
                embed = discord.Embed(
                    title=f"{config.EMOJIS['error']} Timeout Error",
                    description="Image search request timed out. Please try again.",
                    color=config.COLORS['error']
                )
                await ctx.send(embed=embed)
            except requests.exceptions.RequestException as e:
                embed = discord.Embed(
                    title=f"{config.EMOJIS['error']} Connection Error",
                    description="Failed to connect to search API. Please try again later.",
                    color=config.COLORS['error']
                )
                await ctx.send(embed=embed)
            except Exception as e:
                embed = discord.Embed(
                    title=f"{config.EMOJIS['error']} Error",
                    description=f"An unexpected error occurred: {str(e)}",
                    color=config.COLORS['error']
                )
                await ctx.send(embed=embed)
    
    @image_search.error
    async def search_error(self, ctx, error):
        """Error handler for search commands"""
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title=f"{config.EMOJIS['error']} Missing Query",
                description=f"Please provide a search query!\n\n**Usage:** `{ctx.prefix}{ctx.command.name} <query>`",
                color=config.COLORS['error']
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title=f"{config.EMOJIS['clock']} Cooldown Active",
                description=f"Please wait {error.retry_after:.1f}s before searching again.",
                color=config.COLORS['error']
            )
            await ctx.send(embed=embed)

    @commands.command(name="factcheck", aliases=["fc", "fact", "isfact"])
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def factcheck(self, ctx: commands.Context, *, claim: str = None):
        """🔍 Fact-check a claim or a replied-to message using AI.

        Usage:
          Reply to a message and type `,factcheck`
          Or provide a claim directly: `,factcheck The Earth is flat`
        """
        # ── Resolve what to fact-check ──────────────────────────────────────
        text_to_check = None

        if ctx.message.reference:
            try:
                ref_msg = ctx.message.reference.resolved
                if isinstance(ref_msg, discord.Message):
                    text_to_check = ref_msg.content.strip()
            except Exception:
                pass

        if not text_to_check:
            text_to_check = claim

        if not text_to_check:
            return await ctx.send(
                embed=discord.Embed(
                    title="❌ Nothing to Fact-Check",
                    description=(
                        "**Reply to a message** and run `,factcheck`\n"
                        "— or —\n"
                        "Provide a claim directly: `,factcheck The moon is made of cheese`"
                    ),
                    color=config.COLORS["error"],
                )
            )

        if len(text_to_check) > 1000:
            text_to_check = text_to_check[:1000] + "…"

        # ── Call OpenAI via raw aiohttp (avoids httpx SDK incompatibility) ───
        async with ctx.typing():
            try:
                system_prompt = (
                    "You are a strict, impartial fact-checker. "
                    "Given a claim, evaluate it as accurately as possible using your training knowledge. "
                    "Respond in this EXACT JSON format with no markdown fences:\n"
                    "{\n"
                    '  "verdict": "FACT" or "CAP" or "MIXED" or "UNVERIFIABLE",\n'
                    '  "confidence": <integer 0-100>,\n'
                    '  "summary": "<one-sentence plain-English summary of your finding>",\n'
                    '  "explanation": "<2-4 sentences with reasoning and context>",\n'
                    '  "sources": "<notable sources or knowledge areas that support this; leave empty string if none>"\n'
                    "}\n"
                    "VERDICT rules:\n"
                    "  FACT — clearly true and well-supported\n"
                    "  CAP  — false, misleading, or a common misconception\n"
                    "  MIXED — partially true, nuanced, or depends on context\n"
                    "  UNVERIFIABLE — opinion, prediction, or impossible to verify\n"
                    "Do NOT include any text outside the JSON object."
                )

                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Claim to fact-check:\n{text_to_check}"},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 400,
                }

                headers = {
                    "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                }

                import aiohttp as _aiohttp
                import json as _json
                import re as _re

                async with _aiohttp.ClientSession() as _sess:
                    async with _sess.post(
                        "https://api.openai.com/v1/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=_aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status != 200:
                            err_body = await resp.text()
                            raise ValueError(f"OpenAI returned HTTP {resp.status}: {err_body[:200]}")
                        data = await resp.json()

                raw = data["choices"][0]["message"]["content"].strip()

                # Parse JSON
                try:
                    result = _json.loads(raw)
                except _json.JSONDecodeError:
                    match = _re.search(r"\{.*\}", raw, _re.DOTALL)
                    if match:
                        result = _json.loads(match.group())
                    else:
                        raise ValueError("Could not parse AI response as JSON.")

                verdict     = result.get("verdict", "UNVERIFIABLE").upper()
                confidence  = int(result.get("confidence", 50))
                summary     = result.get("summary", "No summary.")
                explanation = result.get("explanation", "")
                sources     = result.get("sources", "")

            except Exception as e:
                return await ctx.send(
                    embed=discord.Embed(
                        title="❌ Fact-Check Failed",
                        description=f"AI service error: `{e}`",
                        color=config.COLORS["error"],
                    )
                )

        # ── Build embed ──────────────────────────────────────────────────────
        verdict_map = {
            "FACT":          ("✅ FACT",          discord.Color.green(),           "🟢"),
            "CAP":           ("🧢 CAP",            discord.Color.red(),             "🔴"),
            "MIXED":         ("⚖️ MIXED",          discord.Color.orange(),          "🟡"),
            "UNVERIFIABLE":  ("🤷 UNVERIFIABLE",   discord.Color.from_rgb(80,80,80),"⚫"),
        }
        label, color, dot = verdict_map.get(verdict, verdict_map["UNVERIFIABLE"])

        # Confidence bar
        filled  = int(confidence / 10)
        conf_bar = "█" * filled + "░" * (10 - filled)

        # Trim the claim for display
        display_claim = text_to_check if len(text_to_check) <= 200 else text_to_check[:197] + "…"

        embed = discord.Embed(
            title=f"{label}",
            description=f"**{summary}**",
            color=color,
        )

        embed.add_field(
            name="📝 Claim",
            value=f">>> {display_claim}",
            inline=False,
        )

        embed.add_field(
            name="🧠 Explanation",
            value=explanation or "No further explanation.",
            inline=False,
        )

        embed.add_field(
            name=f"{dot} Confidence",
            value=f"`{conf_bar}` **{confidence}%**",
            inline=True,
        )

        if sources:
            embed.add_field(
                name="📚 Sources / References",
                value=sources,
                inline=True,
            )

        embed.set_footer(
            text=f"Fact-checked by AI • Requested by {ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url,
        )

        await ctx.send(embed=embed)

    @factcheck.error
    async def factcheck_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('clock','⏱️')} Cooldown",
                description=f"Wait **{error.retry_after:.1f}s** before fact-checking again.",
                color=config.COLORS["error"],
            )
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Search(bot))

