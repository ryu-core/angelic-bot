"""
Music Cog — Angelic Bot
━━━━━━━━━━━━━━━━━━━━━━━
Sources:
  • Spotify URLs  → metadata via Spotify API  → audio via YouTube (yt-dlp)
  • Plain text    → direct YouTube search via yt-dlp
Features:
  • Spotify track / album / playlist support
  • Lazy YouTube resolution for playlists (instant queue)
  • Premium audio filters, 24/7 mode, MySQL history
"""

import asyncio
import math
import os
import random
import re
from collections import deque
from datetime import datetime, timezone
from typing import Union

import discord
import yt_dlp
from discord.ext import commands

# ─────────────────────────────────────────────────────────────────────────────
#  Optional Spotify import (graceful if spotipy not installed)
# ─────────────────────────────────────────────────────────────────────────────
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    _SPOTIPY_AVAILABLE = True
except ImportError:
    _SPOTIPY_AVAILABLE = False

yt_dlp.utils.bug_reports_message = lambda: ""

# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────

EMBED_COLOR    = 0x9b59b6
SPOTIFY_COLOR  = 0x1DB954   # Spotify green for Spotify embeds
INACTIVITY_SEC = 180
MAX_QUEUE      = 200
PLAYLIST_CAP   = 50         # max tracks loaded from a Spotify playlist

YTDL_OPTIONS = {
    "format":             "bestaudio/best",
    "noplaylist":         True,
    "quiet":              True,
    "no_warnings":        True,
    "source_address":     "0.0.0.0",
    "nocheckcertificate": True,
    "ignoreerrors":       False,
    "logtostderr":        False,
    "extract_flat":       False,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options":        "-vn",
}

# Spotify URL patterns
_SP_TRACK    = re.compile(r"open\.spotify\.com/track/([A-Za-z0-9]+)")
_SP_ALBUM    = re.compile(r"open\.spotify\.com/album/([A-Za-z0-9]+)")
_SP_PLAYLIST = re.compile(r"open\.spotify\.com/playlist/([A-Za-z0-9]+)")


# ─────────────────────────────────────────────────────────────────────────────
#  Spotify client (lazy init)
# ─────────────────────────────────────────────────────────────────────────────

_sp_client: "spotipy.Spotify | None" = None

