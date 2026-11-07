"""
TTS (Text-to-Speech) Commands
Supports multiple voice/language options via gTTS
,ttsvc starts a continuous session — the bot reads every message you type until you run ,stoptts
"""
import discord
from discord.ext import commands
from discord import app_commands
from utils.embeds import error_embed
import config
import io
import asyncio
import shutil
import os
import tempfile

# Available voices (gTTS language codes)
TTS_VOICES = {
    'en': 'English (US)', 'en-au': 'English (AU)', 'en-uk': 'English (UK)',
    'en-in': 'English (Indian)', 'fr': 'French', 'de': 'German',
    'es': 'Spanish', 'it': 'Italian', 'pt': 'Portuguese', 'ja': 'Japanese',
    'ko': 'Korean', 'zh-CN': 'Chinese', 'hi': 'Hindi', 'ar': 'Arabic',
    'ru': 'Russian', 'tr': 'Turkish', 'nl': 'Dutch', 'sv': 'Swedish',
    'pl': 'Polish', 'th': 'Thai', 'vi': 'Vietnamese', 'id': 'Indonesian',
    'fil': 'Filipino', 'bn': 'Bengali', 'ta': 'Tamil', 'te': 'Telugu',
}

FFMPEG = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')


def _generate_tts_file(text: str, voice: str) -> str:
    """Generate TTS audio and save to a temp file. Returns the temp path."""
    from gtts import gTTS
    tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
    tmp.close()
    gTTS(text=text, lang=voice, slow=False).save(tmp.name)
    return tmp.name


async def _safe_connect_vc(guild: discord.Guild, channel: discord.VoiceChannel) -> discord.VoiceClient:
    """
    Force-disconnect any existing VC session, then connect fresh with retries.
    'list index out of range' is a known discord.py UDP discovery bug — retrying fixes it.
    """
    existing = guild.voice_client
    if existing is not None:
        try:
            await existing.disconnect(force=True)
        except Exception:
            pass
        await asyncio.sleep(2.0)  # Must wait for Discord to release the old session

    last_error = None
    for attempt in range(3):
        try:
            vc = await channel.connect(timeout=30.0, reconnect=True)
            await asyncio.sleep(1.0)  # Let UDP handshake settle
            return vc
        except Exception as e:
            last_error = e
            print(f"[Voice] connect attempt {attempt + 1} failed: {e}")
            # Cleanup stale client before retrying
            if guild.voice_client:
                try:
                    await guild.voice_client.disconnect(force=True)
                except Exception:
                    pass
            if attempt < 2:
                await asyncio.sleep(2.0)

    raise RuntimeError(f"Could not connect to voice after 3 attempts: {last_error}")


async def _play_file_in_vc(vc: discord.VoiceClient, file_path: str):
    """Play an mp3 file in the given connected VoiceClient."""
    if vc.is_playing():
        vc.stop()
    vc.play(discord.FFmpegPCMAudio(file_path, executable=FFMPEG))
    while vc.is_playing():
        await asyncio.sleep(0.4)


