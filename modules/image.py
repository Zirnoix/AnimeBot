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

def generate_next_card(
    anime: Dict[str, Any],
    out_path: str = "/tmp/next_card.png",
    scale: float = 1.6,          # Taille de travail (qualité)
    panel_scale: float = 0.7,    # <<< RÉDUIT visuellement la carte (0.6–0.8)
    final_w: int = 1280,         # Taille fichier final (Discord l’affiche pareil)
    blur_base: int = 12          # Flou de fond (plus petit = moins flou)
) -> str:
    """
    Carte avec fond flouté, mini-cover, titre auto-fit (2 lignes max + ellipsis),
    panneau “verre” *compact* via `panel_scale`, puis downscale en `final_w` (16:9).
    """
    # --- TAILLE DE TRAVAIL ---
    base_W, base_H = 1200, 675
    W = int(base_W * scale)
    H = int(base_H * scale)

    cover = _fetch_image(anime.get("cover"))
    bg = _fit_cover(cover, (W, H)).filter(
        ImageFilter.GaussianBlur(int(blur_base * scale))
    ).convert("RGBA")

    # --- VIGNETTE & GRADIENT ---
    vignette = Image.new("L", (W, H), 0)
    vg_draw = ImageDraw.Draw(vignette)
    vg_draw.ellipse((-W * 0.2, -H * 0.2, W * 1.2, H * 1.2), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(int(120 * scale)))
    vg = Image.new("RGBA", (W, H), (0, 0, 0, 180))
    vg.putalpha(ImageOps.invert(vignette))
    bg.alpha_composite(vg)

    grad_h = int(320 * scale)
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        grad.putpixel((0, y), int(255 * (y / grad_h)))
    grad = grad.resize((W, grad_h))
    g_rgba = Image.new("RGBA", (W, grad_h), (0, 0, 0, 200))
    g_rgba.putalpha(grad)
    bg.alpha_composite(g_rgba, (0, H - grad_h))

    # --- PANNEAU COMPACT ---
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

    draw.rounded_rectangle(
        (x0, y0, x1, y1),
        radius=radius,
        fill=(0, 0, 0, 120),
        outline=(255, 255, 255, 50),
        width=border,
    )

    # --- MINI-COVER COMPACTE ---
    thumb_w = int(300 * scale * panel_scale)
    ratio = cover.width / cover.height if cover.height else 1
    thumb = cover.copy()
    th = int(thumb_w / ratio) if ratio != 0 else thumb_w
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

    # --- TEXTES ---
    title = anime.get("title_romaji") or anime.get("title_english") or anime.get("title_native") or "Titre inconnu"
    episode = anime.get("episode") or "?"
    when = anime.get("when") or "date inconnue"
    genres = anime.get("genres") or []
    genres_txt = " • ".join(genres[:4]) if genres else "—"

    # Helpers auto-fit
    def fit_font_size_to_width(text: str, max_w: int, start_size: int, min_size: int = 24) -> ImageFont.FreeTypeFont:
        size = start_size
        meas = ImageDraw.Draw(panel).textlength
        while size >= min_size:
            f = _load_font(size)
            if meas(text, font=f) <= max_w:
                return f
            size -= 2
        return _load_font(min_size)

    def wrap_title_two_lines(text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
        words = text.split()
        lines, cur = [], ""
        meas = ImageDraw.Draw(panel).textlength
        for w in words:
            t = (cur + " " + w).strip()
            if meas(t, font=font) <= max_w:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
                if len(lines) == 2:
                    break
        if len(lines) < 2 and cur:
            lines.append(cur)
        if len(lines) == 2:
            while lines[1] and meas(lines[1] + "…", font=font) > max_w and font.size > 24:
                lines[1] = lines[1].rsplit(" ", 1)[0] if " " in lines[1] else lines[1][:-1]
            if lines[1]:
                lines[1] += "…"
        return lines[:2]

    # Tailles de base (réduites par panel_scale)
    base_title = int(84 * scale * panel_scale)
    base_sub   = int(44 * scale * panel_scale)
    base_meta  = int(36 * scale * panel_scale)

    # Zone texte (à droite de la mini-cover)
    tx = tx_img + tw + int(28 * scale * panel_scale)
    ty = y0 + int(32 * scale * panel_scale)
    max_w = x1 - tx - int(28 * scale * panel_scale)

    # Titre : ajuste font + wrap 2 lignes
    f_title_try = fit_font_size_to_width(title, max_w, base_title, min_size=max(int(32 * scale * panel_scale), 18))
    title_lines = wrap_title_two_lines(title, f_title_try, max_w)

    # Épisode/Genres/Date : auto-fit aussi
    f_sub  = fit_font_size_to_width(f"Épisode {episode}", max_w, base_sub,  max(int(24 * scale * panel_scale), 16))
    f_meta = fit_font_size_to_width(genres_txt,        max_w, base_meta, max(int(20 * scale * panel_scale), 14))
    f_meta2= fit_font_size_to_width(when,             max_w, base_meta, max(int(20 * scale * panel_scale), 14))

    def draw_shadowed(txt, xy, font, fill=(255, 255, 255, 245)):
        x, y = xy
        draw.text((x + int(3 * scale * panel_scale), y + int(3 * scale * panel_scale)), txt, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), txt, font=font, fill=fill)

    # Titre (max 2 lignes)
    gap_big   = int(8 * scale * panel_scale)
    gap_mid   = int(6 * scale * panel_scale)
    gap_small = int(4 * scale * panel_scale)

    for line in title_lines:
        draw_shadowed(line, (tx, ty), f_title_try)
        ty += f_title_try.size + gap_big

    ty += gap_small
    draw_shadowed(f"Épisode {episode}", (tx, ty), f_sub);  ty += f_sub.size + gap_mid
    draw_shadowed(genres_txt, (tx, ty), f_meta, (235, 235, 235, 240)); ty += f_meta.size + gap_small
    draw_shadowed(when, (tx, ty), f_meta2, (235, 235, 235, 240))

    # --- COMPOSITE & EXPORT ---
    bg.alpha_composite(panel)
    out = bg.convert("RGB")

    # Downscale final (16:9)
    final_h = int(final_w * 9 / 16)
    out = out.resize((final_w, final_h), Image.LANCZOS)

    out.save(out_path, format="PNG", quality=95)
    return out_path
