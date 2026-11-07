import discord
from discord import app_commands
import config

def create_embed(embed_type='info', **kwargs):
    """Create a premium styled embed"""
    
    color_map = {
        'success': config.COLORS['success'],
        'error': config.COLORS['error'],
        'primary': config.COLORS['primary'],
        'secondary': config.COLORS['secondary'],
        'info': config.COLORS['primary']
    }
    
    embed = discord.Embed(
        color=color_map.get(embed_type, config.COLORS['primary']),
        timestamp=discord.utils.utcnow()
    )
    
    embed.set_footer(text='xiel')
    
    if 'title' in kwargs:
        embed.title = kwargs['title']
    if 'description' in kwargs:
        embed.description = kwargs['description']
    if 'fields' in kwargs:
        for field in kwargs['fields']:
            embed.add_field(
                name=field.get('name', '\u200b'),
                value=field.get('value', '\u200b'),
                inline=field.get('inline', False)
            )
    if 'thumbnail' in kwargs:
        embed.set_thumbnail(url=kwargs['thumbnail'])
    if 'image' in kwargs:
        embed.set_image(url=kwargs['image'])
    if 'author' in kwargs:
        author = kwargs['author']
        embed.set_author(
            name=author.get('name', ''),
            icon_url=author.get('icon_url', '')
        )
    
    return embed

def success_embed(title, description):
    """Create a success embed"""
    return create_embed('success', title=f"{config.EMOJIS['success']} {title}", description=description)

def error_embed(title, description):
    """Create an error embed"""
    return create_embed('error', title=f"{config.EMOJIS['error']} {title}", description=description)

def info_embed(title, description):
    """Create an info embed"""
    return create_embed('primary', title=f"{config.EMOJIS['info']} {title}", description=description)

def loading_embed(description='Processing...'):
    """Create a loading embed"""
    return create_embed('secondary', title=f"{config.EMOJIS['loading']} Please Wait", description=description)
