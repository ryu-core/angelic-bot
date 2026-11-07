"""
Ticket Sorting System
Automatically moves channels to different categories when they are renamed.

Use case: Ticket bots rename channels based on status (e.g. "closed-0001",
"billing-0023", "resolved-ticket"). This cog detects those renames and
moves the channel into the correct category automatically.

Commands:
  ,ticketsort add <keyword> <category>   — Add a sorting rule
  ,ticketsort remove <keyword>           — Remove a rule
  ,ticketsort list                       — Show all rules
  ,ticketsort clear                      — Remove all rules
  ,ticketsort test <channel-name>        — Test which rule matches
"""
import discord
from discord.ext import commands
from utils.embeds import success_embed, error_embed, info_embed
from utils.database import settings_db
import config


class TicketSort(commands.Cog):
    """Automatic ticket channel sorting by name"""

    def __init__(self, bot):
        self.bot = bot

    @property
    def qualified_name(self):
        return "TicketSort"

    # ─── LISTENER: Channel rename detection ───

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        """Detect channel renames and sort into the matching category."""
        # Only care about text channels
        if not isinstance(after, discord.TextChannel):
            return

        # Only trigger if the name actually changed
        if before.name == after.name:
            return

        guild = after.guild
        rules = settings_db.get_ticket_sort_rules(guild.id)
        if not rules:
            return

        new_name = after.name.lower()
        matched_rule = None

        for rule in rules:
            keyword = rule['keyword']
            mode = rule.get('match_mode', 'startswith')

            if mode == 'startswith' and new_name.startswith(keyword):
                matched_rule = rule
                break
            elif mode == 'contains' and keyword in new_name:
                matched_rule = rule
                break
            elif mode == 'endswith' and new_name.endswith(keyword):
                matched_rule = rule
                break
            elif mode == 'exact' and new_name == keyword:
                matched_rule = rule
                break

        if not matched_rule:
            return

        # Get the target category
        target_category_id = int(matched_rule['category_id'])
        target_category = guild.get_channel(target_category_id)

        if not target_category or not isinstance(target_category, discord.CategoryChannel):
            return

        # Don't move if already in the correct category
        if after.category_id == target_category_id:
            return

        # Check bot permissions
        perms = target_category.permissions_for(guild.me)
        if not perms.manage_channels:
            return

        try:
            await after.edit(
                category=target_category,
                reason=f"Ticket Sort: channel renamed to '{after.name}' → matched rule '{matched_rule['keyword']}'"
            )

            # Send a subtle log message in the channel
            embed = discord.Embed(
                description=f"📂 Channel sorted into **{target_category.name}** (matched: `{matched_rule['keyword']}`)",
                color=config.COLORS['primary']
            )
            embed.set_footer(text="Ticket Sorting System")
            try:
                await after.send(embed=embed, delete_after=10)
            except discord.Forbidden:
                pass

        except discord.Forbidden:
            pass
        except discord.HTTPException as e:
            print(f"[TicketSort] Failed to move channel {after.name}: {e}")

    # ─── COMMANDS ───

    @commands.group(name='ticketsort', aliases=['ts', 'tsort'], invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def ticketsort(self, ctx):
        """View ticket sorting rules"""
        rules = settings_db.get_ticket_sort_rules(ctx.guild.id)
        if not rules:
            return await ctx.reply(embed=info_embed('No Sorting Rules',
                f'No ticket sort rules configured.\n\n'
                f'**Quick Start:**\n'
                f'`{config.PREFIX}ticketsort add closed #Closed-Tickets`\n'
                f'`{config.PREFIX}ticketsort add billing #Billing`\n'
                f'`{config.PREFIX}ticketsort add resolved #Resolved`\n\n'
                f'When a channel is renamed to start with the keyword,\n'
                f'it will be automatically moved to that category.'))

        embed = discord.Embed(
            title="📂 Ticket Sorting Rules",
            color=config.COLORS['primary']
        )

        desc = ""
        for i, rule in enumerate(rules, 1):
            category = ctx.guild.get_channel(int(rule['category_id']))
            cat_name = category.name if category else f"Unknown ({rule['category_id']})"
            mode_emoji = {'startswith': '▶️', 'contains': '🔍', 'endswith': '◀️', 'exact': '🎯'}.get(rule['match_mode'], '▶️')
            desc += f"**{i}.** {mode_emoji} `{rule['keyword']}` → **{cat_name}**\n"

        embed.description = desc
        embed.set_footer(text=f"{len(rules)} rule(s) • Channels are auto-sorted when renamed")
        await ctx.reply(embed=embed)

    @ticketsort.command(name='add', aliases=['set'])
    @commands.has_permissions(manage_channels=True)
    async def ticketsort_add(self, ctx, keyword: str = None, category: discord.CategoryChannel = None, mode: str = 'startswith'):
        """Add a sorting rule

        Modes: startswith (default), contains, endswith, exact
        Example: ,ticketsort add closed #Closed-Tickets
        """
        if not keyword or not category:
            embed = discord.Embed(
                title="📂 Add Sorting Rule",
                description=(
                    f"**Usage:** `{config.PREFIX}ticketsort add <keyword> <#category> [mode]`\n\n"
                    f"**Modes:**\n"
                    f"▶️ `startswith` — Channel name starts with keyword *(default)*\n"
                    f"🔍 `contains` — Channel name contains keyword anywhere\n"
                    f"◀️ `endswith` — Channel name ends with keyword\n"
                    f"🎯 `exact` — Channel name is exactly the keyword\n\n"
                    f"**Examples:**\n"
                    f"`{config.PREFIX}ticketsort add closed #Closed-Tickets`\n"
                    f"`{config.PREFIX}ticketsort add billing #Billing-Support`\n"
                    f"`{config.PREFIX}ticketsort add -resolved #Resolved contains`"
                ),
                color=config.COLORS['warning']
            )
            return await ctx.reply(embed=embed)

        # Validate mode
        valid_modes = ['startswith', 'contains', 'endswith', 'exact']
        if mode.lower() not in valid_modes:
            return await ctx.reply(embed=error_embed('Invalid Mode',
                f'Mode must be one of: {", ".join(f"`{m}`" for m in valid_modes)}'))

        keyword = keyword.lower().strip()
        if len(keyword) < 1 or len(keyword) > 50:
            return await ctx.reply(embed=error_embed('Invalid Keyword',
                'Keyword must be 1-50 characters long.'))

        # Check max rules per guild
        existing = settings_db.get_ticket_sort_rules(ctx.guild.id)
        if len(existing) >= 25:
            return await ctx.reply(embed=error_embed('Limit Reached',
                'Maximum of 25 sorting rules per server.'))

        success = settings_db.add_ticket_sort_rule(ctx.guild.id, keyword, category.id, mode.lower())
        if success:
            mode_desc = {'startswith': 'starts with', 'contains': 'contains', 'endswith': 'ends with', 'exact': 'is exactly'}.get(mode.lower(), mode)
            await ctx.reply(embed=success_embed('Rule Added',
                f'📂 When a channel name **{mode_desc}** `{keyword}`,\n'
                f'it will be moved to **{category.name}**.'))
        else:
            await ctx.reply(embed=error_embed('Failed', 'Could not add the sorting rule.'))

    @ticketsort.command(name='remove', aliases=['del', 'delete'])
    @commands.has_permissions(manage_channels=True)
    async def ticketsort_remove(self, ctx, *, keyword: str = None):
        """Remove a sorting rule"""
        if not keyword:
            return await ctx.reply(embed=error_embed('Usage',
                f'`{config.PREFIX}ticketsort remove <keyword>`'))

        removed = settings_db.remove_ticket_sort_rule(ctx.guild.id, keyword.strip())
        if removed:
            await ctx.reply(embed=success_embed('Rule Removed',
                f'Sorting rule for `{keyword.lower().strip()}` has been removed.'))
        else:
            await ctx.reply(embed=error_embed('Not Found',
                f'No sorting rule found for `{keyword.lower().strip()}`.'))

    @ticketsort.command(name='list', aliases=['rules', 'show'])
    @commands.has_permissions(manage_channels=True)
    async def ticketsort_list(self, ctx):
        """Show all sorting rules (same as ,ticketsort)"""
        await self.ticketsort(ctx)

    @ticketsort.command(name='clear', aliases=['reset'])
    @commands.has_permissions(manage_channels=True)
    async def ticketsort_clear(self, ctx):
        """Remove all sorting rules"""
        count = settings_db.clear_ticket_sort_rules(ctx.guild.id)
        if count > 0:
            await ctx.reply(embed=success_embed('Rules Cleared',
                f'Removed **{count}** sorting rule(s).'))
        else:
            await ctx.reply(embed=info_embed('No Rules', 'There were no rules to clear.'))

    @ticketsort.command(name='test', aliases=['check', 'simulate'])
    @commands.has_permissions(manage_channels=True)
    async def ticketsort_test(self, ctx, *, channel_name: str = None):
        """Test which rule a channel name would match

        Example: ,ticketsort test closed-ticket-0042
        """
        if not channel_name:
            return await ctx.reply(embed=error_embed('Usage',
                f'`{config.PREFIX}ticketsort test <channel-name>`\n'
                f'Example: `{config.PREFIX}ticketsort test closed-ticket-0042`'))

        rules = settings_db.get_ticket_sort_rules(ctx.guild.id)
        if not rules:
            return await ctx.reply(embed=info_embed('No Rules', 'No sorting rules configured.'))

        test_name = channel_name.lower().strip()
        matched = None

        for rule in rules:
            keyword = rule['keyword']
            mode = rule.get('match_mode', 'startswith')

            if mode == 'startswith' and test_name.startswith(keyword):
                matched = rule
                break
            elif mode == 'contains' and keyword in test_name:
                matched = rule
                break
            elif mode == 'endswith' and test_name.endswith(keyword):
                matched = rule
                break
            elif mode == 'exact' and test_name == keyword:
                matched = rule
                break

        if matched:
            category = ctx.guild.get_channel(int(matched['category_id']))
            cat_name = category.name if category else f"Unknown ({matched['category_id']})"
            await ctx.reply(embed=success_embed('✅ Match Found',
                f'Channel `{test_name}` matches rule:\n\n'
                f'**Keyword:** `{matched["keyword"]}`\n'
                f'**Mode:** `{matched["match_mode"]}`\n'
                f'**→ Category:** **{cat_name}**'))
        else:
            await ctx.reply(embed=info_embed('No Match',
                f'Channel `{test_name}` does not match any sorting rule.'))


async def setup(bot):
    await bot.add_cog(TicketSort(bot))
