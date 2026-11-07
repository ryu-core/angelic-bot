import discord
from discord.ext import commands, tasks
import asyncio
import random
import re
import io
import os
import time
import traceback
from datetime import datetime, UTC
from utils.embeds import success_embed, error_embed
import config
import mysql.connector

DISCORD_EPOCH_MS = 1420070400000

LEGACY_GIVEAWAY_EMOJIS = {'ðŸŽ‰'}
GIVEAWAY_EMOJI = "\N{PARTY POPPER}"

GIVEAWAY_EMOJI = '🎉'

GIVEAWAY_EMOJI = "\N{PARTY POPPER}"


def _get_mysql_connection():
    """Create a MySQL connection using environment variables."""
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', ''),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER', ''),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DATABASE', ''),
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci'
    )


class Giveaways(commands.Cog):
    """Giveaway system for hosting server giveaways"""
    
    def __init__(self, bot):
        self.bot = bot
        self._end_tasks = {}
        self._ending_giveaways = set()
        self._memory_entries = {}
        self._active_giveaways = {}
        asyncio.create_task(self.init_db())
        asyncio.create_task(self._schedule_existing_giveaways())
        self.check_giveaways.start()
    
    async def init_db(self):
        """Initialize giveaway table in MySQL"""
        def _init():
            conn = _get_mysql_connection()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS giveaways (
                        message_id BIGINT PRIMARY KEY,
                        channel_id BIGINT,
                        guild_id BIGINT,
                        host_id BIGINT,
                        prize TEXT,
                        winners INT,
                        end_time BIGINT,
                        ended TINYINT DEFAULT 0,
                        image_url TEXT,
                        required_daily_messages INT DEFAULT 0,
                        required_weekly_messages INT DEFAULT 0,
                        required_monthly_messages INT DEFAULT 0,
                        required_total_messages INT DEFAULT 0,
                        requirement_bypass_role_id BIGINT
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS giveaway_entries (
                        message_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        guild_id BIGINT,
                        entered_at BIGINT,
                        PRIMARY KEY (message_id, user_id),
                        INDEX idx_giveaway_entries_message (message_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                ''')
                # Add missing columns if the table already existed with an old schema
                migrations = [
                    "ALTER TABLE giveaways ADD COLUMN end_time BIGINT",
                    "ALTER TABLE giveaways ADD COLUMN ended TINYINT DEFAULT 0",
                    "ALTER TABLE giveaways ADD COLUMN image_url TEXT",
                    "ALTER TABLE giveaways ADD COLUMN channel_id BIGINT",
                    "ALTER TABLE giveaways ADD COLUMN guild_id BIGINT",
                    "ALTER TABLE giveaways ADD COLUMN host_id BIGINT",
                    "ALTER TABLE giveaways ADD COLUMN winners INT",
                    "ALTER TABLE giveaways ADD COLUMN required_daily_messages INT DEFAULT 0",
                    "ALTER TABLE giveaways ADD COLUMN required_weekly_messages INT DEFAULT 0",
                    "ALTER TABLE giveaways ADD COLUMN required_monthly_messages INT DEFAULT 0",
                    "ALTER TABLE giveaways ADD COLUMN required_total_messages INT DEFAULT 0",
                    "ALTER TABLE giveaways ADD COLUMN requirement_bypass_role_id BIGINT",
                    "ALTER TABLE giveaway_entries ADD COLUMN guild_id BIGINT",
                    "ALTER TABLE giveaway_entries ADD COLUMN entered_at BIGINT",
                ]
                for sql in migrations:
                    try:
                        cursor.execute(sql)
                    except Exception:
                        pass  # Column already exists — safe to ignore
                conn.commit()
            finally:
                cursor.close()
                conn.close()
        await asyncio.to_thread(_init)
    
    def _sync_execute(self, query, params=None, fetchone=False, fetchall=False):
        """Execute a MySQL query synchronously and return results."""
        conn = _get_mysql_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params)
            result = None
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            conn.commit()
            return result
        finally:
            cursor.close()
            conn.close()

    async def _execute(self, query, params=None, fetchone=False, fetchall=False):
        """Execute a MySQL query asynchronously."""
        return await asyncio.to_thread(
            self._sync_execute, query, params, fetchone, fetchall
        )

    def _sync_execute_rowcount(self, query, params=None):
        """Execute a MySQL write query and return affected row count."""
        conn = _get_mysql_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rowcount = cursor.rowcount
            conn.commit()
            return rowcount
        finally:
            cursor.close()
            conn.close()

    async def _execute_rowcount(self, query, params=None):
        return await asyncio.to_thread(self._sync_execute_rowcount, query, params)

    def _is_giveaway_emoji(self, emoji):
        emoji_text = str(emoji)
        return emoji_text == GIVEAWAY_EMOJI or emoji_text in LEGACY_GIVEAWAY_EMOJIS

    async def _get_channel(self, channel_id):
        channel = self.bot.get_channel(channel_id)
        if channel:
            return channel
        try:
            return await self.bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def _record_entry(self, message_id, guild_id, user_id):
        import time
        await self._execute(
            '''INSERT IGNORE INTO giveaway_entries (message_id, user_id, guild_id, entered_at)
               VALUES (%s, %s, %s, %s)''',
            (message_id, user_id, guild_id, int(time.time()))
        )

    async def _remove_entry(self, message_id, user_id):
        await self._execute(
            'DELETE FROM giveaway_entries WHERE message_id = %s AND user_id = %s',
            (message_id, user_id)
        )

    async def _get_saved_entry_ids(self, message_id):
        try:
            rows = await asyncio.wait_for(
                self._execute(
                    'SELECT user_id FROM giveaway_entries WHERE message_id = %s',
                    (message_id,), fetchall=True
                ),
                timeout=3
            )
        except Exception as e:
            print(f"Failed to load saved giveaway entries for {message_id}: {e}")
            traceback.print_exc()
            return set()
        return {int(row['user_id']) for row in rows or []}

    async def _backfill_entries_from_reaction(self, message, giveaway):
        reaction = next(
            (reaction for reaction in message.reactions if self._is_giveaway_emoji(reaction.emoji)),
            None
        )
        if not reaction:
            return None

        user_ids = set()
        async for user in reaction.users(limit=None):
            if user.bot or user.id == giveaway['host_id']:
                continue
            user_ids.add(user.id)
            try:
                await asyncio.wait_for(
                    self._record_entry(message.id, giveaway['guild_id'], user.id),
                    timeout=1
                )
            except Exception:
                pass
        return user_ids

    async def _collect_entry_ids(self, message, giveaway):
        memory_ids = set(self._memory_entries.get(int(message.id), set()))
        try:
            reaction_ids = await self._backfill_entries_from_reaction(message, giveaway)
        except Exception as e:
            print(f"Failed to backfill giveaway reaction entries for {message.id}: {e}")
            traceback.print_exc()
            reaction_ids = None
        saved_ids = await self._get_saved_entry_ids(message.id)
        entry_ids = set()
        entry_ids.update(saved_ids)
        entry_ids.update(memory_ids)
        if reaction_ids is not None:
            entry_ids.update(reaction_ids)
        entry_ids.discard(int(giveaway['host_id']))
        if self.bot.user:
            entry_ids.discard(self.bot.user.id)
        print(
            f"Giveaway entries collected for {message.id}: "
            f"memory={sorted(memory_ids)} "
            f"reaction={sorted(reaction_ids) if reaction_ids is not None else None} "
            f"saved={sorted(saved_ids)} "
            f"final={sorted(entry_ids)}"
        )
        return list(entry_ids)

    def _winner_mentions(self, winner_ids):
        return ", ".join(f"<@{user_id}>" for user_id in winner_ids)

    def _message_requirements(self, giveaway):
        return {
            "daily": int(giveaway.get("required_daily_messages") or 0),
            "weekly": int(giveaway.get("required_weekly_messages") or 0),
            "monthly": int(giveaway.get("required_monthly_messages") or 0),
            "total": int(giveaway.get("required_total_messages") or 0),
        }

    def _has_message_requirements(self, giveaway):
        return any(value > 0 for value in self._message_requirements(giveaway).values())

    def _format_message_requirements(self, giveaway):
        requirements = self._message_requirements(giveaway)
        labels = [f"{period}: `{amount:,}`" for period, amount in requirements.items() if amount > 0]
        bypass_role_id = giveaway.get("requirement_bypass_role_id")
        if bypass_role_id:
            labels.append(f"bypass: <@&{int(bypass_role_id)}>")
        return "\n".join(labels) if labels else "none"

    async def _message_counts_for_users(self, guild_id, user_ids):
        stats_cog = self.bot.get_cog("MessageStats")
        if stats_cog and hasattr(stats_cog, "get_counts_for_users"):
            return await stats_cog.get_counts_for_users(guild_id, user_ids)

        result = {int(user_id): {"daily": 0, "weekly": 0, "monthly": 0, "total": 0} for user_id in user_ids}
        if not user_ids:
            return result

        now = datetime.now(UTC)
        iso = now.isocalendar()
        keys = {
            "daily": now.strftime("%Y-%m-%d"),
            "weekly": f"{iso.year}-W{iso.week:02d}",
            "monthly": now.strftime("%Y-%m"),
            "total": "all",
        }
        placeholders = ",".join(["%s"] * len(user_ids))
        period_clause = " OR ".join(["(period_type = %s AND period_key = %s)" for _ in keys])
        params = [int(guild_id), *[int(user_id) for user_id in user_ids]]
        for period, period_key in keys.items():
            params.extend([period, period_key])
        try:
            rows = await self._execute(
                f"""
                SELECT user_id, period_type, count
                FROM bot_message_counts
                WHERE guild_id = %s
                  AND user_id IN ({placeholders})
                  AND ({period_clause})
                """,
                tuple(params),
                fetchall=True,
            )
        except Exception as e:
            print(f"Failed to load fallback message counts: {e}")
            return result

        for row in rows or []:
            user_id = int(row["user_id"])
            period = row["period_type"]
            if user_id in result and period in result[user_id]:
                result[user_id][period] = int(row.get("count") or 0)
        return result

    async def _member_has_bypass_role(self, guild, user_id, role_id):
        if not guild or not role_id:
            return False
        member = guild.get_member(int(user_id))
        if not member:
            try:
                member = await guild.fetch_member(int(user_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return False
        return any(role.id == int(role_id) for role in getattr(member, "roles", []))

    async def _filter_message_requirement_entries(self, guild, entry_ids, giveaway):
        requirements = self._message_requirements(giveaway)
        if not any(amount > 0 for amount in requirements.values()):
            return list(entry_ids)

        counts = await self._message_counts_for_users(giveaway["guild_id"], entry_ids)
        bypass_role_id = giveaway.get("requirement_bypass_role_id")
        eligible = []
        for user_id in entry_ids:
            if await self._member_has_bypass_role(guild, user_id, bypass_role_id):
                eligible.append(user_id)
                continue
            user_counts = counts.get(int(user_id), {})
            if all(int(user_counts.get(period, 0)) >= amount for period, amount in requirements.items() if amount > 0):
                eligible.append(user_id)
        return eligible

    async def _edit_giveaway_message(self, message, embed):
        try:
            await message.edit(embed=embed)
        except discord.HTTPException as e:
            print(f"Failed to edit giveaway message {message.id}: {e}")

    async def _send_winner_announcement(self, channel, message, winner_mentions, prize):
        content = f"{GIVEAWAY_EMOJI} Congratulations {winner_mentions}! You won **{prize}**!"
        try:
            await channel.send(content, reference=message, mention_author=False)
        except discord.HTTPException:
            await channel.send(content)

    async def _send_no_winner_announcement(self, channel, message, prize):
        content = f"{GIVEAWAY_EMOJI} Giveaway ended for **{prize}**, but there were no valid entries."
        try:
            await channel.send(content, reference=message, mention_author=False)
        except discord.HTTPException:
            await channel.send(content)

    def _schedule_giveaway_end(self, message_id, end_time, giveaway_snapshot=None):
        existing = self._end_tasks.pop(int(message_id), None)
        if existing and not existing.done():
            existing.cancel()

        print(f"Giveaway timer armed: message_id={int(message_id)} end_time={int(end_time)}")
        self._end_tasks[int(message_id)] = asyncio.create_task(
            self._end_giveaway_later(int(message_id), int(end_time), giveaway_snapshot)
        )

    async def _end_giveaway_later(self, message_id, end_time, giveaway_snapshot=None):
        try:
            await self.bot.wait_until_ready()
            delay = max(0, end_time - int(time.time()))
            if delay:
                await asyncio.sleep(delay)
            await self.end_giveaway(
                message_id,
                force=giveaway_snapshot is not None,
                giveaway_override=giveaway_snapshot
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Scheduled giveaway end failed for {message_id}: {e}")
            traceback.print_exc()
        finally:
            task = self._end_tasks.get(message_id)
            if task is asyncio.current_task():
                self._end_tasks.pop(message_id, None)

    async def _schedule_existing_giveaways(self):
        try:
            await self.bot.wait_until_ready()
            rows = await self._execute(
                'SELECT message_id, end_time FROM giveaways WHERE ended = 0',
                fetchall=True
            )
            for row in rows or []:
                self._schedule_giveaway_end(row['message_id'], row['end_time'])
        except Exception as e:
            print(f"Failed to schedule existing giveaways: {e}")
            traceback.print_exc()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not payload.guild_id or not self._is_giveaway_emoji(payload.emoji):
            return
        if self.bot.user and payload.user_id == self.bot.user.id:
            return
        if payload.member and payload.member.bot:
            return

        giveaway = self._active_giveaways.get(int(payload.message_id))
        if not giveaway:
            giveaway = await self._execute(
                'SELECT host_id FROM giveaways WHERE message_id = %s AND guild_id = %s AND ended = 0',
                (payload.message_id, payload.guild_id), fetchone=True
            )
        if not giveaway or payload.user_id == int(giveaway['host_id']):
            return

        self._memory_entries.setdefault(int(payload.message_id), set()).add(int(payload.user_id))
        await self._record_entry(payload.message_id, payload.guild_id, payload.user_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if not payload.guild_id or not self._is_giveaway_emoji(payload.emoji):
            return

        giveaway = self._active_giveaways.get(int(payload.message_id))
        if not giveaway:
            giveaway = await self._execute(
                'SELECT message_id FROM giveaways WHERE message_id = %s AND guild_id = %s AND ended = 0',
                (payload.message_id, payload.guild_id), fetchone=True
            )
        if giveaway:
            entries = self._memory_entries.get(int(payload.message_id))
            if entries is not None:
                entries.discard(int(payload.user_id))
            await self._remove_entry(payload.message_id, payload.user_id)
    
    def parse_duration(self, duration_str):
        """Parse duration string like '1h', '1hr', '1hour', '30m', '30min' to seconds"""
        if not duration_str:
            return None
            
        # Normalize common variations
        duration_str = duration_str.lower().strip()
        duration_str = duration_str.replace('hours', 'h')
        duration_str = duration_str.replace('hour', 'h')
        duration_str = duration_str.replace('hr', 'h')
        duration_str = duration_str.replace('hrs', 'h')
        duration_str = duration_str.replace('minutes', 'm')
        duration_str = duration_str.replace('minute', 'm')
        duration_str = duration_str.replace('min', 'm')
        duration_str = duration_str.replace('mins', 'm')
        duration_str = duration_str.replace('seconds', 's')
        duration_str = duration_str.replace('second', 's')
        duration_str = duration_str.replace('sec', 's')
        duration_str = duration_str.replace('secs', 's')
        duration_str = duration_str.replace('days', 'd')
        duration_str = duration_str.replace('day', 'd')
        
        # Strict validation - must match pattern exactly
        pattern = r'^(\d+[smhd])+$'
        if not re.fullmatch(pattern, duration_str):
            return None
        
        # Extract all time components
        component_pattern = r'(\d+)([smhd])'
        matches = re.findall(component_pattern, duration_str)
        
        if not matches:
            return None
        
        total_seconds = 0
        for amount, unit in matches:
            amount = int(amount)
            if unit == 's':
                total_seconds += amount
            elif unit == 'm':
                total_seconds += amount * 60
            elif unit == 'h':
                total_seconds += amount * 3600
            elif unit == 'd':
                total_seconds += amount * 86400
        
        return total_seconds

    def _message_id_to_timestamp_ms(self, message_id):
        """Convert a Discord snowflake ID to its creation timestamp in milliseconds."""
        return (int(message_id) >> 22) + DISCORD_EPOCH_MS

    def _format_delay(self, total_seconds):
        if total_seconds >= 3600:
            hours = int(total_seconds // 3600)
            remainder_seconds = total_seconds % 3600
            minutes = int(remainder_seconds // 60)
            seconds = remainder_seconds % 60
            return f"{hours}h {minutes}m {seconds:.3f}s"
        if total_seconds >= 60:
            minutes = int(total_seconds // 60)
            seconds = total_seconds % 60
            return f"{minutes}m {seconds:.3f}s"
        return f"{total_seconds:.3f} seconds"
    
    @commands.group(name='giveaway', aliases=['gw'], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def giveaway(self, ctx):
        """Bleed-style giveaway command group."""
        await ctx.reply(embed=error_embed(
            'Invalid Usage',
            f'**Usage:** `{config.PREFIX}giveaway start <duration> <winners> <prize>`\n'
            f'**Aliases:** `{config.PREFIX}gw start`, `{config.PREFIX}gstart`\n'
            f'**Other:** `end`, `reroll`, `cancel`, `edit`, `delay`'
        ))

    @commands.command(name='gstart', aliases=['gwstart'])
    @commands.has_permissions(manage_guild=True)
    async def gstart(self, ctx, duration: str = None, winners: int = None, *, prize: str = None):
        await self._start_giveaway(ctx, duration, winners, prize)

    @giveaway.command(name='start', aliases=['create'])
    @commands.has_permissions(manage_guild=True)
    async def giveaway_start(self, ctx, duration: str = None, winners: int = None, *, prize: str = None):
        await self._start_giveaway(ctx, duration, winners, prize)

    async def _start_giveaway(self, ctx, duration: str = None, winners: int = None, prize: str = None):
        """Start a giveaway
        
        Usage: ,gstart <duration> <winners> <prize> [image_url]
        Example: ,gstart 1h 1 Discord Nitro
        Example with image: ,gstart 2h 3 Robux https://i.imgur.com/image.png
        Or attach an image to your command message!
        
        Duration formats: 30s, 5m, 1h, 2d
        """
        image = None

        # Check for image attachment first
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.content_type and attachment.content_type.startswith('image/'):
                image = attachment.url
        
        # Check if prize contains an image URL
        if prize and image is None:
            parts = prize.rsplit(' ', 1)
            if len(parts) == 2 and (parts[1].startswith('http://') or parts[1].startswith('https://')):
                prize = parts[0]
                image = parts[1]
        
        if not duration or not winners or not prize:
            return await ctx.reply(embed=error_embed(
                'Invalid Usage',
                f'**Usage:** `{config.PREFIX}gstart <duration> <winners> <prize> [image]`\n'
                f'**Example:** `{config.PREFIX}gstart 1h 1 Discord Nitro`\n'
                f'**With URL:** `{config.PREFIX}gstart 2h 3 Robux https://i.imgur.com/image.png`\n'
                f'**With attachment:** Upload an image with your command!\n\n'
                f'**Duration:** `30s`, `5m`, `1h`, `2d`'
            ))
        
        # Parse duration
        seconds = self.parse_duration(duration)
        if not seconds or seconds < 10:
            return await ctx.reply(embed=error_embed(
                'Invalid Duration',
                'Duration must be at least 10 seconds.\n**Examples:** `30s`, `5m`, `1h`, `2d`'
            ))
        
        if winners < 1 or winners > 20:
            return await ctx.reply(embed=error_embed(
                'Invalid Winners',
                'Winner count must be between 1 and 20.'
            ))
        
        # Calculate end time using Unix timestamp (always UTC-based)
        current_timestamp = int(time.time())
        end_time = current_timestamp + seconds
        
        
        # Handle image attachment - download and re-upload to prevent expiration
        image_file = None
        if ctx.message.attachments and image:
            try:
                attachment = ctx.message.attachments[0]
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    image_bytes = await attachment.read()
                    image_file = discord.File(
                        fp=io.BytesIO(image_bytes),
                        filename=attachment.filename
                    )
            except Exception as e:
                print(f"Error handling image: {e}")
                image_file = None
        
        # Create giveaway embed - clean design
        embed = discord.Embed(
            title=f"{prize} {GIVEAWAY_EMOJI}",
            description=f"React with {GIVEAWAY_EMOJI} to enter the giveaway.",
            color=0xf39c12
        )
        
        # Discord automatically shows times in each user's local timezone
        embed.add_field(
            name="⏰ Ends In",
            value=f"<t:{end_time}:R>\n<t:{end_time}:F>",
            inline=False
        )
        embed.add_field(name="Winners", value=str(winners), inline=True)
        embed.add_field(name="Hosted by", value=ctx.author.mention, inline=True)
        
        # Add image if provided (as URL or file) - with validation
        if image_file:
            embed.set_image(url=f"attachment://{image_file.filename}")
        elif image and isinstance(image, str) and (image.startswith('http://') or image.startswith('https://')):
            embed.set_image(url=image)
        
        embed.set_footer(text=f"Giveaway")
        
        # Send giveaway message with file if available
        if image_file:
            giveaway_msg = await ctx.send(file=image_file, embed=embed)
        else:
            giveaway_msg = await ctx.send(embed=embed)
        
        await giveaway_msg.add_reaction(GIVEAWAY_EMOJI)
        self._memory_entries[giveaway_msg.id] = set()

        giveaway_snapshot = {
            'message_id': giveaway_msg.id,
            'channel_id': ctx.channel.id,
            'guild_id': ctx.guild.id,
            'host_id': ctx.author.id,
            'prize': prize,
            'winners': winners,
            'end_time': end_time,
            'ended': 0,
            'image_url': None,
            'required_daily_messages': 0,
            'required_weekly_messages': 0,
            'required_monthly_messages': 0,
            'required_total_messages': 0,
            'requirement_bypass_role_id': None
        }
        self._active_giveaways[giveaway_msg.id] = giveaway_snapshot
        self._schedule_giveaway_end(giveaway_msg.id, end_time, giveaway_snapshot)
        
        # Delete command message
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass  # Bot doesn't have permission to delete messages
        except Exception as e:
            print(f"Error deleting command message: {e}")
        
        # Save to database
        # Get the final image URL (either from file attachment or direct URL)
        final_image_url = None
        if image_file:
            # The image was uploaded, get its URL from the sent message
            if giveaway_msg.embeds and giveaway_msg.embeds[0].image:
                final_image_url = giveaway_msg.embeds[0].image.url
        elif image and isinstance(image, str) and (image.startswith('http://') or image.startswith('https://')):
            final_image_url = image
        giveaway_snapshot['image_url'] = final_image_url
        
        try:
            await asyncio.wait_for(
                self._execute(
                    '''INSERT INTO giveaways (
                           message_id, channel_id, guild_id, host_id, prize, winners, end_time, image_url,
                           required_daily_messages, required_weekly_messages, required_monthly_messages,
                           required_total_messages, requirement_bypass_role_id
                       )
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                    (
                        giveaway_msg.id, ctx.channel.id, ctx.guild.id, ctx.author.id, prize, winners,
                        end_time, final_image_url, 0, 0, 0, 0, None
                    )
                ),
                timeout=5
            )
        except Exception as e:
            print(f"Giveaway DB save skipped for {giveaway_msg.id}: {e}")
            traceback.print_exc()
        
        # Send confirmation with actual duration - improved precision
        duration_parts = []
        remaining = seconds
        
        if remaining >= 86400:
            days = remaining // 86400
            duration_parts.append(f"{days} day(s)")
            remaining %= 86400
        if remaining >= 3600:
            hours = remaining // 3600
            duration_parts.append(f"{hours} hour(s)")
            remaining %= 3600
        if remaining >= 60:
            minutes = remaining // 60
            duration_parts.append(f"{minutes} minute(s)")
            remaining %= 60
        if remaining > 0 or not duration_parts:
            duration_parts.append(f"{remaining} second(s)")
        
        duration_text = " ".join(duration_parts)
        
        conf = await ctx.send(embed=success_embed(
            'Giveaway Started!',
            f'{GIVEAWAY_EMOJI} Giveaway for **{prize}** has started!\n'
            f'⏰ Duration: **{duration_text}**\n'
            f'⏰ Ends <t:{end_time}:R>'
        ))
        await conf.delete(delay=10)
    
    @commands.command(name='gend')
    @commands.has_permissions(manage_guild=True)
    async def gend(self, ctx, message_id: int = None):
        """End a giveaway early
        
        Usage: ,gend <message_id>
        """
        if not message_id:
            return await ctx.reply(embed=error_embed(
                'Missing Message ID',
                f'**Usage:** `{config.PREFIX}gend <message_id>`\n'
                f'Right-click the giveaway message and copy its ID.'
            ))
        
        # Check if giveaway exists
        giveaway = await self._execute(
            'SELECT * FROM giveaways WHERE message_id = %s AND guild_id = %s',
            (message_id, ctx.guild.id), fetchone=True
        )
        
        if not giveaway:
            return await ctx.reply(embed=error_embed(
                'Giveaway Not Found',
                'No active giveaway found with that message ID.'
            ))
        
        # End the giveaway
        await self.end_giveaway(message_id, force=True)
        self._end_tasks.pop(int(message_id), None)
        await ctx.reply(embed=success_embed('Giveaway Ended', '🎉 Giveaway has been ended!'))

    @giveaway.command(name='end')
    @commands.has_permissions(manage_guild=True)
    async def giveaway_end(self, ctx, message_id: int = None):
        await ctx.invoke(self.gend, message_id=message_id)
    
    @commands.command(name='gcancel')
    @commands.has_permissions(manage_guild=True)
    async def gcancel(self, ctx, message_id: int = None):
        """Cancel a giveaway without picking winners
        
        Usage: ,gcancel <message_id>
        """
        if not message_id:
            return await ctx.reply(embed=error_embed(
                'Missing Message ID',
                f'**Usage:** `{config.PREFIX}gcancel <message_id>`\n'
                f'Right-click the giveaway message and copy its ID.'
            ))
        
        # Check if giveaway exists
        giveaway = await self._execute(
            'SELECT * FROM giveaways WHERE message_id = %s AND guild_id = %s AND ended = 0',
            (message_id, ctx.guild.id), fetchone=True
        )
        
        if not giveaway:
            return await ctx.reply(embed=error_embed(
                'Giveaway Not Found',
                'No active giveaway found with that message ID.'
            ))
        
        # Get giveaway message
        channel = await self._get_channel(giveaway['channel_id'])
        if not channel:
            return await ctx.reply(embed=error_embed('Error', 'Giveaway channel not found.'))
        
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.reply(embed=error_embed('Error', 'Giveaway message not found.'))
        except discord.HTTPException as e:
            return await ctx.reply(embed=error_embed('Error', f'Failed to fetch message: {str(e)}'))
        
        # Update database - mark as ended
        await self._execute('UPDATE giveaways SET ended = 1 WHERE message_id = %s', (message_id,))
        task = self._end_tasks.pop(int(message_id), None)
        if task and not task.done():
            task.cancel()
        self._active_giveaways.pop(int(message_id), None)
        self._memory_entries.pop(int(message_id), None)
        await self._execute('DELETE FROM giveaway_entries WHERE message_id = %s', (message_id,))
        
        # Update embed to show cancellation
        embed = discord.Embed(
            title="Giveaway Cancelled",
            description=f"**Prize:** {giveaway['prize']}\n\nThis giveaway was cancelled by {ctx.author.mention}.",
            color=0xe74c3c
        )
        
        # Re-add image if it existed
        if giveaway['image_url']:
            embed.set_image(url=giveaway['image_url'])
        
        embed.set_footer(text="Giveaway cancelled")
        
        await message.edit(embed=embed)
        await ctx.reply(embed=success_embed('Giveaway Cancelled', '❌ Giveaway has been cancelled!'))

    @giveaway.command(name='cancel')
    @commands.has_permissions(manage_guild=True)
    async def giveaway_cancel(self, ctx, message_id: int = None):
        await ctx.invoke(self.gcancel, message_id=message_id)
    
    @commands.command(name='gedit')
    @commands.has_permissions(manage_guild=True)
    async def gedit(self, ctx, message_id: int = None, field: str = None, *, value: str = None):
        """Edit a giveaway's details
        
        Usage: ,gedit <message_id> <field> <value>
        Fields: prize, winners, duration
        Examples: 
          ,gedit 123456 prize New Discord Nitro
          ,gedit 123456 winners 3
          ,gedit 123456 duration 2h
        """
        if not message_id or not field or not value:
            return await ctx.reply(embed=error_embed(
                'Missing Arguments',
                f'**Usage:** `{config.PREFIX}gedit <message_id> <field> <value>`\n'
                f'**Fields:** `prize`, `winners`, `duration`\n\n'
                f'**Examples:**\n'
                f'`{config.PREFIX}gedit 123456 prize New Prize`\n'
                f'`{config.PREFIX}gedit 123456 winners 3`\n'
                f'`{config.PREFIX}gedit 123456 duration 2h`'
            ))
        
        field = field.lower()
        if field not in ['prize', 'winners', 'duration']:
            return await ctx.reply(embed=error_embed(
                'Invalid Field',
                f'Field must be one of: `prize`, `winners`, `duration`'
            ))
        
        # Check if giveaway exists
        giveaway = await self._execute(
            'SELECT * FROM giveaways WHERE message_id = %s AND guild_id = %s AND ended = 0',
            (message_id, ctx.guild.id), fetchone=True
        )
        
        if not giveaway:
            return await ctx.reply(embed=error_embed(
                'Giveaway Not Found',
                'No active giveaway found with that message ID.'
            ))
        
        # Get giveaway message
        channel = await self._get_channel(giveaway['channel_id'])
        if not channel:
            return await ctx.reply(embed=error_embed('Error', 'Giveaway channel not found.'))
        
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.reply(embed=error_embed('Error', 'Giveaway message not found.'))
        except discord.HTTPException as e:
            return await ctx.reply(embed=error_embed('Error', f'Failed to fetch message: {str(e)}'))
        
        # Update based on field
        new_prize = giveaway['prize']
        new_winners = giveaway['winners']
        new_end_time = giveaway['end_time']
        
        if field == 'prize':
            new_prize = value
            await self._execute('UPDATE giveaways SET prize = %s WHERE message_id = %s', (new_prize, message_id))
        
        elif field == 'winners':
            try:
                new_winners = int(value)
                if new_winners < 1 or new_winners > 20:
                    return await ctx.reply(embed=error_embed('Invalid Value', 'Winner count must be between 1 and 20.'))
                await self._execute('UPDATE giveaways SET winners = %s WHERE message_id = %s', (new_winners, message_id))
            except ValueError:
                return await ctx.reply(embed=error_embed('Invalid Value', 'Winners must be a number.'))
        
        elif field == 'duration':
            seconds = self.parse_duration(value)
            if not seconds or seconds < 10:
                return await ctx.reply(embed=error_embed(
                    'Invalid Duration',
                    'Duration must be at least 10 seconds.\n**Examples:** `30s`, `5m`, `1h`, `2d`'
                ))
            
            current_timestamp = int(time.time())
            new_end_time = current_timestamp + seconds
            
            await self._execute('UPDATE giveaways SET end_time = %s WHERE message_id = %s', (new_end_time, message_id))
            self._schedule_giveaway_end(message_id, new_end_time)
        
        # Update embed with new information
        embed = discord.Embed(
            title=f"{new_prize} {GIVEAWAY_EMOJI}",
            description=f"React with {GIVEAWAY_EMOJI} to enter the giveaway.",
            color=0xf39c12
        )
        
        embed.add_field(
            name="⏰ Ends In",
            value=f"<t:{new_end_time}:R>\n<t:{new_end_time}:F>",
            inline=False
        )
        embed.add_field(name="Winners", value=str(new_winners), inline=True)
        
        # Get host
        host = self.bot.get_user(giveaway['host_id'])
        if host:
            embed.add_field(name="Hosted by", value=host.mention, inline=True)
        
        # Re-add image if it existed
        if giveaway['image_url']:
            embed.set_image(url=giveaway['image_url'])
        
        embed.set_footer(text=f"Giveaway (Edited by {ctx.author.name})")
        
        await message.edit(embed=embed)
        await ctx.reply(embed=success_embed(
            'Giveaway Updated!',
            f'✅ Updated **{field}** to: **{value}**'
        ))

    @giveaway.command(name='edit')
    @commands.has_permissions(manage_guild=True)
    async def giveaway_edit(self, ctx, message_id: int = None, field: str = None, *, value: str = None):
        await ctx.invoke(self.gedit, message_id=message_id, field=field, value=value)
    
    @commands.command(name='greroll')
    @commands.has_permissions(manage_guild=True)
    async def greroll(self, ctx, message_id: int = None):
        """Reroll a giveaway winner
        
        Usage: ,greroll <message_id>
        """
        if not message_id:
            return await ctx.reply(embed=error_embed(
                'Missing Message ID',
                f'**Usage:** `{config.PREFIX}greroll <message_id>`'
            ))
        
        # Check if giveaway exists and is ended
        giveaway = await self._execute(
            'SELECT * FROM giveaways WHERE message_id = %s AND guild_id = %s AND ended = 1',
            (message_id, ctx.guild.id), fetchone=True
        )
        
        if not giveaway:
            return await ctx.reply(embed=error_embed(
                'Giveaway Not Found',
                'No ended giveaway found with that message ID.'
            ))
        
        # Get giveaway message
        channel = await self._get_channel(giveaway['channel_id'])
        if not channel:
            return await ctx.reply(embed=error_embed('Error', 'Giveaway channel not found.'))
        
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.reply(embed=error_embed('Error', 'Giveaway message not found.'))
        except discord.HTTPException as e:
            return await ctx.reply(embed=error_embed('Error', f'Failed to fetch message: {str(e)}'))
        
        raw_entry_ids = await self._collect_entry_ids(message, giveaway)
        entry_ids = await self._filter_message_requirement_entries(ctx.guild, raw_entry_ids, giveaway)
        if len(entry_ids) == 0:
            return await ctx.reply(embed=error_embed('No Entries', 'No eligible entries for this giveaway.'))
        
        # Pick new winner
        winner_count = min(giveaway['winners'], len(entry_ids))
        winners = random.sample(entry_ids, winner_count)
        
        # Announce new winner
        winner_mentions = self._winner_mentions(winners)
        
        embed = discord.Embed(
            title="Giveaway Rerolled!",
            description=f"**New Winner(s):** {winner_mentions}\n**Prize:** {giveaway['prize']}",
            color=0xe67e22
        )
        
        await channel.send(embed=embed)
        await ctx.reply(embed=success_embed('Rerolled!', f'New winner(s): {winner_mentions}'))

    @giveaway.command(name='reroll')
    @commands.has_permissions(manage_guild=True)
    async def giveaway_reroll(self, ctx, message_id: int = None):
        await ctx.invoke(self.greroll, message_id=message_id)

    @commands.command(name='gdelay', aliases=['gwdelay'])
    async def gdelay(self, ctx, id1: str = None, id2: str = None):
        """Calculate the exact delay between two Discord message IDs.

        Usage: ,gdelay <message_id_1> <message_id_2>
        """
        if not id1 or not id2:
            return await ctx.reply(embed=error_embed(
                'Missing Message IDs',
                f'**Usage:** `{config.PREFIX}gdelay <message_id_1> <message_id_2>`\n'
                f'You can also use `{config.PREFIX}gw delay <message_id_1> <message_id_2>`.'
            ))

        if not id1.isdigit() or not id2.isdigit():
            return await ctx.reply(embed=error_embed(
                'Invalid Message IDs',
                'Message IDs must contain numbers only.'
            ))

        try:
            time1_ms = self._message_id_to_timestamp_ms(id1)
            time2_ms = self._message_id_to_timestamp_ms(id2)
        except (TypeError, ValueError, OverflowError):
            return await ctx.reply(embed=error_embed(
                'Invalid Message IDs',
                'Make sure both message IDs are valid Discord snowflakes.'
            ))

        total_seconds = abs(time2_ms - time1_ms) / 1000
        first_timestamp = int(time1_ms / 1000)
        second_timestamp = int(time2_ms / 1000)

        embed = discord.Embed(
            title="Message Delay",
            description=f"{config.EMOJIS['clock']} The exact time delay is **{self._format_delay(total_seconds)}**",
            color=config.COLORS["primary"],
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="First Message", value=f"<t:{first_timestamp}:F>", inline=False)
        embed.add_field(name="Second Message", value=f"<t:{second_timestamp}:F>", inline=False)
        embed.set_footer(text="xiel")

        await ctx.reply(embed=embed)

    @giveaway.command(name='delay')
    async def giveaway_delay(self, ctx, id1: str = None, id2: str = None):
        await ctx.invoke(self.gdelay, id1=id1, id2=id2)

    async def _get_active_giveaway_for_config(self, ctx, message_id):
        giveaway = self._active_giveaways.get(int(message_id))
        if giveaway and int(giveaway.get("guild_id") or 0) == ctx.guild.id:
            return giveaway

        giveaway = await self._execute(
            'SELECT * FROM giveaways WHERE message_id = %s AND guild_id = %s AND ended = 0',
            (message_id, ctx.guild.id),
            fetchone=True,
        )
        return giveaway

    def _set_active_requirement_value(self, message_id, key, value):
        active = self._active_giveaways.get(int(message_id))
        if active is not None:
            active[key] = value

    @commands.group(name="glock", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def glock(self, ctx):
        await ctx.reply(embed=error_embed(
            "Invalid Usage",
            f"Use `{config.PREFIX}glock messages <message_id> <daily|weekly|monthly|total> <amount>`, "
            f"`{config.PREFIX}glock bypass <message_id> <@role|none>`, or "
            f"`{config.PREFIX}glock clear <message_id> [period|all]`."
        ))

    @glock.command(name="messages")
    @commands.has_permissions(manage_guild=True)
    async def glock_messages(self, ctx, message_id: int = None, period: str = None, amount: int = None):
        if not message_id or not period or amount is None:
            return await ctx.reply(embed=error_embed("Missing Arguments", f"Use `{config.PREFIX}glock messages <message_id> <daily|weekly|monthly|total> <amount>`."))

        period = period.lower()
        column_map = {
            "daily": "required_daily_messages",
            "weekly": "required_weekly_messages",
            "monthly": "required_monthly_messages",
            "total": "required_total_messages",
        }
        if period not in column_map:
            return await ctx.reply(embed=error_embed("Invalid Period", "Use `daily`, `weekly`, `monthly`, or `total`."))
        if amount < 0:
            return await ctx.reply(embed=error_embed("Invalid Amount", "Message requirement must be 0 or higher."))

        giveaway = await self._get_active_giveaway_for_config(ctx, message_id)
        if not giveaway:
            return await ctx.reply(embed=error_embed("Giveaway Not Found", "No active giveaway found with that message ID."))

        column = column_map[period]
        await self._execute(f"UPDATE giveaways SET {column} = %s WHERE message_id = %s", (amount, message_id))
        self._set_active_requirement_value(message_id, column, amount)
        await ctx.reply(embed=success_embed("Requirement Updated", f"{period.title()} message requirement set to `{amount:,}`."))

    @glock.command(name="bypass")
    @commands.has_permissions(manage_guild=True)
    async def glock_bypass(self, ctx, message_id: int = None, *, role_text: str = None):
        if not message_id or not role_text:
            return await ctx.reply(embed=error_embed("Missing Arguments", f"Use `{config.PREFIX}glock bypass <message_id> <@role|none>`."))

        giveaway = await self._get_active_giveaway_for_config(ctx, message_id)
        if not giveaway:
            return await ctx.reply(embed=error_embed("Giveaway Not Found", "No active giveaway found with that message ID."))

        if role_text.lower().strip() in {"none", "off", "clear", "disable"}:
            role_id = None
            label = "disabled"
        elif ctx.message.role_mentions:
            role_id = ctx.message.role_mentions[0].id
            label = ctx.message.role_mentions[0].mention
        else:
            return await ctx.reply(embed=error_embed("Invalid Role", "Mention a role or use `none`."))

        await self._execute("UPDATE giveaways SET requirement_bypass_role_id = %s WHERE message_id = %s", (role_id, message_id))
        self._set_active_requirement_value(message_id, "requirement_bypass_role_id", role_id)
        await ctx.reply(embed=success_embed("Bypass Updated", f"Requirement bypass role: {label}."))

    @glock.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def glock_clear(self, ctx, message_id: int = None, period: str = "all"):
        if not message_id:
            return await ctx.reply(embed=error_embed("Missing Message ID", f"Use `{config.PREFIX}glock clear <message_id> [daily|weekly|monthly|total|all]`."))

        giveaway = await self._get_active_giveaway_for_config(ctx, message_id)
        if not giveaway:
            return await ctx.reply(embed=error_embed("Giveaway Not Found", "No active giveaway found with that message ID."))

        period = (period or "all").lower()
        column_map = {
            "daily": "required_daily_messages",
            "weekly": "required_weekly_messages",
            "monthly": "required_monthly_messages",
            "total": "required_total_messages",
        }
        if period == "all":
            updates = {column: 0 for column in column_map.values()}
            updates["requirement_bypass_role_id"] = None
        elif period in column_map:
            updates = {column_map[period]: 0}
        else:
            return await ctx.reply(embed=error_embed("Invalid Period", "Use `daily`, `weekly`, `monthly`, `total`, or `all`."))

        set_clause = ", ".join(f"{column} = %s" for column in updates)
        await self._execute(
            f"UPDATE giveaways SET {set_clause} WHERE message_id = %s",
            (*updates.values(), message_id),
        )
        for column, value in updates.items():
            self._set_active_requirement_value(message_id, column, value)
        await ctx.reply(embed=success_embed("Requirements Cleared", f"Cleared `{period}` message requirements."))

    @commands.command(name="greq")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def greq(self, ctx, message_id: int = None):
        if not message_id:
            return await ctx.reply(embed=error_embed("Missing Message ID", f"Use `{config.PREFIX}greq <message_id>`."))

        giveaway = await self._get_active_giveaway_for_config(ctx, message_id)
        if not giveaway:
            giveaway = await self._execute(
                'SELECT * FROM giveaways WHERE message_id = %s AND guild_id = %s',
                (message_id, ctx.guild.id),
                fetchone=True,
            )
        if not giveaway:
            return await ctx.reply(embed=error_embed("Giveaway Not Found", "No giveaway found with that message ID."))

        embed = discord.Embed(
            title="Giveaway Requirements",
            description=f"**Prize:** {giveaway['prize']}\n\n{self._format_message_requirements(giveaway)}",
            color=config.COLORS["primary"],
        )
        await ctx.reply(embed=embed)
    
    async def end_giveaway(self, message_id, force=False, giveaway_override=None):
        """End a giveaway and pick winners"""
        giveaway = giveaway_override
        if giveaway is None:
            giveaway = await self._execute(
                'SELECT * FROM giveaways WHERE message_id = %s', (message_id,), fetchone=True
            )
        
        if not giveaway or (int(giveaway.get('ended') or 0) != 0 and not force):
            return
        
        # Get channel and message
        channel = await self._get_channel(giveaway['channel_id'])
        if not channel:
            print(f"Giveaway channel {giveaway['channel_id']} not found")
            return
        
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            print(f"Giveaway message {message_id} not found")
            return
        except discord.HTTPException as e:
            print(f"Failed to fetch giveaway message: {e}")
            return

        if force and giveaway_override is None:
            try:
                await self._execute('UPDATE giveaways SET ended = 1 WHERE message_id = %s', (message_id,))
            except Exception as e:
                print(f"Failed to mark forced giveaway {message_id} ended: {e}")
                traceback.print_exc()
        elif force:
            pass
        else:
            # Claim after the message is fetchable, so transient Discord fetch
            # failures do not strand the giveaway as ended-but-unannounced.
            claimed = await self._execute_rowcount(
                'UPDATE giveaways SET ended = 1 WHERE message_id = %s AND ended = 0',
                (message_id,)
            )
            if claimed == 0:
                return
        
        raw_entry_ids = await self._collect_entry_ids(message, giveaway)
        entry_ids = await self._filter_message_requirement_entries(channel.guild, raw_entry_ids, giveaway)
        if len(entry_ids) == 0:
            # No valid entries
            no_entry_text = "No valid entries!"
            if raw_entry_ids and self._has_message_requirements(giveaway):
                no_entry_text = "No eligible entries met the message requirements!"
            embed = discord.Embed(
                title=f"{GIVEAWAY_EMOJI} Giveaway Ended",
                description=f"**Prize:** {giveaway['prize']}\n\n{no_entry_text}",
                color=0xe74c3c
            )
            if self._has_message_requirements(giveaway):
                embed.add_field(name="Message Requirements", value=self._format_message_requirements(giveaway), inline=False)
                embed.add_field(name="Entries", value=f"`0` eligible / `{len(raw_entry_ids)}` reacted", inline=False)
            # Re-add image if it existed
            if giveaway['image_url']:
                embed.set_image(url=giveaway['image_url'])
            await self._edit_giveaway_message(message, embed)
            await self._send_no_winner_announcement(channel, message, giveaway['prize'])
            self._active_giveaways.pop(int(message_id), None)
            self._memory_entries.pop(int(message_id), None)
            return
        
        # Pick winners
        winner_count = min(giveaway['winners'], len(entry_ids))
        winners = random.sample(entry_ids, winner_count)
        winner_mentions = self._winner_mentions(winners)
        
        # Update giveaway message - show it's ended, not a countdown
        embed = discord.Embed(
            title=f"{GIVEAWAY_EMOJI} Giveaway Ended!",
            description=f"**Prize:** {giveaway['prize']}",
            color=0x2ecc71
        )
        embed.add_field(
            name="⏰ Status",
            value=f"**Ended** at <t:{giveaway['end_time']}:f>",
            inline=False
        )
        embed.add_field(name="Winner(s)", value=winner_mentions, inline=False)
        if self._has_message_requirements(giveaway):
            embed.add_field(name="Message Requirements", value=self._format_message_requirements(giveaway), inline=False)
            embed.add_field(name="Entries", value=f"`{len(entry_ids)}` eligible / `{len(raw_entry_ids)}` reacted", inline=True)
        else:
            embed.add_field(name="Entries", value=f"{len(entry_ids)} participants", inline=True)
        
        # Re-add image if it existed
        if giveaway['image_url']:
            embed.set_image(url=giveaway['image_url'])
        
        embed.set_footer(text="Giveaway ended")
        embed.timestamp = datetime.fromtimestamp(int(giveaway['end_time']), UTC)
        
        await self._edit_giveaway_message(message, embed)
        
        # Announce winners
        await self._send_winner_announcement(channel, message, winner_mentions, giveaway['prize'])
        self._active_giveaways.pop(int(message_id), None)
        self._memory_entries.pop(int(message_id), None)
    
    @tasks.loop(seconds=5)
    async def check_giveaways(self):
        """Background task to check for ended giveaways"""
        try:
            current_time = int(datetime.now(UTC).timestamp())
            
            ended = await self._execute(
                'SELECT message_id FROM giveaways WHERE end_time <= %s AND ended = 0',
                (current_time,), fetchall=True
            )
            
            if ended:
                for row in ended:
                    await self.end_giveaway(row['message_id'])
                    await asyncio.sleep(2)  # Prevent rate limiting
        except Exception as e:
            print(f"Error checking giveaways: {e}")
            traceback.print_exc()
    
    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()
    
    def cog_unload(self):
        self.check_giveaways.cancel()
        for task in self._end_tasks.values():
            if not task.done():
                task.cancel()
        self._end_tasks.clear()
    
    # Error handlers for better UX
    @gstart.error
    async def gstart_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed(
                'Missing Permissions',
                'You need **Manage Server** permission to start giveaways.'
            ))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(embed=error_embed(
                'Missing Arguments',
                f'**Usage:** `{config.PREFIX}gstart <duration> <winners> <prize> [image]`\n'
                f'**Example:** `{config.PREFIX}gstart 1h 1 Discord Nitro`'
            ))
        else:
            await ctx.reply(embed=error_embed('Error', f'An error occurred: {str(error)}'))
    
    @gend.error
    async def gend_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed(
                'Missing Permissions',
                'You need **Manage Server** permission to end giveaways.'
            ))
        else:
            await ctx.reply(embed=error_embed('Error', f'An error occurred: {str(error)}'))
    
    @greroll.error
    async def greroll_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed(
                'Missing Permissions',
                'You need **Manage Server** permission to reroll giveaways.'
            ))
        else:
            await ctx.reply(embed=error_embed('Error', f'An error occurred: {str(error)}'))
    
    @gcancel.error
    async def gcancel_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed(
                'Missing Permissions',
                'You need **Manage Server** permission to cancel giveaways.'
            ))
        else:
            await ctx.reply(embed=error_embed('Error', f'An error occurred: {str(error)}'))
    
    @gedit.error
    async def gedit_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=error_embed(
                'Missing Permissions',
                'You need **Manage Server** permission to edit giveaways.'
            ))
        else:
            await ctx.reply(embed=error_embed('Error', f'An error occurred: {str(error)}'))

async def setup(bot):
    await bot.add_cog(Giveaways(bot))
