# modules/image.py (extrait)
import os
import re
import tempfile
import time
from typing import Dict, Any, Optional
from io import BytesIO
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageOps
import requests

from modules import core as _core

_IMG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AnimeBot/1.0; +https://anilist.co/)",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://anilist.co/",
}


def _fetch_image(url: Optional[str]) -> Image.Image:
    """Télécharge la cover ; si échec (403, timeout, URL vide), fond gris foncé (comme avant)."""
    if not url:
        return Image.new("RGB", (1200, 675), (20, 22, 26))
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=14, headers=_IMG_HEADERS)
            r.raise_for_status()
            return Image.open(BytesIO(r.content)).convert("RGB")
        except Exception:
            if attempt < 2:
                time.sleep(0.35)
    return Image.new("RGB", (1200, 675), (20, 22, 26))


def _fetch_cover_for_card(anime: Dict[str, Any]) -> Image.Image:
    """Essaie plusieurs URLs AniList (extraLarge → large → medium) si présentes dans `cover_urls`."""
    urls = anime.get("cover_urls")
    if isinstance(urls, list) and urls:
        for u in urls:
            if not u:
                continue
            for attempt in range(2):
                try:
                    r = requests.get(str(u), timeout=14, headers=_IMG_HEADERS)
                    r.raise_for_status()
                    return Image.open(BytesIO(r.content)).convert("RGB")
                except Exception:
                    if attempt == 0:
                        time.sleep(0.25)
        return Image.new("RGB", (1200, 675), (20, 22, 26))
    return _fetch_image(anime.get("cover") if isinstance(anime.get("cover"), str) else None)

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()

def generate_next_card(
    anime: Dict[str, Any],
    out_path: Optional[str] = None,
    scale: float = 1.2,
    blur: int = 10,
    padding: int = 40
) -> str:
    """
    Génère une carte compacte: fond flouté + panneau verre + mini-cover + crop autour du panneau.
    `anime` doit contenir: cover (URL), title_romaji/english/native, episode, genres (list), when (str).
    """
    if not out_path:
        out_path = os.path.join(tempfile.gettempdir(), "next_card.png")
    # --- Canvas de travail (grand, puis on croppe) ---
    W, H = int(1400 * scale), int(800 * scale)

    cover = _fetch_cover_for_card(anime)
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
    episode = _core.format_episode_line_part(anime.get("episode"), anime)
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


# --- Couleurs identité « rosé / bleu » (carte /mycard) ---
_MYCARD_COL_BG_TOP = (26, 22, 42)
_MYCARD_COL_BG_BOT = (40, 32, 58)
_MYCARD_COL_STRIPE_TOP = (244, 114, 182)  # pink
_MYCARD_COL_STRIPE_BOT = (96, 165, 250)  # blue
_MYCARD_COL_PINK = (236, 72, 153)
_MYCARD_COL_BLUE = (59, 130, 246)
_MYCARD_COL_TEXT = (252, 231, 243)
_MYCARD_COL_MUTED = (148, 163, 184)
# Stats (lisibilité + identité)
_MYCARD_COL_STAT_LABEL = (255, 196, 228)  # libellé (Quiz, Devinettes…)
_MYCARD_COL_STAT_SEP = (130, 120, 155)  # tirets « — »
_MYCARD_COL_STAT_HINT = (165, 210, 252)  # précision entre parenthèses
_MYCARD_COL_STAT_SHADOW = (12, 8, 22)
_MYCARD_COL_STAT_BULLET = (150, 195, 255)  # puce ▸
_MYCARD_COL_STAT_NUM = (255, 210, 235)  # chiffres (un peu plus vifs)

_STAT_NUM_RE = re.compile(r"\b(\d{1,3}(?:\s\d{3})*|\d+)\b")


def _mycard_project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mycard_bundled_font(*parts: str) -> Optional[str]:
    p = os.path.join(_mycard_project_root(), *parts)
    return p if os.path.isfile(p) else None


