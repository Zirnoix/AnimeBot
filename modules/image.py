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
    Carte 1200x675 : fond flouté + vignette + panneau verre + mini cover nette.
    Affiche: Titre, Épisode, Genres, Date/heure.
    """
    W, H = 1200, 675
    cover = _fetch_image(anime.get("cover"))
    bg = _fit_cover(cover, (W, H)).filter(ImageFilter.GaussianBlur(30)).convert("RGBA")

    # Vignette radiale douce (assombrit les bords)
    vignette = Image.new("L", (W, H), 0)
    vg_draw = ImageDraw.Draw(vignette)
    vg_draw.ellipse((-W*0.2, -H*0.2, W*1.2, H*1.2), fill=255)  # grand cercle blanc
    vignette = vignette.filter(ImageFilter.GaussianBlur(120))
    # normaliser et inverser (bords sombres)
    vg = Image.new("RGBA", (W, H), (0, 0, 0, 180))
    vg.putalpha(ImageOps.invert(vignette))
    bg.alpha_composite(vg)

    # Bande gradient bas (lisibilité)
    grad = Image.new("L", (1, 300))
    for y in range(300):
        grad.putpixel((0, y), int(255 * (y / 300)))
    grad = grad.resize((W, 300))
    g_rgba = Image.new("RGBA", (W, 300), (0, 0, 0, 190))
    g_rgba.putalpha(grad)
    bg.alpha_composite(g_rgba, (0, H - 300))

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)

    pad = 40
    panel_h = 260
    y0 = H - panel_h - pad
    x0 = pad
    x1 = W - pad
    y1 = H - pad

    # Panneau verre
    draw.rounded_rectangle((x0, y0, x1, y1), radius=28, fill=(0, 0, 0, 110), outline=(255, 255, 255, 45), width=2)

    # Mini cover nette à gauche
    thumb_w = 200
    ratio = cover.width / cover.height if cover.height else 1
    thumb = cover.copy()
    th = int(thumb_w / ratio) if ratio != 0 else thumb_w
    thumb = thumb.resize((thumb_w, th if th <= panel_h else panel_h), Image.LANCZOS)
    # centrer verticalement dans le panneau
    ty = y0 + (panel_h - thumb.height) // 2
    panel.alpha_composite(thumb.convert("RGBA"), (x0 + 18, ty))

    # Textes
    title = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Titre inconnu"
    episode = anime.get("episode") or "?"
    when = anime.get("when") or "date inconnue"
    genres = anime.get("genres") or []
    genres_txt = " • ".join(genres[:4]) if genres else "—"

    f_title = _load_font(56)
    f_sub   = _load_font(32)
    f_meta  = _load_font(28)

    # zone texte à droite de la mini cover
    tx = x0 + 18 + thumb_w + 24
    ty = y0 + 28
    max_w = x1 - tx - 24

    def draw_shadowed(txt, xy, font, fill=(255,255,255,240)):
        x, y = xy
        # ombre
        draw.text((x+2, y+2), txt, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), txt, font=font, fill=fill)

    # Titre multi-lignes
    words = title.split()
    lines, cur = [], ""
    measure = ImageDraw.Draw(panel).textlength
    for w in words:
        test = (cur + " " + w).strip()
        if measure(test, font=f_title) <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    for i, line in enumerate(lines[:2]):  # 2 lignes max pour garder de l'air
        draw_shadowed(line, (tx, ty), f_title); ty += f_title.size + 6

    ty += 6
    draw_shadowed(f"Épisode {episode}", (tx, ty), f_sub, (255,255,255,230)); ty += f_sub.size + 4
    draw_shadowed(genres_txt, (tx, ty), f_meta, (230,230,230,230)); ty += f_meta.size + 4
    draw_shadowed(when, (tx, ty), f_meta, (230,230,230,230))

    bg.alpha_composite(panel)

    out = bg.convert("RGB")
    out.save(out_path, format="PNG", quality=95)
    return out_path
