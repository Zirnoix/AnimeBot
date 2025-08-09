# modules/image.py
from typing import Dict, Any, Optional
from io import BytesIO
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageOps
import requests

def _fetch_image(url: Optional[str]) -> Image.Image:
    if not url:
        return Image.new("RGB", (1200, 675), (20, 22, 26))
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGB")
        return img
    except Exception:
        return Image.new("RGB", (1200, 675), (20, 22, 26))

def _fit_cover(img: Image.Image, size=(1200, 675)) -> Image.Image:
    bg = img.copy()
    bg = bg.resize(size, Image.LANCZOS)
    return bg

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    # Essaie DejaVu (souvent dispo), sinon fallback PIL par défaut
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()

def generate_next_card(data, out_path="next_card.png", scale=1.2, blur_radius=12, padding=40):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
    import requests
    from io import BytesIO

    # Charger image de fond
    bg_url = data.get("coverImage", {}).get("extraLarge") or data.get("coverImage", {}).get("large")
    response = requests.get(bg_url)
    bg_img = Image.open(BytesIO(response.content)).convert("RGBA")

    # Fond flouté
    bg_blur = bg_img.filter(ImageFilter.GaussianBlur(blur_radius))

    # Cover
    cover_url = data.get("coverImage", {}).get("large")
    cover_img = Image.open(BytesIO(requests.get(cover_url).content)).convert("RGBA")

    # Taille de la carte (grand format pour éviter perte qualité avant crop)
    card_width = 1280
    card_height = 720
    card = Image.new("RGBA", (card_width, card_height))
    card.paste(bg_blur.resize((card_width, card_height)), (0, 0))

    # Zone du panneau
    panel_height = int(cover_img.height * scale * 0.9)
    panel_y = (card_height - panel_height) // 2
    panel_x = int(card_width * 0.05)

    # Panneau noir semi-transparent
    panel_width = int(card_width * 0.8)
    panel = Image.new("RGBA", (panel_width, panel_height), (0, 0, 0, 160))
    card.paste(panel, (panel_x, panel_y), panel)

    # Cover à gauche
    cover_size = int(panel_height * 0.9)
    cover_x = panel_x + int(panel_height * 0.05)
    cover_y = panel_y + (panel_height - cover_size) // 2
    cover_resized = cover_img.resize((cover_size, cover_size))
    card.paste(cover_resized, (cover_x, cover_y), cover_resized)

    # Police
    font_title = ImageFont.truetype("arial.ttf", int(40 * scale))
    font_info = ImageFont.truetype("arial.ttf", int(26 * scale))

    # Texte
    draw = ImageDraw.Draw(card)
    text_x = cover_x + cover_size + 20
    text_y = cover_y
    draw.text((text_x, text_y), data.get("title", {}).get("romaji", "Inconnu"), font=font_title, fill="white")

    text_y += int(50 * scale)
    draw.text((text_x, text_y), f"Épisode {data.get('episode')}", font=font_info, fill="white")

    text_y += int(35 * scale)
    draw.text((text_x, text_y), " • ".join(data.get("genres", [])), font=font_info, fill="white")

    text_y += int(35 * scale)
    draw.text((text_x, text_y), data.get("when", ""), font=font_info, fill="white")

    # === CROP autour du panneau ===
    crop_left = panel_x - padding
    crop_top = panel_y - padding
    crop_right = panel_x + panel_width + padding
    crop_bottom = panel_y + panel_height + padding

    cropped_card = card.crop((crop_left, crop_top, crop_right, crop_bottom))

    # Sauvegarder
    cropped_card.save(out_path)
    return out_path
