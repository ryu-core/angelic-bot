"""
Quote Image Generator - Bleed Style
Mimics Bleed bot's clean, minimal quote design
"""

import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from typing import Optional
import os


class QuoteImageGenerator:
    """Generate Bleed-style quote images: avatar left, quote right, black background"""
    
    def __init__(self, width: int = 1200, height: int = 630):
        """Initialize quote image generator"""
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
    
    def get_dynamic_font_size(self, text_length: int) -> int:
        """Calculate font size based on text length"""
        if text_length < 15:
            return 120  # Large for short quotes
        elif text_length < 30:
            return 100
        elif text_length < 50:
            return 85
        elif text_length < 80:
            return 70
        elif text_length < 120:
            return 60
        else:
            return 50
    
    def wrap_text(self, text: str, font: ImageFont, max_width: int) -> list:
        """Wrap text to fit within max width"""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = self.draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
            
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines
    
    async def generate(
        self,
        quote_text: str,
        author: Optional[str] = None,
        avatar_url: Optional[str] = None,
        username: Optional[str] = None,
        theme: str = "ocean"  # Ignored, kept for compatibility
    ) -> io.BytesIO:
        """
        Generate Bleed-style quote image
        
        Args:
            quote_text: The quote text
            author: Ignored (using username instead)
            avatar_url: User avatar URL
            username: User name shown as "- username"
            theme: Ignored (using custom background)
        """
        # Load custom background image (wavy gradient)
        background_path = "assets/quote_background.png"
        try:
            if os.path.exists(background_path):
                self.canvas = Image.open(background_path).convert('RGB')
                self.canvas = self.canvas.resize((self.width, self.height), Image.Resampling.LANCZOS)
            else:
                # Fallback to black if image not found
                print(f"Background not found at {background_path}, using black")
                self.canvas = Image.new('RGB', (self.width, self.height), (0, 0, 0))
        except Exception as e:
            print(f"Failed to load background: {e}, using black")
            self.canvas = Image.new('RGB', (self.width, self.height), (0, 0, 0))
        
        self.draw = ImageDraw.Draw(self.canvas)
        
        # White text
        text_color = (255, 255, 255)
        
        # Calculate font size
        font_size = self.get_dynamic_font_size(len(quote_text))
        
        # Load fonts - Linux first (Pterodactyl)
        try:
            quote_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
            username_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            try:
                quote_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
                username_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 40)
            except:
                try:
                    quote_font = ImageFont.truetype("fonts/Poppins-Regular.ttf", font_size)
                    username_font = ImageFont.truetype("fonts/Poppins-Regular.ttf", 40)
                except:
                    quote_font = ImageFont.load_default()
                    username_font = ImageFont.load_default()
        
        # Add avatar on LEFT side if available
        avatar_width = 550  # Wider for more prominence (was 450)
        if avatar_url:
            avatar_img = await self.download_avatar(avatar_url)
            if avatar_img:
                # Crop to square and resize to fill left side
                avatar_img = avatar_img.convert('RGB')
                
                # Crop to square (center crop)
                width, height = avatar_img.size
                size = min(width, height)
                left = (width - size) // 2
                top = (height - size) // 2
                avatar_img = avatar_img.crop((left, top, left + size, top + size))
                
                # Zoom in slightly (1.1x) for closer crop like Bleed
                zoom_size = int(size * 1.1)
                avatar_img = avatar_img.resize((zoom_size, zoom_size), Image.Resampling.LANCZOS)
                
                # Crop back to original size (center)
                zoom_offset = (zoom_size - size) // 2
                avatar_img = avatar_img.crop((zoom_offset, zoom_offset, zoom_offset + size, zoom_offset + size))
                
                # Resize to fill height
                avatar_img = avatar_img.resize((avatar_width, self.height), Image.Resampling.LANCZOS)
                
                # Create gradient fade effect on right edge (like Bleed)
                # Create alpha mask for gradient fade
                fade_width = 150  # Width of fade effect
                mask = Image.new('L', (avatar_width, self.height), 255)
                mask_draw = ImageDraw.Draw(mask)
                
                # Draw gradient fade on right edge
                for x in range(fade_width):
                    # Calculate alpha (255 = opaque, 0 = transparent)
                    alpha = int(255 * (1 - (x / fade_width)))
                    mask_draw.line([(avatar_width - fade_width + x, 0), (avatar_width - fade_width + x, self.height)], fill=alpha)
                
                # Convert avatar to RGBA and apply mask
                avatar_img = avatar_img.convert('RGBA')
                avatar_img.putalpha(mask)
                
                # Paste on left with transparency
                self.canvas.paste(avatar_img, (0, 0), avatar_img)
        
        # Text area (RIGHT side)
        text_start_x = avatar_width + 60  # Start after avatar with padding
        text_max_width = self.width - text_start_x - 60  # Padding on right
        
        # Wrap text
        wrapped_lines = self.wrap_text(quote_text, quote_font, text_max_width)
        
        # Calculate spacing
        line_spacing = int(font_size * 1.2)
        total_text_height = len(wrapped_lines) * line_spacing
        
        # Username height
        username_height = 60 if username else 0
        available_height = self.height - 100
        
        # Smart fitting - reduce size if too tall
        attempts = 0
        while total_text_height + username_height > available_height and font_size > 30 and attempts < 10:
            font_size -= 5
            attempts += 1
            
            # Reload font
            try:
                quote_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
            except:
                try:
                    quote_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
                except:
                    quote_font = ImageFont.load_default()
            
            wrapped_lines = self.wrap_text(quote_text, quote_font, text_max_width)
            line_spacing = int(font_size * 1.2)
            total_text_height = len(wrapped_lines) * line_spacing
        
        # Center text vertically
        start_y = (self.height - total_text_height - username_height) // 2
        
        # Draw quote text
        for i, line in enumerate(wrapped_lines):
            y = start_y + (i * line_spacing)
            self.draw.text((text_start_x, y), line, font=quote_font, fill=text_color)
        
        # Add username as "- USERNAME" below quote
        if username:
            username_text = f"- {username}"
            username_y = start_y + total_text_height + 20
            self.draw.text((text_start_x, username_y), username_text, font=username_font, fill=text_color)
        
        # Convert to BytesIO
        output = io.BytesIO()
        self.canvas.save(output, format='PNG', quality=95)
        output.seek(0)
        
        return output
