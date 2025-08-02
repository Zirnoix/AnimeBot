# restructured_bot/modules/image.py

import io
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .genre_emoji import genre_emojis
from .core import JOURS_FR

def load_font(size: int = 20, bold: bool = False) -> ImageFont.FreeTypeFont:
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def generate_next_image(ep: dict, dt: datetime, tagline: str = "Prochain épisode") -> io.BytesIO | None:
    width, height = 900, 500
    card = Image.new("RGB", (width, height), color=(30, 30, 30))

    # Load background
    try:
        response = requests.get(ep.get("image"), timeout=10)
        bg = Image.open(io.BytesIO(response.content)).convert("RGB").resize((width, height))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=6))
        card.paste(bg)
    except Exception:
        pass

    draw = ImageDraw.Draw(card)

    title = ep.get("title", "Titre inconnu")
    genres = ep.get("genres", [])
    episode_num = ep.get("episode", "?")

    # Fonts
    title_font = load_font(40, bold=True)
    info_font = load_font(24)
    small_font = load_font(18)

    # Draw box overlay
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 180))
    card.paste(overlay, (0, 0), overlay)

    x, y = 50, 40
    draw.text((x, y), title, font=title_font, fill="white")
    y += title_font.getsize(title)[1] + 20

    jour_fr = JOURS_FR.get(dt.strftime("%A"), dt.strftime("%A"))
    horaire = dt.strftime("%d %b %Y • %H:%M")
    draw.text((x, y), f"{jour_fr} → {horaire}", font=info_font, fill=(220, 220, 220))
    y += info_font.getsize(horaire)[1] + 20

    draw.text((x, y), f"Épisode {episode_num}", font=info_font, fill="gold")
    y += info_font.getsize("Ep.")[1] + 20

    draw.text((x, height - 50), tagline, font=small_font, fill=(180, 180, 180))

    # Paste genre emojis
    emoji_size = 42
    emoji_paths = genre_emojis(genres)[:5]
    for i, emoji_path in enumerate(emoji_paths):
        try:
            emoji_img = Image.open(emoji_path).convert("RGBA").resize((emoji_size, emoji_size))
            card.paste(emoji_img, (width - (i+1)*(emoji_size+10), height - emoji_size - 20), emoji_img)
        except Exception:
            continue

    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf
