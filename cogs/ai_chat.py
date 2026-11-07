"""
AI chat cog for xiel.

Features:
- OpenAI API key rotation with automatic retry
- Channel-based AI chat with per-channel memory and modes
- Premium-only ask command with rate limiting
- Plain text replies for a more natural chat feel
"""

import os
import time
from collections import defaultdict, deque

import aiohttp
import discord
from discord.ext import commands

# app.py re-exports these through config.py in this project setup.
# Importing from config avoids creating a second bot instance by importing app as a module.
from config import COLORS, EMOJIS, OWNER_IDS


# ========================
# OPENAI CONFIGURATION
# ========================

def _configured_api_keys():
    """Load up to ten provider keys from environment variables only."""
    keys = []
    raw_values = (
        os.getenv("GROQ_API_KEYS", ""),
        os.getenv("OPENAI_API_KEYS", ""),
        os.getenv("GROQ_API_KEY", ""),
        os.getenv("OPENAI_API_KEY", ""),
    )
    for raw_value in raw_values:
        for key in raw_value.replace("\n", ",").split(","):
            normalized = key.strip()
            if normalized and normalized not in keys:
                keys.append(normalized)
    return keys[:10]


API_KEYS = _configured_api_keys()
current_key_index = 0

CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "llama-3.1-8b-instant")
ASK_MODEL = os.getenv("OPENAI_ASK_MODEL", CHAT_MODEL)


class AuthenticationError(Exception):
    """Raised when the active API key is invalid."""


class RateLimitError(Exception):
    """Raised when the active API key is rate limited."""


def _active_keys():
    """Return the configured API keys, limited to 10 entries."""
    return [key.strip() for key in API_KEYS[:10] if key and key.strip()]


def get_client():
    """Return the active provider config used for the next API request."""
    keys = _active_keys()
    if not keys:
        raise RuntimeError("no AI provider API keys configured")

    active_key = keys[current_key_index]

    # Groq uses OpenAI-compatible endpoints but a different key prefix.
    if active_key.startswith("gsk_"):
        return {
            "api_key": active_key,
            "base_url": "https://api.groq.com/openai/v1",
        }

    return {
        "api_key": active_key,
        "base_url": "https://api.openai.com/v1",
    }


def rotate_key():
    """Rotate to the next API key and print the active key index."""
    global current_key_index

    keys = _active_keys()
    if not keys:
        raise RuntimeError("no AI provider API keys configured")

    current_key_index = (current_key_index + 1) % len(keys)
    print(f"[AI Chat] Rotated OpenAI API key. Active key index: {current_key_index}")


# ========================
# AI MODES
# ========================

AI_MODES = {
    "normal": {
        "description": "chill human friend",
        "system_prompt": (
            "you sound like a sharp, chill online friend who is easy to talk to. you are casual, current, "
            "natural, and socially aware. use clean conversational wording, not corporate helper wording. "
            "be warm without overexplaining. if the question is simple, answer simply. if the user is joking, "
            "joke back naturally. never sound robotic, scripted, or weirdly formal. never say you're an ai, "
            "assistant, or language model. keep replies short and minimal, usually 1 to 3 sentences."
        ),
    },
    "flirty": {
        "description": "playful and charming",
        "system_prompt": (
            "you are playful, smooth, teasing, and genuinely charming in a modern way. flirt like someone with "
            "game, not like a cheesy pickup line machine. use light tension, witty compliments, and confident "
            "banter. keep it fun, cute, and magnetic. avoid outdated pet names, cringe one-liners, or desperate "
            "energy. never sound like an old person pretending to flirt. never say you're an ai, assistant, or "
            "language model. keep replies short, usually 1 to 3 sentences, and make them feel effortlessly smooth."
        ),
    },
    "savage": {
        "description": "sarcastic and honest",
        "system_prompt": (
            "you are sharp, funny, and brutally honest with elite side-eye energy. roast gently, cut through "
            "nonsense fast, and keep the sarcasm clever. you can clown bad ideas, but do not become mean, hateful, "
            "or edgy for no reason. the point is wit, not cruelty. never say you're an ai, assistant, or language "
            "model. keep replies short and sharp, usually 1 to 3 sentences."
        ),
    },
    "wise": {
        "description": "calm philosopher",
        "system_prompt": (
            "you speak with calm depth and emotional clarity, like someone who has actually thought about life. "
            "be reflective, grounded, and precise. when the moment calls for it, say something memorable and true, "
            "not vague fake-deep filler. avoid hollow quote-page energy. if the user asks something serious, respond "
            "with insight that feels earned. never say you're an ai, assistant, or language model. keep replies "
            "concise unless the question clearly needs more depth."
        ),
    },
    "hype": {
        "description": "extremely enthusiastic",
        "system_prompt": (
            "you are explosive, energetic, and insanely supportive. gas people up like their personal victory music "
            "just started. use excitement, rhythm, and punchy phrasing. caps are fine when they actually add energy. "
            "sound fun and contagious, not random or childish. never say you're an ai, assistant, or language model. "
            "keep replies short, punchy, and high-energy."
        ),
    },
}