def _mycard_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Noto Sans dans fonts/ (repo), sinon DejaVu à la racine du projet, sinon système."""
    noto = "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"
    path = _mycard_bundled_font("fonts", noto)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    for n in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf") if bold else ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
        p = _mycard_bundled_font(n)
        if p:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _mycard_font_oblique(size: int) -> ImageFont.ImageFont:
    """Italique : Noto Italic dans fonts/, sinon DejaVu oblique / droit."""
    p = _mycard_bundled_font("fonts", "NotoSans-Italic.ttf")
    if p:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    for n in ("DejaVuSans-Oblique.ttf", "DejaVuSans-Italic.ttf"):
        bp = _mycard_bundled_font(n)
        if bp:
            try:
                return ImageFont.truetype(bp, size)
            except Exception:
                pass
    return _mycard_font(size, bold=False)


def _mycard_iter_body_segments(body: str) -> list[tuple[str, bool]]:
    """Découpe le corps : nombres (avec espaces milliers) en gras ; le reste en normal."""
    if not body:
        return []
    parts: list[tuple[str, bool]] = []
    pos = 0
    for m in _STAT_NUM_RE.finditer(body):
        if m.start() > pos:
            parts.append((body[pos : m.start()], False))
        parts.append((m.group(1), True))
        pos = m.end()
    if pos < len(body):
        parts.append((body[pos:], False))
    return parts


_MYCARD_BULLET_W = 7
_MYCARD_BULLET_H = 10
_MYCARD_BULLET_GAP = 8  # espace triangle → début du texte (aligné sur le pseudo)


def _mycard_line_center_y(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.ImageFont) -> float:
    """Centre vertical visuel d’une ligne de texte (pour aligner la puce)."""
    if not text:
        text = "."
    try:
        bbox = draw.textbbox((x, y), text, font=font)
        return (bbox[1] + bbox[3]) / 2.0
    except Exception:
        return float(y) + 11.0


def _mycard_draw_stat_bullet_triangle(draw: ImageDraw.ImageDraw, x_left: int, y_center: float) -> None:
    """Triangle vers la droite, centré sur y_center (aligné avec le texte)."""
    w, h = _MYCARD_BULLET_W, _MYCARD_BULLET_H
    y0 = int(y_center - h / 2)
    y_mid = int(y_center)
    pts = [(x_left, y0), (x_left, y0 + h), (x_left + w, y_mid)]
    sh = [(p[0] + 1, p[1] + 1) for p in pts]
    draw.polygon(sh, fill=_MYCARD_COL_STAT_SHADOW)
    draw.polygon(pts, fill=_MYCARD_COL_STAT_BULLET)


def _mycard_parse_stat_line(line: str) -> tuple[str, str, str]:
    """Découpe label — corps … (hint optionnel en fin de ligne)."""
    line = line.strip()
    hint = ""
    mp = re.search(r"\s*\(([^)]+)\)\s*$", line)
    if mp:
        hint = mp.group(1).strip()
        line = line[: mp.start()].rstrip()
    if " — " in line:
        a, b = line.split(" — ", 1)
        return (a.strip(), b.strip(), hint)
    return (line, "", hint)


def _mycard_draw_stat_line(
    draw: ImageDraw.ImageDraw,
    x_text: int,
    y: int,
    line: str,
    max_chars: int,
) -> None:
    """x_text = même abscisse que le pseudo ; triangle à gauche dans la marge. Libellé + corps + hint."""
    line = _mycard_trunc(line, max_chars)
    label, body, hint = _mycard_parse_stat_line(line)
    font_lb = _mycard_font(22, bold=True)
    font_bd = _mycard_font(21, bold=False)
    font_num = _mycard_font(25, bold=True)
    font_hi = _mycard_font_oblique(17)
    sep = " — "

    cy = _mycard_line_center_y(draw, x_text, y, label or "Quiz", font_lb)
    tri_left = x_text - _MYCARD_BULLET_GAP - _MYCARD_BULLET_W
    _mycard_draw_stat_bullet_triangle(draw, tri_left, cy)

    cx = x_text

    for txt, font, fill in ((label, font_lb, _MYCARD_COL_STAT_LABEL),):
        if not txt:
            continue
        draw.text((cx + 1, y + 1), txt, font=font, fill=_MYCARD_COL_STAT_SHADOW)
        draw.text((cx, y), txt, font=font, fill=fill)
        cx += _mycard_text_width(draw, txt, font)

    if body:
        for txt, font, fill in ((sep, font_bd, _MYCARD_COL_STAT_SEP),):
            draw.text((cx + 1, y + 1), txt, font=font, fill=_MYCARD_COL_STAT_SHADOW)
            draw.text((cx, y), txt, font=font, fill=fill)
            cx += _mycard_text_width(draw, txt, font)
        for seg, is_num in _mycard_iter_body_segments(body):
            font = font_num if is_num else font_bd
            fill = _MYCARD_COL_STAT_NUM if is_num else _MYCARD_COL_TEXT
            dy = 0
            draw.text((cx + 1, y + 1 + dy), seg, font=font, fill=_MYCARD_COL_STAT_SHADOW)
            draw.text((cx, y + dy), seg, font=font, fill=fill)
            cx += _mycard_text_width(draw, seg, font)

    if hint:
        ht = f" ({hint})"
        draw.text((cx + 1, y + 1), ht, font=font_hi, fill=_MYCARD_COL_STAT_SHADOW)
        draw.text((cx, y), ht, font=font_hi, fill=_MYCARD_COL_STAT_HINT)


def _mycard_fmt_xp(n: int) -> str:
    """Affichage compact type 12k / 123k."""
    n = int(n)
    if n >= 1_000_000:
        s = f"{n / 1_000_000:.1f}M"
        return s.replace(".0M", "M")
    if n >= 1000:
        s = f"{n / 1000:.1f}k"
        return s.replace(".0k", "k")
    return str(n)


def _mycard_gradient_bg(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    r0, g0, b0 = _MYCARD_COL_BG_TOP
    r1, g1, b1 = _MYCARD_COL_BG_BOT
    for y in range(h):
        t = y / max(1, h - 1)
        img.putpixel(
            (0, y),
            (
                int(r0 + (r1 - r0) * t),
                int(g0 + (g1 - g0) * t),
                int(b0 + (b1 - b0) * t),
            ),
        )
    for x in range(1, w):
        for y in range(h):
            img.putpixel((x, y), img.getpixel((0, y)))
    return img


def _mycard_left_stripe(img: Image.Image, stripe_w: int) -> None:
    h = img.height
    rt, gt, bt = _MYCARD_COL_STRIPE_TOP
    rb, gb, bb = _MYCARD_COL_STRIPE_BOT
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(rt + (rb - rt) * t)
        g = int(gt + (gb - gt) * t)
        b = int(bt + (bb - bt) * t)
        for x in range(stripe_w):
            img.putpixel((x, y), (r, g, b))


def _mycard_circle_avatar(raw: Image.Image, size: int) -> Image.Image:
    raw = raw.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(raw, (0, 0), mask)
    return out


def _mycard_rounded_rect_mask(size: tuple[int, int], radius: int) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return m


def _mycard_text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    try:
        return float(font.getlength(text))
    except Exception:
        bbox = draw.textbbox((0, 0), text, font=font)
        return float(bbox[2] - bbox[0])


def _mycard_trunc(s: str, max_len: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def generate_mycard_image(
    *,
    display_name: str,
    avatar_url: str,
    level: int,
    xp: int,
    next_xp: int,
    anilist_username: Optional[str] = None,
    anime_fav: Optional[str] = None,
    line_play: Optional[str] = None,
    line_record: Optional[str] = None,
) -> BytesIO:
    """
    Carte panoramique : avatar, pseudo, AniList / favori optionnels, barre XP (rose → bleu), mini-jeux.
    (Pas de titre global : les emojis Discord ne rendent pas dans Pillow.)
    """
    W, H = 980, 360
    av_size = 178
    stripe_w = 12
    pad = 20
    base_rgb = _mycard_gradient_bg(W, H)
    _mycard_left_stripe(base_rgb, stripe_w)
    base = base_rgb.convert("RGBA")

    try:
        av_src = _fetch_image(avatar_url)
        av = _mycard_circle_avatar(av_src, av_size)
    except Exception:
        av = Image.new("RGBA", (av_size, av_size), (60, 55, 75, 255))
    ax = stripe_w + pad
    ay = (H - av_size) // 2
    base.paste(av, (ax, ay), av)

    draw = ImageDraw.Draw(base)
    font_name = _mycard_font(42, bold=True)
    font_sub = _mycard_font(24, bold=False)
    font_al = _mycard_font(22, bold=False)
    font_xp = _mycard_font(22, bold=False)
    font_lvl = _mycard_font(34, bold=True)

    tx = ax + av_size + 22
    name = _mycard_trunc(display_name or "?", 28)
    y = 26
    draw.text((tx, y), name, font=font_name, fill=_MYCARD_COL_TEXT)
    y += 50
    if anilist_username:
        al_txt = f"AniList · {_mycard_trunc(anilist_username, 40)}"
        draw.text((tx, y), al_txt, font=font_al, fill=(167, 139, 250))
        y += 32
    if anime_fav:
        fav_txt = f"Favori · {_mycard_trunc(anime_fav, 48)}"
        draw.text((tx, y), fav_txt, font=font_sub, fill=_MYCARD_COL_MUTED)
        y += 32

    row_top = y + 14
    xp_txt = f"{_mycard_fmt_xp(xp)} / {_mycard_fmt_xp(next_xp)} XP"
    lvl_txt = f"Niveau {int(level)}"
    tw_xp = _mycard_text_width(draw, xp_txt, font_xp)
    tw_lv = _mycard_text_width(draw, lvl_txt, font_lvl)
    gap_bar_lvl = 14
    gap_xp_bar = 8
    inner_w = W - tx - pad
    bar_w = max(180, inner_w - gap_bar_lvl - tw_lv)
    bar_h = 24
    radius = 12
    ratio = 1.0 if next_xp <= 0 else max(0.0, min(1.0, float(xp) / float(next_xp)))
    fill_w = max(6, int(bar_w * ratio))

    try:
        bb_xp = draw.textbbox((0, 0), xp_txt, font=font_xp)
        h_xp = float(bb_xp[3] - bb_xp[1])
    except Exception:
        h_xp = 22.0
    try:
        bb_lv = draw.textbbox((0, 0), lvl_txt, font=font_lvl)
        h_lv = float(bb_lv[3] - bb_lv[1])
    except Exception:
        h_lv = 34.0

    # Écran 1 : XP au-dessus, aligné à droite sur la fin de la barre ; barre large ;
    # niveau à droite de la barre, centré sur la même bande que la barre (pas avec les stats).
    xp_x = int(tx + bar_w - tw_xp)
    xp_y = int(row_top)
    bar_y = int(row_top + h_xp + gap_xp_bar)
    lvl_x = int(tx + bar_w + gap_bar_lvl)
    lvl_y = int(bar_y + (bar_h - h_lv) / 2)

    draw.rounded_rectangle(
        (tx, bar_y, tx + bar_w, bar_y + bar_h),
        radius=radius,
        fill=(35, 30, 52, 255),
    )

    grad = Image.new("RGB", (fill_w, bar_h))
    rp, gp, bp = _MYCARD_COL_PINK
    rb_, gb_, bb_ = _MYCARD_COL_BLUE
    for x in range(fill_w):
        t = x / max(1, fill_w - 1)
        r = int(rp + (rb_ - rp) * t)
        g = int(gp + (gb_ - gp) * t)
        b = int(bp + (bb_ - bp) * t)
        for yy in range(bar_h):
            grad.putpixel((x, yy), (r, g, b))
    mask = _mycard_rounded_rect_mask((fill_w, bar_h), radius)
    grad_rgba = Image.merge("RGBA", (*grad.split(), mask))
    base.alpha_composite(grad_rgba, (tx, bar_y))

    draw = ImageDraw.Draw(base)
    draw.text((xp_x + 1, xp_y + 1), xp_txt, font=font_xp, fill=(8, 6, 14))
    draw.text((xp_x, xp_y), xp_txt, font=font_xp, fill=_MYCARD_COL_MUTED)
    draw.text((lvl_x + 1, lvl_y + 1), lvl_txt, font=font_lvl, fill=(8, 6, 14))
    draw.text((lvl_x, lvl_y), lvl_txt, font=font_lvl, fill=_MYCARD_COL_TEXT)

    y_stats = int(bar_y + bar_h + 28)
    if line_play:
        _mycard_draw_stat_line(draw, tx, y_stats, line_play, 90)
        y_stats += 32
    if line_record:
        _mycard_draw_stat_line(draw, tx, y_stats, line_record, 90)

    out = base.convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", quality=95)
    buf.seek(0)
    return buf