def _get_spotify() -> "spotipy.Spotify | None":
    """Lazily initialise the Spotify client. Returns None if creds missing."""
    global _sp_client
    if _sp_client is not None:
        return _sp_client
    if not _SPOTIPY_AVAILABLE:
        return None
    cid     = os.getenv("SPOTIFY_CLIENT_ID",     "")
    csecret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    if not cid or not csecret:
        return None
    try:
        _sp_client = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=cid, client_secret=csecret
            )
        )
        return _sp_client
    except Exception as e:
        print(f"[Music] Spotify init failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  yt-dlp extraction helper (safe, fresh instance per call)
# ─────────────────────────────────────────────────────────────────────────────

def _ytdl_extract(query: str) -> dict:
    """
    Synchronous — must be called inside run_in_executor.
    Creates a fresh YoutubeDL instance to avoid shared-state threading bugs.
    """
    if not query.startswith(("http://", "https://", "ytsearch")):
        query = f"ytsearch1:{query}"

    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
        data = ydl.extract_info(query, download=False)

    if data is None:
        raise RuntimeError("yt-dlp returned nothing.")
    if "entries" in data:
        entries = [e for e in data["entries"] if e]
        if not entries:
            raise RuntimeError("No results found.")
        data = entries[0]
    return data


# ─────────────────────────────────────────────────────────────────────────────
#  Spotify metadata helpers (synchronous, run in executor)
# ─────────────────────────────────────────────────────────────────────────────

class SpotifyMeta:
    """Lightweight container for a Spotify track's display metadata."""
    __slots__ = ("title", "artist", "duration", "thumbnail", "spotify_url")

    def __init__(self, title: str, artist: str, duration: int,
                 thumbnail: str, spotify_url: str):
        self.title       = title
        self.artist      = artist
        self.duration    = duration          # seconds
        self.thumbnail   = thumbnail
        self.spotify_url = spotify_url

    @property
    def search_query(self) -> str:
        return f"{self.title} {self.artist}"

    @property
    def display_title(self) -> str:
        return f"{self.title} — {self.artist}"


def _sp_track_to_meta(t: dict) -> SpotifyMeta:
    """Convert a Spotify API track dict → SpotifyMeta."""
    title   = t.get("name", "Unknown")
    artists = ", ".join(a["name"] for a in t.get("artists", []))
    dur_ms  = t.get("duration_ms", 0)
    images  = (t.get("album") or {}).get("images") or t.get("images") or []
    thumb   = images[0]["url"] if images else ""
    url     = (t.get("external_urls") or {}).get("spotify", "")
    return SpotifyMeta(title, artists, dur_ms // 1000, thumb, url)


def _resolve_spotify_track(track_id: str) -> list[SpotifyMeta]:
    sp = _get_spotify()
    if not sp:
        raise RuntimeError("Spotify not configured.")
    t = sp.track(track_id)
    return [_sp_track_to_meta(t)]


def _resolve_spotify_album(album_id: str) -> list[SpotifyMeta]:
    sp = _get_spotify()
    if not sp:
        raise RuntimeError("Spotify not configured.")
    album   = sp.album(album_id)
    thumb   = (album.get("images") or [{}])[0].get("url", "")
    results = []
    resp    = sp.album_tracks(album_id, limit=50)
    for t in resp.get("items", []):
        if not t:
            continue
        # album_tracks items don't have album.images, inject thumb manually
        meta = SpotifyMeta(
            title=t.get("name", "Unknown"),
            artist=", ".join(a["name"] for a in t.get("artists", [])),
            duration=t.get("duration_ms", 0) // 1000,
            thumbnail=thumb,
            spotify_url=(t.get("external_urls") or {}).get("spotify", ""),
        )
        results.append(meta)
        if len(results) >= PLAYLIST_CAP:
            break
    return results


def _resolve_spotify_playlist(playlist_id: str) -> list[SpotifyMeta]:
    sp = _get_spotify()
    if not sp:
        raise RuntimeError("Spotify not configured.")
    results = []
    resp    = sp.playlist_tracks(playlist_id, limit=50,
                                  fields="items(track(name,artists,duration_ms,"
                                         "external_urls,album(images)))")
    for item in resp.get("items", []):
        t = item.get("track")
        if not t:
            continue
        results.append(_sp_track_to_meta(t))
        if len(results) >= PLAYLIST_CAP:
            break
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  Track classes
# ─────────────────────────────────────────────────────────────────────────────

class Track:
    """A fully resolved, playable track."""
    __slots__ = ("title", "url", "stream_url", "duration", "thumbnail", "requester")

    def __init__(self, data: dict, requester: discord.Member):
        self.title      = data.get("title", "Unknown")
        self.url        = data.get("webpage_url") or data.get("url", "")
        self.stream_url = data.get("url", "")
        self.duration   = data.get("duration") or 0
        self.thumbnail  = data.get("thumbnail", "")
        self.requester  = requester

    def make_source(self, volume: float = 0.5,
                    ffmpeg_opts: dict | None = None) -> discord.PCMVolumeTransformer:
        opts = ffmpeg_opts or FFMPEG_OPTIONS
        return discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(self.stream_url, **opts),
            volume=volume,
        )


class PendingTrack:
    """
    A Spotify track queued before its YouTube URL has been resolved.
    Resolution (YouTube search) happens lazily just before playback.
    """
    __slots__ = ("title", "url", "duration", "thumbnail", "requester", "_meta")

    def __init__(self, meta: SpotifyMeta, requester: discord.Member):
        self._meta     = meta
        self.title     = meta.display_title
        self.url       = meta.spotify_url
        self.duration  = meta.duration
        self.thumbnail = meta.thumbnail
        self.requester = requester

    async def resolve(self, loop: asyncio.AbstractEventLoop) -> Track:
        """Search YouTube for this Spotify track and return a playable Track."""
        data = await loop.run_in_executor(None, _ytdl_extract, self._meta.search_query)
        t = Track(data, self.requester)
        # Keep Spotify artwork and display title (better than YouTube's)
        t.title     = self.title
        t.url       = self.url or t.url
        t.thumbnail = self.thumbnail or t.thumbnail
        t.duration  = self.duration or t.duration
        return t


# Union type for the queue
AnyTrack = Union[Track, PendingTrack]


# ─────────────────────────────────────────────────────────────────────────────
#  Per-guild state
# ─────────────────────────────────────────────────────────────────────────────

class GuildMusicState:
    def __init__(self):
        self.queue:        deque[AnyTrack]            = deque()
        self.current:      Track | None               = None
        self.volume:       float                      = 0.5
        self.loop:         bool                       = False
        self.loop_queue:   bool                       = False
        self.mode_247:     bool                       = False
        self.audio_filter: str                        = ""
        self.text_channel: discord.TextChannel | None = None
        self.track_start:  float | None               = None
        self._inactivity:  asyncio.Task | None        = None


# ─────────────────────────────────────────────────────────────────────────────
#  Paginated queue view
# ─────────────────────────────────────────────────────────────────────────────

class QueueView(discord.ui.View):
    PER_PAGE = 10

    def __init__(self, tracks: list[AnyTrack], current: Track | None,
                 guild_name: str):
        super().__init__(timeout=120)
        self.tracks     = tracks
        self.current    = current
        self.guild_name = guild_name
        self.page       = 0
        self.total      = max(1, math.ceil(len(tracks) / self.PER_PAGE))
        self._sync()

    def _sync(self):
        self.btn_prev.disabled = self.page == 0
        self.btn_next.disabled = self.page >= self.total - 1
        self.btn_page.label    = f"{self.page + 1}/{self.total}"

    def _embed(self) -> discord.Embed:
        e = discord.Embed(title=f"🎵 Queue — {self.guild_name}", color=EMBED_COLOR)
        if self.current:
            pending = isinstance(self.current, PendingTrack)
            icon    = "🎵" if not pending else "⏳"
            e.add_field(
                name=f"{icon} Now Playing",
                value=f"[{self.current.title}]({self.current.url}) "
                      f"`{_fmt(self.current.duration)}` — {self.current.requester.mention}",
                inline=False,
            )
        start = self.page * self.PER_PAGE
        chunk = self.tracks[start: start + self.PER_PAGE]
        if chunk:
            lines = []
            for i, t in enumerate(chunk, start + 1):
                icon = "🎧" if isinstance(t, PendingTrack) else "🎵"
                lines.append(
                    f"`{i}.` {icon} [{t.title}]({t.url}) "
                    f"`{_fmt(t.duration)}` — {t.requester.mention}"
                )
            e.add_field(name="📋 Up Next", value="\n".join(lines), inline=False)
        else:
            e.add_field(name="📋 Up Next", value="Queue is empty.", inline=False)
        total_s = sum(t.duration for t in self.tracks)
        e.set_footer(text=f"{len(self.tracks)} track(s) • Total: {_fmt(total_s)}")
        return e

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def btn_prev(self, interaction: discord.Interaction, _):
        self.page = max(0, self.page - 1); self._sync()
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def btn_page(self, interaction: discord.Interaction, _):
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def btn_next(self, interaction: discord.Interaction, _):
        self.page = min(self.total - 1, self.page + 1); self._sync()
        await interaction.response.edit_message(embed=self._embed(), view=self)

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True


# ─────────────────────────────────────────────────────────────────────────────
#  Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(seconds: int | float) -> str:
    if not seconds:
        return "Live"
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _bar(elapsed: float, total: float, n: int = 18) -> str:
    if not total:
        return "─" * n + " 🔴 Live"
    pct    = min(elapsed / total, 1.0)
    filled = int(pct * n)
    return "▬" * filled + "🔘" + "─" * (n - filled)


def _me(title: str, **kw) -> discord.Embed:
    return discord.Embed(title=f"🎵 {title}", color=EMBED_COLOR, **kw)


def _ee(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=f"❌ {title}", description=desc, color=0xe74c3c)


# ─────────────────────────────────────────────────────────────────────────────
#  Database helpers
# ─────────────────────────────────────────────────────────────────────────────

def _db_connect():
    import mysql.connector

    connection_config = {
        "host": os.getenv("MYSQL_HOST", "").strip(),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "").strip(),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "").strip(),
    }
    missing = [
        name
        for name in ("host", "user", "password", "database")
        if not connection_config[name]
    ]
    if missing:
        raise RuntimeError(
            "Music database is unavailable; missing MySQL settings: "
            + ", ".join(missing)
        )
    return mysql.connector.connect(
        **connection_config,
    )


