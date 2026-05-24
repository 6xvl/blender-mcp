"""Generate side-label textures: solid color + big letter centered."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path(__file__).parent
SIZE = 512

SIDES = {
    "TOP":    ("T", (255,  60,  60)),
    "BOTTOM": ("B", (110,  20,  20)),
    "FRONT":  ("F", ( 60, 220,  80)),
    "BACK":   ("K", ( 20, 100,  40)),
    "LEFT":   ("L", ( 60,  90, 240)),
    "RIGHT":  ("R", ( 80, 220, 240)),
}

def load_font(px):
    for cand in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"):
        try: return ImageFont.truetype(cand, px)
        except: pass
    return ImageFont.load_default()

font = load_font(380)
for side, (letter, bg) in SIDES.items():
    img = Image.new("RGB", (SIZE, SIZE), bg)
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), letter, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (SIZE - w) // 2 - bbox[0]
    y = (SIZE - h) // 2 - bbox[1]
    d.text((x, y), letter, fill=(255, 255, 255), font=font)
    path = OUT / f"{side}.png"
    img.save(path)
    print(f"{path}  ({letter})")
