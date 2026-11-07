"""
Welcome Card Generator
Creates aesthetic welcome/goodbye cards for new/leaving members
"""

import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from typing import Optional
import os


class WelcomeCardGenerator:
    """Generate welcome card images for new members"""
    
    def __init__(self, width: int = 1200, height: int = 400):
        """Initialize welcome card generator"""
        self.width = width
        self.height = height
        self.canvas = None
        self.draw = None
    
    async def download_avatar(self, avatar_url: str) -> Optional[Image.Image]:
        """Download user avatar from URL"""
        try:
            print(f"📥 Downloading avatar from: {avatar_url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.read()
                        print(f"✅ Avatar downloaded successfully ({len(data)} bytes)")
                        return Image.open(io.BytesIO(data))
                    else:
                        print(f"❌ Avatar download failed: HTTP {response.status}")
        except Exception as e:
            print(f"❌ Failed to download avatar: {e}")
            return None
    
    def create_circular_avatar(self, avatar: Image.Image, size: int = 200) -> Image.Image:
        """Create circular avatar with glow effect"""
        avatar = avatar.resize((size, size), Image.Resampling.LANCZOS)
        
        # Create circular mask
        mask = Image.new('L', (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)
        
        # Apply mask
        output = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        output.paste(avatar, (0, 0))
        output.putalpha(mask)
        
        return output
    
    async def generate(
        self,
        avatar_url: str,
        username: str,
        discriminator: str,
        server_name: str,
        member_count: int,
        card_type: str = "welcome"  # "welcome" or "goodbye"
    ) -> io.BytesIO:
        """
        Generate welcome/goodbye card
        
        Args:
            avatar_url: User avatar URL
            username: Username
            discriminator: User discriminator/tag
            server_name: Server name
            member_count: Total member count
            card_type: "welcome" or "goodbye"
        """
        # Load custom background or create gradient
        background_path = f"assets/{card_type}_background.png"
        try:
            if os.path.exists(background_path):
                self.canvas = Image.open(background_path).convert('RGB')
                self.canvas = self.canvas.resize((self.width, self.height), Image.Resampling.LANCZOS)
            else:
                # Create gradient background
                self.canvas = Image.new('RGB', (self.width, self.height))
                draw_temp = ImageDraw.Draw(self.canvas)
                
                if card_type == "welcome":
                    # Green-blue gradient for welcome
                    for y in range(self.height):
                        ratio = y / self.height
                        r = int(46 - ratio * 20)
                        g = int(204 - ratio * 50)
                        b = int(113 + ratio * 100)
                        draw_temp.line([(0, y), (self.width, y)], fill=(r, g, b))
                else:
                    # Red-orange gradient for goodbye
                    for y in range(self.height):
                        ratio = y / self.height
                        r = int(231 - ratio * 30)
                        g = int(76 + ratio * 50)
                        b = int(60 - ratio * 20)
                        draw_temp.line([(0, y), (self.width, y)], fill=(r, g, b))
        except:
            # Fallback gradient
            self.canvas = Image.new('RGB', (self.width, self.height))
            draw_temp = ImageDraw.Draw(self.canvas)
            for y in range(self.height):
                ratio = y / self.height
                r = int(46 - ratio * 20)
                g = int(204 - ratio * 50)
                b = int(113 + ratio * 100)
                draw_temp.line([(0, y), (self.width, y)], fill=(r, g, b))
        
        self.draw = ImageDraw.Draw(self.canvas)
        
        # Load fonts
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
            name_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
            info_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 35)
        except:
            try:
                title_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 80)
                name_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 50)
                info_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 35)
            except:
                title_font = ImageFont.load_default()
                name_font = ImageFont.load_default()
                info_font = ImageFont.load_default()
        
        # Download and place avatar (TOP RIGHT corner)
        avatar_size = 150  # Smaller size for top right
        avatar = await self.download_avatar(avatar_url)
        
        if avatar:
            circular = self.create_circular_avatar(avatar.convert('RGB'), avatar_size)
            # Position in top right corner with padding
            avatar_x = self.width - avatar_size - 40
            avatar_y = 40
            print(f"🎨 Avatar position: TOP RIGHT at ({avatar_x}, {avatar_y})")  # Debug
            
            # Add glow effect
            glow_size = avatar_size + 20
            glow = Image.new('RGBA', (glow_size, glow_size), (255, 255, 255, 0))
            glow_draw = ImageDraw.Draw(glow)
            for i in range(10, 0, -1):
                alpha = int(30 - i * 2)
                glow_draw.ellipse([10-i, 10-i, glow_size-10+i, glow_size-10+i], 
                                fill=(255, 255, 255, alpha))
            
            # Paste glow then avatar
            self.canvas = self.canvas.convert('RGBA')
            self.canvas.paste(glow, (avatar_x - 10, avatar_y - 10), glow)
            self.canvas.paste(circular, (avatar_x, avatar_y), circular)
            self.canvas = self.canvas.convert('RGB')
            self.draw = ImageDraw.Draw(self.canvas)
            print(f"✅ Avatar pasted successfully to canvas")
        
        # Text area (FULL WIDTH CENTER since avatar is now in corner)
        text_start_x = 50  # Left padding
        text_area_width = self.width - 100  # Full width with padding
        center_y = self.height // 2 - 30  # Slightly higher to avoid cloud area
        
        # Welcome/Goodbye text (CENTERED)
        title_text = "WELCOME!" if card_type == "welcome" else "GOODBYE!"
        bbox = self.draw.textbbox((0, 0), title_text, font=title_font)
        title_width = bbox[2] - bbox[0]
        title_x = text_start_x + (text_area_width - title_width) // 2  # Center in available space
        title_y = center_y - 90
        
        # Shadow
        self.draw.text((title_x + 4, title_y + 4), title_text, font=title_font, fill=(0, 0, 0, 100))
        self.draw.text((title_x, title_y), title_text, font=title_font, fill=(255, 255, 255))
        
        # Username (CENTERED)
        full_name = username if not discriminator or discriminator == "0" else f"{username}#{discriminator}"
        bbox = self.draw.textbbox((0, 0), full_name, font=name_font)
        name_width = bbox[2] - bbox[0]
        name_x = text_start_x + (text_area_width - name_width) // 2
        name_y = center_y - 10
        self.draw.text((name_x + 2, name_y + 2), full_name, font=name_font, fill=(0, 0, 0, 80))
        self.draw.text((name_x, name_y), full_name, font=name_font, fill=(255, 255, 255))
        
        # Server info (CENTERED)
        if card_type == "welcome":
            info_text = f"Welcome to {server_name}!"
        else:
            info_text = f"Goodbye from {server_name}"
        
        bbox = self.draw.textbbox((0, 0), info_text, font=info_font)
        info_width = bbox[2] - bbox[0]
        info_x = text_start_x + (text_area_width - info_width) // 2
        info_y = center_y + 50
        self.draw.text((info_x, info_y), info_text, font=info_font, fill=(240, 240, 240))
        
        # Member count (CENTERED, adjusted to be visible above clouds)
        if card_type == "welcome":
            count_text = f"You are member #{member_count:,}"
        else:
            count_text = f"{member_count:,} members remaining"
        
        bbox = self.draw.textbbox((0, 0), count_text, font=info_font)
        count_width = bbox[2] - bbox[0]
        count_x = text_start_x + (text_area_width - count_width) // 2
        count_y = info_y + 45
        self.draw.text((count_x, count_y), count_text, font=info_font, fill=(220, 220, 220))
        
        # Convert to BytesIO
        output = io.BytesIO()
        self.canvas.save(output, format='PNG', quality=95)
        output.seek(0)
        
        return output
