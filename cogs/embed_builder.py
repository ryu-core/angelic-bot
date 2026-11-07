"""
Custom Embed Builder Cog
Interactive embed creation using Discord UI
"""
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import config


class EmbedBuilderModal(Modal, title="Custom Embed Builder"):
    """Modal for creating custom embeds"""

    embed_title = TextInput(
        label="Title",
        placeholder="Enter embed title (optional)",
        required=False,
        max_length=256
    )

    description = TextInput(
        label="Description",
        placeholder="Enter embed description",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000
    )

    color = TextInput(
        label="Color (hex code)",
        placeholder="e.g., #9b59b6 or 9b59b6",
        required=False,
        max_length=7
    )

    footer = TextInput(
        label="Footer Text",
        placeholder="Enter footer text (optional)",
        required=False,
        max_length=2048
    )

    image_url = TextInput(
        label="Image URL",
        placeholder="https://example.com/image.png (optional)",
        required=False,
        max_length=500
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        """Handle embed creation"""
        try:
            color = config.COLORS['primary']
            if self.color.value:
                color_str = self.color.value.strip().replace('#', '')
                try:
                    color = int(color_str, 16)
                except ValueError:
                    color = config.COLORS['primary']

            embed = discord.Embed(
                title=self.embed_title.value if self.embed_title.value else None,
                description=self.description.value,
                color=color
            )

            if self.footer.value:
                embed.set_footer(text=self.footer.value)

            if self.image_url.value:
                embed.set_image(url=self.image_url.value)

            view = EmbedPreviewView(embed, interaction.user, self.bot)
            await interaction.response.send_message(
                "**Embed Preview:**",
                embed=embed,
                view=view,
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"Error creating embed: {e}",
                ephemeral=True
            )


class EmbedPreviewView(View):
    """View for previewing and sending the embed"""

    def __init__(self, embed, author, bot):
        super().__init__(timeout=180)
        self.embed = embed
        self.author = author
        self.bot = bot

    async def _send_as_bleed(self, interaction: discord.Interaction):
        channel = interaction.channel
        guild = interaction.guild
        if not channel:
            raise RuntimeError("Could not find the channel to send this embed.")
        if not guild:
            await channel.send(embed=self.embed)
            return

        bot_member = guild.me
        if not bot_member and self.bot.user:
            bot_member = guild.get_member(self.bot.user.id)
        if not bot_member:
            raise RuntimeError("Could not check my webhook permissions in this server.")

        perms = channel.permissions_for(bot_member)
        if not perms.manage_webhooks:
            raise PermissionError("I need Manage Webhooks permission to send embeds as Bleed.")

        webhook = None
        try:
            webhook = await channel.create_webhook(
                name="Bleed",
                reason=f"Custom embed sent by {interaction.user}"
            )
            avatar_url = self.bot.user.display_avatar.url if self.bot.user else None
            await webhook.send(
                embed=self.embed,
                username="Bleed",
                avatar_url=avatar_url,
                wait=True
            )
        finally:
            if webhook:
                try:
                    await webhook.delete(reason="Temporary Bleed embed webhook cleanup")
                except Exception:
                    pass

    @discord.ui.button(label="Send to Channel", style=discord.ButtonStyle.success)
    async def send_button(self, interaction: discord.Interaction, button: Button):
        """Send the embed to the channel"""
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message(
                "Only the embed creator can send this!",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self._send_as_bleed(interaction)
            await interaction.followup.send(
                "Embed sent successfully!",
                ephemeral=True
            )
            self.stop()
        except PermissionError:
            await interaction.followup.send(
                "I need **Manage Webhooks** permission to send this as Bleed.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"Failed to send embed: {e}",
                ephemeral=True
            )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        """Cancel embed creation"""
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message(
                "Only the embed creator can cancel this!",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Embed creation cancelled.",
            ephemeral=True
        )
        self.stop()


class EmbedBuilder(commands.Cog):
    """Custom embed creation commands"""

    def __init__(self, bot):
        self.bot = bot

    @property
    def qualified_name(self):
        return "Customization"

    @commands.command(name='embed', aliases=['createembed', 'customembed'])
    @commands.has_permissions(manage_messages=True)
    async def create_embed(self, ctx):
        """Create a custom embed message.

        Usage: ,embed
        """
        modal = EmbedBuilderModal(self.bot)

        view = OpenModalView(modal)
        embed = discord.Embed(
            title="Custom Embed Builder",
            description=(
                "Click the button below to open the embed builder.\n\n"
                "**You can customize:**\n"
                "- Title\n"
                "- Description\n"
                "- Color (hex code)\n"
                "- Footer text\n"
                "- Image URL\n\n"
                "After filling the form, you'll get a preview before sending."
            ),
            color=config.COLORS['primary']
        )
        await ctx.reply(embed=embed, view=view)

    @create_embed.error
    async def embed_error(self, ctx, error):
        """Error handler for embed command"""
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title=f"{config.EMOJIS.get('error', 'Error')} Missing Permissions",
                description="You need **Manage Messages** permission to create custom embeds!",
                color=config.COLORS['error']
            )
            await ctx.reply(embed=embed)


class OpenModalView(View):
    """View with button to open the embed builder modal"""

    def __init__(self, modal):
        super().__init__(timeout=180)
        self.modal = modal

    @discord.ui.button(label="Open Embed Builder", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: Button):
        """Open the embed builder modal"""
        await interaction.response.send_modal(self.modal)


async def setup(bot):
    await bot.add_cog(EmbedBuilder(bot))
