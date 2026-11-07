# cogs/crypto.py
import discord
from discord.ext import commands
import aiohttp
from datetime import datetime
import math
import json
import os

# ─── In-memory portfolio store  (guild-agnostic, resets on restart) ───────────
# Structure: { user_id: { "BTCUSDT": qty, ... } }
_portfolios: dict[int, dict[str, float]] = {}

class Crypto(commands.Cog):
    """📈 Real-time crypto data powered by Binance & CoinGecko."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        import asyncio
        asyncio.create_task(self.session.close())

    # ──────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────────
    async def get_binance_data(self, symbol: str, pair: str):
        """Fetch 24-hr ticker from Binance."""
        ticker = f"{symbol.upper()}{pair.upper()}"
        url = "https://api.binance.com/api/v3/ticker/24hr"
        try:
            async with self.session.get(url, params={"symbol": ticker}) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 400:
                    return "NOT_FOUND"
                return None
        except Exception:
            return None

    async def get_binance_price(self, symbol: str, pair: str = "USDT"):
        """Quick last-price helper. Returns float or None."""
        data = await self.get_binance_data(symbol, pair)
        if isinstance(data, dict):
            return float(data["lastPrice"])
        return None

    async def get_coingecko(self, endpoint: str, params: dict = None):
        """Generic CoinGecko GET."""
        base = "https://api.coingecko.com/api/v3"
        try:
            async with self.session.get(f"{base}{endpoint}", params=params or {}) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            pass
        return None

    def create_progress_bar(self, low, high, current):
        """Visual bar showing where price sits between low/high."""
        if high - low == 0:
            return "🔘▬▬▬▬▬▬▬▬▬▬"
        percentage = (current - low) / (high - low)
        pos = max(0, min(int(percentage * 10), 9))
        return "".join("🔘" if i == pos else "▬" for i in range(10))

    @staticmethod
    def fmt(num: float) -> str:
        if num > 1000:
            return f"{num:,.2f}"
        if num < 0.01:
            return f"{num:.6f}"
        return f"{num:.3f}"

    @staticmethod
    def human_fmt(num: float) -> str:
        suffixes = ["", "K", "M", "B", "T"]
        mag = 0
        while abs(num) >= 1000 and mag < 4:
            mag += 1
            num /= 1000.0
        return f"{num:.2f}{suffixes[mag]}"

    def _sentiment(self, pct: float):
        if pct >= 5.0:
            return "🚀 MOONING"
        if pct > 0:
            return "🐂 BULLISH"
        if pct <= -5.0:
            return "🩸 CRASHING"
        return "🐻 BEARISH"

    # ──────────────────────────────────────────────────────────────────────────
    # 1. PRICE  ─  ,crypto / ,c / ,price / ,coin
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="crypto", aliases=["c", "price", "coin"])
    async def crypto(self, ctx: commands.Context, symbol: str, pair: str = "USDT"):
        """📊 Full 24-hr Binance market snapshot for any pair.

        Usage: `,crypto BTC` or `,crypto ETH BTC`"""
        async with ctx.typing():
            data = await self.get_binance_data(symbol, pair)
            if data == "NOT_FOUND":
                return await ctx.send(f"❌ Pair **{symbol.upper()}/{pair.upper()}** not found on Binance.")
            if not data:
                return await ctx.send("❌ Binance API is currently unavailable.")

            last_price  = float(data["lastPrice"])
            price_change = float(data["priceChange"])
            change_pct  = float(data["priceChangePercent"])
            high        = float(data["highPrice"])
            low         = float(data["lowPrice"])
            open_price  = float(data["openPrice"])
            vol_base    = float(data["volume"])
            vol_quote   = float(data["quoteVolume"])
            bid         = float(data["bidPrice"])
            ask         = float(data["askPrice"])
            vwap        = float(data["weightedAvgPrice"])
            trades      = int(data["count"])

            spread      = ask - bid
            spread_pct  = (spread / ask) * 100 if ask else 0

            is_up    = change_pct >= 0
            color    = discord.Color.green() if is_up else discord.Color.red()
            arrow    = "📈" if is_up else "📉"
            live_dot = "🟢" if is_up else "🔴"
            sentiment = self._sentiment(change_pct)

            icon_url = (
                f"https://raw.githubusercontent.com/spothq/cryptocurrency-icons"
                f"/master/128/color/{symbol.lower()}.png"
            )
            binance_logo = (
                "https://public.bnbstatic.com/20190405/"
                "eb2349c3-b218-43f3-b92e-525142806529.png"
            )

            embed = discord.Embed(color=color, timestamp=datetime.now())
            embed.set_author(
                name=f"{symbol.upper()} / {pair.upper()} • Binance Spot",
                icon_url=binance_logo,
            )
            embed.set_thumbnail(url=icon_url)
            embed.title = f"{live_dot} {self.fmt(last_price)} {pair.upper()}"
            embed.description = f"**{sentiment}** • `{arrow} {change_pct:+.2f}%` (24h)"

            embed.add_field(
                name="📊 Market Stats",
                value=(
                    f"**Change:** `{self.fmt(price_change)}`\n"
                    f"**VWAP:** `{self.fmt(vwap)}`\n"
                    f"**Open:** `{self.fmt(open_price)}`"
                ),
                inline=True,
            )
            embed.add_field(
                name="💰 Volume & Activity",
                value=(
                    f"**Vol ({symbol.upper()}):** `{self.human_fmt(vol_base)}`\n"
                    f"**Vol ({pair.upper()}):** `{self.human_fmt(vol_quote)}`\n"
                    f"**Trades:** `{trades:,}`"
                ),
                inline=True,
            )
            embed.add_field(
                name="⚖️ Order Book",
                value=(
                    f"**Bid:** `{self.fmt(bid)}`\n"
                    f"**Ask:** `{self.fmt(ask)}`\n"
                    f"**Spread:** `{spread_pct:.3f}%`"
                ),
                inline=True,
            )
            bar = self.create_progress_bar(low, high, last_price)
            embed.add_field(
                name="📉 24h Range",
                value=f"`L: {self.fmt(low)}` {bar} `H: {self.fmt(high)}`",
                inline=False,
            )
            embed.set_footer(text=f"Binance API • {pair.upper()} Market")
            await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. COMPARE  ─  ,compare / ,cc
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="compare", aliases=["cc", "cmp"])
    async def compare(self, ctx: commands.Context, *symbols: str):
        """📊 Side-by-side comparison of up to 5 coins (pair defaults to USDT).

        Usage: `,compare BTC ETH SOL`"""
        if not symbols:
            return await ctx.send("❌ Provide at least 1 symbol. E.g. `,compare BTC ETH SOL`")
        symbols = symbols[:5]

        async with ctx.typing():
            rows = []
            for sym in symbols:
                data = await self.get_binance_data(sym, "USDT")
                if not isinstance(data, dict):
                    rows.append((sym.upper(), None))
                    continue
                rows.append((
                    sym.upper(),
                    {
                        "price": float(data["lastPrice"]),
                        "pct":   float(data["priceChangePercent"]),
                        "vol":   float(data["quoteVolume"]),
                        "high":  float(data["highPrice"]),
                        "low":   float(data["lowPrice"]),
                    },
                ))

            color = discord.Color.blurple()
            embed = discord.Embed(
                title="📊 Crypto Comparison (vs USDT)",
                color=color,
                timestamp=datetime.now(),
            )

            for sym, info in rows:
                if info is None:
                    embed.add_field(name=f"❓ {sym}", value="Not found on Binance", inline=False)
                    continue
                arrow = "📈" if info["pct"] >= 0 else "📉"
                embed.add_field(
                    name=f"{arrow} {sym}/USDT",
                    value=(
                        f"**Price:** `{self.fmt(info['price'])}`\n"
                        f"**24h:** `{info['pct']:+.2f}%`\n"
                        f"**Vol:** `{self.human_fmt(info['vol'])} USDT`\n"
                        f"**Range:** `{self.fmt(info['low'])} – {self.fmt(info['high'])}`"
                    ),
                    inline=True,
                )

            embed.set_footer(text="Binance API • Real-time data")
            await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # 3. CONVERT  ─  ,convert / ,cv
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="convert", aliases=["cv", "conv"])
    async def convert(
        self,
        ctx: commands.Context,
        amount: float,
        from_sym: str,
        to_sym: str = "USDT",
    ):
        """🔄 Convert an amount between two crypto assets using live Binance prices.

        Usage: `,convert 0.5 BTC ETH` or `,convert 1000 USDT SOL`"""
        async with ctx.typing():
            from_sym = from_sym.upper()
            to_sym   = to_sym.upper()

            # Try direct pair first
            price_in_usdt_from = None
            price_in_usdt_to   = None

            if from_sym == "USDT":
                price_in_usdt_from = 1.0
            else:
                price_in_usdt_from = await self.get_binance_price(from_sym, "USDT")

            if to_sym == "USDT":
                price_in_usdt_to = 1.0
            else:
                price_in_usdt_to = await self.get_binance_price(to_sym, "USDT")

            if price_in_usdt_from is None or price_in_usdt_to is None:
                return await ctx.send(
                    f"❌ Could not fetch prices for **{from_sym}** or **{to_sym}**."
                )

            usdt_value = amount * price_in_usdt_from
            result     = usdt_value / price_in_usdt_to

            color = discord.Color.gold()
            embed = discord.Embed(
                title="🔄 Crypto Converter",
                description=(
                    f"**{amount:,.6g} {from_sym}**  →  **{self.fmt(result)} {to_sym}**"
                ),
                color=color,
                timestamp=datetime.now(),
            )
            embed.add_field(name=f"{from_sym} price (USDT)", value=f"`{self.fmt(price_in_usdt_from)}`", inline=True)
            embed.add_field(name=f"{to_sym} price (USDT)",   value=f"`{self.fmt(price_in_usdt_to)}`",   inline=True)
            embed.add_field(name="USDT value",               value=f"`{self.fmt(usdt_value)}`",         inline=True)
            embed.set_footer(text="Rates via Binance spot • approx. conversion")
            await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # 4. TRENDING  ─  ,trending / ,hot
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="trending", aliases=["hot", "trend"])
    async def trending(self, ctx: commands.Context):
        """🔥 Top trending coins right now (CoinGecko).

        Usage: `,trending`"""
        async with ctx.typing():
            data = await self.get_coingecko("/search/trending")
            if not data:
                return await ctx.send("❌ CoinGecko API is currently unavailable.")

            coins = data.get("coins", [])[:7]
            embed = discord.Embed(
                title="🔥 Trending Coins on CoinGecko",
                color=discord.Color.orange(),
                timestamp=datetime.now(),
            )

            lines = []
            for idx, entry in enumerate(coins, 1):
                item = entry.get("item", {})
                name   = item.get("name", "?")
                sym    = item.get("symbol", "?").upper()
                rank   = item.get("market_cap_rank", "?")
                score  = item.get("score", 0)
                price_btc = item.get("price_btc", 0)
                lines.append(
                    f"**{idx}.** {name} (`{sym}`) — MCap Rank #{rank}\n"
                    f"    Price ≈ `{price_btc:.8f} BTC`"
                )

            embed.description = "\n".join(lines) if lines else "No data returned."
            embed.set_footer(text="CoinGecko Trending • updates every 10 min")
            await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # 5. DOMINANCE  ─  ,dominance / ,dom
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="dominance", aliases=["dom", "domination"])
    async def dominance(self, ctx: commands.Context):
        """🏆 Live BTC & ETH market dominance and global crypto cap.

        Usage: `,dominance`"""
        async with ctx.typing():
            data = await self.get_coingecko("/global")
            if not data:
                return await ctx.send("❌ CoinGecko API is unavailable.")

            gdata = data.get("data", {})
            total_cap  = gdata.get("total_market_cap", {}).get("usd", 0)
            total_vol  = gdata.get("total_volume", {}).get("usd", 0)
            btc_dom    = gdata.get("market_cap_percentage", {}).get("btc", 0)
            eth_dom    = gdata.get("market_cap_percentage", {}).get("eth", 0)
            active     = gdata.get("active_cryptocurrencies", 0)
            exchanges  = gdata.get("markets", 0)
            cap_change = gdata.get("market_cap_change_percentage_24h_usd", 0)

            color = discord.Color.gold()
            embed = discord.Embed(
                title="🌐 Global Crypto Market Overview",
                color=color,
                timestamp=datetime.now(),
            )
            embed.add_field(
                name="💰 Market Capitalization",
                value=(
                    f"**Total Cap:** `${self.human_fmt(total_cap)}`\n"
                    f"**24h Change:** `{cap_change:+.2f}%`\n"
                    f"**24h Volume:** `${self.human_fmt(total_vol)}`"
                ),
                inline=True,
            )
            embed.add_field(
                name="🏆 Dominance",
                value=(
                    f"**BTC:** `{btc_dom:.2f}%`\n"
                    f"**ETH:** `{eth_dom:.2f}%`\n"
                    f"**Others:** `{100 - btc_dom - eth_dom:.2f}%`"
                ),
                inline=True,
            )
            embed.add_field(
                name="📊 Market Stats",
                value=(
                    f"**Active Coins:** `{active:,}`\n"
                    f"**Exchanges:** `{exchanges:,}`"
                ),
                inline=True,
            )

            # BTC dominance progress bar
            btc_bar_filled = int(btc_dom / 10)
            btc_bar = "█" * btc_bar_filled + "░" * (10 - btc_bar_filled)
            eth_bar_filled = int(eth_dom / 10)
            eth_bar = "█" * eth_bar_filled + "░" * (10 - eth_bar_filled)

            embed.add_field(
                name="📊 Dominance Bars",
                value=(
                    f"BTC `{btc_bar}` {btc_dom:.1f}%\n"
                    f"ETH `{eth_bar}` {eth_dom:.1f}%"
                ),
                inline=False,
            )
            embed.set_footer(text="CoinGecko Global Data")
            await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # 6. FEAR & GREED  ─  ,feargreed / ,fg
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="feargreed", aliases=["fg", "fear", "greed"])
    async def feargreed(self, ctx: commands.Context):
        """😱 Crypto Fear & Greed Index from alternative.me.

        Usage: `,feargreed`"""
        async with ctx.typing():
            url = "https://api.alternative.me/fng/?limit=7&format=json"
            try:
                async with self.session.get(url) as resp:
                    if resp.status != 200:
                        return await ctx.send("❌ Could not fetch Fear & Greed data.")
                    raw = await resp.json()
            except Exception:
                return await ctx.send("❌ Fear & Greed API unavailable.")

            entries = raw.get("data", [])
            if not entries:
                return await ctx.send("❌ No data returned.")

            current    = entries[0]
            value      = int(current["value"])
            label      = current["value_classification"]
            timestamp  = datetime.utcfromtimestamp(int(current["timestamp"]))

            # Pick color & emoji based on score
            if value <= 25:
                color = discord.Color.red()
                mood_emoji = "😱"
            elif value <= 45:
                color = discord.Color.orange()
                mood_emoji = "😰"
            elif value <= 55:
                color = discord.Color.yellow()
                mood_emoji = "😐"
            elif value <= 75:
                color = discord.Color.green()
                mood_emoji = "😁"
            else:
                color = discord.Color.from_rgb(0, 200, 100)
                mood_emoji = "🤑"

            # Build gauge bar
            filled = int(value / 10)
            bar    = "█" * filled + "░" * (10 - filled)

            embed = discord.Embed(
                title=f"{mood_emoji} Crypto Fear & Greed Index",
                description=f"**{value}/100** — {label}\n`{bar}`",
                color=color,
                timestamp=datetime.now(),
            )

            # 7-day history
            history_lines = []
            for entry in entries[1:]:
                v  = int(entry["value"])
                lbl = entry["value_classification"]
                ts  = datetime.utcfromtimestamp(int(entry["timestamp"])).strftime("%b %d")
                icon = "🔴" if v <= 45 else "🟡" if v <= 55 else "🟢"
                history_lines.append(f"{icon} **{ts}** — {v} ({lbl})")

            if history_lines:
                embed.add_field(
                    name="📅 Last 7 Days",
                    value="\n".join(history_lines),
                    inline=False,
                )

            embed.set_footer(text="Data: alternative.me/fng")
            await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # 7. TOP GAINERS / LOSERS  ─  ,gainers  /  ,losers
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="gainers", aliases=["topgainers", "movers"])
    async def gainers(self, ctx: commands.Context, pair: str = "USDT", top: int = 5):
        """🚀 Top gainers on Binance in the last 24h.

        Usage: `,gainers` or `,gainers USDT 10`"""
        await self._top_movers(ctx, pair, top, mode="gainers")

    @commands.command(name="losers", aliases=["toplosers", "worst"])
    async def losers(self, ctx: commands.Context, pair: str = "USDT", top: int = 5):
        """📉 Biggest losers on Binance in the last 24h.

        Usage: `,losers` or `,losers USDT 10`"""
        await self._top_movers(ctx, pair, top, mode="losers")

    async def _top_movers(self, ctx, pair: str, top: int, mode: str):
        top = max(1, min(top, 15))
        async with ctx.typing():
            url = "https://api.binance.com/api/v3/ticker/24hr"
            try:
                async with self.session.get(url) as resp:
                    if resp.status != 200:
                        return await ctx.send("❌ Binance API error.")
                    all_tickers = await resp.json()
            except Exception:
                return await ctx.send("❌ Could not reach Binance.")

            pair = pair.upper()
            filtered = [
                t for t in all_tickers
                if t["symbol"].endswith(pair) and float(t["quoteVolume"]) > 500_000
            ]

            if not filtered:
                return await ctx.send(f"❌ No tickers found for pair **{pair}**.")

            key = "priceChangePercent"
            if mode == "gainers":
                sorted_tickers = sorted(filtered, key=lambda t: float(t[key]), reverse=True)
                title = f"🚀 Top {top} Gainers ({pair} pairs, 24h)"
                color = discord.Color.green()
                emoji = "📈"
            else:
                sorted_tickers = sorted(filtered, key=lambda t: float(t[key]))
                title = f"📉 Top {top} Losers ({pair} pairs, 24h)"
                color = discord.Color.red()
                emoji = "📉"

            embed = discord.Embed(title=title, color=color, timestamp=datetime.now())
            lines = []
            for i, t in enumerate(sorted_tickers[:top], 1):
                sym = t["symbol"].replace(pair, "")
                pct = float(t[key])
                price = float(t["lastPrice"])
                vol   = float(t["quoteVolume"])
                lines.append(
                    f"**{i}.** `{sym}/{pair}` {emoji} **{pct:+.2f}%**\n"
                    f"    Price: `{self.fmt(price)}` | Vol: `{self.human_fmt(vol)} {pair}`"
                )

            embed.description = "\n".join(lines)
            embed.set_footer(text="Binance API • min vol filter: $500K")
            await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # 8. PORTFOLIO  ─  ,portfolio / ,port
    # ──────────────────────────────────────────────────────────────────────────
    @commands.group(name="portfolio", aliases=["port", "pf"], invoke_without_command=True)
    async def portfolio(self, ctx: commands.Context):
        """💼 View your crypto portfolio value (vs USDT).

        Subcommands: `add`, `remove`, `clear`
        Usage: `,portfolio`"""
        uid  = ctx.author.id
        data = _portfolios.get(uid, {})
        if not data:
            return await ctx.send(
                "💼 Your portfolio is empty.\n"
                f"Add coins with `,portfolio add <SYMBOL> <QTY>` — e.g. `,portfolio add BTC 0.5`"
            )

        async with ctx.typing():
            total_usd = 0.0
            rows = []
            for sym, qty in data.items():
                price = await self.get_binance_price(sym, "USDT")
                if price is None:
                    rows.append((sym, qty, None, None))
                    continue
                value = qty * price
                total_usd += value
                rows.append((sym, qty, price, value))

            color = discord.Color.blurple()
            embed = discord.Embed(
                title=f"💼 {ctx.author.display_name}'s Portfolio",
                color=color,
                timestamp=datetime.now(),
            )

            lines = []
            for sym, qty, price, value in rows:
                if price is None:
                    lines.append(f"❓ **{sym}** — {qty:g} units (price unavailable)")
                    continue
                weight = (value / total_usd * 100) if total_usd else 0
                lines.append(
                    f"**{sym}/USDT** — `{qty:g}` units\n"
                    f"  Price: `{self.fmt(price)}` | Value: `${self.fmt(value)}` | `{weight:.1f}%`"
                )

            embed.description = "\n".join(lines)
            embed.add_field(
                name="💰 Total Portfolio Value",
                value=f"**`${self.fmt(total_usd)}`**",
                inline=False,
            )
            embed.set_footer(text="Prices via Binance • balances reset on restart")
            await ctx.send(embed=embed)

    @portfolio.command(name="add")
    async def portfolio_add(self, ctx: commands.Context, symbol: str, qty: float):
        """➕ Add a coin to your portfolio.

        Usage: `,portfolio add ETH 2.5`"""
        symbol = symbol.upper()
        if qty <= 0:
            return await ctx.send("❌ Quantity must be greater than 0.")
        # Quick validation — does the pair exist?
        price = await self.get_binance_price(symbol, "USDT")
        if price is None:
            return await ctx.send(f"❌ `{symbol}/USDT` not found on Binance.")

        uid = ctx.author.id
        if uid not in _portfolios:
            _portfolios[uid] = {}
        _portfolios[uid][symbol] = _portfolios[uid].get(symbol, 0) + qty

        embed = discord.Embed(
            description=(
                f"✅ Added **{qty:g} {symbol}** to your portfolio.\n"
                f"Total held: `{_portfolios[uid][symbol]:g} {symbol}`\n"
                f"Current price: `{self.fmt(price)} USDT`"
            ),
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @portfolio.command(name="remove", aliases=["rm", "del", "delete"])
    async def portfolio_remove(self, ctx: commands.Context, symbol: str, qty: float = None):
        """➖ Remove a coin (or partial amount) from your portfolio.

        Usage: `,portfolio remove BTC` or `,portfolio remove BTC 0.1`"""
        symbol = symbol.upper()
        uid    = ctx.author.id
        data   = _portfolios.get(uid, {})

        if symbol not in data:
            return await ctx.send(f"❌ You don't have `{symbol}` in your portfolio.")

        if qty is None or qty >= data[symbol]:
            del data[symbol]
            msg = f"🗑️ Removed all **{symbol}** from your portfolio."
        else:
            data[symbol] -= qty
            msg = f"🗑️ Removed **{qty:g} {symbol}**. Remaining: `{data[symbol]:g}`."

        await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.red()))

    @portfolio.command(name="clear")
    async def portfolio_clear(self, ctx: commands.Context):
        """🗑️ Clear your entire portfolio.

        Usage: `,portfolio clear`"""
        _portfolios.pop(ctx.author.id, None)
        await ctx.send(embed=discord.Embed(
            description="🗑️ Your portfolio has been cleared.",
            color=discord.Color.red(),
        ))

    # ──────────────────────────────────────────────────────────────────────────
    # 9. ATH  ─  ,ath
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="ath")
    async def ath(self, ctx: commands.Context, coin_id: str):
        """🏆 All-time high info for a coin (CoinGecko ID).

        Usage: `,ath bitcoin` or `,ath ethereum`"""
        async with ctx.typing():
            data = await self.get_coingecko(
                f"/coins/{coin_id.lower()}",
                {"localization": "false", "tickers": "false", "community_data": "false"},
            )
            if not data or "error" in data:
                return await ctx.send(
                    f"❌ Coin **{coin_id}** not found. Use the CoinGecko slug, e.g. `bitcoin`, `ethereum`, `solana`."
                )

            mkt   = data.get("market_data", {})
            ath   = mkt.get("ath", {}).get("usd", 0)
            ath_d = mkt.get("ath_date", {}).get("usd", "?")
            atl   = mkt.get("atl", {}).get("usd", 0)
            atl_d = mkt.get("atl_date", {}).get("usd", "?")
            cur   = mkt.get("current_price", {}).get("usd", 0)
            from_ath = mkt.get("ath_change_percentage", {}).get("usd", 0)

            if ath_d and ath_d != "?":
                ath_d = ath_d[:10]
            if atl_d and atl_d != "?":
                atl_d = atl_d[:10]

            name   = data.get("name", coin_id)
            sym    = data.get("symbol", "?").upper()
            thumb  = data.get("image", {}).get("small", "")

            embed = discord.Embed(
                title=f"🏆 {name} ({sym}) — All-Time Stats",
                color=discord.Color.gold(),
                timestamp=datetime.now(),
            )
            if thumb:
                embed.set_thumbnail(url=thumb)

            embed.add_field(
                name="📈 All-Time High",
                value=f"`${self.fmt(ath)}`\n{ath_d}",
                inline=True,
            )
            embed.add_field(
                name="📉 All-Time Low",
                value=f"`${self.fmt(atl)}`\n{atl_d}",
                inline=True,
            )
            embed.add_field(
                name="💰 Current Price",
                value=f"`${self.fmt(cur)}`",
                inline=True,
            )
            embed.add_field(
                name="📊 From ATH",
                value=f"`{from_ath:.2f}%`",
                inline=True,
            )
            embed.set_footer(text="CoinGecko • use CoinGecko coin slug as ID")
            await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # 10. CRYPTOHELP  ─  ,cryptohelp
    # ──────────────────────────────────────────────────────────────────────────
    @commands.command(name="cryptohelp", aliases=["chelp"])
    async def cryptohelp(self, ctx: commands.Context):
        """📚 Lists all crypto module commands.

        Usage: `,cryptohelp`"""
        embed = discord.Embed(
            title="📈 Crypto Commands",
            description="All commands for the crypto module.",
            color=discord.Color.blurple(),
            timestamp=datetime.now(),
        )
        cmds = [
            ("`crypto` / `c` / `price`", "`<symbol> [pair]`", "Full 24h market snapshot from Binance"),
            ("`compare` / `cc`",         "`<sym1> <sym2> ...`", "Side-by-side comparison (up to 5)"),
            ("`convert` / `cv`",         "`<amt> <from> <to>`", "Live crypto conversion"),
            ("`trending` / `hot`",       "",                   "Top trending coins (CoinGecko)"),
            ("`dominance` / `dom`",      "",                   "BTC/ETH dominance & global cap"),
            ("`feargreed` / `fg`",       "",                   "Fear & Greed Index + 7-day history"),
            ("`gainers`",                "`[pair] [top]`",     "Top 24h gainers on Binance"),
            ("`losers`",                 "`[pair] [top]`",     "Top 24h losers on Binance"),
            ("`portfolio` / `pf`",       "",                   "View your portfolio value"),
            ("`portfolio add`",          "`<sym> <qty>`",      "Add a coin to your portfolio"),
            ("`portfolio remove`",       "`<sym> [qty]`",      "Remove a coin from your portfolio"),
            ("`portfolio clear`",        "",                   "Wipe your portfolio"),
            ("`ath`",                    "`<coingecko-id>`",   "All-time high & low for any coin"),
        ]
        for name, usage, desc in cmds:
            embed.add_field(
                name=f"{name} {usage}",
                value=desc,
                inline=False,
            )
        embed.set_footer(text="Powered by Binance & CoinGecko APIs")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Crypto(bot))
