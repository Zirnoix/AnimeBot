# modules/image.py
from typing import Dict, Any, Optional
from io import BytesIO
from PIL import Image, ImageFilter, ImageDraw, ImageFont
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

def generate_next_card(anime: Dict[str, Any], out_path: str = "/tmp/next_card.png") -> str:
    """
    Crée une image 1200x675 avec fond flouté + overlay infos.
    anime = { title_*, episode, airingAt (déjà formaté si tu veux), cover, genres }
    """
    W, H = 1200, 675
    cover = _fetch_image(anime.get("cover"))
    bg = _fit_cover(cover, (W, H)).filter(ImageFilter.GaussianBlur(20))

    # assombrir le fond
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 110))
    bg = bg.convert("RGBA")
    bg.alpha_composite(dark)

    # zone info (panneau semi-transparent)
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    # rectangle en bas
    pad = 40
    panel_h = 280
    draw.rounded_rectangle(
        (pad, H - panel_h - pad, W - pad, H - pad),
        radius=24,
        fill=(0, 0, 0, 130),
        outline=(255, 255, 255, 40),
        width=2
    )

    # textes
    title = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Titre inconnu"
    episode = anime.get("episode") or "?"
    when = anime.get("when") or "date inconnue"
    genres = anime.get("genres") or []
    genres_txt = " • ".join(genres[:4]) if genres else "—"

    f_title = _load_font(54)
    f_sub   = _load_font(30)
    f_meta  = _load_font(26)

    # positions
    x = pad + 40
    y = H - panel_h - pad + 40

    # Titre (retour à la ligne si besoin)
    max_w = W - (pad + 40) - pad
    def draw_multiline(text, font, x, y, line_spacing=10):
        lines = []
        words = text.split()
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if ImageDraw.Draw(panel).textlength(test, font=font) <= max_w:
                cur = test
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        for i, line in enumerate(lines):
            draw.text((x, y), line, fill=(255, 255, 255, 240), font=font)
            y += font.size + line_spacing
        return y

    y = draw_multiline(title, f_title, x, y, line_spacing=6)
    y += 6
    draw.text((x, y), f"Épisode {episode}", fill=(255, 255, 255, 220), font=f_sub)
    y += f_sub.size + 6
    draw.text((x, y), genres_txt, fill=(220, 220, 220, 220), font=f_meta)
    y += f_meta.size + 6
    draw.text((x, y), when, fill=(220, 220, 220, 220), font=f_meta)

    # composite panel over bg
    bg.alpha_composite(panel)

    out = bg.convert("RGB")
    out.save(out_path, format="PNG", quality=95)
    return out_path
