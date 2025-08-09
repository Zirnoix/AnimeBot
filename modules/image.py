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

def generate_next_card(anime: Dict[str, Any], out_path: str = "/tmp/next_card.png", scale: float = 1.8) -> str:
    # ... tout ton code avant inchangé ...

    panel_h = int(320*scale)  # +20px vs avant pour plus d'air
    # ... reste identique jusqu'à "Textes plus gros" ...

    # ------------ HELPERS D'AUTO-FIT ------------
    def fit_font_size_to_width(text: str, max_w: int, start_size: int, min_size: int = 24) -> ImageFont.FreeTypeFont:
        size = start_size
        while size >= min_size:
            f = _load_font(size)
            if ImageDraw.Draw(panel).textlength(text, font=f) <= max_w:
                return f
            size -= 2
        return _load_font(min_size)

    def wrap_title_two_lines(text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
        words = text.split()
        lines, cur = [], ""
        measure = ImageDraw.Draw(panel).textlength
        for w in words:
            t = (cur + " " + w).strip()
            if measure(t, font=font) <= max_w:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
                if len(lines) == 2:  # déjà 2 lignes -> on coupe
                    break
        if len(lines) < 2 and cur:
            lines.append(cur)

        # Si plus de 2 lignes auraient été nécessaires, ellipsis sur la 2e
        if len(lines) == 2:
            while measure(lines[1] + "…", font=font) > max_w and font.size > 24:
                # raccourcit doucement
                lines[1] = lines[1].rsplit(" ", 1)[0] if " " in lines[1] else lines[1][:-1]
                if not lines[1]:
                    break
            if lines[1]:
                lines[1] += "…"
        return lines[:2]
    # --------------------------------------------

    # Textes plus gros (ta base)
    title = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Titre inconnu"
    episode = anime.get("episode") or "?"
    when = anime.get("when") or "date inconnue"
    genres = anime.get("genres") or []
    genres_txt = " • ".join(genres[:4]) if genres else "—"

    # Tailles de départ “XXL”
    base_title = int(84*scale)
    base_sub   = int(44*scale)
    base_meta  = int(36*scale)

    tx = tx_img + tw + int(28*scale)
    ty = y0 + int(32*scale)
    max_w = x1 - tx - int(28*scale)

    # Ajuste la police du titre à la largeur si nécessaire (avant wrapping)
    f_title_try = fit_font_size_to_width(title, max_w, base_title, min_size=int(36*scale))
    title_lines = wrap_title_two_lines(title, f_title_try, max_w)

    # Si deux lignes + encore trop large, on baisse un cran supplémentaire
    # (rare, mais sécurise)
    if len(title_lines) == 2 and ImageDraw.Draw(panel).textlength(title_lines[0], font=f_title_try) > max_w:
        f_title_try = _load_font(max(int(f_title_try.size - 4), int(32*scale)))
        title_lines = wrap_title_two_lines(title, f_title_try, max_w)

    # Épisode / Genres / Date : on auto-fit aussi
    f_sub  = fit_font_size_to_width(f"Épisode {episode}", max_w, base_sub,  int(28*scale))
    f_meta = fit_font_size_to_width(genres_txt,        max_w, base_meta, int(24*scale))
    f_meta2= fit_font_size_to_width(when,             max_w, base_meta, int(24*scale))

    def draw_shadowed(txt, xy, font, fill=(255,255,255,245)):
        x, y = xy
        draw.text((x+int(3*scale), y+int(3*scale)), txt, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), txt, font=font, fill=fill)

    # Titre (2 lignes max)
    for line in title_lines:
        draw_shadowed(line, (tx, ty), f_title_try)
        ty += f_title_try.size + int(8*scale)

    ty += int(4*scale)
    draw_shadowed(f"Épisode {episode}", (tx, ty), f_sub);  ty += f_sub.size + int(6*scale)
    draw_shadowed(genres_txt, (tx, ty), f_meta, (235,235,235,240)); ty += f_meta.size + int(4*scale)
    draw_shadowed(when, (tx, ty), f_meta2, (235,235,235,240))

    bg.alpha_composite(panel)
    out = bg.convert("RGB")
    out.save(out_path, format="PNG", quality=95)
    return out_path

