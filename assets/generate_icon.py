"""
Generate High-Resolution Enterprise Icon for FRAME Desktop Application
"""

import pathlib
from PIL import Image, ImageDraw, ImageFont

assets_dir = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\assets")
assets_dir.mkdir(parents=True, exist_ok=True)
icon_path = assets_dir / "frame_icon.ico"
png_path = assets_dir / "frame_icon.png"

# Create a 256x256 high-resolution icon
size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Dark gradient rounded background
bg_color = (6, 9, 14, 255)
border_color = (0, 191, 165, 255) # Cyan teal
draw.rounded_rectangle([8, 8, size - 8, size - 8], radius=48, fill=bg_color, outline=border_color, width=6)

# Inner gold framing
draw.rounded_rectangle([24, 24, size - 24, size - 24], radius=36, fill=(13, 17, 26, 255), outline=(212, 175, 55, 200), width=4)

# Draw stylized 'F' or geometric sniper reticle
# Reticle circle
cx, cy = size // 2, size // 2
draw.ellipse([cx - 50, cy - 50, cx + 50, cy + 50], outline=(0, 229, 255, 220), width=4)
draw.line([cx - 70, cy, cx - 30, cy], fill=(0, 229, 255, 220), width=4)
draw.line([cx + 30, cy, cx + 70, cy], fill=(0, 229, 255, 220), width=4)
draw.line([cx, cy - 70, cx, cy - 30], fill=(0, 229, 255, 220), width=4)
draw.line([cx, cy + 30, cx, cy + 70], fill=(0, 229, 255, 220), width=4)

# Golden center diamond
diamond = [(cx, cy - 18), (cx + 18, cy), (cx, cy + 18), (cx - 18, cy)]
draw.polygon(diamond, fill=(255, 215, 0, 255))

# Save PNG and ICO
img.save(png_path, format="PNG")
img.save(icon_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

print(f"[ICON] Generated icon at: {icon_path}")
