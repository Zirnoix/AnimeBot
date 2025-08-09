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

# Assure-toi d'avoir en haut du fichier:
# from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageOps
# import requests
# from io import BytesIO
# (et _fetch_image, _fit_cover, _load_font déjà définies)

def generate_next_card(
    anime: dict,
    out_path: str = "/tmp/next_card.png",
    scale: float = 1.6,
    panel_scale: float = 0.7,
    blur_base: int = 12,
    crop: bool = True,
    crop_pad: int = 40,
    final_w: int | None = None,   # ex: 900 si tu veux forcer une taille
) -> str:
    # ---------- CANVAS DE TRAVAIL ----------
    base_W, base_H = 1200, 675
    W = int(base_W * scale)
    H = int(base_H * scale)

    cover = _fetch_image(anime.get("cover"))
    bg = _fit_cover(cover, (W, H)).filter(ImageFilter.GaussianBlur(int(blur_base * scale))).convert("RGBA")

    # Vignette radiale + gradient bas
    vignette = Image.new("L", (W, H), 0)
    vg_draw = ImageDraw.Draw(vignette)
    vg_draw.ellipse((-W*0.2, -H*0.2, W*1.2, H*1.2), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(int(120*scale)))
    vg = Image.new("RGBA", (W, H), (0, 0, 0, 170))
    vg.putalpha(ImageOps.invert(vignette))
    bg.alpha_composite(vg)

    grad_h = int(320*scale)
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        grad.putpixel((0, y), int(255*(y/grad_h)))
    grad = grad.resize((W, grad_h))
    g_rgba = Image.new("RGBA", (W, grad_h), (0, 0, 0, 190))
    g_rgba.putalpha(grad)
    bg.alpha_composite(g_rgba, (0, H - grad_h))

    # ---------- PANNEAU ----------
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)

    pad    = int(44  * scale * panel_scale)
    panel_h= int(320 * scale * panel_scale)
    radius = int(32  * scale * panel_scale)
    border = int(2   * scale * panel_scale)

    y0 = H - panel_h - pad
    x0 = pad
    x1 = W - pad
    y1 = H - pad

    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=(0,0,0,120), outline=(255,255,255,50), width=border)

    # Mini-cover
    thumb_w = int(300 * scale * panel_scale)
    ratio = cover.width / cover.height if cover.height else 1
    thumb = cover.copy()
    th = int(thumb_w / ratio) if ratio else thumb_w
    if th > panel_h:
        tw = int(panel_h * ratio)
        th = panel_h
        thumb = thumb.resize((tw, th), Image.LANCZOS)
    else:
        tw = thumb_w
        thumb = thumb.resize((tw, th), Image.LANCZOS)

    ty = y0 + (panel_h - th) // 2
    tx_img = x0 + int(22 * scale * panel_scale)
    panel.alpha_composite(thumb.convert("RGBA"), (tx_img, ty))

    # ---------- TEXTES ----------
    title = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Titre inconnu"
    episode = anime.get("episode") or "?"
    when = anime.get("when") or "date inconnue"
    genres = anime.get("genres") or []
    genres_txt = " • ".join(genres[:4]) if genres else "—"

    # helpers
    def fit_font(text, max_w, start, min_=18):
        size = start
        meas = ImageDraw.Draw(panel).textlength
        while size >= min_:
            f = _load_font(size)
            if meas(text, font=f) <= max_w: return f
            size -= 2
        return _load_font(min_)

    def wrap2(text, font, max_w):
        words = text.split()
        lines, cur = [], ""
        meas = ImageDraw.Draw(panel).textlength
        for w in words:
            t = (cur + " " + w).strip()
            if meas(t, font=font) <= max_w:
                cur = t
            else:
                if cur: lines.append(cur)
                cur = w
                if len(lines) == 2: break
        if len(lines) < 2 and cur: lines.append(cur)
        if len(lines) == 2:
            while lines[1] and meas(lines[1] + "…", font=font) > max_w and font.size > 18:
                lines[1] = lines[1].rsplit(" ", 1)[0] if " " in lines[1] else lines[1][:-1]
            if lines[1]: lines[1] += "…"
        return lines[:2]

    base_title = int(84 * scale * panel_scale)
    base_sub   = int(44 * scale * panel_scale)
    base_meta  = int(36 * scale * panel_scale)

    tx = tx_img + tw + int(28 * scale * panel_scale)
    ty = y0 + int(32 * scale * panel_scale)
    max_w = x1 - tx - int(28 * scale * panel_scale)

    f_title = fit_font(title, max_w, base_title, max(int(32 * scale * panel_scale), 18))
    lines = wrap2(title, f_title, max_w)

    def shadow(txt, xy, font, fill=(255,255,255,245)):
        x, y = xy
        draw.text((x+int(3*scale*panel_scale), y+int(3*scale*panel_scale)), txt, font=font, fill=(0,0,0,180))
        draw.text((x, y), txt, font=font, fill=fill)

    gap_big   = int(8 * scale * panel_scale)
    gap_mid   = int(6 * scale * panel_scale)
    gap_small = int(4 * scale * panel_scale)

    for line in lines:
        shadow(line, (tx, ty), f_title); ty += f_title.size + gap_big

    f_sub  = fit_font(f"Épisode {episode}", max_w, base_sub,  max(int(24 * scale * panel_scale), 16))
    f_meta = fit_font(genres_txt,          max_w, base_meta, max(int(20 * scale * panel_scale), 14))
    f_meta2= fit_font(when,               max_w, base_meta, max(int(20 * scale * panel_scale), 14))

    ty += gap_small
    shadow(f"Épisode {episode}", (tx, ty), f_sub);  ty += f_sub.size + gap_mid
    shadow(genres_txt, (tx, ty), f_meta, (235,235,235,240)); ty += f_meta.size + gap_small
    shadow(when, (tx, ty), f_meta2, (235,235,235,240))

    # ---------- COMPOSE ----------
    bg.alpha_composite(panel)
    out = bg.convert("RGB")

    # ---------- CROP AUTOUR DU PANNEAU ----------
    if crop:
        left   = max(0, x0 - crop_pad)
        top    = max(0, y0 - crop_pad)
        right  = min(W, x1 + crop_pad)
        bottom = min(H, y1 + crop_pad)
        out = out.crop((left, top, right, bottom))

    # ---------- RESIZE FINAL ----------
    if final_w:
        final_h = int(final_w * out.height / out.width)
        out = out.resize((final_w, final_h), Image.LANCZOS)

    out.save(out_path, format="PNG", quality=95)
    return out_path
