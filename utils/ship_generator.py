"""
Ship Image Generator
Creates aesthetic compatibility/ship images with two users
"""

import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont
from typing import Optional
import os


class ShipImageGenerator:
    """Generate ship/compatibility images with two users"""
    
    def __init__(self, width: int = 1200, height: int = 400):
        """Initialize ship image generator"""
        self.width = width
        self.height = height
        self.canvas = None
        self.draw = None
    
    async def download_avatar(self, avatar_url: str) -> Optional[Image.Image]:
        """Download user avatar from URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.read()
                        return Image.open(io.BytesIO(data))
        except Exception as e:
            print(f"Failed to download avatar: {e}")
            return None
    
    def create_circular_avatar(self, avatar: Image.Image, size: int = 200) -> Image.Image:
        """Create circular avatar with border"""
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
    
    def draw_heart(self, x: int, y: int, size: int, color: tuple, filled: bool = True):
        """Draw a heart shape"""
        # Simplified heart using circles and polygon
        fill_color = color if filled else None
        outline_color = color if not filled else None
        width = 3 if not filled else 0
        
        # Two circles for top of heart
        r = size // 4
        self.draw.ellipse([x - r, y, x + r, y + 2*r], fill=fill_color, outline=outline_color, width=width)
        self.draw.ellipse([x + size//2 - r, y, x + size//2 + r, y + 2*r], fill=fill_color, outline=outline_color, width=width)
        
        # Triangle for bottom
        points = [
            (x - r, y + r),  # Left
            (x + size//2 + r, y + r),  # Right
            (x + size//4, y + size)  # Bottom point
        ]
        self.draw.polygon(points, fill=fill_color, outline=outline_color)
    
    def calculate_compatibility(self, user1_id: int, user2_id: int) -> int:
        """Calculate compatibility percentage — random each time.
        Special case: two specific users always get 100%.
        """
        import random as _random

        # Hardcoded 100% for a specific pair
        SPECIAL_PAIR = {868065615758368789, 1048961628051349514}
        if {user1_id, user2_id} == SPECIAL_PAIR:
            return 100

        # Fully random every time (20-100)
        return _random.randint(20, 100)
    
    async def generate(
        self,
        avatar1_url: str,
        avatar2_url: str,
        username1: str,
        username2: str,
        user1_id: int,
        user2_id: int
    ) -> io.BytesIO:
        """
        Generate ship image
        
        Args:
            avatar1_url: First user avatar URL
            avatar2_url: Second user avatar URL
            username1: First username
            username2: Second username
            user1_id: First user ID (for compatibility calc)
            user2_id: Second user ID
        """
        # Load custom background or create gradient
        background_path = "assets/ship_background.png"
        try:
            if os.path.exists(background_path):
                self.canvas = Image.open(background_path).convert('RGB')
                self.canvas = self.canvas.resize((self.width, self.height), Image.Resampling.LANCZOS)
            else:
                # Create pink-red gradient background
                self.canvas = Image.new('RGB', (self.width, self.height))
                draw_temp = ImageDraw.Draw(self.canvas)
                for y in range(self.height):
                    ratio = y / self.height
                    r = int(255 - ratio * 50)
                    g = int(105 + ratio * 50)
                    b = int(180 - ratio * 50)
                    draw_temp.line([(0, y), (self.width, y)], fill=(r, g, b))
        except:
            # Fallback gradient
            self.canvas = Image.new('RGB', (self.width, self.height))
            draw_temp = ImageDraw.Draw(self.canvas)
            for y in range(self.height):
                ratio = y / self.height
                r = int(255 - ratio * 50)
                g = int(105 + ratio * 50)
                b = int(180 - ratio * 50)
                draw_temp.line([(0, y), (self.width, y)], fill=(r, g, b))
        
        self.draw = ImageDraw.Draw(self.canvas)
        
        # Load fonts
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 70)
            name_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
            percent_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90)
        except:
            try:
                title_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 70)
                name_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 40)
                percent_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 90)
            except:
                title_font = ImageFont.load_default()
                name_font = ImageFont.load_default()
                percent_font = ImageFont.load_default()
        
        # Calculate compatibility
        compatibility = self.calculate_compatibility(user1_id, user2_id)
        
        # Download and place avatars
        avatar_size = 180
        avatar1 = await self.download_avatar(avatar1_url)
        avatar2 = await self.download_avatar(avatar2_url)
        
        # Left avatar
        if avatar1:
            circular1 = self.create_circular_avatar(avatar1.convert('RGB'), avatar_size)
            avatar1_x = 120
            avatar1_y = (self.height - avatar_size) // 2
            self.canvas.paste(circular1, (avatar1_x, avatar1_y), circular1)
            
            # Username below
            bbox = self.draw.textbbox((0, 0), username1, font=name_font)
            text_width = bbox[2] - bbox[0]
            name_x = avatar1_x + (avatar_size - text_width) // 2
            self.draw.text((name_x, avatar1_y + avatar_size + 15), username1, font=name_font, fill=(255, 255, 255))
        
        # Right avatar
        if avatar2:
            circular2 = self.create_circular_avatar(avatar2.convert('RGB'), avatar_size)
            avatar2_x = self.width - avatar_size - 120
            avatar2_y = (self.height - avatar_size) // 2
            self.canvas.paste(circular2, (avatar2_x, avatar2_y), circular2)
            
            # Username below
            bbox = self.draw.textbbox((0, 0), username2, font=name_font)
            text_width = bbox[2] - bbox[0]
            name_x = avatar2_x + (avatar_size - text_width) // 2
            self.draw.text((name_x, avatar2_y + avatar_size + 15), username2, font=name_font, fill=(255, 255, 255))
        
        # Center area - hearts and percentage
        center_x = self.width // 2
        center_y = self.height // 2
        
        # Draw multiple hearts
        heart_color = (255, 255, 255)
        self.draw_heart(center_x - 60, center_y - 80, 40, heart_color, filled=True)
        self.draw_heart(center_x + 20, center_y - 80, 40, heart_color, filled=True)
        self.draw_heart(center_x - 20, center_y - 100, 50, (255, 192, 203), filled=True)
        
        # Compatibility percentage
        percent_text = f"{compatibility}%"
        bbox = self.draw.textbbox((0, 0), percent_text, font=percent_font)
        text_width = bbox[2] - bbox[0]
        percent_x = center_x - text_width // 2
        percent_y = center_y - 20
        
        # Shadow
        self.draw.text((percent_x + 3, percent_y + 3), percent_text, font=percent_font, fill=(0, 0, 0, 100))
        self.draw.text((percent_x, percent_y), percent_text, font=percent_font, fill=(255, 255, 255))
        
        # "Compatibility" text below
        compat_text = "COMPATIBILITY"
        bbox = self.draw.textbbox((0, 0), compat_text, font=name_font)
        text_width = bbox[2] - bbox[0]
        compat_x = center_x - text_width // 2
        self.draw.text((compat_x, percent_y + 100), compat_text, font=name_font, fill=(255, 255, 255))
        
        # Convert to BytesIO
        output = io.BytesIO()
        self.canvas.save(output, format='PNG', quality=95)
        output.seek(0)
        
        return output
