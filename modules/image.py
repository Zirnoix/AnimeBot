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
    """
    Carte 1200x675 upscalée (scale) pour une lecture ultra confortable.
    1.6 ≈ 1920x1080, 1.8 ≈ 2160x1215.
    """
    base_W, base_H = 1200, 675
    W = int(base_W * scale)
    H = int(base_H * scale)

    cover = _fetch_image(anime.get("cover"))
    bg = _fit_cover(cover, (W, H)).filter(ImageFilter.GaussianBlur(int(30*scale))).convert("RGBA")

    # Vignette + gradient bas
    vignette = Image.new("L", (W, H), 0)
    vg_draw = ImageDraw.Draw(vignette)
    vg_draw.ellipse((-W*0.2, -H*0.2, W*1.2, H*1.2), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(int(120*scale)))
    vg = Image.new("RGBA", (W, H), (0, 0, 0, 180))
    vg.putalpha(ImageOps.invert(vignette))
    bg.alpha_composite(vg)

    grad_h = int(320*scale)
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        grad.putpixel((0, y), int(255 * (y / grad_h)))
    grad = grad.resize((W, grad_h))
    g_rgba = Image.new("RGBA", (W, grad_h), (0, 0, 0, 200))
    g_rgba.putalpha(grad)
    bg.alpha_composite(g_rgba, (0, H - grad_h))

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)

    pad = int(44*scale)
    panel_h = int(300*scale)
    y0 = H - panel_h - pad
    x0 = pad
    x1 = W - pad
    y1 = H - pad

    draw.rounded_rectangle((x0, y0, x1, y1), radius=int(32*scale), fill=(0, 0, 0, 120), outline=(255, 255, 255, 50), width=int(2*scale))

    # Mini-cover plus grande
    thumb_w = int(300*scale)
    ratio = cover.width / cover.height if cover.height else 1
    thumb = cover.copy()
    th = int(thumb_w / ratio) if ratio != 0 else thumb_w
    if th > panel_h:
        thumb = thumb.resize((int(panel_h*ratio), panel_h), Image.LANCZOS)
        tw, th = thumb.size
    else:
        thumb = thumb.resize((thumb_w, th), Image.LANCZOS)
        tw, th = thumb.size

    ty = y0 + (panel_h - th) // 2
    tx_img = x0 + int(22*scale)
    panel.alpha_composite(thumb.convert("RGBA"), (tx_img, ty))

    # Textes plus gros
    title = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Titre inconnu"
    episode = anime.get("episode") or "?"
    when = anime.get("when") or "date inconnue"
    genres = anime.get("genres") or []
    genres_txt = " • ".join(genres[:4]) if genres else "—"

    f_title = _load_font(int(84*scale))   # était 56 → bien plus grand
    f_sub   = _load_font(int(44*scale))   # "Épisode"
    f_meta  = _load_font(int(36*scale))   # genres + date

    tx = tx_img + tw + int(28*scale)
    ty = y0 + int(32*scale)
    max_w = x1 - tx - int(28*scale)

    def draw_shadowed(txt, xy, font, fill=(255,255,255,245)):
        x, y = xy
        draw.text((x+int(3*scale), y+int(3*scale)), txt, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), txt, font=font, fill=fill)

    # Titre wrap (2 lignes max)
    words = title.split()
    lines, cur = [], ""
    measure = ImageDraw.Draw(panel).textlength
    for w in words:
        test = (cur + " " + w).strip()
        if measure(test, font=f_title) <= max_w:
            cur = test
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    for line in lines[:2]:
        draw_shadowed(line, (tx, ty), f_title); ty += f_title.size + int(8*scale)

    ty += int(8*scale)
    draw_shadowed(f"Épisode {episode}", (tx, ty), f_sub); ty += f_sub.size + int(8*scale)
    draw_shadowed(genres_txt, (tx, ty), f_meta, (235,235,235,240)); ty += f_meta.size + int(6*scale)
    draw_shadowed(when, (tx, ty), f_meta, (235,235,235,240))

    bg.alpha_composite(panel)
    out = bg.convert("RGB")
    out.save(out_path, format="PNG", quality=95)
    return out_path

