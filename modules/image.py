# modules/image.py (extrait)
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
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return Image.new("RGB", (1200, 675), (20, 22, 26))

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()

def generate_next_card(
    anime: Dict[str, Any],
    out_path: str = "/tmp/next_card.png",
    scale: float = 1.2,
    blur: int = 10,
    padding: int = 40
) -> str:
    """
    Génère une carte compacte: fond flouté + panneau verre + mini-cover + crop autour du panneau.
    `anime` doit contenir: cover (URL), title_romaji/english/native, episode, genres (list), when (str).
    """
    # --- Canvas de travail (grand, puis on croppe) ---
    W, H = int(1400 * scale), int(800 * scale)

    cover = _fetch_image(anime.get("cover"))
    bg = cover.copy().resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(int(blur * scale))).convert("RGBA")

    # vignette douce
    vignette = Image.new("L", (W, H), 0)
    dvg = ImageDraw.Draw(vignette)
    dvg.ellipse((-W*0.2, -H*0.2, W*1.2, H*1.2), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(int(100 * scale)))
    shade = Image.new("RGBA", (W, H), (0,0,0,170))
    shade.putalpha(ImageOps.invert(vignette))
    bg.alpha_composite(shade)

    # gradient bas léger (améliore lisibilité)
    grad_h = int(240 * scale)
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        grad.putpixel((0, y), int(255 * (y / grad_h)))
    grad = grad.resize((W, grad_h))
    g_rgba = Image.new("RGBA", (W, grad_h), (0, 0, 0, 180))
    g_rgba.putalpha(grad)
    bg.alpha_composite(g_rgba, (0, H - grad_h))

    panel = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(panel)

    # --- Dimensions panneau + mini-cover ---
    pad      = int(36 * scale)
    panel_h  = int(260 * scale)
    radius   = int(26 * scale)
    border   = int(2  * scale)

    # centré verticalement
    y0 = H - panel_h - pad
    x0 = pad
    x1 = W - pad
    y1 = H - pad

    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=(0,0,0,120), outline=(255,255,255,45), width=border)

    # mini-cover
    thumb_w = int(220 * scale)
    ratio = cover.width / cover.height if cover.height else 1
    th = int(thumb_w / ratio) if ratio else thumb_w
    if th > panel_h:
        tw = int(panel_h * ratio); th = panel_h
        thumb = cover.resize((tw, th), Image.LANCZOS)
    else:
        tw = thumb_w
        thumb = cover.resize((tw, th), Image.LANCZOS)

    tx_img = x0 + int(18 * scale)
    ty_img = y0 + (panel_h - th)//2
    panel.alpha_composite(thumb.convert("RGBA"), (tx_img, ty_img))

    # --- Textes ---
    title = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Titre inconnu"
    episode = anime.get("episode") or "?"
    when = anime.get("when") or "date inconnue"
    genres = anime.get("genres") or []
    genres_txt = " • ".join(genres[:4]) if genres else "—"

    # helpers
    def textw(t, f): return ImageDraw.Draw(panel).textlength(t, font=f)
    def draw_shadowed(txt, xy, f, fill=(255,255,255,240)):
        x,y = xy
        ImageDraw.Draw(panel).text((x+int(2*scale), y+int(2*scale)), txt, font=f, fill=(0,0,0,180))
        ImageDraw.Draw(panel).text((x,y), txt, font=f, fill=fill)

    base_title = _load_font(int(50 * scale))  # titre
    base_sub   = _load_font(int(40 * scale))  # épisode
    base_meta  = _load_font(int(36 * scale))  # genres + date

    tx = tx_img + tw + int(20 * scale)
    ty = y0 + int(22 * scale)
    max_w = x1 - tx - int(18 * scale)

    # wrap titre sur 2 lignes + ellipsis si besoin
    def wrap_two_lines(text, font, max_w):
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if textw(t, font) <= max_w:
                cur = t
            else:
                if cur: lines.append(cur)
                cur = w
                if len(lines) == 2: break
        if len(lines) < 2 and cur: lines.append(cur)
        if len(lines) == 2 and textw(lines[1], font) > max_w:
            while lines[1] and textw(lines[1] + "…", font) > max_w:
                lines[1] = lines[1][:-1]
            lines[1] += "…"
        return lines[:2]

    title_lines = wrap_two_lines(title, base_title, max_w)
    for line in title_lines:
        draw_shadowed(line, (tx, ty), base_title); ty += base_title.size + int(6*scale)

    ty += int(2*scale)
    draw_shadowed(f"Épisode {episode}", (tx, ty), base_sub); ty += base_sub.size + int(4*scale)
    draw_shadowed(genres_txt, (tx, ty), base_meta, (230,230,230,240)); ty += base_meta.size + int(2*scale)
    draw_shadowed(when, (tx, ty), base_meta, (230,230,230,240))

    # --- Composite + CROP autour du panneau ---
    bg.alpha_composite(panel)
    # zone panneau + padding
    crop_left   = max(0, x0 - padding)
    crop_top    = max(0, y0 - padding)
    crop_right  = min(W, x1 + padding)
    crop_bottom = min(H, y1 + padding)
    out = bg.crop((crop_left, crop_top, crop_right, crop_bottom)).convert("RGB")

    out.save(out_path, format="PNG", quality=95)
    return out_path
