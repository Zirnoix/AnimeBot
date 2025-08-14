# modules/animethemes.py
from __future__ import annotations
import random
from typing import Optional, Tuple, Dict, Any, List, Set
import asyncio

try:
    import aiohttp
except Exception:
    aiohttp = None

from modules import core

BASE = "https://api.animethemes.moe"
THEME_KIND = "OP"  # on cible les openings

async def _fetch_json(url: str) -> Optional[Dict[str, Any]]:
    if not aiohttp:
        return None
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, timeout=12) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        return None
    return None

async def random_opening() -> Optional[Tuple[str, str, str]]:
    """
    Retourne (anime_title, theme_display, video_url) ou None.
    """
    url = (
        f"{BASE}/anime?include=animethemes.animethemeentries.videos"
        f"&fields[anime]=name&limit=1&random"
    )
    data = await _fetch_json(url)
    if not data:
        return None

    animes: List[Dict[str, Any]] = data.get("anime") or []
    if not animes:
        return None
    anime = animes[0]
    title = anime.get("name") or "Titre inconnu"

    themes = anime.get("animethemes") or []
    themes = [t for t in themes if (t.get("type") or "").upper() == THEME_KIND]
    if not themes:
        return None

    theme = random.choice(themes)
    theme_display = theme.get("slug") or theme.get("type") or THEME_KIND

    videos: List[str] = []
    for entry in (theme.get("animethemeentries") or []):
        for v in (entry.get("videos") or []):
            link = v.get("link") or v.get("audio") or v.get("video")
            if link:
                videos.append(link)

    if not videos:
        return None

    video_url = random.choice(videos)
    return title, theme_display, video_url

# ---------- Version avec filtres via AniList ----------

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
    score100 = media.get("averageScore") or 0  # 0..100
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
    min_year: int = 2005,
    min_score_10: float = 5.0,  # 5/10
    banned_genres: Optional[Set[str]] = None,
    banned_formats: Optional[Set[str]] = None,
    max_attempts: int = 10,
) -> Optional[Tuple[str, str, str]]:
    """
    Tente jusqu'à max_attempts de renvoyer (title, theme_label, video_url)
    qui passe les filtres AniList (année, score, genres exclus, formats exclus).
    """
    banned_genres = banned_genres or {"mahou shoujo", "kids"}  # ajoute ce que tu veux
    banned_formats = banned_formats or {"MUSIC"}               # évite “Music”-only, ONA si tu veux etc.

    for _ in range(max_attempts):
        got = await random_opening()
        if not got:
            continue
        title, theme_label, video_url = got

        # AniList lookup (core.query_anilist est sync → to_thread)
        try:
            data = await asyncio.to_thread(core.query_anilist, _ANILIST_QUERY, {"search": title})
            media_list = data.get("data", {}).get("Page", {}).get("media", []) or []
            if not media_list:
                continue
            media = media_list[0]
        except Exception:
            continue

        if _passes_filters(
            media,
            min_year=min_year,
            min_score_10=min_score_10,
            banned_genres=banned_genres,
            banned_formats=banned_formats,
        ):
            # utilise le titre romaji/english pour l’affichage & réponses
            clean_title = _title_from_media(media)
            return clean_title, theme_label, video_url

    return None
