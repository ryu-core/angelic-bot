"""
Premium Commands Cog for xiel
Paid commands: mimic, roastvc, ghost-ping-detector, grant, add-trigger, corrupt
Bot profile commands (separate): botavatar, botreset
"""
import discord
from discord.ext import commands, tasks
import asyncio
import random
import os
import sys
import io
import tempfile
from datetime import datetime, timedelta, UTC
from urllib.parse import urlparse

import aiohttp
from gtts import gTTS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'database'))
from models import Database, GhostPingConfig, ServerWebhook, TempRole, AutoTrigger

import config
from utils.database import settings_db
from utils.embeds import success_embed, error_embed, info_embed
from utils.premium import (
    premium_required,
    check_premium,
    grant_premium,
    revoke_premium,
    get_all_premium,
    bot_profile_required,
    normalize_premium_command,
    SUPPORT_SERVER,
    PREMIUM_COMMANDS,
)

# Pre-defined roasts for the VC roast command
ROASTS = [
    "Hey {user}, your mic quality sounds like you're streaming from inside a washing machine.",
    "Yo {user}, even your internet connection is trying to leave this conversation.",
    "{user}, you talk so much in VC but say absolutely nothing of value.",
    "Hey {user}, I've heard better takes from a random number generator.",
    "{user}, your voice sounds like someone stepping on a rubber duck... underwater.",
    "Attention everyone, {user} just joined, and somehow the average IQ of this call just dropped.",
    "{user}, even your push-to-talk button is trying to mute you permanently.",
    "Hey {user}, if boring was a superpower, you'd be the most powerful being in the universe.",
    "{user}, I've been in this VC for 5 seconds and I already want to disconnect.",
    "{user}, your gaming skills are about as good as your microphone quality — both are terrible.",
]


def _is_allowed_profile_image_url(url: str) -> bool:
    """Allow only HTTPS images hosted by Discord's attachment/CDN domains."""
    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return False
    hostname = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and (
            hostname == "cdn.discordapp.com"
            or hostname.endswith(".cdn.discordapp.com")
            or hostname == "media.discordapp.net"
            or hostname.endswith(".media.discordapp.net")
        )
    )


async def _download_profile_image(url: str, max_bytes: int):
    if not _is_allowed_profile_image_url(url):
        raise ValueError(
            "For safety, use an image attachment or a Discord CDN image URL."
        )

    timeout = aiohttp.ClientTimeout(total=15, connect=5)
    async with aiohttp.ClientSession(timeout=timeout) as http_session:
        async with http_session.get(url, allow_redirects=False) as response:
            if response.status != 200:
                raise ValueError("Discord could not download that image.")
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type not in {
                "image/png",
                "image/jpeg",
                "image/gif",
                "image/webp",
            }:
                raise ValueError("The attachment is not a supported image.")
            declared_size = response.content_length
            if declared_size is not None and declared_size > max_bytes:
                raise ValueError(f"Image is too large (maximum {max_bytes // (1024 * 1024)} MB).")

            content = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ValueError(
                        f"Image is too large (maximum {max_bytes // (1024 * 1024)} MB)."
                    )
            return bytes(content), content_type


def parse_duration(duration_str: str) -> timedelta:
    """Parse a duration string like '1h', '30m', '2d' into a timedelta"""
    duration_str = duration_str.lower().strip()
    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
    
    if not duration_str:
        raise ValueError("Empty duration")
    
    unit = duration_str[-1]
    if unit not in multipliers:
        raise ValueError(f"Invalid unit '{unit}'. Use s/m/h/d/w")
    
    try:
        amount = int(duration_str[:-1])
    except ValueError:
        raise ValueError(f"Invalid number in duration: {duration_str[:-1]}")
    
    if amount <= 0:
        raise ValueError("Duration must be positive")
    if amount > 365 and unit == 'd':
        raise ValueError("Maximum duration is 365 days")
    
    return timedelta(seconds=amount * multipliers[unit])


