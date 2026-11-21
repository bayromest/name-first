"""Draw the icon and the social preview image.

Usage: python tools/make_images.py   (needs pillow)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = "C:/Windows/Fonts/segoeui.ttf"
FONT_BOLD = "C:/Windows/Fonts/segoeuib.ttf"
ORANGE = (255, 160, 40)   # Blender's selected-object outline
BG = (32, 32, 32)


def icon(size=256):
    s = size * 4 / 256  # drawn at 4x on a 256 grid, then downsampled
    w = round(256 * s)
    im = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, w - 1), radius=56 * s, fill=(48, 48, 48))
    # A text field, like Blender's rename popup.
    x0, y0, x1, y1 = 28 * s, 92 * s, 228 * s, 164 * s
    d.rounded_rectangle((x0, y0, x1, y1), radius=14 * s, fill=(24, 24, 24), outline=(70, 70, 70), width=round(3 * s))
    font = ImageFont.truetype(FONT_BOLD, round(44 * s))
    text = "Name"
    tx, ty = x0 + 20 * s, (y0 + y1) / 2
    d.text((tx, ty), text, font=font, fill=(236, 236, 236), anchor="lm")
    cx = tx + d.textlength(text, font=font) + 8 * s
    d.rounded_rectangle((cx, y0 + 16 * s, cx + 7 * s, y1 - 16 * s), radius=3 * s, fill=ORANGE)
    return im.resize((size, size), Image.LANCZOS)


def social():
    im = Image.new("RGB", (1280, 640), BG)
    d = ImageDraw.Draw(im)
    preview = Image.open(ROOT / "assets" / "preview.png").convert("RGB")
    preview = preview.resize((560, 560), Image.LANCZOS)
    mask = Image.new("L", preview.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 559, 559), radius=24, fill=255)
    im.paste(preview, (680, 40), mask)
    im.paste(icon(96), (80, 150), icon(96))
    d.text((80, 270), "Name First", font=ImageFont.truetype(FONT_BOLD, 72), fill=(236, 236, 236))
    body = ImageFont.truetype(FONT, 30)
    for i, line in enumerate(["Name every object the moment", "you add it, like a variable.", "", "A tiny Blender extension."]):
        d.text((82, 370 + i * 42), line, font=body, fill=(160, 160, 160))
    return im


if __name__ == "__main__":
    icon().save(ROOT / "icons" / "name-first.png")
    social().save(ROOT / "assets" / "social-preview.png")
