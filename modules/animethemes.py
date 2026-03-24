# modules/animethemes.py
from __future__ import annotations
import random, json, os, asyncio
from typing import Optional, Tuple, Dict, Any, List, Set

try:
    import aiohttp
except Exception:
    aiohttp = None

from modules import core

BASE = "https://api.animethemes.moe"
THEME_KIND = "OP"  # openings
CACHE_FILE = os.path.join("assets", "animethemes_cache.json")

# ---------- HTTP helpers ----------
async def _fetch_json(url: str) -> Optional[Dict[str, Any]]:
    if not aiohttp:
        return None
    try:
        async with aiohttp.ClientSession(
            headers={"Accept": "application/json", "User-Agent": "AnimeBot/guessop"}
        ) as sess:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        return None
    return None

def _norm_url(link: Optional[str]) -> Optional[str]:
    if not link:
        return None
    if link.startswith("//"):
        return "https:" + link
    if link.startswith("/"):
        return BASE.rstrip("/") + link
    return link

def _pick_video(entry: Dict[str, Any]) -> Optional[str]:
    vids = entry.get("videos") or []
    random.shuffle(vids)
    for v in vids:
        link = _norm_url(
            v.get("link") or v.get("audio") or v.get("video") or v.get("source")
        )
        if link:
            return link
    return None

# ---------- Stratégie A: /anime?random ----------
async def _random_opening_via_anime_random() -> Optional[Tuple[str, str, str]]:
    url = (
        f"{BASE}/anime"
        f"?include=animethemes.animethemeentries.videos,media"
        f"&fields[anime]=name,slug"
        f"&limit=1&random"
    )
    data = await _fetch_json(url)
    if not data:
        return None
    animes: List[Dict[str, Any]] = data.get("anime") or data.get("data") or []
    if not animes:
        return None
    anime = animes[0]
    title = anime.get("name") or anime.get("slug") or "Titre inconnu"
    themes = [t for t in (anime.get("animethemes") or []) if (t.get("type") or "").upper() == THEME_KIND]
    random.shuffle(themes)
    for theme in themes:
        entries = theme.get("animethemeentries") or []
        random.shuffle(entries)
        for entry in entries:
            link = _pick_video(entry)
            if link:
                return title, theme.get("slug") or THEME_KIND, link
    return None

# ---------- Stratégie B: fallback via cache ----------
def _random_from_cache() -> Optional[Tuple[str, str, str]]:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            return None
        pick = random.choice(data)
        return pick["title"], pick.get("theme", "OP"), pick["url"]
    except Exception:
        return None

# ---------- Pagination : plusieurs animes / page (nouvelles URLs vs ?random seul) ----------
async def harvest_openings_from_page(
    page: int = 1,
    page_size: int = 25,
) -> List[Tuple[str, str, str]]:
    """
    Liste d’openings (titre, thème, URL) pour une page du catalogue AnimeThemes.
    À combiner avec le catalogue SQLite : beaucoup d’URLs ne sont pas dans `?random`.
    """
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    url = (
        f"{BASE}/anime"
        f"?include=animethemes.animethemeentries.videos"
        f"&fields[anime]=name,slug"
        f"&page[number]={page}&page[size]={page_size}"
    )
    data = await _fetch_json(url)
    if not data:
        return []
    animes: List[Dict[str, Any]] = data.get("anime") or []
    out: List[Tuple[str, str, str]] = []
    for anime in animes:
        title = anime.get("name") or anime.get("slug") or "?"
        themes = [
            t
            for t in (anime.get("animethemes") or [])
            if (t.get("type") or "").upper() == THEME_KIND
        ]
        for theme in themes:
            for entry in theme.get("animethemeentries") or []:
                link = _pick_video(entry)
                if link:
                    out.append((title, theme.get("slug") or THEME_KIND, link))
    return out


# ---------- API publique ----------
async def random_opening() -> Optional[Tuple[str, str, str]]:
    got = await _random_opening_via_anime_random()
    if got:
        return got
    return _random_from_cache()

# ---------- Version filtrée via AniList ----------
_ANILIST_QUERY = """
query ($search: String) {
  Page(perPage: 1) {
    media(type: ANIME, search: $search, sort: POPULARITY_DESC) {
      id
      title { romaji english native }
      seasonYear
      averageScore
      genres
      format
    }
  }
}
"""

def _title_from_media(m: Dict[str, Any]) -> str:
    t = m.get("title") or {}
    return t.get("romaji") or t.get("english") or t.get("native") or "?"

def _passes_filters(
    media: Dict[str, Any],
    min_year: int,
    min_score_10: float,
    banned_genres: Set[str],
    banned_formats: Set[str],
) -> bool:
    year = media.get("seasonYear") or 0
    score100 = media.get("averageScore") or 0
    score10 = score100 / 10.0
    genres = {g.lower() for g in (media.get("genres") or [])}
    format_ = (media.get("format") or "").upper()
    if year < min_year:
        return False
    if score10 < min_score_10:
        return False
    if any(bg.lower() in genres for bg in banned_genres):
        return False
    if format_ in banned_formats:
        return False
    return True

async def random_opening_filtered(
    min_year: int = 2000,
    min_score_10: float = 4.0,
    banned_genres: Optional[Set[str]] = None,
    banned_formats: Optional[Set[str]] = None,
    max_attempts: int = 12,
) -> Optional[Tuple[str, str, str]]:
    banned_genres = banned_genres or set()
    banned_formats = banned_formats or {"MUSIC"}
    for _ in range(max_attempts):
        got = await random_opening()
        if not got:
            continue
        title, theme_label, video_url = got
        try:
            data = await asyncio.to_thread(core.query_anilist, _ANILIST_QUERY, {"search": title})
            media_list = data.get("data", {}).get("Page", {}).get("media", []) or []
            if not media_list:
                continue
            media = media_list[0]
        except Exception:
            continue
        if _passes_filters(media, min_year, min_score_10, banned_genres, banned_formats):
            clean_title = _title_from_media(media)
            return clean_title, theme_label, video_url
    return None
