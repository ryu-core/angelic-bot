import discord
from discord.ext import commands
import asyncio
from utils.embeds import create_embed
import config

class General(commands.Cog):
    """General bot commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    # Help command moved to dedicated cogs/help.py for better organization
    
    @commands.command(name='ping')
    async def ping(self, ctx):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000)
        
        if latency < 100:
            color = config.COLORS['success']
            status = 'Excellent'
        elif latency < 200:
            color = config.COLORS['secondary']
            status = 'Good'
        else:
            color = config.COLORS['error']
            status = 'Poor'
        
        embed = discord.Embed(
            title='🏓 Pong!',
            description=f'**Latency:** {latency}ms\n**Status:** {status}',
            color=color
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name='quote')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def quote(self, ctx, *, args: str = None):
        """Generate a beautiful quote image
        
        Usage: ,quote <text> [--author <name>] [--theme <theme>]
        Themes: ocean, sunset, forest, midnight, fire, purple, lavender, mint
        
        Examples:
          ,quote Be yourself; everyone else is already taken.
          ,quote Success is not final --author Winston Churchill --theme ocean
        """
        if not args:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Missing Quote Text',
                description=f'**Usage:** `{config.PREFIX}quote <text> [--author <name>] [--theme <theme>]`\n\n'
                f'**Themes:** ocean, sunset, forest, midnight, fire, purple, lavender, mint\n\n'
                f'**Example:**\n`{config.PREFIX}quote "Be yourself" --author Anonymous --theme sunset`'
            ))
        
        # Parse arguments
        import shlex
        try:
            parts = shlex.split(args)
        except ValueError:
            parts = args.split()
        
        quote_text = []
        author = None
        theme = "ocean"
        
        i = 0
        while i < len(parts):
            if parts[i] == '--author' and i + 1 < len(parts):
                author = parts[i + 1]
                i += 2
            elif parts[i] == '--theme' and i + 1 < len(parts):
                theme = parts[i + 1].lower()
                i += 2
            else:
                quote_text.append(parts[i])
                i += 1
        
        quote_text = ' '.join(quote_text)
        
        # Validate word count (100 words max)
        word_count = len(quote_text.split())
        if word_count > 100:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Quote Too Long',
                description=f'Quote exceeds 100 word limit.\n**Your quote:** {word_count} words\n**Maximum:** 100 words'
            ))
        
        # Validate quote length
        if len(quote_text) > 500:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Quote Too Long',
                description='Quote must be 500 characters or less.'
            ))
        
        if not quote_text:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Missing Quote Text',
                description='Please provide quote text.'
            ))
        
        # Send "generating" message
        async with ctx.typing():
            try:
                # Import generator
                from utils.quote_generator import QuoteImageGenerator
                
                # Generate image
                generator = QuoteImageGenerator()
                image_bytes = await generator.generate(
                    quote_text=quote_text,
                    author=author,
                    avatar_url=str(ctx.author.display_avatar.url),
                    username=ctx.author.name,  # Use .name instead of .display_name
                    theme=theme
                )
                
                # Send image
                file = discord.File(image_bytes, filename="quote.png")
                await ctx.send(file=file)
                
            except ImportError as e:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Quote Generator Not Available',
                    description=f'The quote generator feature is currently unavailable.\nError: {str(e)}'
                ))
            except Exception as e:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Generation Failed',
                    description=f'Failed to generate quote image: {str(e)}'
                ))
    
    @commands.command(name='translate', aliases=['tr'])
    async def translate(self, ctx, target_language: str = None, *, text: str = None):
        """Translate text to different languages
        
        Usage:
        ,translate <text> - Translate to English (auto-detect source)
        ,translate <language> <text> - Translate to specified language
        
        Common languages: en, es, fr, de, it, pt, ru, ja, ko, zh-CN, hi, ar
        """
        try:
            from deep_translator import GoogleTranslator
            
            # Check if replying to a message
            if ctx.message.reference:
                replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                
                # If no target language specified, translate reply to English
                if not target_language:
                    target_language = 'en'
                    text = replied_message.content
                # If target language specified but no text, use reply content
                elif not text:
                    text = replied_message.content
                # If both specified, ignore reply and use provided text
            
            # If no arguments provided and not replying, show usage
            if not target_language:
                embed = discord.Embed(
                    title="🌐 Translation Help",
                    description=(
                        f"**Usage:**\n"
                        f"`{config.PREFIX}translate <text>` - Translate to English\n"
                        f"`{config.PREFIX}translate <lang> <text>` - Translate to language\n"
                        f"**Reply + translate** - Reply to message and use command\n\n"
                        f"**Popular Languages:**\n"
                        f"🇬🇧 `en` English • 🇪🇸 `es` Spanish • 🇫🇷 `fr` French • 🇩🇪 `de` German\n"
                        f"🇮🇹 `it` Italian • 🇵🇹 `pt` Portuguese • 🇷🇺 `ru` Russian • 🇯🇵 `ja` Japanese\n"
                        f"🇰🇷 `ko` Korean • 🇨🇳 `zh-CN` Chinese • 🇮🇳 `hi` Hindi • 🇸🇦 `ar` Arabic\n"
                        f"🇹🇷 `tr` Turkish • 🇳🇱 `nl` Dutch • 🇵🇱 `pl` Polish • 🇻🇳 `vi` Vietnamese\n"
                        f"🇹🇭 `th` Thai • 🇮🇩 `id` Indonesian • 🇸🇪 `sv` Swedish • 🇬🇷 `el` Greek\n"
                        f"🇨🇿 `cs` Czech • 🇷🇴 `ro` Romanian • 🇺🇦 `uk` Ukrainian • 🇭🇺 `hu` Hungarian\n\n"
                        f"**Examples:**\n"
                        f"`{config.PREFIX}translate Hola como estas` - To English\n"
                        f"`{config.PREFIX}translate es Hello world` - To Spanish\n"
                        f"Reply to message + `{config.PREFIX}translate` - Reply to English\n"
                        f"Reply to message + `{config.PREFIX}translate fr` - Reply to French"
                    ),
                    color=config.COLORS['primary']
                )
                embed.set_footer(text="Powered by Google Translate | 100+ languages supported")
                return await ctx.reply(embed=embed)
            
            # Get supported languages
            supported_langs = GoogleTranslator().get_supported_languages(as_dict=True)
            
            # Check if target_language is actually a language code
            if text is None:
                # No second argument, so translate target_language (which is the text) to English
                text = target_language
                target_language = 'en'
            else:
                # Check if target_language is valid
                if target_language.lower() not in supported_langs.values() and target_language not in supported_langs.values():
                    # Invalid language, treat everything as text to translate to English
                    text = f"{target_language} {text}"
                    target_language = 'en'
            
            # Detect source language and translate
            translator = GoogleTranslator(source='auto', target=target_language.lower())
            result = await asyncio.to_thread(translator.translate, text)
            
            # Get language names
            lang_dict = {v: k for k, v in supported_langs.items()}
            target_lang_name = lang_dict.get(target_language.lower(), target_language).title()
            
            # Send only the translated text
            translated = result[:2000] if len(result) > 2000 else result
            await ctx.reply(translated)
            
        except Exception as e:
            await ctx.reply(embed=create_embed(
                'error',
                title='Translation Failed',
                description=f'Could not translate text. Make sure the language code is valid.\n```{str(e)}```'
            ))
    
    @commands.command(name='steal', aliases=['addemoji', 'steal_emoji'])
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def steal(self, ctx, emoji_or_id: str = None, *, name: str = None):
        """Steal an emoji from another server and add it here
        
        Usage:
        ,steal :emoji: - Steal a custom emoji
        ,steal :emoji: custom_name - Steal with a custom name
        ,steal 123456789 - Steal by emoji ID
        Reply to message + ,steal - Steal emoji from replied message
        
        Requires: Manage Emojis permission
        """
        import re
        import aiohttp
        
        # Check if replying to a message
        if ctx.message.reference and not emoji_or_id:
            replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            
            # Extract emojis from replied message
            emoji_pattern = r'<(a?):([a-zA-Z0-9_]+):([0-9]+)>'
            emojis_found = re.findall(emoji_pattern, replied_message.content)
            
            if not emojis_found:
                return await ctx.reply(embed=create_embed(
                    'error',
                    title='No Emoji Found',
                    description='The message you replied to doesn\'t contain any custom emojis!'
                ))
            
            # Use the first emoji found
            is_animated = emojis_found[0][0] == 'a'
            emoji_name = emojis_found[0][1]
            emoji_id = emojis_found[0][2]
            emoji_or_id = f'<{"a" if is_animated else ""}:{emoji_name}:{emoji_id}>'
        
        if not emoji_or_id:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Missing Emoji',
                description=f'**Usage:**\n'
                f'`{config.PREFIX}steal :emoji:` - Steal a custom emoji\n'
                f'`{config.PREFIX}steal :emoji: name` - Steal with custom name\n'
                f'`{config.PREFIX}steal 123456789` - Steal by emoji ID\n'
                f'**Reply + steal** - Reply to message with emoji\n\n'
                f'**Note:** You need **Manage Emojis** permission!'
            ))
        
        # Try to parse custom emoji format <:name:id> or <a:name:id>
        custom_emoji_match = re.match(r'<(a?):([a-zA-Z0-9_]+):([0-9]+)>', emoji_or_id)
        
        if custom_emoji_match:
            # Custom emoji format
            is_animated = custom_emoji_match.group(1) == 'a'
            emoji_name = custom_emoji_match.group(2)
            emoji_id = custom_emoji_match.group(3)
        elif emoji_or_id.isdigit():
            # Direct emoji ID
            emoji_id = emoji_or_id
            emoji_name = name or f'emoji_{emoji_id}'
            is_animated = False  # We'll check this when fetching
        else:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Invalid Emoji',
                description='Please provide a valid custom emoji or emoji ID.\n\n'
                f'**Examples:**\n'
                f'`{config.PREFIX}steal :my_emoji:`\n'
                f'`{config.PREFIX}steal 123456789`\n'
                f'**Or reply to a message with emoji**'
            ))

        
        # Use custom name if provided
        if name:
            emoji_name = name.replace(' ', '_')
        
        # Build emoji URL
        extension = 'gif' if is_animated else 'png'
        emoji_url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{extension}'
        
        async with ctx.typing():
            try:
                # Download emoji
                async with aiohttp.ClientSession() as session:
                    async with session.get(emoji_url) as resp:
                        if resp.status == 404:
                            # Try the other format
                            extension = 'png' if extension == 'gif' else 'gif'
                            emoji_url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{extension}'
                            async with session.get(emoji_url) as resp2:
                                if resp2.status != 200:
                                    return await ctx.reply(embed=create_embed(
                                        'error',
                                        title='Emoji Not Found',
                                        description='Could not find this emoji. Make sure it\'s a valid custom emoji!'
                                    ))
                                emoji_bytes = await resp2.read()
                                is_animated = extension == 'gif'
                        elif resp.status != 200:
                            return await ctx.reply(embed=create_embed(
                                'error',
                                title='Download Failed',
                                description=f'Failed to download emoji (Status: {resp.status})'
                            ))
                        else:
                            emoji_bytes = await resp.read()
                
                # Check emoji slots
                emoji_limit = ctx.guild.emoji_limit
                current_static = len([e for e in ctx.guild.emojis if not e.animated])
                current_animated = len([e for e in ctx.guild.emojis if e.animated])
                
                if is_animated and current_animated >= emoji_limit:
                    return await ctx.reply(embed=create_embed(
                        'error',
                        title='Emoji Limit Reached',
                        description=f'This server has reached the animated emoji limit ({emoji_limit})!'
                    ))
                elif not is_animated and current_static >= emoji_limit:
                    return await ctx.reply(embed=create_embed(
                        'error',
                        title='Emoji Limit Reached',
                        description=f'This server has reached the static emoji limit ({emoji_limit})!'
                    ))
                
                # Clean emoji name (Discord requires 2-32 alphanumeric + underscore characters)
                emoji_name = re.sub(r'[^a-zA-Z0-9_]', '', emoji_name)[:32]
                if len(emoji_name) < 2:
                    emoji_name = f'emoji_{emoji_id}'[:32]
                
                # Upload emoji to server
                new_emoji = await ctx.guild.create_custom_emoji(
                    name=emoji_name,
                    image=emoji_bytes,
                    reason=f'Emoji stolen by {ctx.author} ({ctx.author.id})'
                )
                
                # Success message
                embed = discord.Embed(
                    title='✅ Emoji Stolen Successfully!',
                    description=f'Added {new_emoji} to this server!',
                    color=config.COLORS['success']
                )
                embed.add_field(name='Name', value=f'`:{new_emoji.name}:`', inline=True)
                embed.add_field(name='Type', value='Animated' if is_animated else 'Static', inline=True)
                embed.add_field(name='ID', value=f'`{new_emoji.id}`', inline=True)
                embed.set_thumbnail(url=new_emoji.url)
                embed.set_footer(text=f'Stolen by {ctx.author.name}', icon_url=ctx.author.display_avatar.url)
                
                await ctx.reply(embed=embed)
                
            except discord.Forbidden:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Missing Permissions',
                    description='I need **Manage Emojis** permission to add emojis!'
                ))
            except discord.HTTPException as e:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Upload Failed',
                    description=f'Failed to upload emoji: {str(e)}'
                ))
            except Exception as e:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Error',
                    description=f'An error occurred: {str(e)}'
                ))
    
    
    @commands.command(name='image', aliases=['pic'])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def image(self, ctx, *, query: str = None):
        """Search for images using Google
        
        Usage: ,image <query>
        """
        if not query:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Missing Query',
                description=f'Please provide a search query!\n**Usage:** `{config.PREFIX}image <query>`'
            ))
        
        # NSFW filter — block explicit queries
        from cogs.search import is_nsfw_query
        if is_nsfw_query(query):
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', '❌')} Search Blocked",
                description="🚫 **NSFW content is not allowed!**\n\nThis bot does not permit searching for explicit or inappropriate images.",
                color=config.COLORS['error']
            )
            return await ctx.reply(embed=embed)
        
        # Check if API key is configured
        if not config.SERPER_API_KEY:
            return await ctx.reply(embed=create_embed(
                'error',
                title='API Not Configured',
                description='Serper API key is not configured. Please contact the bot owner.'
            ))
        
        async with ctx.typing():
            try:
                from utils.serper import search_images
                from cogs.search import ImagePaginationView
                
                # Perform image search - get more results for pagination
                result = await search_images(query, num_results=10)
                
                if not result['success']:
                    return await ctx.reply(embed=create_embed(
                        'error',
                        title='Search Failed',
                        description=f"Failed to perform image search: {result.get('error', 'Unknown error')}"
                    ))
                
                if result['total'] == 0:
                    return await ctx.reply(embed=create_embed(
                        'error',
                        title='No Results Found',
                        description=f'No images found for **"{query}"**. Try a different search term!'
                    ))
                
                # Convert result format to match ImagePaginationView expectations
                images = []
                for img in result['images']:
                    images.append({
                        'imageUrl': img['image_url'],
                        'title': img['title'],
                        'link': img['source_url']
                    })
                
                # Create pagination view with buttons
                view = ImagePaginationView(images, query, ctx.author)
                embed = view.create_embed()
                
                await ctx.reply(embed=embed, view=view)
                
            except ImportError as e:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Module Not Available',
                    description=f'The image search module is currently unavailable: {str(e)}'
                ))
            except Exception as e:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Error',
                    description=f'An error occurred: {str(e)}'
                ))
    

    
    @commands.command(name='members', aliases=['memberlist', 'inrole'])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def members(self, ctx, *, role: discord.Role = None):
        """View all members with a specific role
        
        Usage: ,members <role>
        """
        if not role:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Missing Role',
                description=f'Please specify a role!\n**Usage:** `{config.PREFIX}members <role>`'
            ))
        
        # Get all members with this role
        members_with_role = [member for member in ctx.guild.members if role in member.roles]
        
        if not members_with_role:
            return await ctx.reply(embed=create_embed(
                'error',
                title='No Members Found',
                description=f'No members have the {role.mention} role.'
            ))
        
        # Sort members: online first, then by name
        members_with_role.sort(key=lambda m: (m.status == discord.Status.offline, m.display_name.lower()))
        
        # Count online members
        online_count = sum(1 for m in members_with_role if m.status != discord.Status.offline)
        
        # Create member list with status indicators
        member_list = []
        for member in members_with_role[:50]:  # Limit to 50 to avoid embed limits
            status_emoji = {
                discord.Status.online: '🟢',
                discord.Status.idle: '🟡',
                discord.Status.dnd: '🔴',
                discord.Status.offline: '⚫'
            }.get(member.status, '⚫')
            member_list.append(f"{status_emoji} {member.mention}")
        
        # Split into chunks if too many members
        chunk_size = 20
        chunks = [member_list[i:i + chunk_size] for i in range(0, len(member_list), chunk_size)]
        
        # Create embed
        embed = discord.Embed(
            title=f"👥 Members with {role.name}",
            description=f"**Total:** {len(members_with_role)} members\n**Online:** {online_count} members",
            color=role.color if role.color != discord.Color.default() else config.COLORS['primary']
        )
        
        # Add member fields
        for i, chunk in enumerate(chunks[:3]):  # Max 3 chunks to avoid embed limits
            field_name = f"Members ({i*chunk_size + 1}-{i*chunk_size + len(chunk)})" if len(chunks) > 1 else "Members"
            embed.add_field(
                name=field_name,
                value='\n'.join(chunk),
                inline=False
            )
        
        # Add note if more than 50 members
        if len(members_with_role) > 50:
            embed.set_footer(text=f"Showing first 50 of {len(members_with_role)} members")
        else:
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        
        await ctx.reply(embed=embed)


    @commands.command(name='sticker', aliases=['stealsticker', 'addsticker'])
    @commands.has_permissions(manage_emojis_and_stickers=True)
    @commands.bot_has_permissions(manage_emojis_and_stickers=True)
    async def sticker(self, ctx):
        """Steal a sticker from a replied message and add it to this server.

        Usage: Reply to a message that has a sticker, then run ,sticker
        Requires: Manage Emojis & Stickers permission
        """
        import aiohttp
        import io as _io

        if not ctx.message.reference:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Reply Required',
                description=f'**Usage:** Reply to a message that has a sticker, then use `{config.PREFIX}sticker`'
            ))

        try:
            replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except Exception:
            return await ctx.reply(embed=create_embed(
                'error', title='Error', description='Could not fetch the replied message.'
            ))

        if not replied_message.stickers:
            return await ctx.reply(embed=create_embed(
                'error',
                title='No Sticker Found',
                description='The replied message does not contain a sticker!'
            ))

        sticker_item = replied_message.stickers[0]

        # Check sticker slots
        sticker_limit = ctx.guild.sticker_limit
        current_stickers = len(ctx.guild.stickers)
        if current_stickers >= sticker_limit:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Sticker Limit Reached',
                description=f'This server has reached the sticker limit ({sticker_limit} stickers)!'
            ))

        async with ctx.typing():
            try:
                # Fetch the full sticker to learn its format
                full_sticker = await sticker_item.fetch()
                fmt = full_sticker.format  # StickerFormatType: png, apng, lottie, gif

                # Determine extension and build CDN URL from the sticker ID directly
                # (full_sticker.url can 404 for some sticker types — construct it manually)
                sticker_id = full_sticker.id
                if fmt == discord.StickerFormatType.lottie:
                    ext = 'json'
                elif fmt == discord.StickerFormatType.apng:
                    ext = 'png'
                elif fmt == discord.StickerFormatType.gif:
                    ext = 'gif'
                else:
                    ext = 'png'

                original_url = str(getattr(full_sticker, 'url', '') or '')
                cdn_url = f'https://cdn.discordapp.com/stickers/{sticker_id}.{ext}'
                media_url = f'https://media.discordapp.net/stickers/{sticker_id}.{ext}'
                download_urls = []
                for url in (cdn_url, original_url, media_url):
                    if url and url not in download_urls:
                        download_urls.append(url)

                # Download sticker — try primary CDN then fallback
                sticker_bytes = None
                async with aiohttp.ClientSession() as session:
                    for try_url in download_urls:
                        async with session.get(try_url) as resp:
                            if resp.status == 200:
                                sticker_bytes = await resp.read()
                                break

                if not sticker_bytes:
                    return await ctx.reply(embed=create_embed(
                        'error',
                        title='Download Failed',
                        description=(
                            f'Could not download this sticker. '
                            f'It may be a **Lottie** (Discord built-in animated) sticker '
                            f'which cannot be stolen, or it may be unavailable.'
                        )
                    ))

                # Discord sticker max size is 512 KB for PNG/APNG/GIF, 100 KB for Lottie.
                # Do not auto-compress here: that is exactly what caused quality loss.
                max_size = 100 * 1024 if ext == 'json' else 512 * 1024

                if len(sticker_bytes) > max_size:
                    return await ctx.reply(embed=create_embed(
                        'error',
                        title='Sticker Too Large',
                        description=(
                            f'This sticker is **{len(sticker_bytes) // 1024} KB**, but Discord only allows '
                            f'**{max_size // 1024} KB** for this format.\n'
                            'I did not resize it because that would lower the quality.'
                        )
                    ))

                # Upload sticker
                sticker_file = discord.File(
                    fp=_io.BytesIO(sticker_bytes),
                    filename=f'{full_sticker.name}.{ext}'
                )

                new_sticker = await ctx.guild.create_sticker(
                    name=full_sticker.name[:30],
                    description=full_sticker.description or 'Stolen sticker',
                    emoji='😀',
                    file=sticker_file,
                    reason=f'Sticker stolen by {ctx.author} ({ctx.author.id})'
                )

                embed = discord.Embed(
                    title='✅ Sticker Stolen!',
                    description=f'Added **{new_sticker.name}** to this server!',
                    color=config.COLORS['success']
                )
                embed.add_field(name='Format', value=ext.upper(), inline=True)
                embed.add_field(name='Size', value=f'{len(sticker_bytes) // 1024} KB', inline=True)
                embed.set_thumbnail(url=new_sticker.url)
                embed.set_footer(text=f'Stolen by {ctx.author.name}', icon_url=ctx.author.display_avatar.url)
                await ctx.reply(embed=embed)

            except discord.Forbidden:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Missing Permissions',
                    description='I need **Manage Emojis & Stickers** permission!'
                ))
            except discord.HTTPException as e:
                # Give a clear reason why Discord rejected it
                detail = str(e)
                hint = ''
                if '30039' in detail or 'sticker_limit' in detail.lower():
                    hint = '\nThe server has reached its sticker limit.'
                elif 'file' in detail.lower() or 'size' in detail.lower():
                    hint = '\nThe sticker file is too large (max 512 KB for PNG/APNG, 100 KB for Lottie).'
                elif 'format' in detail.lower():
                    hint = '\nThis sticker format is not supported by Discord for upload.'
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Upload Failed',
                    description=f'Discord rejected the sticker: `{e}`{hint}'
                ))
            except Exception as e:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Error',
                    description=f'An error occurred: {e}'
                ))

    @commands.command(name='deletesticker', aliases=['delsticker', 'removesticker'])
    @commands.has_permissions(manage_emojis_and_stickers=True)
    @commands.bot_has_permissions(manage_emojis_and_stickers=True)
    async def deletesticker(self, ctx):
        """Delete a server sticker from a replied message.

        Usage: Reply to a message that used this server's sticker, then run ,deletesticker
        Requires: Manage Emojis & Stickers permission
        """
        if not ctx.message.reference:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Reply Required',
                description=f'**Usage:** Reply to a message with a server sticker, then use `{config.PREFIX}deletesticker`'
            ))

        try:
            replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except Exception:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Error',
                description='Could not fetch the replied message.'
            ))

        if not replied_message.stickers:
            return await ctx.reply(embed=create_embed(
                'error',
                title='No Sticker Found',
                description='The replied message does not contain a sticker!'
            ))

        sticker_item = replied_message.stickers[0]
        sticker = discord.utils.get(ctx.guild.stickers, id=sticker_item.id)
        if not sticker:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Not A Server Sticker',
                description='I can only delete stickers that belong to this server.'
            ))

        sticker_name = sticker.name
        try:
            await sticker.delete(reason=f'Sticker deleted by {ctx.author} ({ctx.author.id})')
        except discord.Forbidden:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Missing Permissions',
                description='I need **Manage Emojis & Stickers** permission!'
            ))
        except discord.HTTPException as e:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Delete Failed',
                description=f'Discord rejected the sticker delete: `{e}`'
            ))

        embed = discord.Embed(
            title='✅ Sticker Deleted!',
            description=f'Deleted **{sticker_name}** from this server.',
            color=config.COLORS['success']
        )
        embed.set_footer(text=f'Deleted by {ctx.author.name}', icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.command(name='uploadsticker', aliases=['picsticker', 'makesticker'])
    @commands.has_permissions(manage_emojis_and_stickers=True)
    @commands.bot_has_permissions(manage_emojis_and_stickers=True)
    async def uploadsticker(self, ctx, *, name: str = None):
        """Upload an attached or replied image as a server sticker.

        Usage: ,uploadsticker [name] with an image attached, or reply to an image.
        Requires: Manage Emojis & Stickers permission
        """
        import io as _io
        import re
        from pathlib import Path

        def clean_sticker_name(value):
            value = re.sub(r'[^A-Za-z0-9_ ]+', '', value or '').strip()
            value = re.sub(r'\s+', '_', value)
            if len(value) == 1:
                value = f'{value}_'
            return (value or 'sticker')[:30]

        def looks_like_image(attachment):
            content_type = (attachment.content_type or '').lower()
            filename = attachment.filename.lower()
            return content_type.startswith('image/') or filename.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.apng'))

        async def find_image_attachment():
            for attachment in ctx.message.attachments:
                if looks_like_image(attachment):
                    return attachment

            if not ctx.message.reference:
                return None

            try:
                replied = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            except Exception:
                return None

            for attachment in replied.attachments:
                if looks_like_image(attachment):
                    return attachment
            return None

        if len(ctx.guild.stickers) >= ctx.guild.sticker_limit:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Sticker Limit Reached',
                description=f'This server has reached the sticker limit ({ctx.guild.sticker_limit} stickers)!'
            ))

        attachment = await find_image_attachment()
        if not attachment:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Image Required',
                description=(
                    f'Attach an image and run `{config.PREFIX}uploadsticker [name]`, '
                    f'or reply to an image with `{config.PREFIX}uploadsticker [name]`.'
                )
            ))

        if attachment.size > 10 * 1024 * 1024:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Image Too Large',
                description='Please use an image under 10 MB.'
            ))

        sticker_name = clean_sticker_name(name or Path(attachment.filename).stem)
        source_ext = Path(attachment.filename).suffix.lower()
        animated_source = source_ext in {'.gif', '.apng'}

        async with ctx.typing():
            try:
                image_bytes = await attachment.read()
                max_size = 512 * 1024

                if animated_source:
                    if len(image_bytes) > max_size:
                        return await ctx.reply(embed=create_embed(
                            'error',
                            title='Sticker Too Large',
                            description=(
                                f'This animated image is **{len(image_bytes) // 1024} KB**, but Discord only allows '
                                '**512 KB** for sticker uploads. I did not resize it because that would lower quality.'
                            )
                        ))
                    upload_ext = 'png' if source_ext == '.apng' else source_ext.lstrip('.')
                    sticker_bytes = image_bytes
                else:
                    from PIL import Image

                    with Image.open(_io.BytesIO(image_bytes)) as img:
                        img = img.convert('RGBA')
                        img.thumbnail((320, 320), Image.LANCZOS)
                        canvas = Image.new('RGBA', (320, 320), (0, 0, 0, 0))
                        x = (320 - img.width) // 2
                        y = (320 - img.height) // 2
                        canvas.paste(img, (x, y), img)

                        output = _io.BytesIO()
                        canvas.save(output, format='PNG', optimize=True)
                        sticker_bytes = output.getvalue()
                    upload_ext = 'png'

                    if len(sticker_bytes) > max_size:
                        return await ctx.reply(embed=create_embed(
                            'error',
                            title='Sticker Too Large',
                            description=(
                                f'This image becomes **{len(sticker_bytes) // 1024} KB** as a Discord sticker, '
                                'but Discord only allows **512 KB**. Try a simpler or smaller image.'
                            )
                        ))

                sticker_file = discord.File(
                    fp=_io.BytesIO(sticker_bytes),
                    filename=f'{sticker_name}.{upload_ext}'
                )
                new_sticker = await ctx.guild.create_sticker(
                    name=sticker_name,
                    description=f'Uploaded by {ctx.author}',
                    emoji='😀',
                    file=sticker_file,
                    reason=f'Sticker uploaded by {ctx.author} ({ctx.author.id})'
                )

                embed = discord.Embed(
                    title='✅ Sticker Uploaded!',
                    description=f'Added **{new_sticker.name}** to this server.',
                    color=config.COLORS['success']
                )
                embed.add_field(name='Format', value=upload_ext.upper(), inline=True)
                embed.add_field(name='Size', value=f'{len(sticker_bytes) // 1024} KB', inline=True)
                embed.set_thumbnail(url=new_sticker.url)
                embed.set_footer(text=f'Uploaded by {ctx.author.name}', icon_url=ctx.author.display_avatar.url)
                await ctx.reply(embed=embed)

            except discord.Forbidden:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Missing Permissions',
                    description='I need **Manage Emojis & Stickers** permission!'
                ))
            except discord.HTTPException as e:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Upload Failed',
                    description=f'Discord rejected the sticker: `{e}`'
                ))
            except Exception as e:
                await ctx.reply(embed=create_embed(
                    'error',
                    title='Error',
                    description=f'An error occurred: {e}'
                ))

    # ──────────────────────────── reactall ──────────────────────────────
    @commands.command(name='reactall', aliases=['multireact', 'emojiall', 'addreacts'])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def reactall(self, ctx):
        """React to a message with ALL emojis it contains! 🎭

        Reply to any message to add every emoji from it as a reaction.

        Usage: Reply to a message and type ,reactall
        Aliases: multireact, emojiall, addreacts
        """
        import re

        # Must be a reply
        ref = ctx.message.reference
        if not ref or not ref.message_id:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Reply to a Message!',
                description=(
                    f'You need to **reply** to a message that contains emojis!\n'
                    f'**Usage:** Reply to a message and type `{config.PREFIX}reactall`'
                )
            ))

        # Fetch the referenced message
        try:
            target_msg = ref.resolved or await ctx.channel.fetch_message(ref.message_id)
        except (discord.NotFound, discord.HTTPException):
            return await ctx.reply(embed=create_embed(
                'error',
                title='Message Not Found',
                description='Could not find the message you replied to.'
            ))

        content = target_msg.content
        if not content:
            return await ctx.reply(embed=create_embed(
                'error',
                title='No Text Content',
                description='That message has no text content to find emojis in.'
            ))

        # ── Extract all emoji from message ────────────────────────────────────
        collected = []
        seen = set()

        # Custom Discord emojis: <:name:id> or <a:name:id>
        custom_pattern = re.compile(r'<(a?):(\w+):(\d+)>')
        for match in custom_pattern.finditer(content):
            animated = bool(match.group(1))
            name = match.group(2)
            emoji_id = int(match.group(3))
            key = f"custom:{emoji_id}"
            if key not in seen:
                seen.add(key)
                emoji_obj = ctx.bot.get_emoji(emoji_id)
                if emoji_obj:
                    collected.append(emoji_obj)
                else:
                    prefix = 'a' if animated else ''
                    collected.append(f'<{prefix}:{name}:{emoji_id}>')

        # Unicode emoji — broad range covering most standard emoji blocks
        unicode_pattern = re.compile(
            "[\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002600-\U000027BF"
            "\U0001F900-\U0001F9FF"
            "\U0001FA00-\U0001FA6F"
            "\U0001FA70-\U0001FAFF"
            "\U00002702-\U000027B0"
            "\u2764\u2665\u2666\u2663\u2660"
            "\u231A\u231B\u23E9-\u23F3\u23F8-\u23FA"
            "\u25AA\u25AB\u25B6\u25C0\u25FB-\u25FE"
            "\u2614\u2615\u2648-\u2653\u267F\u2693\u26A1\u26AA\u26AB"
            "\u26BD\u26BE\u26C4\u26C5\u26CE\u26D4\u26EA\u26F2\u26F3"
            "\u26F5\u26FA\u26FD\u2702\u2705\u2708-\u270D\u270F]",
            flags=re.UNICODE
        )
        for char in unicode_pattern.findall(content):
            if char not in seen and char.strip():
                seen.add(char)
                collected.append(char)

        if not collected:
            return await ctx.reply(embed=create_embed(
                'error',
                title='No Emojis Found',
                description="That message doesn't contain any recognisable emojis!"
            ))

        # Cap at 20 (Discord's reaction cap per message)
        cap = 20
        to_react = collected[:cap]
        skipped = len(collected) - len(to_react)

        # ── React to the target message ────────────────────────────────────────
        added = 0
        failed_emojis = []
        for emoji in to_react:
            try:
                await target_msg.add_reaction(emoji)
                added += 1
            except discord.Forbidden:
                return await ctx.reply(embed=create_embed(
                    'error',
                    title='Missing Permission',
                    description="I don't have **Add Reactions** permission in this channel!"
                ))
            except discord.HTTPException:
                failed_emojis.append(str(emoji))

        # ── Confirmation ──────────────────────────────────────────────────────
        desc = f'Added **{added}** reaction{"s" if added != 1 else ""} to [that message]({target_msg.jump_url})!'
        if failed_emojis:
            desc += f'\n⚠️ Could not add: {", ".join(failed_emojis[:5])}'
        if skipped:
            desc += f'\n*(Capped at {cap} reactions — {skipped} skipped)*'

        await ctx.reply(embed=create_embed(
            'success',
            title='Reactions Added! 🎭',
            description=desc
        ), delete_after=8)

        # Clean up the command message
        try:
            await ctx.message.delete()
        except Exception:
            pass

    # ──────────────────────────── stealall ──────────────────────────────
    @commands.command(name='stealall', aliases=['addemojis', 'multisteal'])
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def stealall(self, ctx):
        """Steal all custom emojis from a replied message and add them to the server
        
        Usage: Reply to a message and type ,stealall
        Requires: Manage Emojis permission
        """
        import re
        import aiohttp
        
        # Must be replying to a message
        ref = ctx.message.reference
        if not ref or not ref.message_id:
            return await ctx.reply(embed=create_embed(
                'error',
                title='Reply to a Message!',
                description=(
                    f'You need to **reply** to a message containing custom emojis!\n'
                    f'**Usage:** Reply to a message and type `{config.PREFIX}stealall`'
                )
            ))
        
        try:
            replied_message = ref.resolved or await ctx.channel.fetch_message(ref.message_id)
        except (discord.NotFound, discord.HTTPException):
            return await ctx.reply(embed=create_embed(
                'error',
                title='Message Not Found',
                description='Could not find the message you replied to.'
            ))
        
        # Extract emojis from replied message
        emoji_pattern = r'<(a?):([a-zA-Z0-9_]+):([0-9]+)>'
        emojis_found = re.findall(emoji_pattern, replied_message.content)
        
        if not emojis_found:
            return await ctx.reply(embed=create_embed(
                'error',
                title='No Emoji Found',
                description="The message you replied to doesn't contain any custom emojis!"
            ))
        
        # Remove duplicate emojis from the message content list
        unique_emojis = []
        seen_ids = set()
        for is_animated_str, name, emoji_id in emojis_found:
            if emoji_id not in seen_ids:
                seen_ids.add(emoji_id)
                unique_emojis.append((is_animated_str == 'a', name, emoji_id))
        
        # Cap at 15 emojis per execution to prevent extreme rate limiting
        limit = 15
        to_steal = unique_emojis[:limit]
        
        async with ctx.typing():
            success_emojis = []
            failed_emojis = []
            
            async with aiohttp.ClientSession() as session:
                for is_animated, emoji_name, emoji_id in to_steal:
                    # Check emoji slots
                    emoji_limit = ctx.guild.emoji_limit
                    current_static = len([e for e in ctx.guild.emojis if not e.animated])
                    current_animated = len([e for e in ctx.guild.emojis if e.animated])
                    
                    if is_animated and current_animated >= emoji_limit:
                        failed_emojis.append(f"`{emoji_name}` (animated limit reached)")
                        continue
                    elif not is_animated and current_static >= emoji_limit:
                        failed_emojis.append(f"`{emoji_name}` (static limit reached)")
                        continue
                    
                    extension = 'gif' if is_animated else 'png'
                    emoji_url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{extension}'
                    
                    try:
                        async with session.get(emoji_url) as resp:
                            if resp.status == 404:
                                extension = 'png' if extension == 'gif' else 'gif'
                                emoji_url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{extension}'
                                async with session.get(emoji_url) as resp2:
                                    if resp2.status != 200:
                                        failed_emojis.append(f"`{emoji_name}` (not found)")
                                        continue
                                    emoji_bytes = await resp2.read()
                                    is_animated = extension == 'gif'
                            elif resp.status != 200:
                                failed_emojis.append(f"`{emoji_name}` (download failed)")
                                continue
                            else:
                                emoji_bytes = await resp.read()
                        
                        # Clean emoji name (Discord requirements 2-32 alphanumeric + underscore)
                        cleaned_name = re.sub(r'[^a-zA-Z0-9_]', '', emoji_name)[:32]
                        if len(cleaned_name) < 2:
                            cleaned_name = f'emoji_{emoji_id}'[:32]
                        
                        # Upload emoji
                        new_emoji = await ctx.guild.create_custom_emoji(
                            name=cleaned_name,
                            image=emoji_bytes,
                            reason=f'Multiple emojis stolen by {ctx.author} ({ctx.author.id})'
                        )
                        success_emojis.append(new_emoji)
                        
                    except Exception as e:
                        failed_emojis.append(f"`{emoji_name}` ({str(e)})")
            
            # Build report embed
            embed = discord.Embed(
                title="🎨 Multiple Emoji Stolen Report",
                color=config.COLORS['success'] if success_emojis else config.COLORS['error']
            )
            
            if success_emojis:
                success_list = " ".join([str(e) for e in success_emojis])
                embed.add_field(
                    name=f"✅ Successfully Added ({len(success_emojis)})",
                    value=success_list[:1024],
                    inline=False
                )
            
            if failed_emojis:
                failed_list = "\n".join(failed_emojis)
                embed.add_field(
                    name=f"❌ Failed to Add ({len(failed_emojis)})",
                    value=failed_list[:1024],
                    inline=False
                )
            
            if len(unique_emojis) > limit:
                embed.set_footer(text=f"Showing report for first {limit} emojis (total {len(unique_emojis)} found).")
            else:
                embed.set_footer(text=f"Triggered by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
                
            await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(General(bot))