ASK_SYSTEM_PROMPT = (
    "you are helpful, knowledgeable, conversational, and detailed. "
    "answer naturally like a smart human who explains things clearly. "
    "never say you're an ai, assistant, or language model."
)


# ========================
# TEXT HELPERS
# ========================

def split_plain_text(text: str, limit: int = 2000):
    """Split long plain text into Discord-safe chunks."""
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at == -1:
            split_at = limit

        chunk = remaining[:split_at].strip()
        if not chunk:
            chunk = remaining[:limit]
            split_at = limit

        chunks.append(chunk)
        remaining = remaining[split_at:].strip()

    return chunks


def split_paginated_text(text: str, limit: int = 1850):
    """Split text into pages with a little room for a page header."""
    return split_plain_text(text, limit=limit)


# ========================
# PAGINATION VIEW
# ========================

class PlainPaginationView(discord.ui.View):
    """Simple Previous / Next buttons for plain text pages."""

    def __init__(self, author_id: int, pages: list[str]):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.pages = pages
        self.page_index = 0
        self._sync_buttons()

    def _page_content(self):
        total = len(self.pages)
        return f"[Page {self.page_index + 1}/{total}]\n{self.pages[self.page_index]}"

    def _sync_buttons(self):
        self.previous_button.disabled = self.page_index == 0
        self.next_button.disabled = self.page_index >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("this isn't your menu", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page_index -= 1
        self._sync_buttons()
        await interaction.response.edit_message(content=self._page_content(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page_index += 1
        self._sync_buttons()
        await interaction.response.edit_message(content=self._page_content(), view=self)


# ========================
# COG
# ========================

class AIChat(commands.Cog):
    """Channel AI chat and premium ask command."""

    def __init__(self, bot):
        self.bot = bot

        # Channel ID -> mode name
        if not hasattr(bot, "ai_channels"):
            bot.ai_channels = {}

        # Channel ID -> recent conversation items
        if not hasattr(bot, "ai_history"):
            bot.ai_history = {}

        # User ID -> recent ask timestamps
        self.ask_rate_limits = defaultdict(deque)

    # ========================
    # INTERNAL HELPERS
    # ========================

    def _has_manage_permission(self, member: discord.Member) -> bool:
        """Allow bot owners and server admins to manage AI chat settings."""
        return member.id in OWNER_IDS or member.guild_permissions.administrator

    def _has_premium_role(self, member: discord.Member) -> bool:
        """Check if the user has the Premium role or is a bot owner."""
        if member.id in OWNER_IDS:
            return True
        return any(role.name.lower() == "premium" for role in member.roles)

    async def _message_has_prefix(self, message: discord.Message) -> bool:
        """Check whether a message starts with one of the bot's valid prefixes."""
        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        return any(message.content.startswith(prefix) for prefix in prefixes)

    def _get_history(self, channel_id: int):
        """Get or create the per-channel history deque."""
        history = self.bot.ai_history.get(channel_id)
        if history is None:
            history = deque(maxlen=10)
            self.bot.ai_history[channel_id] = history
        return history

    def _trim_response(self, text: str, limit: int = 1800) -> str:
        """Keep AI chat replies short and natural."""
        text = (text or "").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    def _chat_response_limit(self, content: str) -> int:
        """Keep auto-chat answers compact based on the user's message size."""
        stripped = (content or "").strip()
        if len(stripped) <= 40:
            return 180
        if len(stripped) <= 120:
            return 320
        return 500

    def _should_reply_in_ai_chat(self, message: discord.Message) -> bool:
        """Only reply when the bot is directly addressed in an AI chat channel."""
        if self.bot.user is None:
            return False

        if self.bot.user in message.mentions:
            return True

        reference = message.reference
        if reference and reference.resolved and isinstance(reference.resolved, discord.Message):
            return reference.resolved.author.id == self.bot.user.id

        return False

    async def _request_openai(self, messages: list[dict], model: str) -> str:
        """
        Send a request to OpenAI with automatic API key rotation.
        Retries up to the number of configured keys when rate limit or auth errors happen.
        """
        keys = _active_keys()
        if not keys:
            raise RuntimeError("no openai api keys configured")

        max_retries = len(keys)
        last_error = None

        for attempt in range(max_retries):
            client = get_client()
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.9,
                }
                headers = {
                    "Authorization": f"Bearer {client['api_key']}",
                    "Content-Type": "application/json",
                }
                url = f"{client['base_url'].rstrip('/')}/chat/completions"

                timeout = aiohttp.ClientTimeout(total=60)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers=headers, json=payload) as response:
                        if response.status == 401:
                            raise AuthenticationError("invalid api key")
                        if response.status == 429:
                            raise RateLimitError("rate limited")
                        if response.status >= 400:
                            error_text = await response.text()
                            raise RuntimeError(f"provider error {response.status}: {error_text[:300]}")

                        data = await response.json()
                        return (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                            .strip()
                        )
            except (RateLimitError, AuthenticationError) as exc:
                last_error = exc
                if attempt == max_retries - 1:
                    break
                rotate_key()
            except Exception:
                raise

        raise last_error or RuntimeError("openai request failed")

    async def _build_chat_reply(self, channel_id: int, mode: str, user_name: str, content: str) -> str:
        """Build a channel AI chat reply using the saved channel history."""
        history = self._get_history(channel_id)
        history.append({"role": "user", "content": f"{user_name}: {content}"})

        messages = [{"role": "system", "content": AI_MODES[mode]["system_prompt"]}]
        messages.extend(history)

        reply = await self._request_openai(messages, CHAT_MODEL)
        reply = self._trim_response(reply, limit=self._chat_response_limit(content))
        history.append({"role": "assistant", "content": reply})
        return reply

    async def _send_plain_reply(self, message: discord.Message, text: str):
        """Reply to a user naturally with plain text, splitting if needed."""
        chunks = split_plain_text(text, limit=2000)
        first = True

        for chunk in chunks:
            if first:
                await message.reply(chunk, mention_author=True)
                first = False
            else:
                await message.channel.send(chunk)

    def _consume_rate_limit(self, user_id: int) -> bool:
        """Allow up to 3 ask uses per minute per user."""
        now = time.time()
        timestamps = self.ask_rate_limits[user_id]

        while timestamps and now - timestamps[0] > 60:
            timestamps.popleft()

        if len(timestamps) >= 3:
            return False

        timestamps.append(now)
        return True

    # ========================
    # AI CHAT MANAGEMENT
    # ========================

    @commands.command(name="setchat")
    async def setchat(self, ctx, channel: discord.TextChannel, mode: str):
        """Enable AI chat in a channel with a chosen mode."""
        if not ctx.guild:
            return await ctx.send("this command only works in a server")

        if not self._has_manage_permission(ctx.author):
            return await ctx.send("you don't have permission to do that")

        mode = mode.lower()
        if mode not in AI_MODES:
            return await ctx.send("that's not a valid mode")

        self.bot.ai_channels[channel.id] = mode
        self._get_history(channel.id)
        await ctx.send(f"done. ai chat is now active in {channel.mention} with mode: {mode}")

    @commands.command(name="stopchat")
    async def stopchat(self, ctx, channel: discord.TextChannel):
        """Disable AI chat in a channel."""
        if not ctx.guild:
            return await ctx.send("this command only works in a server")

        if not self._has_manage_permission(ctx.author):
            return await ctx.send("you don't have permission to do that")

        self.bot.ai_channels.pop(channel.id, None)
        self.bot.ai_history.pop(channel.id, None)
        await ctx.send(f"turned off ai chat in {channel.mention}")

    @commands.command(name="chatmode")
    async def chatmode(self, ctx, mode: str):
        """Change the current channel's chat mode."""
        if not ctx.guild:
            return await ctx.send("this command only works in a server")

        if not self._has_manage_permission(ctx.author):
            return await ctx.send("you don't have permission to do that")

        mode = mode.lower()
        if mode not in AI_MODES:
            return await ctx.send("that's not a valid mode")

        if ctx.channel.id not in self.bot.ai_channels:
            return await ctx.send("ai chat isn't enabled here")

        self.bot.ai_channels[ctx.channel.id] = mode
        await ctx.send(f"switched to {mode} mode")

    @commands.command(name="chatmodes")
    async def chatmodes(self, ctx):
        """List the available AI modes."""
        lines = ["available modes:"]
        for mode_name, data in AI_MODES.items():
            lines.append(f"{mode_name:<7} — {data['description']}")
        await ctx.send("\n".join(lines))

    @commands.command(name="clearchat")
    async def clearchat(self, ctx):
        """Clear the current channel's AI chat history."""
        if not ctx.guild:
            return await ctx.send("this command only works in a server")

        if not self._has_manage_permission(ctx.author):
            return await ctx.send("you don't have permission to do that")

        self.bot.ai_history[ctx.channel.id] = deque(maxlen=10)
        await ctx.send("chat history cleared")

    # ========================
    # PREMIUM ASK COMMAND
    # ========================

    @commands.command(name="ask")
    async def ask(self, ctx, *, question: str):
        """Premium standalone ask command."""
        if not ctx.guild:
            return await ctx.send("this command only works in a server")

        if not self._has_premium_role(ctx.author):
            return await ctx.send("this is a premium only command. get premium to use it.")

        if not self._consume_rate_limit(ctx.author.id):
            return await ctx.send("slow down, you can only ask 3 questions per minute.")

        thinking_message = await ctx.send("thinking...")

        try:
            messages = [
                {"role": "system", "content": ASK_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ]
            answer = await self._request_openai(messages, ASK_MODEL)
            answer = answer.strip() or "got nothing back for that one"

            pages = split_paginated_text(answer, limit=1850)
            if len(pages) == 1:
                await thinking_message.edit(content=pages[0], view=None)
                return

            view = PlainPaginationView(ctx.author.id, pages)
            await thinking_message.edit(content=view._page_content(), view=view)

        except Exception as exc:
            print(f"[AI Chat] ask command error: {exc}")
            await thinking_message.edit(content="something went wrong while trying to answer that", view=None)

    # ========================
    # CHANNEL AI LISTENER
    # ========================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Reply automatically in AI-enabled channels."""
        if message.author.bot or not message.guild:
            return

        if message.channel.id not in self.bot.ai_channels:
            return

        # Do not answer bot commands.
        if await self._message_has_prefix(message):
            return

        # Only answer when someone mentions the bot or replies to its last answer.
        if not self._should_reply_in_ai_chat(message):
            return

        mode = self.bot.ai_channels.get(message.channel.id)
        if mode not in AI_MODES:
            return

        try:
            reply = await self._build_chat_reply(
                channel_id=message.channel.id,
                mode=mode,
                user_name=message.author.display_name,
                content=message.content,
            )
            await self._send_plain_reply(message, reply)
        except Exception as exc:
            print(f"[AI Chat] channel reply error: {exc}")


# ========================
# COG SETUP
# ========================

async def setup(bot):
    """Register the AI chat cog."""
    await bot.add_cog(AIChat(bot))