class TTSCommands(commands.Cog):
    """Text-to-Speech commands with multiple voices"""

    def __init__(self, bot):
        self.bot = bot
        # Active continuous TTS sessions: guild_id -> {user_id, voice, vc, queue, task}
        self._sessions: dict[int, dict] = {}

    @property
    def qualified_name(self):
        return "Utility"

    # ─────────────────────────────────────────────
    #  SESSION RUNNER — reads queued messages in VC
    # ─────────────────────────────────────────────
    async def _session_runner(self, guild_id: int):
        session = self._sessions.get(guild_id)
        if not session:
            return
        vc: discord.VoiceClient = session['vc']
        queue: asyncio.Queue = session['queue']
        voice: str = session['voice']

        try:
            while guild_id in self._sessions:
                try:
                    text = await asyncio.wait_for(queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    # 5 min idle — auto-stop
                    break

                if text is None:  # Sentinel: stop signal
                    break

                if not vc.is_connected():
                    break

                try:
                    path = await asyncio.get_event_loop().run_in_executor(
                        None, _generate_tts_file, text, voice
                    )
                    await _play_file_in_vc(vc, path)
                except Exception as e:
                    print(f"[TTS session] play error: {e}")
                finally:
                    try:
                        os.remove(path)
                    except Exception:
                        pass
        finally:
            if guild_id in self._sessions:
                del self._sessions[guild_id]
            if vc.is_connected():
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass

    # ─────────────────────────────────────────────
    #  MESSAGE LISTENER for continuous TTS sessions
    # ─────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        guild_id = message.guild.id
        session = self._sessions.get(guild_id)
        if not session:
            return
        if message.author.id != session['user_id']:
            return
        if message.content.startswith(config.PREFIX):
            return  # ignore commands

        # Send message to the queue
        text = message.content.strip()
        if text:
            await session['queue'].put(text)

    # ─────────────────────────────────────────────
    #  ,tts  — one-shot (joins VC if user is in one)
    # ─────────────────────────────────────────────
    @commands.command(name='tts', aliases=['speak', 'say'])
    async def tts(self, ctx, voice: str = 'en', *, text: str = None):
        """Convert text to speech audio. Joins your VC and reads aloud.

        Usage: ,tts [voice] <text>
        Use ,ttsvoices to see all voices. If not in VC, sends an audio file.
        """
        if voice not in TTS_VOICES:
            text = (voice + ' ' + text) if text else voice
            voice = 'en'

        if not text:
            return await ctx.reply(embed=error_embed('Usage',
                f'`{config.PREFIX}tts [voice] <text>`\nUse `{config.PREFIX}ttsvoices` for all voices.'))

        if len(text) > 500:
            return await ctx.reply(embed=error_embed('Too Long', 'Maximum 500 characters.'))

        # If user is in VC, play there
        if FFMPEG and ctx.author.voice and ctx.author.voice.channel:
            vc_channel = ctx.author.voice.channel
            perms = vc_channel.permissions_for(ctx.guild.me)
            if perms.connect and perms.speak:
                voice_name = TTS_VOICES.get(voice, voice)
                embed = discord.Embed(
                    description=f"🔊 **{voice_name}**: {text[:200]}{'...' if len(text) > 200 else ''}",
                    color=config.COLORS['primary']
                )
                embed.set_footer(text=f"Requested by {ctx.author.display_name}")
                await ctx.reply(embed=embed)
                try:
                    vc = await _safe_connect_vc(ctx.guild, vc_channel)
                    path = await asyncio.get_event_loop().run_in_executor(
                        None, _generate_tts_file, text, voice
                    )
                    try:
                        await _play_file_in_vc(vc, path)
                    finally:
                        try:
                            os.remove(path)
                        except Exception:
                            pass
                except Exception as e:
                    await ctx.send(embed=error_embed('TTS Error', f'Could not play in VC: `{e}`'))
                finally:
                    if ctx.guild.voice_client and ctx.guild.voice_client.is_connected():
                        await ctx.guild.voice_client.disconnect(force=True)
                return

        # Fallback: send mp3 file in chat
        try:
            from gtts import gTTS

            def _render_tts():
                output = io.BytesIO()
                gTTS(text=text, lang=voice, slow=False).write_to_fp(output)
                return output.getvalue()

            buf = io.BytesIO(await asyncio.to_thread(_render_tts))
            voice_name = TTS_VOICES.get(voice, voice)
            embed = discord.Embed(
                description=f"🔊 **{voice_name}**: {text[:200]}{'...' if len(text) > 200 else ''}",
                color=config.COLORS['primary']
            )
            embed.set_footer(text=f"Requested by {ctx.author.display_name}")
            await ctx.reply(embed=embed, file=discord.File(buf, filename='tts.mp3'))
        except Exception as e:
            await ctx.reply(embed=error_embed('TTS Error', f'Could not generate speech: `{e}`'))

    # ─────────────────────────────────────────────
    #  ,ttsvc — start a CONTINUOUS TTS session
    # ─────────────────────────────────────────────
    @commands.command(name='ttsvc', aliases=['speakvc', 'sayvc'])
    async def ttsvc(self, ctx, voice: str = 'en'):
        """Start a continuous TTS session in your voice channel.

        The bot joins your VC and reads every message you type aloud.
        Run ,stoptts to end the session.

        Usage: ,ttsvc [voice]
        """
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.reply(embed=error_embed('Not in VC',
                'You must be in a voice channel to start a TTS session!'))

        if voice not in TTS_VOICES:
            voice = 'en'

        vc_channel = ctx.author.voice.channel
        perms = vc_channel.permissions_for(ctx.guild.me)
        if not perms.connect or not perms.speak:
            return await ctx.reply(embed=error_embed('No Permissions',
                f'I need **Connect** and **Speak** in **{vc_channel.name}**!'))

        if not FFMPEG:
            return await ctx.reply(embed=error_embed('ffmpeg Missing',
                'Voice playback requires **ffmpeg** to be installed on the host server.'))

        # If there's already a session in this guild, stop it
        if ctx.guild.id in self._sessions:
            old = self._sessions.pop(ctx.guild.id)
            await old['queue'].put(None)  # signal stop

        voice_name = TTS_VOICES.get(voice, voice)
        msg = await ctx.reply(embed=discord.Embed(
            title="🔊 TTS Session Starting...",
            description=f"Joining **{vc_channel.name}** — using **{voice_name}** voice.\n\nJust type messages and I'll read them aloud!\nRun `{config.PREFIX}stoptts` to stop.",
            color=config.COLORS['primary']
        ).set_footer(text=f"Session owner: {ctx.author.display_name}"))

        try:
            vc = await _safe_connect_vc(ctx.guild, vc_channel)
        except Exception as e:
            return await msg.edit(embed=error_embed('Connection Failed', f'Could not join VC: `{e}`'))

        queue: asyncio.Queue = asyncio.Queue()
        session = {
            'user_id': ctx.author.id,
            'voice': voice,
            'vc': vc,
            'queue': queue,
            'channel_id': ctx.channel.id,
        }
        self._sessions[ctx.guild.id] = session

        # Update message to show we're live
        await msg.edit(embed=discord.Embed(
            title="🎙️ TTS Session Active",
            description=(
                f"**Voice:** {voice_name}\n"
                f"**VC:** {vc_channel.name}\n\n"
                f"Type anything in this channel and I'll read it aloud!\n"
                f"Run `{config.PREFIX}stoptts` to end the session."
            ),
            color=0x57f287
        ).set_footer(text=f"Session owner: {ctx.author.display_name}"))

        # Run the session loop as a background task
        task = asyncio.create_task(self._session_runner(ctx.guild.id))
        session['task'] = task

    # ─────────────────────────────────────────────
    #  ,stoptts — end the current TTS session
    # ─────────────────────────────────────────────
    @commands.command(name='stoptts', aliases=['ttstop', 'endtts'])
    async def stoptts(self, ctx):
        """Stop the ongoing TTS session in this server."""
        if ctx.guild.id not in self._sessions:
            return await ctx.reply(embed=error_embed('No Session',
                f'No active TTS session! Start one with `{config.PREFIX}ttsvc`'))

        session = self._sessions.get(ctx.guild.id)
        # Allow session owner or admins to stop
        if (ctx.author.id != session['user_id']
                and not ctx.author.guild_permissions.manage_guild
                and ctx.author.id not in config.OWNER_IDS):
            return await ctx.reply(embed=error_embed('Not Your Session',
                'Only the session owner or admins can stop the TTS session!'))

        await session['queue'].put(None)  # Sentinel to stop the runner

        embed = discord.Embed(
            title="🔇 TTS Session Ended",
            description="The TTS session has been stopped.",
            color=config.COLORS['error']
        )
        embed.set_footer(text=f"Stopped by {ctx.author.display_name}")
        await ctx.reply(embed=embed)

    # ─────────────────────────────────────────────
    #  ,ttsvoices
    # ─────────────────────────────────────────────
    @commands.command(name='ttsvoices', aliases=['voices', 'ttslangs'])
    async def ttsvoices(self, ctx):
        """Show all available TTS voices"""
        desc = '\n'.join(f'`{code}` — {name}' for code, name in TTS_VOICES.items())
        embed = discord.Embed(title="🔊 Available TTS Voices", description=desc,
                              color=config.COLORS['primary'])
        embed.set_footer(
            text=f"One-shot: {config.PREFIX}tts <voice> <text>  |  Continuous: {config.PREFIX}ttsvc [voice]  |  Stop: {config.PREFIX}stoptts"
        )
        await ctx.reply(embed=embed)

    # ─────────────────────────────────────────────
    #  Slash: /tts
    # ─────────────────────────────────────────────
    @app_commands.command(name='tts', description='Convert text to speech (plays in your VC if you are in one)')
    @app_commands.describe(text='Text to convert to speech', voice='Voice/language to use')
    @app_commands.choices(voice=[
        app_commands.Choice(name='English (US)', value='en'),
        app_commands.Choice(name='English (AU)', value='en-au'),
        app_commands.Choice(name='English (UK)', value='en-uk'),
        app_commands.Choice(name='French', value='fr'),
        app_commands.Choice(name='German', value='de'),
        app_commands.Choice(name='Spanish', value='es'),
        app_commands.Choice(name='Japanese', value='ja'),
        app_commands.Choice(name='Korean', value='ko'),
        app_commands.Choice(name='Hindi', value='hi'),
    ])
    async def tts_slash(self, interaction: discord.Interaction, text: str, voice: str = 'en'):
        if len(text) > 500:
            return await interaction.response.send_message("Maximum 500 characters.", ephemeral=True)
        await interaction.response.defer()
        try:
            from gtts import gTTS
            buf = io.BytesIO()
            gTTS(text=text, lang=voice, slow=False).write_to_fp(buf)
            buf.seek(0)
            voice_name = TTS_VOICES.get(voice, voice)
            embed = discord.Embed(
                description=f"🔊 **{voice_name}**: {text[:200]}",
                color=config.COLORS['primary']
            )
            await interaction.followup.send(embed=embed, file=discord.File(buf, filename='tts.mp3'))
        except Exception as e:
            await interaction.followup.send(f"TTS Error: `{e}`")


async def setup(bot):
    await bot.add_cog(TTSCommands(bot))