class PremiumCommands(commands.Cog):
    """💎 Premium commands — exclusive paid features"""

    ROASTVC_NAMESPACE = "premium_roastvc"
    ROASTVC_DISABLED_KEY = "voice_disabled"
    
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.db.create_tables()
        self._temp_role_tasks = {}
        self._roastvc_voice_disabled_until = {}
        self.check_expired_roles.start()
    
    def cog_unload(self):
        self.check_expired_roles.cancel()
    
    # ========================
    # TEMP ROLE EXPIRY LOOP
    # ========================
    @tasks.loop(minutes=1)
    async def check_expired_roles(self):
        """Check and remove expired temporary roles"""
        session = self.db.get_session()
        try:
            now = datetime.now(UTC)
            expired = session.query(TempRole).filter(TempRole.expires_at <= now).all()
            
            for tr in expired:
                try:
                    guild = self.bot.get_guild(tr.server_id)
                    if guild:
                        member = guild.get_member(tr.user_id)
                        role = guild.get_role(tr.role_id)
                        if member and role and role in member.roles:
                            await member.remove_roles(role, reason="Temporary role expired")
                except Exception as e:
                    print(f"Error removing expired temp role: {e}")
                
                session.delete(tr)
            
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Error in temp role check loop: {e}")
        finally:
            session.close()
    
    @check_expired_roles.before_loop
    async def before_check_expired_roles(self):
        await self.bot.wait_until_ready()
    
    async def _connect_to_voice_channel(self, guild: discord.Guild, channel: discord.VoiceChannel | discord.StageChannel):
        """Connect to, or move within, a guild voice channel safely."""
        existing_vc = guild.voice_client

        if existing_vc and existing_vc.is_connected():
            if existing_vc.channel and existing_vc.channel.id == channel.id:
                try:
                    await self._wait_for_voice_ready(existing_vc)
                except Exception:
                    try:
                        await self._hard_cleanup_voice(existing_vc)
                    except Exception:
                        pass
                    raise
                return existing_vc

            await existing_vc.move_to(channel)
            try:
                await self._wait_for_voice_ready(existing_vc)
            except Exception:
                try:
                    await self._hard_cleanup_voice(existing_vc)
                except Exception:
                    pass
                raise
            return existing_vc

        last_err = None
        for attempt in range(1):
            try:
                vc = await channel.connect(timeout=30.0, reconnect=True)
                try:
                    await self._wait_for_voice_ready(vc)
                except Exception:
                    try:
                        await self._hard_cleanup_voice(vc)
                    except Exception:
                        pass
                    raise
                return vc
            except Exception as e:
                last_err = e
                print(f"[roastvc] connect attempt {attempt + 1} failed: {e}")
                if guild.voice_client:
                    try:
                        await self._hard_cleanup_voice(guild.voice_client)
                    except Exception:
                        pass

        raise RuntimeError(f"Could not connect to voice: {last_err}")

    async def _wait_for_voice_ready(self, vc: discord.VoiceClient, timeout: float = 10.0):
        """Wait until the voice client is actually connected before playback."""
        start = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - start < timeout:
            if vc and vc.is_connected() and vc.channel is not None:
                return
            await asyncio.sleep(0.25)

        raise RuntimeError("voice client never became ready")

    async def _play_roast_audio(self, vc: discord.VoiceClient, temp_file: str, ffmpeg_path: str):
        """Play a roast audio file and wait for playback to finish."""
        if not vc or not vc.is_connected():
            raise RuntimeError("Not connected to voice.")

        if vc.is_playing():
            vc.stop()

        playback_done = asyncio.Event()

        def after_playback(error):
            if error:
                print(f"[roastvc] playback error: {error}")
            self.bot.loop.call_soon_threadsafe(playback_done.set)

        source = discord.FFmpegPCMAudio(temp_file, executable=ffmpeg_path)
        vc.play(source, after=after_playback)
        await asyncio.wait_for(playback_done.wait(), timeout=45)

    async def _hard_cleanup_voice(self, vc: discord.VoiceClient | None):
        """Disconnect and cleanup a stale voice client as aggressively as possible."""
        if vc is None:
            return

        try:
            if vc.is_playing():
                vc.stop()
        except Exception:
            pass

        try:
            await vc.disconnect(force=True)
        except Exception:
            pass

        try:
            vc.cleanup()
        except Exception:
            pass

    async def _send_roast_file_fallback(self, ctx, loading_msg, roast_embed, temp_file: str):
        """Fallback when voice playback is unavailable on the host."""
        roast_embed = roast_embed.copy()
        roast_embed.set_footer(text=f"Requested by {ctx.author.display_name} • xiel Premium (voice fallback)")
        with open(temp_file, 'rb') as f:
            tts_file = discord.File(f, filename='roast.mp3')
        await loading_msg.edit(embed=roast_embed)
        await ctx.send("couldn't play it in vc, so here's the roast audio instead", file=tts_file)

    def _voice_roast_disabled_for_guild(self, guild_id: int) -> bool:
        """Return whether VC roast is temporarily disabled for this guild."""
        if settings_db and settings_db.get_setting(self.ROASTVC_NAMESPACE, guild_id, self.ROASTVC_DISABLED_KEY, False):
            return True

        until = self._roastvc_voice_disabled_until.get(guild_id)
        if not until:
            return False
        if datetime.now(UTC) >= until:
            self._roastvc_voice_disabled_until.pop(guild_id, None)
            return False
        return True

    def _disable_voice_roast_temporarily(self, guild_id: int, minutes: int = 30):
        """Temporarily skip VC playback attempts after a host voice failure."""
        until = datetime.now(UTC) + timedelta(minutes=minutes)
        self._roastvc_voice_disabled_until[guild_id] = until
        print(f"[roastvc] voice playback disabled for guild {guild_id} until {until.isoformat()}")

        if settings_db:
            settings_db.set_setting(self.ROASTVC_NAMESPACE, guild_id, self.ROASTVC_DISABLED_KEY, True)

    def _can_manage_premium_access(self, user_id: int) -> bool:
        return user_id in config.OWNER_IDS or user_id in config.CO_OWNER_IDS

    async def _grant_premium_access_from_command(self, ctx, member: discord.Member, command_name: str, server_id: str = None):
        """Grant premium command access from Discord."""
        if not self._can_manage_premium_access(ctx.author.id):
            return await ctx.reply(embed=error_embed('Owner Only', 'Only bot owners and co-owners can grant premium access.'))

        canonical = normalize_premium_command(command_name)
        if not canonical:
            commands_list = ', '.join(PREMIUM_COMMANDS)
            return await ctx.reply(embed=error_embed(
                'Invalid Premium Command',
                f'Use one of: `all`, `{commands_list}`'
            ))

        target_server_id = ctx.guild.id
        if server_id:
            maybe_server_id = server_id.strip()
            if maybe_server_id.isdigit():
                target_server_id = int(maybe_server_id)

        granted = grant_premium(member.id, target_server_id, canonical, ctx.author.id)
        if not granted:
            return await ctx.reply(embed=error_embed(
                'Already Granted',
                f'{member.mention} already has `{canonical}` premium access in server `{target_server_id}`.'
            ))

        await ctx.reply(embed=success_embed(
            'Premium Granted',
            f'{member.mention} can now use `{canonical}` in server `{target_server_id}`.'
        ))

    async def _revoke_premium_access_from_command(self, ctx, member: discord.Member, command_name: str, server_id: str = None):
        """Revoke premium command access from Discord."""
        if not self._can_manage_premium_access(ctx.author.id):
            return await ctx.reply(embed=error_embed('Owner Only', 'Only bot owners and co-owners can revoke premium access.'))

        canonical = normalize_premium_command(command_name)
        if not canonical:
            commands_list = ', '.join(PREMIUM_COMMANDS)
            return await ctx.reply(embed=error_embed(
                'Invalid Premium Command',
                f'Use one of: `all`, `{commands_list}`'
            ))

        target_server_id = ctx.guild.id
        if server_id:
            maybe_server_id = server_id.strip()
            if maybe_server_id.isdigit():
                target_server_id = int(maybe_server_id)

        revoked = revoke_premium(member.id, target_server_id, canonical)
        if not revoked:
            return await ctx.reply(embed=error_embed(
                'Not Found',
                f'No `{canonical}` premium access found for {member.mention} in server `{target_server_id}`.'
            ))

        await ctx.reply(embed=success_embed(
            'Premium Revoked',
            f'{member.mention} can no longer use `{canonical}` in server `{target_server_id}`.'
        ))
    
    # ========================
    # MIMIC COMMAND
    # ========================
    @commands.command(name='mimic')
    @commands.has_permissions(manage_messages=True, manage_webhooks=True)
    @premium_required('mimic')
    async def mimic(self, ctx, member: discord.Member = None, *, message: str = None):
        """🎭 Send a message as another user using webhooks (Premium)"""
        if not member:
            return await ctx.reply(embed=error_embed('Missing User', f'Usage: `{config.PREFIX}mimic @user <message>`'))
        if not message:
            return await ctx.reply(embed=error_embed('Missing Message', f'Usage: `{config.PREFIX}mimic @user <message>`'))
        
        # Don't allow mimicking bots
        if member.bot:
            return await ctx.reply(embed=error_embed('Cannot Mimic', "You can't mimic bots!"))
        
        # Check permissions
        bot_perms = ctx.channel.permissions_for(ctx.guild.me)
        if not bot_perms.manage_webhooks:
            return await ctx.reply(embed=error_embed('Permission Error', "I need **Manage Webhooks** permission!"))
        webhook = None
        try:
            # Create webhook
            webhook = await ctx.channel.create_webhook(name=member.display_name)
            
            # Preserve clear attribution so the command cannot be used for covert impersonation.
            avatar_url = member.display_avatar.url if member.display_avatar else None
            await webhook.send(
                content=(
                    f"{message}\n\n"
                    f"-# Sent by {ctx.author.mention} via xiel's mimic command"
                ),
                username=member.display_name,
                avatar_url=avatar_url,
                allowed_mentions=discord.AllowedMentions.none()
            )
        except discord.Forbidden as e:
            await ctx.reply(embed=error_embed('Permission Error', f"Missing permissions: {e}"))
        except Exception as e:
            await ctx.reply(embed=error_embed('Error', f'Failed to mimic: {e}'))
        finally:
            if webhook is not None:
                try:
                    await webhook.delete()
                except discord.HTTPException as exc:
                    print(f"[Mimic] Failed to delete temporary webhook: {exc}")
    
    # ========================
    # ROAST VC COMMAND
    # ========================
    @commands.command(name='roastvc')
    @premium_required('roastvc')
    async def roastvc(self, ctx, member: discord.Member = None):
        """🔥 Join VC, roast user with TTS audio, then leave (Premium)"""
        if not member:
            return await ctx.reply(embed=error_embed('Missing User', f'Usage: `{config.PREFIX}roastvc @user`'))

        if not member.voice or not member.voice.channel:
            return await ctx.reply(embed=error_embed('Not in VC', f'{member.mention} is not in a voice channel!'))

        vc_channel = member.voice.channel
        me = ctx.guild.me or ctx.guild.get_member(self.bot.user.id)
        if not me:
            return await ctx.reply(embed=error_embed('Error', "I couldn't find my member data in this server."))

        perms = vc_channel.permissions_for(me)
        if not perms.view_channel or not perms.connect or not perms.speak:
            return await ctx.reply(embed=error_embed('No Permissions', "I need **View Channel**, **Connect**, and **Speak** permissions in that voice channel!"))

        roast_text = random.choice(ROASTS).format(user=member.display_name)
        roast_embed = discord.Embed(title="🔥 ROASTED!", description=f"> {roast_text}", color=0xff6b35)
        roast_embed.set_author(name=f"Roasting {member.display_name}", icon_url=member.display_avatar.url)
        roast_embed.set_footer(text=f"Requested by {ctx.author.display_name} • xiel Premium")

        loading_msg = await ctx.reply(embed=info_embed('🎤 Roast Incoming', f'Joining **{vc_channel.name}** to roast {member.mention}...'))

        vc = None
        temp_file = None

        try:
            # Generate TTS mp3 into a unique temp file.
            temp_handle = tempfile.NamedTemporaryFile(prefix=f"roast_{ctx.guild.id}_", suffix=".mp3", delete=False)
            temp_file = temp_handle.name
            temp_handle.close()

            tts = gTTS(text=roast_text, lang='en', slow=False)
            tts.save(temp_file)

            # Try to use system ffmpeg — fall back to embed-only if unavailable
            import shutil
            ffmpeg_path = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')

            if ffmpeg_path and not self._voice_roast_disabled_for_guild(ctx.guild.id):
                try:
                    vc = await self._connect_to_voice_channel(ctx.guild, vc_channel)

                    if isinstance(vc.channel, discord.StageChannel):
                        try:
                            await ctx.guild.me.edit(suppress=False)
                        except Exception:
                            pass

                    await self._play_roast_audio(vc, temp_file, ffmpeg_path)
                except Exception as play_error:
                    print(f"[roastvc] first playback attempt failed: {play_error}")
                    self._disable_voice_roast_temporarily(ctx.guild.id)
                    await self._send_roast_file_fallback(ctx, loading_msg, roast_embed, temp_file)
                    return

                await loading_msg.edit(embed=roast_embed)
            else:
                # No ffmpeg — send roast as embed + TTS file attachment
                await self._send_roast_file_fallback(ctx, loading_msg, roast_embed, temp_file)

        except asyncio.TimeoutError:
            await self._send_roast_file_fallback(ctx, loading_msg, roast_embed, temp_file)
            print("[roastvc] Error: playback timeout")
        except Exception as e:
            await loading_msg.edit(embed=error_embed('Roast Failed', f'Something went wrong: `{e}`'))
            print(f"[roastvc] Error: {e}")

        finally:
            await self._hard_cleanup_voice(vc)
            try:
                os.remove(temp_file)
            except Exception:
                pass

    # ========================
    # GHOST PING DETECTOR
    # ========================
    @commands.command(name='ghost-ping-detector', aliases=['gpd', 'ghostping'])
    @premium_required('ghost-ping-detector')
    async def ghost_ping_detector(self, ctx, toggle: str = None):
        """👻 Toggle ghost ping detection — catches deleted pings (Premium)"""
        if not ctx.author.guild_permissions.manage_guild and ctx.author.id not in config.OWNER_IDS:
            return await ctx.reply(embed=error_embed('No Permission', 'You need **Manage Server** permission!'))
        
        session = self.db.get_session()
        try:
            gp_config = session.query(GhostPingConfig).filter_by(server_id=ctx.guild.id).first()
            
            if toggle is None:
                # Show current status
                is_enabled = gp_config.enabled if gp_config else False
                status = "**✅ Enabled**" if is_enabled else "**❌ Disabled**"
                embed = info_embed(
                    '👻 Ghost Ping Detector',
                    f'Status: {status}\n\n'
                    f'Use `{config.PREFIX}ghost-ping-detector on` or `off` to toggle.'
                )
                return await ctx.reply(embed=embed)
            
            enable = toggle.lower() in ['on', 'enable', 'true', '1']
            
            if not gp_config:
                gp_config = GhostPingConfig(
                    server_id=ctx.guild.id,
                    enabled=enable,
                    toggled_by=ctx.author.id
                )
                session.add(gp_config)
            else:
                gp_config.enabled = enable
                gp_config.toggled_by = ctx.author.id
            
            session.commit()
            
            status = "enabled ✅" if enable else "disabled ❌"
            await ctx.reply(embed=success_embed(
                '👻 Ghost Ping Detector',
                f'Ghost ping detection has been **{status}** for this server.'
            ))
            
        except Exception as e:
            session.rollback()
            await ctx.reply(embed=error_embed('Error', f'Failed to update: {e}'))
        finally:
            session.close()
    
    # ========================
    # GRANT (TEMP-ROLE) COMMAND
    # ========================
    @commands.command(name='grant', aliases=['temp-role', 'temprole'])
    async def grant(self, ctx, member: discord.Member = None, target: str = None, *, duration: str = None):
        """⏰ Give someone a temporary role that auto-removes, or grant premium access
        
        Usage: ,grant @user @role <duration>
        Example: ,grant @friend DJ 1h
        Durations: 30m, 1h, 2d, 1w
        """
        if not member:
            return await ctx.reply(embed=error_embed(
                'Missing User',
                f'Usage: `{config.PREFIX}grant @user @role <duration>` or `{config.PREFIX}grant @user <premium-command|all>`'
            ))
        if not target:
            return await ctx.reply(embed=error_embed(
                'Missing Target',
                f'Usage: `{config.PREFIX}grant @user @role <duration>` or `{config.PREFIX}grant @user <premium-command|all>`'
            ))

        role = None
        try:
            role = await commands.RoleConverter().convert(ctx, target)
        except commands.BadArgument:
            role = None

        if role is None:
            return await self._grant_premium_access_from_command(ctx, member, target, duration)

        if not duration:
            return await ctx.reply(embed=error_embed('Missing Duration', f'Usage: `{config.PREFIX}grant @user @role <duration>`\nExample: `1h`, `30m`, `2d`'))

        if ctx.author.id not in config.OWNER_IDS and not check_premium(ctx.author.id, ctx.guild.id, 'grant'):
            return await ctx.reply(embed=error_embed(
                'Premium Required',
                f'You need premium access to `{config.PREFIX}grant`, or bot owner access.'
            ))
        
        # Permission check
        if not ctx.author.guild_permissions.manage_roles and ctx.author.id not in config.OWNER_IDS:
            return await ctx.reply(embed=error_embed('No Permission', 'You need **Manage Roles** permission!'))
        
        # Check role hierarchy
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(embed=error_embed('Role Too High', f'I cannot manage **{role.name}** — it\'s above my highest role!'))
        
        if role >= ctx.author.top_role and ctx.author.id not in config.OWNER_IDS:
            return await ctx.reply(embed=error_embed('Role Too High', f'**{role.name}** is above your highest role!'))
        
        # Parse duration
        try:
            delta = parse_duration(duration)
        except ValueError as e:
            return await ctx.reply(embed=error_embed('Invalid Duration', str(e)))
        
        expires_at = datetime.now(UTC) + delta
        
        # Add role
        try:
            await member.add_roles(role, reason=f"Temp role by {ctx.author} — expires {expires_at.strftime('%Y-%m-%d %H:%M UTC')}")
        except discord.Forbidden:
            return await ctx.reply(embed=error_embed('Permission Error', "I don't have permission to add that role!"))
        
        # Store in database
        session = self.db.get_session()
        try:
            tr = TempRole(
                server_id=ctx.guild.id,
                user_id=member.id,
                role_id=role.id,
                granted_by=ctx.author.id,
                expires_at=expires_at
            )
            session.add(tr)
            session.commit()
        except Exception as e:
            session.rollback()
            return await ctx.reply(embed=error_embed('Database Error', f'Role added but timer failed: {e}'))
        finally:
            session.close()
        
        # Format friendly duration
        total_seconds = int(delta.total_seconds())
        if total_seconds >= 86400:
            dur_str = f"{total_seconds // 86400} day(s)"
        elif total_seconds >= 3600:
            dur_str = f"{total_seconds // 3600} hour(s)"
        elif total_seconds >= 60:
            dur_str = f"{total_seconds // 60} minute(s)"
        else:
            dur_str = f"{total_seconds} second(s)"
        
        embed = success_embed(
            '⏰ Temporary Role Granted',
            f'**{member.mention}** has been given **{role.name}** for **{dur_str}**!\n\n'
            f'🕐 Expires: <t:{int(expires_at.timestamp())}:R>\n'
            f'The role will be **automatically removed** when the time is up.'
        )
        embed.set_footer(text=f"Granted by {ctx.author.display_name} • xiel Premium")
        await ctx.reply(embed=embed)

    @commands.group(name='premium', aliases=['prem'], invoke_without_command=True)
    async def premium(self, ctx):
        """Manage premium command access."""
        await ctx.reply(embed=info_embed(
            'Premium Access',
            f'`{config.PREFIX}premium grant @user <command|all> [server_id]`\n'
            f'`{config.PREFIX}premium revoke @user <command|all> [server_id]`\n'
            f'`{config.PREFIX}premium list [server_id]`'
        ))

    @premium.command(name='grant', aliases=['add'])
    async def premium_grant(self, ctx, member: discord.Member = None, command_name: str = None, server_id: str = None):
        if not member or not command_name:
            return await ctx.reply(embed=error_embed(
                'Invalid Usage',
                f'Usage: `{config.PREFIX}premium grant @user <command|all> [server_id]`'
            ))
        await self._grant_premium_access_from_command(ctx, member, command_name, server_id)

    @premium.command(name='revoke', aliases=['remove'])
    async def premium_revoke(self, ctx, member: discord.Member = None, command_name: str = None, server_id: str = None):
        if not member or not command_name:
            return await ctx.reply(embed=error_embed(
                'Invalid Usage',
                f'Usage: `{config.PREFIX}premium revoke @user <command|all> [server_id]`'
            ))
        await self._revoke_premium_access_from_command(ctx, member, command_name, server_id)

    @premium.command(name='list')
    async def premium_list(self, ctx, server_id: str = None):
        if not self._can_manage_premium_access(ctx.author.id):
            return await ctx.reply(embed=error_embed('Owner Only', 'Only bot owners and co-owners can view premium access.'))

        target_server_id = ctx.guild.id
        if server_id and server_id.strip().isdigit():
            target_server_id = int(server_id.strip())

        records = get_all_premium(target_server_id)
        if not records:
            return await ctx.reply(embed=info_embed('Premium Access', f'No premium grants found for server `{target_server_id}`.'))

        lines = [
            f"<@{record['user_id']}> (`{record['user_id']}`): `{record['command_name']}`"
            for record in records[:20]
        ]
        suffix = f"\n…and {len(records) - 20} more." if len(records) > 20 else ""
        await ctx.reply(embed=info_embed(
            'Premium Access',
            "\n".join(lines) + suffix
        ))
    
    # ========================
    # AUTO-REPLY TRIGGER COMMANDS
    # ========================
    @commands.command(name='add-trigger', aliases=['addtrigger', 'autoreply'])
    @premium_required('add-trigger')
    async def add_trigger(self, ctx, phrase: str = None, *, response: str = None):
        """💬 Add an auto-reply trigger — bot replies when phrase is typed (Premium)
        
        Usage: ,add-trigger "phrase" response text
        Example: ,add-trigger "what is the ip" The server IP is play.example.com
        """
        if not phrase:
            return await ctx.reply(embed=error_embed('Missing Phrase', f'Usage: `{config.PREFIX}add-trigger "phrase" <response>`'))
        if not response:
            return await ctx.reply(embed=error_embed('Missing Response', f'Usage: `{config.PREFIX}add-trigger "phrase" <response>`'))
        
        if not ctx.author.guild_permissions.manage_guild and ctx.author.id not in config.OWNER_IDS:
            return await ctx.reply(embed=error_embed('No Permission', 'You need **Manage Server** permission!'))
        
        phrase_lower = phrase.lower().strip()
        
        session = self.db.get_session()
        try:
            # Check trigger count limit (max 50 per server)
            count = session.query(AutoTrigger).filter_by(server_id=ctx.guild.id).count()
            if count >= 50:
                return await ctx.reply(embed=error_embed('Limit Reached', 'Maximum of 50 triggers per server!'))
            
            # Check for duplicate
            existing = session.query(AutoTrigger).filter_by(
                server_id=ctx.guild.id,
                phrase=phrase_lower
            ).first()
            
            if existing:
                existing.response = response
                existing.created_by = ctx.author.id
                session.commit()
                return await ctx.reply(embed=success_embed(
                    '💬 Trigger Updated',
                    f'Updated response for trigger **"{phrase_lower}"**'
                ))
            
            trigger = AutoTrigger(
                server_id=ctx.guild.id,
                phrase=phrase_lower,
                response=response,
                created_by=ctx.author.id
            )
            session.add(trigger)
            session.commit()
            
            await ctx.reply(embed=success_embed(
                '💬 Trigger Added',
                f'Auto-reply trigger created!\n\n'
                f'**Trigger:** "{phrase_lower}"\n'
                f'**Response:** {response[:200]}'
            ))
            
        except Exception as e:
            session.rollback()
            await ctx.reply(embed=error_embed('Error', f'Failed to add trigger: {e}'))
        finally:
            session.close()
    
    @commands.command(name='remove-trigger', aliases=['removetrigger', 'deltrigger'])
    @premium_required('add-trigger')
    async def remove_trigger(self, ctx, *, phrase: str = None):
        """❌ Remove an auto-reply trigger (Premium)
        
        Usage: ,remove-trigger <phrase>
        """
        if not phrase:
            return await ctx.reply(embed=error_embed('Missing Phrase', f'Usage: `{config.PREFIX}remove-trigger <phrase>`'))
        
        if not ctx.author.guild_permissions.manage_guild and ctx.author.id not in config.OWNER_IDS:
            return await ctx.reply(embed=error_embed('No Permission', 'You need **Manage Server** permission!'))
        
        session = self.db.get_session()
        try:
            deleted = session.query(AutoTrigger).filter_by(
                server_id=ctx.guild.id,
                phrase=phrase.lower().strip()
            ).delete()
            session.commit()
            
            if deleted:
                await ctx.reply(embed=success_embed('❌ Trigger Removed', f'Removed trigger for **"{phrase}"**'))
            else:
                await ctx.reply(embed=error_embed('Not Found', f'No trigger found for **"{phrase}"**'))
        except Exception as e:
            session.rollback()
            await ctx.reply(embed=error_embed('Error', f'Failed: {e}'))
        finally:
            session.close()
    
    @commands.command(name='list-triggers', aliases=['listtriggers', 'triggers'])
    @premium_required('add-trigger')
    async def list_triggers(self, ctx):
        """📋 List all auto-reply triggers for this server (Premium)"""
        session = self.db.get_session()
        try:
            triggers = session.query(AutoTrigger).filter_by(server_id=ctx.guild.id).all()
            
            if not triggers:
                return await ctx.reply(embed=info_embed(
                    '📋 Auto-Reply Triggers',
                    f'No triggers set up yet!\n\nUse `{config.PREFIX}add-trigger "phrase" <response>` to create one.'
                ))
            
            embed = discord.Embed(
                title=f"📋 Auto-Reply Triggers ({len(triggers)})",
                color=0xfbbf24
            )
            
            for t in triggers[:25]:  # Max 25 fields
                response_preview = t.response[:100] + '...' if len(t.response) > 100 else t.response
                embed.add_field(
                    name=f'"{t.phrase}"',
                    value=response_preview,
                    inline=False
                )
            
            if len(triggers) > 25:
                embed.set_footer(text=f"Showing 25 of {len(triggers)} triggers")
            else:
                embed.set_footer(text="xiel Premium • Auto-Reply System")
            
            await ctx.reply(embed=embed)
        finally:
            session.close()
    
    # ========================
    # AUTO-REPLY LISTENER
    # ========================
    @commands.Cog.listener()
    async def on_message(self, message):
        """Check messages against auto-reply triggers"""
        if message.author.bot or not message.guild:
            return
        
        # Don't trigger on command messages
        if message.content.startswith(config.PREFIX):
            return
        
        session = self.db.get_session()
        try:
            triggers = session.query(AutoTrigger).filter_by(server_id=message.guild.id).all()
            
            if not triggers:
                return
            
            msg_lower = message.content.lower()
            for trigger in triggers:
                if trigger.phrase in msg_lower:
                    await message.reply(trigger.response, mention_author=False)
                    break  # Only reply once per message
        except Exception:
            pass
        finally:
            session.close()
    
    
    def _apply_corruption_effects(self, img, level):
        """Apply corruption effects to an image and return a PIL Image (no numpy needed)"""
        from PIL import Image, ImageEnhance, ImageFilter, ImageChops
        
        width, height = img.size
        result = img.copy()
        
        # Effect 1: RGB channel shift (all levels)
        shift = level * 12 + random.randint(-5, 5)
        r, g, b = result.split()
        # Horizontal shift red channel right, blue channel left
        r_data = list(r.getdata())
        b_data = list(b.getdata())
        g_data = list(g.getdata())
        
        shifted_r = [0] * len(r_data)
        shifted_b = [0] * len(b_data)
        shifted_g = [0] * len(g_data)
        
        for y in range(height):
            for x in range(width):
                idx = y * width + x
                # Shift red right
                src_x_r = (x - shift) % width
                shifted_r[idx] = r_data[y * width + src_x_r]
                # Shift blue left
                src_x_b = (x + shift) % width
                shifted_b[idx] = b_data[y * width + src_x_b]
                # Shift green vertically
                src_y_g = (y - shift // 2) % height
                shifted_g[idx] = g_data[src_y_g * width + x]
        
        r.putdata(shifted_r)
        g.putdata(shifted_g)
        b.putdata(shifted_b)
        result = Image.merge('RGB', (r, g, b))
        
        # Effect 2: Scanlines (level 2+)
        if level >= 2:
            pixels = result.load()
            step = max(1, 5 - level)
            darken = 0.3 if level >= 4 else 0.5
            for y in range(0, height, step):
                if y % 2 == 0:
                    for x in range(width):
                        pr, pg, pb = pixels[x, y]
                        pixels[x, y] = (int(pr * darken), int(pg * darken), int(pb * darken))
        
        # Effect 3: Random block displacement (level 3+)
        if level >= 3:
            for _ in range(level * 10):
                y = random.randint(0, max(1, height - 32))
                h = random.randint(3, min(15 + level * 5, height - y))
                shift_px = random.randint(-80 * level, 80 * level)
                # Crop block, shift horizontally by pasting offset
                block = result.crop((0, y, width, y + h))
                # Create shifted version
                shifted_block = Image.new('RGB', (width, h))
                shifted_block.paste(block, (shift_px % width, 0))
                if shift_px % width != 0:
                    shifted_block.paste(block, (shift_px % width - width, 0))
                result.paste(shifted_block, (0, y))
        
        # Effect 4: Static noise (level 2+) — use Pillow's built-in
        if level >= 2:
            noise_img = Image.effect_noise((width, height), level * 25)
            noise_rgb = Image.merge('RGB', (noise_img, noise_img, noise_img))
            result = ImageChops.add(result, noise_rgb, scale=2, offset=-level * 12)
        
        # Effect 5: Red/Horror tint (level 4+)
        if level >= 4:
            r, g, b = result.split()
            r = r.point(lambda p: min(255, p + 60))
            g = g.point(lambda p: int(p * 0.6))
            b = b.point(lambda p: int(p * 0.5))
            result = Image.merge('RGB', (r, g, b))
        
        # Effect 6: Extreme datamoshing (level 5)
        if level >= 5:
            for _ in range(level * 6):
                y = random.randint(0, max(1, height - 20))
                h = random.randint(2, 20)
                shift_amt = random.randint(-200, 200)
                block = result.crop((0, y, width, min(y + h, height)))
                bh = block.size[1]
                shifted_block = Image.new('RGB', (width, bh))
                shifted_block.paste(block, (shift_amt % width, 0))
                if shift_amt % width != 0:
                    shifted_block.paste(block, (shift_amt % width - width, 0))
                result.paste(shifted_block, (0, y))
        
        # Effect 7: Blood-red splotches (level 3+) — use red rectangles
        if level >= 3:
            from PIL import ImageDraw
            draw = ImageDraw.Draw(result)
            for _ in range(level * 4):
                cx = random.randint(20, width - 20)
                cy = random.randint(20, height - 20)
                radius = random.randint(5, 20 + level * 5)
                opacity = random.randint(80, 150)
                draw.ellipse(
                    [(cx - radius, cy - radius), (cx + radius, cy + radius)],
                    fill=(opacity, 0, 0)
                )
        
        return result
    
    # ========================
    # GLITCH PROFILE (CORRUPT) COMMAND
    # ========================
    @commands.command(name='corrupt', aliases=['glitch-profile', 'glitch'])
    @premium_required('corrupt')
    async def corrupt(self, ctx, member: discord.Member = None, level: int = 3, mode: str = "avatar"):
        """👾 Corrupt someone's profile into a glitched horror aesthetic (Premium)
        
        Usage: ,corrupt @user [level 1-5] [mode]
        Level 1: Slight static
        Level 5: Full horror nightmare
        
        Modes:
        - avatar: Corrupt just the avatar (default)
        - profile: Corrupt full profile card (avatar + banner + username)
        """
        if not member:
            member = ctx.author
        
        if level < 1 or level > 5:
            return await ctx.reply(embed=error_embed('Invalid Level', 'Corruption level must be between 1 and 5!'))
        
        mode = mode.lower()
        if mode not in ['avatar', 'profile']:
            mode = 'avatar'
        
        # Pre-check dependencies before entering the main logic
        try:
            from PIL import Image, ImageEnhance, ImageFilter, ImageDraw, ImageFont
        except ImportError:
            return await ctx.reply(embed=error_embed(
                'Missing Dependencies',
                'This command requires `Pillow`. Install with:\n`pip install Pillow`'
            ))
        
        import aiohttp
        
        async with ctx.typing():
            try:
                if mode == 'profile':
                    # CREATE FULL PROFILE CARD
                    # Profile card dimensions: 600x800 (banner + avatar + username)
                    profile_width, profile_height = 600, 800
                    profile_card = Image.new('RGB', (profile_width, profile_height), (47, 49, 54))
                    
                    # Download and corrupt banner
                    banner_height = 240
                    if member.banner:
                        try:
                            banner_url = member.banner.with_size(1024).url
                            async with aiohttp.ClientSession() as http_session:
                                async with http_session.get(str(banner_url)) as resp:
                                    if resp.status == 200:
                                        banner_bytes = await resp.read()
                                        banner_img = Image.open(io.BytesIO(banner_bytes)).convert('RGB')
                                        banner_img = banner_img.resize((profile_width, banner_height))
                                        
                                        # Corrupt banner
                                        banner_img = self._apply_corruption_effects(banner_img, level)
                                        profile_card.paste(banner_img, (0, 0))
                        except:
                            # Use dark corrupted gradient if no banner
                            for y in range(banner_height):
                                for x in range(profile_width):
                                    r = int(20 + random.randint(-10, 10) + (y / banner_height) * 30)
                                    g = int(15 + random.randint(-10, 10))
                                    b = int(25 + random.randint(-10, 10))
                                    profile_card.putpixel((x, y), (r, g, b))
                    else:
                        # Dark corrupted gradient
                        for y in range(banner_height):
                            for x in range(profile_width):
                                r = int(20 + random.randint(-10, 10) + (y / banner_height) * 30)
                                g = int(15 + random.randint(-10, 10))
                                b = int(25 + random.randint(-10, 10))
                                profile_card.putpixel((x, y), (r, g, b))
                    
                    # Download and corrupt avatar
                    avatar_url = member.display_avatar.with_size(512).url
                    async with aiohttp.ClientSession() as http_session:
                        async with http_session.get(str(avatar_url)) as resp:
                            if resp.status != 200:
                                return await ctx.reply(embed=error_embed('Error', 'Could not download avatar'))
                            avatar_bytes = await resp.read()
                    
                    avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert('RGB')
                    avatar_img = avatar_img.resize((256, 256))
                    
                    # Corrupt avatar
                    avatar_img = self._apply_corruption_effects(avatar_img, level)
                    
                    # Create circular mask for avatar
                    mask = Image.new('L', (256, 256), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, 256, 256), fill=255)
                    
                    # Add corrupted border
                    border_mask = Image.new('L', (256, 256), 0)
                    border_draw = ImageDraw.Draw(border_mask)
                    border_draw.ellipse((0, 0, 256, 256), fill=255)
                    border_draw.ellipse((8, 8, 248, 248), fill=0)
                    
                    # Paste avatar with border
                    avatar_with_bg = Image.new('RGB', (256, 256), (139, 0, 0) if level >= 4 else (88, 101, 242))
                    avatar_with_bg.paste(avatar_img, (0, 0), mask)
                    
                    # Position avatar (overlapping banner)
                    avatar_y = banner_height - 80
                    avatar_x = (profile_width - 256) // 2
                    profile_card.paste(avatar_with_bg, (avatar_x, avatar_y), mask)
                    
                    # Add corrupted username
                    draw = ImageDraw.Draw(profile_card)
                    username = member.display_name
                    
                    # Try to load a font, fallback to default
                    try:
                        font = ImageFont.truetype("arial.ttf", 48)
                        small_font = ImageFont.truetype("arial.ttf", 24)
                    except:
                        font = ImageFont.load_default()
                        small_font = ImageFont.load_default()
                    
                    # Draw corrupted username with glitch effect
                    text_y = avatar_y + 280
                    
                    # Multiple offset text layers for glitch effect
                    glitch_offsets = [
                        (-3, -2, (255, 0, 0)),
                        (3, 2, (0, 255, 255)),
                        (0, 0, (255, 255, 255))
                    ]
                    
                    for offset_x, offset_y, color in glitch_offsets:
                        # Calculate text position (centered)
                        try:
                            bbox = draw.textbbox((0, 0), username, font=font)
                            text_width = bbox[2] - bbox[0]
                        except:
                            text_width = len(username) * 20
                        
                        text_x = (profile_width - text_width) // 2 + offset_x
                        draw.text((text_x, text_y + offset_y), username, fill=color, font=font)
                    
                    # Add creepy subtitle
                    subtitle = "C̴̢̛O̷̢͝R̸̨̛R̵̢̾U̴̧̕P̷̨̈́T̸̢̛E̸̢͝D̵̨̛"
                    try:
                        bbox = draw.textbbox((0, 0), subtitle, font=small_font)
                        subtitle_width = bbox[2] - bbox[0]
                    except:
                        subtitle_width = len(subtitle) * 10
                    
                    subtitle_x = (profile_width - subtitle_width) // 2
                    draw.text((subtitle_x, text_y + 60), subtitle, fill=(180, 0, 0), font=small_font)
                    
                    # Add random glitch lines across the whole profile
                    if level >= 3:
                        for _ in range(level * 5):
                            y = random.randint(0, profile_height - 5)
                            h = random.randint(2, 8)
                            draw.rectangle([(0, y), (profile_width, y + h)], 
                                         fill=(random.randint(0, 255), 0, random.randint(0, 100)))
                    
                    # Save profile card
                    buffer = io.BytesIO()
                    profile_card.save(buffer, format='PNG')
                    buffer.seek(0)
                    
                    file = discord.File(buffer, filename='corrupted_profile.png')
                    
                    level_names = {
                        1: "Minor Static",
                        2: "Glitched",
                        3: "Bloodied Corruption",
                        4: "Flesh Horror",
                        5: "NIGHTMARE VOID"
                    }
                    
                    embed = discord.Embed(
                        title=f"👾 CORRUPTED PROFILE — Level {level}: {level_names.get(level, 'Unknown')}",
                        description=f"**{member.mention}**'s profile has been brutally corrupted.",
                        color=0xff0000 if level >= 4 else 0x8b5cf6
                    )
                    embed.set_image(url="attachment://corrupted_profile.png")
                    embed.set_footer(text=f"Corrupted by {ctx.author.display_name} • xiel Premium")
                    
                    await ctx.reply(embed=embed, file=file)
                    
                else:
                    # ORIGINAL AVATAR-ONLY MODE
                    # Download avatar
                    avatar_url = member.display_avatar.with_size(512).url
                    async with aiohttp.ClientSession() as http_session:
                        async with http_session.get(str(avatar_url)) as resp:
                            if resp.status != 200:
                                return await ctx.reply(embed=error_embed('Error', 'Could not download avatar'))
                            avatar_bytes = await resp.read()
                    
                    img = Image.open(io.BytesIO(avatar_bytes)).convert('RGB')
                    img = img.resize((512, 512))
                    
                    # Apply corruption effects
                    result = self._apply_corruption_effects(img, level)
                    
                    # Effect 10: CREEPY TEXT OVERLAYS (level 4+)
                    if level >= 4:
                        draw = ImageDraw.Draw(result)
                        
                        # Horror phrases
                        phrases = ["CORRUPTED", "ERROR", "NO ESCAPE", "HELP", "GLITCH", "LOST", "VOID", "BROKEN"]
                        
                        for _ in range(level * 3):
                            phrase = random.choice(phrases)
                            x = random.randint(10, 400)
                            y = random.randint(10, 480)
                            
                            # Glitchy text with random colors
                            color = (
                                random.randint(200, 255),
                                random.randint(0, 50),
                                random.randint(0, 50)
                            )
                            
                            # Draw text multiple times with slight offsets for glitch effect
                            for offset in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)]:
                                draw.text(
                                    (x + offset[0], y + offset[1]),
                                    phrase,
                                    fill=color if offset == (0, 0) else (color[0]//2, color[1], color[2]),
                                    font=None
                                )
                        
                        # Add glitch lines
                        for _ in range(level * 4):
                            y_pos = random.randint(0, 500)
                            color = (random.randint(200, 255), 0, 0) if random.random() > 0.5 else (0, random.randint(200, 255), 0)
                            draw.line([(0, y_pos), (512, y_pos)], fill=color, width=random.randint(1, 3))
                
                # Save to buffer
                buffer = io.BytesIO()
                result.save(buffer, format='PNG')
                buffer.seek(0)
                
                # Send result
                file = discord.File(buffer, filename='corrupted.png')
                
                level_names = {
                    1: "Minor Static",
                    2: "Glitched",
                    3: "Bloodied Corruption",
                    4: "Flesh Horror",
                    5: "NIGHTMARE VOID"
                }
                
                embed = discord.Embed(
                    title=f"👾 CORRUPTED — Level {level}: {level_names.get(level, 'Unknown')}",
                    description=f"**{member.mention}** has been brutally corrupted.",
                    color=0xff0000 if level >= 4 else 0x8b5cf6
                )
                embed.set_image(url="attachment://corrupted.png")
                embed.set_footer(text=f"Corrupted by {ctx.author.display_name} • xiel Premium")
                
                await ctx.reply(embed=embed, file=file)
                
            except Exception as e:
                await ctx.reply(embed=error_embed('Corruption Failed', f'Error: {e}'))
    
    # ========================
    # BOT AVATAR (PER-GUILD PROFILE)
    # ========================
    @commands.command(name='botavatar')
    @bot_profile_required('botavatar')
    async def botavatar(self, ctx, *, url: str = None):
        """🖼️ Change the bot's avatar for this server (Bot Profile Access)
        
        Sets a per-server custom avatar. The bot's profile picture will
        change in the member list and profile for this server only.
        
        Usage: ,botavatar <url> or attach an image
        """
        if not url and not ctx.message.attachments:
            return await ctx.reply(embed=error_embed(
                'Missing Image',
                f'Usage: `{config.PREFIX}botavatar <url>` or attach an image\n\n'
                f'This will change the bot\'s profile picture **in this server only**.'
            ))
        
        if ctx.message.attachments:
            url = ctx.message.attachments[0].url
        
        async with ctx.typing():
            try:
                # Download image bytes
                import base64

                avatar_bytes, content_type = await _download_profile_image(
                    url,
                    8 * 1024 * 1024,
                )
                
                # Convert to base64 data URI
                b64 = base64.b64encode(avatar_bytes).decode('utf-8')
                
                # Detect image format from content type
                image_format = content_type.split('/')[-1]
                if image_format not in ['png', 'jpeg', 'jpg', 'gif', 'webp']:
                    image_format = 'png'
                if image_format == 'jpg':
                    image_format = 'jpeg'
                
                data_uri = f"data:image/{image_format};base64,{b64}"
                
                # Use Discord's Per-Guild Bot Profile API
                # PATCH /guilds/{guild.id}/members/@me
                route = f'/guilds/{ctx.guild.id}/members/@me'
                
                await self.bot.http.request(
                    discord.http.Route('PATCH', route),
                    json={'avatar': data_uri}
                )
                
                # Store URL in database for reference
                session = self.db.get_session()
                try:
                    sw = session.query(ServerWebhook).filter_by(server_id=ctx.guild.id).first()
                    if not sw:
                        sw = ServerWebhook(
                            server_id=ctx.guild.id,
                            channel_id=ctx.channel.id,
                            webhook_id=0,  # Not used anymore
                            webhook_url='',
                            avatar_url=url
                        )
                        session.add(sw)
                    else:
                        sw.avatar_url = url
                    session.commit()
                except Exception:
                    session.rollback()
                finally:
                    session.close()
                
                embed = success_embed(
                    '🖼️ Bot Avatar Updated',
                    f'The bot\'s profile picture has been changed **in {ctx.guild.name}**!\n\n'
                    f'Check the member list or bot profile to see the new avatar.'
                )
                embed.set_thumbnail(url=url)
                await ctx.reply(embed=embed)
                
            except discord.HTTPException as e:
                await ctx.reply(embed=error_embed('Discord Error', f'Discord rejected the avatar change. Try a different image.\n`{e}`'))
            except ValueError as e:
                await ctx.reply(embed=error_embed('Invalid Image', str(e)))
            except Exception as e:
                await ctx.reply(embed=error_embed('Error', f'Failed to update avatar: {e}'))
    
    # ========================
    # BOT BANNER (PER-GUILD PROFILE)
    # ========================
    @commands.command(name='botbanner')
    @bot_profile_required('botavatar')
    async def botbanner(self, ctx, *, url: str = None):
        """🖼️ Change the bot's banner for this server (Bot Profile Access)
        
        Sets a per-server custom banner. The bot's profile banner will
        change for this server only — just like Bleed bot!
        
        Recommended size: 960x540 or 600x240
        
        Usage: ,botbanner <url> or attach an image
        """
        if not url and not ctx.message.attachments:
            return await ctx.reply(embed=error_embed(
                'Missing Image',
                f'Usage: `{config.PREFIX}botbanner <url>` or attach an image\n\n'
                f'This will change the bot\'s **banner** in this server only.\n'
                f'Recommended size: 960×540 or 600×240'
            ))
        
        if ctx.message.attachments:
            url = ctx.message.attachments[0].url
        
        async with ctx.typing():
            try:
                import base64

                banner_bytes, content_type = await _download_profile_image(
                    url,
                    10 * 1024 * 1024,
                )
                
                # Convert to base64 data URI
                b64 = base64.b64encode(banner_bytes).decode('utf-8')
                
                # Detect image format
                image_format = content_type.split('/')[-1]
                if image_format not in ['png', 'jpeg', 'jpg', 'gif', 'webp']:
                    image_format = 'png'
                if image_format == 'jpg':
                    image_format = 'jpeg'
                
                data_uri = f"data:image/{image_format};base64,{b64}"
                
                # Use Discord's Per-Guild Bot Profile API
                # PATCH /guilds/{guild.id}/members/@me with banner field
                route = f'/guilds/{ctx.guild.id}/members/@me'
                
                await self.bot.http.request(
                    discord.http.Route('PATCH', route),
                    json={'banner': data_uri}
                )
                
                # Store URL in database for reference
                session = self.db.get_session()
                try:
                    sw = session.query(ServerWebhook).filter_by(server_id=ctx.guild.id).first()
                    if not sw:
                        sw = ServerWebhook(
                            server_id=ctx.guild.id,
                            channel_id=ctx.channel.id,
                            webhook_id=0,
                            webhook_url='',
                            banner_url=url
                        )
                        session.add(sw)
                    else:
                        sw.banner_url = url
                    session.commit()
                except Exception:
                    session.rollback()
                finally:
                    session.close()
                
                embed = success_embed(
                    '🖼️ Bot Banner Updated',
                    f'The bot\'s banner has been changed **in {ctx.guild.name}**!\n\n'
                    f'Check the bot\'s profile to see the new banner.'
                )
                embed.set_image(url=url)
                await ctx.reply(embed=embed)
                
            except discord.HTTPException as e:
                await ctx.reply(embed=error_embed('Discord Error', f'Discord rejected the banner change. Try a different image.\n`{e}`'))
            except ValueError as e:
                await ctx.reply(embed=error_embed('Invalid Image', str(e)))
            except Exception as e:
                await ctx.reply(embed=error_embed('Error', f'Failed to update banner: {e}'))


    # ========================
    # RESET BOT IDENTITY (PER-GUILD PROFILE)
    # ========================
    @commands.command(name='botreset', aliases=['resetbot', 'botdefault'])
    @bot_profile_required('botavatar')
    async def botreset(self, ctx):
        """🔄 Reset the bot's custom avatar and banner for this server
        
        Reverts the bot back to its default appearance in this server.
        Clears both the custom avatar and banner.
        """
        async with ctx.typing():
            try:
                # Use Discord's Per-Guild Bot Profile API to reset avatar
                # PATCH /guilds/{guild.id}/members/@me with avatar: null
                route = f'/guilds/{ctx.guild.id}/members/@me'
                
                await self.bot.http.request(
                    discord.http.Route('PATCH', route),
                    json={'avatar': None, 'banner': None}
                )
                
                # Clear from database
                session = self.db.get_session()
                try:
                    sw = session.query(ServerWebhook).filter_by(server_id=ctx.guild.id).first()
                    if sw:
                        sw.avatar_url = None
                        sw.banner_url = None
                        session.commit()
                except Exception:
                    session.rollback()
                finally:
                    session.close()
                
                await ctx.reply(embed=success_embed(
                    '🔄 Bot Profile Reset',
                    f'The bot\'s custom avatar and banner have been removed for **{ctx.guild.name}**.\n'
                    f'The bot will now use its default appearance.'
                ))
                
            except discord.HTTPException as e:
                await ctx.reply(embed=error_embed('Discord Error', f'Failed to reset avatar.\n`{e}`'))
            except Exception as e:
                await ctx.reply(embed=error_embed('Error', f'Failed to reset: {e}'))

    
    # ========================
    # GHOST PING LISTENER
    # ========================
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Detect ghost pings when messages with mentions are deleted"""
        if message.author.bot or not message.guild:
            return
        
        # Check if ghost ping detection is enabled for this server
        session = self.db.get_session()
        try:
            gp_config = session.query(GhostPingConfig).filter_by(
                server_id=message.guild.id
            ).first()
            
            if not gp_config or not gp_config.enabled:
                return
        finally:
            session.close()
        
        # Check if the deleted message had mentions
        mentioned = []
        if message.mentions:
            mentioned = [m for m in message.mentions if not m.bot and m.id != message.author.id]
        if message.role_mentions:
            mentioned.extend(message.role_mentions)
        
        if not mentioned:
            return
        
        # Re-post the ghost ping detection
        mentions_str = ', '.join([m.mention for m in mentioned[:5]])
        
        embed = discord.Embed(
            title="👻 Ghost Ping Detected!",
            description=(
                f"**Pinger:** {message.author.mention}\n"
                f"**Pinged:** {mentions_str}\n"
                f"**Message:** {message.content[:200] if message.content else '*No text content*'}\n"
                f"**Channel:** {message.channel.mention}"
            ),
            color=0xff6b6b,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="👻 Ghost Ping Detector • xiel Premium")
        embed.set_thumbnail(url=message.author.display_avatar.url if message.author.display_avatar else None)
        
        await message.channel.send(
            content=f"⚠️ {mentions_str} — you were ghost pinged!",
            embed=embed
        )

    # ========================
    # SNAPSHOT SERVER COMMAND
    # ========================
    @commands.command(name='snapshot-server', aliases=['snapshot', 'backup-server'])
    @premium_required('snapshot-server')
    @commands.has_permissions(administrator=True)
    async def snapshot_server(self, ctx):
        """📸 Snapshot your server config — channels, roles, settings (Premium)

        Saves a JSON backup to data/backups/
        """
        guild = ctx.guild
        status_embed = discord.Embed(
            title=f"{config.EMOJIS.get('loading', '')} Snapshotting Server…",
            description="Scanning server configuration…",
            color=config.COLORS['primary']
        )
        msg = await ctx.reply(embed=status_embed)

        # Build snapshot data
        snapshot = {
            'guild_name': guild.name,
            'guild_id': guild.id,
            'icon_url': str(guild.icon.url) if guild.icon else None,
            'verification_level': str(guild.verification_level),
            'created_at': datetime.now(UTC).isoformat(),
            'roles': [],
            'categories': [],
            'channels': [],
        }

        # ─── Roles ───
        for role in sorted(guild.roles, key=lambda r: r.position):
            if role.is_default():
                continue
            snapshot['roles'].append({
                'name': role.name,
                'color': role.color.value,
                'permissions': role.permissions.value,
                'position': role.position,
                'hoist': role.hoist,
                'mentionable': role.mentionable,
            })

        # ─── Categories ───
        for cat in guild.categories:
            snapshot['categories'].append({
                'name': cat.name,
                'position': cat.position,
                'id': cat.id,
            })

        # ─── Channels ───
        for ch in guild.channels:
            if isinstance(ch, discord.CategoryChannel):
                continue  # already handled
            ch_data = {
                'name': ch.name,
                'type': str(ch.type),
                'position': ch.position,
                'category_name': ch.category.name if ch.category else None,
            }
            if isinstance(ch, discord.TextChannel):
                ch_data['topic'] = ch.topic
                ch_data['nsfw'] = ch.nsfw
                ch_data['slowmode'] = ch.slowmode_delay
            snapshot['channels'].append(ch_data)

        # Save to file
        backup_dir = os.path.join('data', 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
        filename = f"{guild.id}_{timestamp}.json"
        filepath = os.path.join(backup_dir, filename)

        import json as _json
        with open(filepath, 'w') as f:
            _json.dump(snapshot, f, indent=2)

        done_embed = discord.Embed(
            title=f"{config.EMOJIS.get('success', '')} Snapshot Complete!",
            description=(
                f"**Server:** {guild.name}\n"
                f"**Roles:** {len(snapshot['roles'])}\n"
                f"**Categories:** {len(snapshot['categories'])}\n"
                f"**Channels:** {len(snapshot['channels'])}\n\n"
                f"**File:** `{filename}`"
            ),
            color=config.COLORS['success']
        )
        done_embed.set_footer(text="xiel Premium • Server Snapshot")
        await msg.edit(embed=done_embed)

    # ========================
    # RESTORE SERVER COMMAND
    # ========================
    @commands.command(name='restore-server', aliases=['restore'])
    @premium_required('restore-server')
    @commands.has_permissions(administrator=True)
    async def restore_server(self, ctx):
        """♻️ Restore server from the latest snapshot (Premium)

        Recreates roles and channels from a previous backup.
        """
        import json as _json, glob

        backup_dir = os.path.join('data', 'backups')
        pattern = os.path.join(backup_dir, f"{ctx.guild.id}_*.json")
        files = sorted(glob.glob(pattern), reverse=True)

        if not files:
            return await ctx.reply(embed=error_embed(
                'No Backup Found',
                f'No snapshots exist for this server.\nUse `{config.PREFIX}snapshot-server` first.'
            ))

        latest_file = files[0]
        with open(latest_file, 'r') as f:
            snapshot = _json.load(f)

        # Confirmation prompt
        confirm_embed = discord.Embed(
            title=f"{config.EMOJIS.get('warning', '')} Restore Confirmation",
            description=(
                f"**Restoring from:** `{os.path.basename(latest_file)}`\n"
                f"**Roles:** {len(snapshot.get('roles', []))}\n"
                f"**Categories:** {len(snapshot.get('categories', []))}\n"
                f"**Channels:** {len(snapshot.get('channels', []))}\n\n"
                f"⚠️ This will **create** missing roles and channels.\n"
                f"Existing items will **not** be deleted.\n\n"
                f"React with ✅ within 30s to proceed."
            ),
            color=config.COLORS['warning'] if 'warning' in config.COLORS else 0xfbbf24
        )
        confirm_msg = await ctx.reply(embed=confirm_embed)
        await confirm_msg.add_reaction("✅")

        def check(reaction, user):
            return (
                user.id == ctx.author.id
                and str(reaction.emoji) == "✅"
                and reaction.message.id == confirm_msg.id
            )

        try:
            await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            return await confirm_msg.edit(embed=error_embed("Cancelled", "Restore timed out — no changes made."))

        # ─── Start Restore ───
        progress = await ctx.send(embed=discord.Embed(
            title=f"{config.EMOJIS.get('loading', '')} Restoring…",
            description="Creating roles…",
            color=config.COLORS['primary']
        ))

        created_roles = 0
        created_channels = 0
        errors = []

        # Restore roles
        existing_role_names = {r.name.lower() for r in ctx.guild.roles}
        for role_data in snapshot.get('roles', []):
            if role_data['name'].lower() in existing_role_names:
                continue
            try:
                await ctx.guild.create_role(
                    name=role_data['name'],
                    color=discord.Color(role_data['color']),
                    permissions=discord.Permissions(role_data['permissions']),
                    hoist=role_data.get('hoist', False),
                    mentionable=role_data.get('mentionable', False),
                    reason="Server restore from snapshot"
                )
                created_roles += 1
            except Exception as e:
                errors.append(f"Role `{role_data['name']}`: {e}")

        # Update progress
        await progress.edit(embed=discord.Embed(
            title=f"{config.EMOJIS.get('loading', '')} Restoring…",
            description=f"Roles done ({created_roles} created). Creating channels…",
            color=config.COLORS['primary']
        ))

        # Restore categories first
        existing_cat_names = {c.name.lower() for c in ctx.guild.categories}
        category_map = {}  # name -> category object
        for cat_data in snapshot.get('categories', []):
            if cat_data['name'].lower() in existing_cat_names:
                # Map to existing
                for c in ctx.guild.categories:
                    if c.name.lower() == cat_data['name'].lower():
                        category_map[cat_data['name']] = c
                        break
                continue
            try:
                new_cat = await ctx.guild.create_category(
                    name=cat_data['name'],
                    reason="Server restore from snapshot"
                )
                category_map[cat_data['name']] = new_cat
                created_channels += 1
            except Exception as e:
                errors.append(f"Category `{cat_data['name']}`: {e}")

        # Restore channels
        existing_ch_names = {c.name.lower() for c in ctx.guild.channels}
        for ch_data in snapshot.get('channels', []):
            if ch_data['name'].lower() in existing_ch_names:
                continue
            try:
                cat_obj = None
                if ch_data.get('category_name'):
                    cat_obj = category_map.get(ch_data['category_name'])
                    if not cat_obj:
                        for c in ctx.guild.categories:
                            if c.name.lower() == ch_data['category_name'].lower():
                                cat_obj = c
                                break

                if ch_data['type'] == 'voice':
                    await ctx.guild.create_voice_channel(
                        name=ch_data['name'],
                        category=cat_obj,
                        reason="Server restore from snapshot"
                    )
                else:
                    await ctx.guild.create_text_channel(
                        name=ch_data['name'],
                        category=cat_obj,
                        topic=ch_data.get('topic'),
                        nsfw=ch_data.get('nsfw', False),
                        slowmode_delay=ch_data.get('slowmode', 0),
                        reason="Server restore from snapshot"
                    )
                created_channels += 1
            except Exception as e:
                errors.append(f"Channel `{ch_data['name']}`: {e}")

        # Final embed
        result_desc = (
            f"**Roles created:** {created_roles}\n"
            f"**Channels created:** {created_channels}\n"
        )
        if errors:
            result_desc += f"\n**Errors:** {len(errors)}\n" + "\n".join(errors[:5])

        await progress.edit(embed=discord.Embed(
            title=f"{config.EMOJIS.get('success', '')} Restore Complete!",
            description=result_desc,
            color=config.COLORS['success']
        ))


async def setup(bot):
    await bot.add_cog(PremiumCommands(bot))