def _db_ensure(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS music_history (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            guild_id    BIGINT NOT NULL,
            user_id     BIGINT NOT NULL,
            track_title VARCHAR(512) NOT NULL,
            track_url   VARCHAR(1024) NOT NULL,
            duration    INT DEFAULT 0,
            played_at   DATETIME NOT NULL
        )
    """)
    conn.commit(); cur.close()


def _db_log(conn, guild_id, user_id, track: Track):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO music_history "
        "(guild_id,user_id,track_title,track_url,duration,played_at) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (guild_id, user_id, track.title, track.url, track.duration,
         datetime.now(timezone.utc).replace(tzinfo=None)),
    )
    conn.commit(); cur.close()


def _db_history(conn, guild_id, limit=10):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT track_title,track_url,user_id,played_at "
        "FROM music_history WHERE guild_id=%s "
        "ORDER BY played_at DESC LIMIT %s",
        (guild_id, limit),
    )
    rows = cur.fetchall(); cur.close(); return rows


def _db_top(conn, guild_id, n=5):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT track_title,track_url,COUNT(*) AS plays "
        "FROM music_history WHERE guild_id=%s "
        "GROUP BY track_url,track_title ORDER BY plays DESC LIMIT %s",
        (guild_id, n),
    )
    rows = cur.fetchall(); cur.close(); return rows


def _db_premium(conn, guild_id) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM premium_guilds WHERE guild_id=%s LIMIT 1", (guild_id,))
    row = cur.fetchone(); cur.close(); return row is not None


# ─────────────────────────────────────────────────────────────────────────────
#  Music Cog
# ─────────────────────────────────────────────────────────────────────────────

class Music(commands.Cog):
    """Music system with Spotify + YouTube support."""

    def __init__(self, bot: commands.Bot):
        self.bot    = bot
        self._states: dict[int, GuildMusicState] = {}

    # ── state ─────────────────────────────────────────────────────────────────

    def _st(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self._states:
            self._states[guild_id] = GuildMusicState()
        return self._states[guild_id]

    # ── DB ────────────────────────────────────────────────────────────────────

    async def _is_premium(self, guild_id: int) -> bool:
        def _check():
            conn = _db_connect()
            try:   return _db_premium(conn, guild_id)
            finally: conn.close()
        try:   return await self.bot.loop.run_in_executor(None, _check)
        except Exception: return False

    def _bg_log(self, guild_id: int, user_id: int, track: Track):
        def _run():
            try:
                conn = _db_connect(); _db_ensure(conn)
                _db_log(conn, guild_id, user_id, track)
                conn.close()
            except Exception as e:
                print(f"[Music] DB log error: {e}")
        asyncio.ensure_future(self.bot.loop.run_in_executor(None, _run))

    # ── inactivity ────────────────────────────────────────────────────────────

    def _cancel_idle(self, st: GuildMusicState):
        if st._inactivity and not st._inactivity.done():
            st._inactivity.cancel()
        st._inactivity = None

    def _arm_idle(self, guild: discord.Guild, st: GuildMusicState):
        if st.mode_247: return
        self._cancel_idle(st)
        st._inactivity = asyncio.ensure_future(self._idle_dc(guild, st))

    async def _idle_dc(self, guild: discord.Guild, st: GuildMusicState):
        await asyncio.sleep(INACTIVITY_SEC)
        vc = guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect(force=True)
        ch = st.text_channel
        self._states.pop(guild.id, None)
        if ch:
            try:
                await ch.send(embed=_me("Disconnected",
                    description="Left VC due to inactivity. ⏹️"))
            except Exception:
                pass

    # ── playback core ─────────────────────────────────────────────────────────

    def _ffmpeg_opts(self, st: GuildMusicState) -> dict:
        opts = dict(FFMPEG_OPTIONS)
        if st.audio_filter:
            opts["options"] = f"-vn -af {st.audio_filter}"
        return opts

    def _play_track(self, guild: discord.Guild, st: GuildMusicState,
                    track: Track):
        """Synchronous — creates source and calls vc.play()."""
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return

        source = track.make_source(st.volume, self._ffmpeg_opts(st))
        st.current    = track
        st.track_start = self.bot.loop.time()

        def _after(err):
            if err: print(f"[Music] Player error: {err}")
            asyncio.run_coroutine_threadsafe(
                self._advance(guild, st), self.bot.loop
            )

        vc.play(source, after=_after)
        self._bg_log(guild.id, track.requester.id, track)

        if st.text_channel and not st.loop:
            embed = self._np_embed(track)
            asyncio.run_coroutine_threadsafe(
                st.text_channel.send(embed=embed), self.bot.loop
            )

    async def _advance(self, guild: discord.Guild, st: GuildMusicState):
        """Called when a track ends. Pops next track, resolves if pending."""
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return

        # Loop current track
        if st.loop and st.current:
            self._play_track(guild, st, st.current)
            return

        # Loop queue — re-append finished track
        if st.loop_queue and st.current:
            # Re-add as a PendingTrack would lose stream_url — keep as Track
            st.queue.append(st.current)

        # Pop next
        if not st.queue:
            st.current = None
            self._arm_idle(guild, st)
            if st.text_channel:
                try:
                    await st.text_channel.send(
                        embed=_me("Queue Finished",
                                  description="No more tracks. Use `,play` to add more!"))
                except Exception:
                    pass
            return

        nxt = st.queue.popleft()

        # Resolve PendingTrack (lazy YouTube search)
        if isinstance(nxt, PendingTrack):
            if st.text_channel:
                try:
                    msg = await st.text_channel.send(
                        embed=_me("Resolving",
                                  description=f"🔍 Finding audio for **{nxt.title}**..."))
                except Exception:
                    msg = None
            else:
                msg = None

            try:
                nxt = await nxt.resolve(self.bot.loop)
                if msg:
                    try: await msg.delete()
                    except Exception: pass
            except Exception as e:
                print(f"[Music] PendingTrack resolve failed: {e}")
                if st.text_channel:
                    try:
                        await st.text_channel.send(
                            embed=_ee("Skip", f"Couldn't find audio for that track. Skipping..."))
                    except Exception: pass
                # Skip to the next track
                await self._advance(guild, st)
                return

        self._play_track(guild, st, nxt)

    # ── voice helpers ─────────────────────────────────────────────────────────

    async def _ensure_vc(self, ctx: commands.Context) -> discord.VoiceClient | None:
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.reply(embed=_ee("Not in VC",
                "Join a voice channel first!"))
            return None
        target = ctx.author.voice.channel
        vc     = ctx.guild.voice_client
        if vc:
            if vc.channel.id != target.id:
                await ctx.reply(embed=_ee("Wrong VC",
                    f"I'm already in {vc.channel.mention}."))
                return None
            return vc
        try:
            return await target.connect(timeout=15.0, reconnect=True)
        except asyncio.TimeoutError:
            await ctx.reply(embed=_ee("Timeout", "Couldn't connect in time."))
        except Exception as e:
            await ctx.reply(embed=_ee("Connection Error", str(e)))
        return None

    # ── embeds ────────────────────────────────────────────────────────────────

    def _np_embed(self, track: Track, elapsed: float = 0) -> discord.Embed:
        e = _me("Now Playing")
        e.description = f"[**{track.title}**]({track.url})"
        bar = _bar(elapsed, track.duration)
        e.add_field(
            name="Progress",
            value=f"{bar}\n`{_fmt(int(elapsed))}` / `{_fmt(track.duration)}`",
            inline=False,
        )
        e.add_field(name="Requested by", value=track.requester.mention,  inline=True)
        e.add_field(name="Duration",     value=f"`{_fmt(track.duration)}`", inline=True)
        if track.thumbnail:
            e.set_thumbnail(url=track.thumbnail)
        return e

    # ── Spotify routing ───────────────────────────────────────────────────────

    async def _handle_spotify(self, ctx: commands.Context,
                               query: str, vc: discord.VoiceClient,
                               st: GuildMusicState) -> bool:
        """
        Detect Spotify URL, resolve metadata, queue tracks.
        Returns True if handled, False if not a Spotify URL.
        """
        sp = _get_spotify()

        # Not configured
        if sp is None:
            if _SP_TRACK.search(query) or _SP_ALBUM.search(query) or _SP_PLAYLIST.search(query):
                await ctx.reply(embed=_ee("Spotify Not Configured",
                    "Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in your `.env` file.\n"
                    "Get them at: https://developer.spotify.com/dashboard"))
                return True
            return False

        track_m = _SP_TRACK.search(query)
        album_m = _SP_ALBUM.search(query)
        playlist_m = _SP_PLAYLIST.search(query)

        if not any([track_m, album_m, playlist_m]):
            return False  # Not a Spotify URL

        async with ctx.typing():
            try:
                if track_m:
                    metas = await self.bot.loop.run_in_executor(
                        None, _resolve_spotify_track, track_m.group(1))
                elif album_m:
                    metas = await self.bot.loop.run_in_executor(
                        None, _resolve_spotify_album, album_m.group(1))
                else:
                    metas = await self.bot.loop.run_in_executor(
                        None, _resolve_spotify_playlist, playlist_m.group(1))
            except Exception as e:
                await ctx.reply(embed=_ee("Spotify Error", str(e)))
                return True

        if not metas:
            await ctx.reply(embed=_ee("Empty", "No tracks found on Spotify."))
            return True

        # Single track — resolve YouTube immediately for instant play
        if len(metas) == 1:
            meta = metas[0]
            async with ctx.typing():
                try:
                    data = await self.bot.loop.run_in_executor(
                        None, _ytdl_extract, meta.search_query)
                    track = Track(data, ctx.author)
                    track.title     = meta.display_title
                    track.url       = meta.spotify_url or track.url
                    track.thumbnail = meta.thumbnail or track.thumbnail
                    track.duration  = meta.duration or track.duration
                except Exception as e:
                    await ctx.reply(embed=_ee("Not Found",
                        f"Couldn't find audio for **{meta.display_title}**.\n`{e}`"))
                    return True

            st.queue.append(track)
            e = discord.Embed(title="🎵 Added to Queue", color=SPOTIFY_COLOR)
            e.description = f"[**{track.title}**]({track.url})"
            e.add_field(name="Duration",     value=f"`{_fmt(track.duration)}`", inline=True)
            e.add_field(name="Position",     value=f"`#{len(st.queue)}`",       inline=True)
            e.add_field(name="Requested by", value=ctx.author.mention,          inline=True)
            e.add_field(name="Source",       value="<:spotify:1> Spotify",      inline=True)
            if track.thumbnail:
                e.set_thumbnail(url=track.thumbnail)
            await ctx.reply(embed=e)

        else:
            # Album / playlist — add as PendingTracks (lazy resolution)
            added = 0
            for meta in metas:
                if len(st.queue) >= MAX_QUEUE:
                    break
                st.queue.append(PendingTrack(meta, ctx.author))
                added += 1

            kind = "Album" if album_m else "Playlist"
            e = discord.Embed(title=f"🎵 {kind} Queued", color=SPOTIFY_COLOR)
            e.description = (
                f"Added **{added}** track(s) to the queue.\n"
                f"Audio will be fetched from YouTube as each song plays."
            )
            if metas[0].thumbnail:
                e.set_thumbnail(url=metas[0].thumbnail)
            e.add_field(name="Source", value="Spotify", inline=True)
            e.add_field(name="By", value=ctx.author.mention, inline=True)
            if added < len(metas):
                e.set_footer(text=f"⚠️ Capped at {MAX_QUEUE} tracks.")
            await ctx.reply(embed=e)

        # Start playback if idle
        if not vc.is_playing() and not vc.is_paused():
            nxt = st.queue.popleft()
            if isinstance(nxt, PendingTrack):
                asyncio.ensure_future(self._advance_from_pending(ctx.guild, st, nxt))
            else:
                self._play_track(ctx.guild, st, nxt)

        return True

    async def _advance_from_pending(self, guild: discord.Guild,
                                     st: GuildMusicState, pending: PendingTrack):
        """Resolve a PendingTrack and start playing."""
        if st.text_channel:
            try:
                msg = await st.text_channel.send(
                    embed=_me("Resolving",
                              description=f"🔍 Finding audio for **{pending.title}**..."))
            except Exception:
                msg = None
        else:
            msg = None

        try:
            track = await pending.resolve(self.bot.loop)
            if msg:
                try: await msg.delete()
                except Exception: pass
            self._play_track(guild, st, track)
        except Exception as e:
            print(f"[Music] Initial resolve failed: {e}")
            if msg:
                try: await msg.delete()
                except Exception: pass
            await self._advance(guild, st)

    # =========================================================================
    #  COMMANDS
    # =========================================================================

    @commands.command(name="join", aliases=["connect"])
    async def cmd_join(self, ctx: commands.Context):
        """Join your voice channel."""
        vc = await self._ensure_vc(ctx)
        if vc:
            await ctx.reply(embed=_me("Joined",
                description=f"Connected to **{vc.channel.name}** ✅"))

    @commands.command(name="leave", aliases=["disconnect", "dc"])
    async def cmd_leave(self, ctx: commands.Context):
        """Leave the voice channel."""
        vc = ctx.guild.voice_client
        if not vc:
            return await ctx.reply(embed=_ee("Not Connected", "I'm not in a VC."))
        st = self._st(ctx.guild.id)
        self._cancel_idle(st); st.queue.clear(); st.current = None
        await vc.disconnect(force=True)
        self._states.pop(ctx.guild.id, None)
        await ctx.reply(embed=_me("Left", description="Disconnected. 👋"))

    # ── play ──────────────────────────────────────────────────────────────────

    @commands.command(name="play", aliases=["p"])
    async def cmd_play(self, ctx: commands.Context, *, query: str):
        """Play from Spotify URL, YouTube URL, or search query."""
        vc = await self._ensure_vc(ctx)
        if not vc:
            return

        st = self._st(ctx.guild.id)
        st.text_channel = ctx.channel
        self._cancel_idle(st)

        if len(st.queue) >= MAX_QUEUE:
            return await ctx.reply(embed=_ee("Queue Full",
                f"Max queue size is {MAX_QUEUE} tracks."))

        # ── Route Spotify URLs ────────────────────────────────────────────────
        if await self._handle_spotify(ctx, query, vc, st):
            return

        # ── YouTube / plain text search ───────────────────────────────────────
        async with ctx.typing():
            try:
                data = await self.bot.loop.run_in_executor(
                    None, _ytdl_extract, query)
            except Exception as e:
                return await ctx.reply(embed=_ee("Not Found",
                    f"Couldn't find **{query}**.\n`{e}`"))

        track = Track(data, ctx.author)
        st.queue.append(track)

        e = _me("Added to Queue")
        e.description = f"[**{track.title}**]({track.url})"
        e.add_field(name="Duration",     value=f"`{_fmt(track.duration)}`", inline=True)
        e.add_field(name="Position",     value=f"`#{len(st.queue)}`",       inline=True)
        e.add_field(name="Requested by", value=ctx.author.mention,          inline=True)
        if track.thumbnail:
            e.set_thumbnail(url=track.thumbnail)
        await ctx.reply(embed=e)

        if not vc.is_playing() and not vc.is_paused():
            nxt = st.queue.popleft()
            self._play_track(ctx.guild, st, nxt)

    # ── controls ──────────────────────────────────────────────────────────────

    @commands.command(name="pause")
    async def cmd_pause(self, ctx: commands.Context):
        """Pause playback."""
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            return await ctx.reply(embed=_ee("Not Playing", "Nothing is playing."))
        vc.pause()
        await ctx.reply(embed=_me("Paused", description="⏸️ Paused."))

    @commands.command(name="resume")
    async def cmd_resume(self, ctx: commands.Context):
        """Resume playback."""
        vc = ctx.guild.voice_client
        if not vc or not vc.is_paused():
            return await ctx.reply(embed=_ee("Not Paused", "Nothing is paused."))
        vc.resume()
        self._cancel_idle(self._st(ctx.guild.id))
        await ctx.reply(embed=_me("Resumed", description="▶️ Resumed."))

    @commands.command(name="stop")
    async def cmd_stop(self, ctx: commands.Context):
        """Stop and clear the queue."""
        vc = ctx.guild.voice_client
        if not vc:
            return await ctx.reply(embed=_ee("Not Connected", "Not in a VC."))
        st = self._st(ctx.guild.id)
        st.queue.clear(); st.current = None; st.loop = False; st.loop_queue = False
        if vc.is_playing() or vc.is_paused(): vc.stop()
        self._arm_idle(ctx.guild, st)
        await ctx.reply(embed=_me("Stopped", description="⏹️ Queue cleared."))

    @commands.command(name="skip", aliases=["s"])
    async def cmd_skip(self, ctx: commands.Context):
        """Skip the current track."""
        vc = ctx.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await ctx.reply(embed=_ee("Not Playing", "Nothing to skip."))
        st = self._st(ctx.guild.id)
        was = st.loop; st.loop = False; vc.stop(); st.loop = was
        await ctx.reply(embed=_me("Skipped", description="⏭️ Next track..."))

    # ── volume ────────────────────────────────────────────────────────────────

    @commands.command(name="volume", aliases=["vol"])
    async def cmd_volume(self, ctx: commands.Context, volume: int):
        """Set volume (1–100)."""
        if not 1 <= volume <= 100:
            return await ctx.reply(embed=_ee("Invalid", "Volume must be 1–100."))
        vc = ctx.guild.voice_client
        if not vc:
            return await ctx.reply(embed=_ee("Not Connected", "Not in a VC."))
        st = self._st(ctx.guild.id); st.volume = volume / 100
        if isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = st.volume
        bar = "█" * (volume // 10) + "░" * (10 - volume // 10)
        await ctx.reply(embed=_me("Volume", description=f"`{bar}` **{volume}%**"))

    # ── queue ─────────────────────────────────────────────────────────────────

    @commands.command(name="queue", aliases=["q", "playlist"])
    async def cmd_queue(self, ctx: commands.Context):
        """View the current queue."""
        st = self._st(ctx.guild.id)
        tracks = list(st.queue)
        if not tracks and not st.current:
            return await ctx.reply(embed=_me("Empty",
                description="Queue is empty. Use `,play` to add tracks!"))
        view = QueueView(tracks, st.current, ctx.guild.name)
        msg  = await ctx.reply(embed=view._embed(), view=view)
        view.message = msg

    @commands.command(name="nowplaying", aliases=["np", "current"])
    async def cmd_np(self, ctx: commands.Context):
        """Show the currently playing track."""
        st = self._st(ctx.guild.id)
        if not st.current:
            return await ctx.reply(embed=_ee("Not Playing", "Nothing is playing."))
        elapsed = (self.bot.loop.time() - st.track_start) if st.track_start else 0
        await ctx.reply(embed=self._np_embed(st.current, elapsed))

    @commands.command(name="loop", aliases=["l"])
    async def cmd_loop(self, ctx: commands.Context):
        """Toggle current track loop."""
        st = self._st(ctx.guild.id); st.loop = not st.loop
        await ctx.reply(embed=_me("Loop",
            description=f"Track loop **{'enabled 🔂' if st.loop else 'disabled'}**."))

    @commands.command(name="loopqueue", aliases=["lq"])
    async def cmd_loopqueue(self, ctx: commands.Context):
        """Toggle queue loop."""
        st = self._st(ctx.guild.id); st.loop_queue = not st.loop_queue
        await ctx.reply(embed=_me("Loop Queue",
            description=f"Queue loop **{'enabled 🔁' if st.loop_queue else 'disabled'}**."))

    @commands.command(name="shuffle")
    async def cmd_shuffle(self, ctx: commands.Context):
        """Shuffle the queue."""
        st = self._st(ctx.guild.id)
        if len(st.queue) < 2:
            return await ctx.reply(embed=_ee("Too Short", "Need 2+ tracks to shuffle."))
        lst = list(st.queue); random.shuffle(lst); st.queue = deque(lst)
        await ctx.reply(embed=_me("Shuffled",
            description=f"🔀 Shuffled **{len(st.queue)}** tracks."))

    @commands.command(name="remove", aliases=["rm"])
    async def cmd_remove(self, ctx: commands.Context, position: int):
        """Remove a track by queue position."""
        st = self._st(ctx.guild.id)
        if not st.queue:
            return await ctx.reply(embed=_ee("Empty", "Queue is empty."))
        if not 1 <= position <= len(st.queue):
            return await ctx.reply(embed=_ee("Bad Position",
                f"Must be 1–{len(st.queue)}."))
        lst = list(st.queue); removed = lst.pop(position - 1); st.queue = deque(lst)
        await ctx.reply(embed=_me("Removed",
            description=f"Removed **{removed.title}**."))

    @commands.command(name="skipto", aliases=["goto"])
    async def cmd_skipto(self, ctx: commands.Context, position: int):
        """Jump to a queue position."""
        vc = ctx.guild.voice_client; st = self._st(ctx.guild.id)
        if not st.queue:
            return await ctx.reply(embed=_ee("Empty", "Queue is empty."))
        if not 1 <= position <= len(st.queue):
            return await ctx.reply(embed=_ee("Bad Position", f"Must be 1–{len(st.queue)}."))
        for _ in range(position - 1):
            if st.queue: st.queue.popleft()
        st.loop = False
        if vc and (vc.is_playing() or vc.is_paused()): vc.stop()
        await ctx.reply(embed=_me("Skipped To", description=f"⏩ Jumping to **#{position}**..."))

    @commands.command(name="clearqueue", aliases=["cq"])
    async def cmd_clearqueue(self, ctx: commands.Context):
        """Clear all queued tracks."""
        st = self._st(ctx.guild.id)
        n = len(st.queue); st.queue.clear()
        await ctx.reply(embed=_me("Cleared", description=f"Removed **{n}** track(s). 🗑️"))

    # ── premium ───────────────────────────────────────────────────────────────

    async def _premium_check(self, ctx: commands.Context) -> bool:
        if not await self._is_premium(ctx.guild.id):
            await ctx.reply(embed=_ee("Premium Only",
                "🌟 This feature requires **Premium**. Upgrade to unlock it!"))
            return False
        return True

    def _restart_with_filter(self, guild: discord.Guild, st: GuildMusicState):
        vc = guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            was = st.loop; st.loop = True; vc.stop(); st.loop = was

    @commands.command(name="bassboost", aliases=["bb"])
    async def cmd_bassboost(self, ctx: commands.Context):
        """[Premium] Toggle bass boost."""
        if not await self._premium_check(ctx): return
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            return await ctx.reply(embed=_ee("Not Playing", "Nothing is playing."))
        st = self._st(ctx.guild.id)
        if "bass" in st.audio_filter:
            st.audio_filter = ""; label = "disabled"
        else:
            st.audio_filter = "bass=g=10"; label = "enabled 🔊"
        self._restart_with_filter(ctx.guild, st)
        await ctx.reply(embed=_me("Bass Boost", description=f"Bass Boost **{label}**."))

    @commands.command(name="nightcore", aliases=["nc"])
    async def cmd_nightcore(self, ctx: commands.Context):
        """[Premium] Toggle nightcore filter."""
        if not await self._premium_check(ctx): return
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            return await ctx.reply(embed=_ee("Not Playing", "Nothing is playing."))
        st = self._st(ctx.guild.id)
        if "aresample" in st.audio_filter:
            st.audio_filter = ""; label = "disabled"
        else:
            st.audio_filter = "aresample=48000,asetrate=48000*1.25"; label = "enabled 🌙"
        self._restart_with_filter(ctx.guild, st)
        await ctx.reply(embed=_me("Nightcore", description=f"Nightcore **{label}**."))

    @commands.command(name="seek")
    async def cmd_seek(self, ctx: commands.Context, seconds: int):
        """[Premium] Seek to a timestamp (seconds)."""
        if not await self._premium_check(ctx): return
        vc = ctx.guild.voice_client; st = self._st(ctx.guild.id)
        if not vc or not vc.is_playing() or not st.current:
            return await ctx.reply(embed=_ee("Not Playing", "Nothing is playing."))
        if seconds < 0 or (st.current.duration and seconds > st.current.duration):
            return await ctx.reply(embed=_ee("Bad Time",
                f"Must be 0–{_fmt(st.current.duration)}."))
        opts = dict(FFMPEG_OPTIONS)
        opts["before_options"] = (
            f"-reconnect 1 -reconnect_streamed 1 "
            f"-reconnect_delay_max 5 -ss {seconds}"
        )
        if st.audio_filter:
            opts["options"] = f"-vn -af {st.audio_filter}"
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(st.current.stream_url, **opts),
            volume=st.volume,
        )
        st.track_start = self.bot.loop.time() - seconds

        def _after(err):
            if err: print(f"[Music] Seek error: {err}")
            asyncio.run_coroutine_threadsafe(
                self._advance(ctx.guild, st), self.bot.loop)

        vc.stop(); vc.play(source, after=_after)
        await ctx.reply(embed=_me("Seeked", description=f"⏩ Jumped to `{_fmt(seconds)}`."))

    @commands.command(name="247", aliases=["stay"])
    async def cmd_247(self, ctx: commands.Context):
        """[Premium] Toggle 24/7 mode."""
        if not await self._premium_check(ctx): return
        st = self._st(ctx.guild.id); st.mode_247 = not st.mode_247
        if st.mode_247:
            self._cancel_idle(st)
            desc = "✅ 24/7 enabled — I'll stay in VC forever."
        else:
            desc = "❎ 24/7 disabled."
        await ctx.reply(embed=_me("24/7 Mode", description=desc))

    # ── history ───────────────────────────────────────────────────────────────

    @commands.command(name="history", aliases=["recent"])
    async def cmd_history(self, ctx: commands.Context):
        """Show last 10 songs played."""
        def _fetch():
            conn = _db_connect()
            try: _db_ensure(conn); return _db_history(conn, ctx.guild.id)
            finally: conn.close()

        try:
            rows = await self.bot.loop.run_in_executor(None, _fetch)
        except Exception as exc:
            print(f"[Music] History lookup failed: {exc}")
            return await ctx.reply(embed=_ee(
                "History Unavailable",
                "Music history is temporarily unavailable. Please try again later.",
            ))
        if not rows:
            return await ctx.reply(embed=_me("No History",
                description="No songs played yet."))
        e = _me(f"Recent Tracks — {ctx.guild.name}")
        lines = []
        for i, r in enumerate(rows, 1):
            ts = r["played_at"].strftime("%d/%m %H:%M") if r.get("played_at") else "?"
            lines.append(
                f"`{i}.` [{r['track_title']}]({r['track_url']}) "
                f"— <@{r['user_id']}> `{ts}`"
            )
        e.description = "\n".join(lines)
        e.set_footer(text=f"Last {len(rows)} songs")
        await ctx.reply(embed=e)

    @commands.command(name="toprequest", aliases=["topsongs", "musictop"])
    async def cmd_top(self, ctx: commands.Context):
        """Show top 5 most requested songs."""
        def _fetch():
            conn = _db_connect()
            try: _db_ensure(conn); return _db_top(conn, ctx.guild.id)
            finally: conn.close()

        try:
            rows = await self.bot.loop.run_in_executor(None, _fetch)
        except Exception as exc:
            print(f"[Music] Top requests lookup failed: {exc}")
            return await ctx.reply(embed=_ee(
                "Top Requests Unavailable",
                "Music statistics are temporarily unavailable. Please try again later.",
            ))
        if not rows:
            return await ctx.reply(embed=_me("No Data",
                description="Not enough history yet."))
        e     = _me(f"Top Requests — {ctx.guild.name}")
        icons = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        lines = [
            f"{icons[i]} [{r['track_title']}]({r['track_url']}) — **{r['plays']}** play(s)"
            for i, r in enumerate(rows)
        ]
        e.description = "\n".join(lines)
        await ctx.reply(embed=e)

    # ── listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState):
        guild = member.guild
        vc    = guild.voice_client
        if not vc or not vc.channel or before.channel != vc.channel:
            return
        humans = [m for m in vc.channel.members if not m.bot]
        if not humans:
            st = self._st(guild.id)
            if not st.mode_247:
                self._arm_idle(guild, st)

    # ── error handler ─────────────────────────────────────────────────────────

    async def cog_command_error(self, ctx: commands.Context,
                                error: commands.CommandError):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(embed=_ee("Missing Argument",
                f"Usage: `,{ctx.command.name} {ctx.command.signature}`"))
        elif isinstance(error, commands.BadArgument):
            await ctx.reply(embed=_ee("Bad Argument", str(error)))
        else:
            print(f"[Music] Error in {ctx.command}: {error}")
            raise error


# ─────────────────────────────────────────────────────────────────────────────
#  Setup
# ─────────────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
