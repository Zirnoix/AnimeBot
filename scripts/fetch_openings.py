# scripts/fetch_openings.py
# Télécharge des OP (audio MP3) depuis AnimeThemes via /videos?filter[themeType]=OP
# Sauvegarde dans assets/audio/openings et écrit un manifest.json
#
# Dépendances:
#   pip install aiohttp
#   (ffmpeg non requis ici)
#
from __future__ import annotations
import os, re, json, asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

# ========= CONFIG =========
OUT_DIR   = Path("assets/audio/openings")
MANIFEST  = Path("assets/audio/manifest.json")
MAX_OPS   = 300          # combien d'OP au total (augmente si tu veux)
PAGE_SIZE = 100          # 100 max selon l’API
CONCURRENCY = 6          # téléchargements simultanés

# Filtres AniList (désactive d’abord si tu veux “voir du son” arriver)
USE_ANILIST_FILTERS = True
MIN_YEAR      = 2005
MIN_SCORE_10  = 5.0
BANNED_GENRES = {"mahou shoujo", "kids"}
BANNED_FORMATS = {"MUSIC"}

# Endpoints
AT_BASE   = "https://api.animethemes.moe"
AT_VIDEOS = f"{AT_BASE}/videos"   # JSON:API
ANILIST_GQL = "https://graphql.anilist.co"

# ========= UTILS =========
def ensure_dirs():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

def load_manifest() -> Dict[str, Any]:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_manifest(data: Dict[str, Any]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s\-]", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text.replace(" ", "_")[:100] or "untitled"

async def fetch_json(session: aiohttp.ClientSession, url: str, params: Optional[Dict[str, Any]]=None) -> Optional[dict]:
    headers = {"Accept": "application/vnd.api+json", "User-Agent": "AnimeBot-OPFetcher/2.0"}
    for attempt in range(3):
        try:
            async with session.get(url, params=params, headers=headers, timeout=40) as resp:
                if resp.status == 200:
                    return await resp.json()
                txt = await resp.text()
                print(f"[fetch_json] {url} -> {resp.status} (try {attempt+1}/3)")
                print(f"[fetch_json] body: {txt[:240]!r}")
                await asyncio.sleep(1.2)
        except Exception as e:
            print(f"[fetch_json] Exception: {e} (try {attempt+1}/3)")
            await asyncio.sleep(1.2)
    return None

async def download_file(session: aiohttp.ClientSession, url: str, dest: Path) -> bool:
    try:
        async with session.get(url, timeout=60) as resp:
            if resp.status != 200:
                print(f"[download] HTTP {resp.status} -> {url}")
                return False
            with dest.open("wb") as f:
                async for chunk in resp.content.iter_chunked(1<<14):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception as e:
        print(f"[download] Exception {e} -> {url}")
        return False

# ========= ANILIST =========
ANILIST_QUERY = """
query($ids:[Int]) {
  Page(perPage: 50) {
    media(id_in: $ids, type: ANIME) {
      id
      title { romaji english native }
      averageScore
      format
      genres
      seasonYear
    }
  }
}
"""

async def anilist_lookup(session: aiohttp.ClientSession, ids: List[int]) -> Dict[int, Dict]:
    out: Dict[int, Dict] = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i+50]
        try:
            async with session.post(ANILIST_GQL, json={"query": ANILIST_QUERY, "variables": {"ids": chunk}}, timeout=40) as resp:
                data = await resp.json()
            for m in data["data"]["Page"]["media"]:
                out[int(m["id"])] = m
        except Exception:
            pass
    return out

def allow_media(m: Dict[str, Any]) -> bool:
    if not USE_ANILIST_FILTERS:
        return True
    # année
    year = m.get("seasonYear") or 0
    if year and year < MIN_YEAR:
        return False
    # score (/100 → /10)
    score = m.get("averageScore")
    if score is not None and (score/10.0) < MIN_SCORE_10:
        return False
    # format
    fmt = (m.get("format") or "").upper()
    if fmt in BANNED_FORMATS:
        return False
    # genres
    lg = {g.lower() for g in (m.get("genres") or [])}
    if lg & BANNED_GENRES:
        return False
    return True

# ========= PARSING /videos =========
def map_included(included: List[dict]) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """Retourne deux maps: anime_by_id, videos_by_id (si besoin) depuis included."""
    anime_by_id: Dict[str, dict] = {}
    videos_by_id: Dict[str, dict] = {}
    for obj in included or []:
        t = obj.get("type")
        if t == "anime":
            anime_by_id[str(obj.get("id"))] = obj
        elif t == "videos":
            videos_by_id[str(obj.get("id"))] = obj
    return anime_by_id, videos_by_id

def extract_video_records(payload: dict) -> List[dict]:
    """
    L'endpoint /videos renvoie généralement:
    - data: [ {type:"videos", id, attributes:{basename, ...}, relationships:{anime:{data:{type,id}} ...}} ]
    - included: [ objets 'anime', ... ]
    """
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []

def get_anime_for_video(video: dict, anime_by_id: Dict[str, dict]) -> Optional[dict]:
    rel = (video.get("relationships") or {}).get("anime", {})
    ref = (rel.get("data") or {})
    if ref.get("type") == "anime":
        return anime_by_id.get(str(ref.get("id")))
    return None

def extract_anilist_id_from_anime(anime_obj: dict) -> Optional[int]:
    # Dans included anime.attributes, AnimeThemes met souvent anilistId directement
    try:
        aid = (anime_obj.get("attributes") or {}).get("anilist_id") or (anime_obj.get("attributes") or {}).get("anilistId")
        if aid:
            return int(aid)
    except Exception:
        pass
    # sinon regarde 'resources' si présent (mais pas garanti sur /videos)
    resources = (anime_obj.get("attributes") or {}).get("resources") or []
    for r in resources:
        site = (r.get("site") or "").lower()
        if "anilist" in site and r.get("external_id"):
            try:
                return int(r["external_id"])
            except Exception:
                pass
    return None

# ========= MAIN =========
async def main():
    ensure_dirs()
    manifest = load_manifest()
    total = 0
    collected_ids: List[int] = []
    to_process: List[Tuple[str, str, Optional[int]]] = []
    # (basename, title_fallback, anilistId?)

    async with aiohttp.ClientSession() as session:
        page = 1
        while True:
            if total >= MAX_OPS:
                break
            params = {
                "filter[themeType]": "OP",
                "page[number]": page,
                "page[size]": PAGE_SIZE,
                "include": "anime",  # on veut l'anime lié
            }
            payload = await fetch_json(session, AT_VIDEOS, params=params)
            if not payload:
                print(f"[videos] page {page}: no payload, stop.")
                break

            videos = extract_video_records(payload)
            included = payload.get("included") or []
            anime_by_id, _ = map_included(included)

            if not videos:
                print(f"[videos] page {page}: 0 videos, stop.")
                break

            for v in videos:
                attrs = v.get("attributes") or {}
                basename = attrs.get("basename")
                if not basename:
                    continue
                # titre fallback (si pas AniList)
                title_fallback = (attrs.get("title") or "").strip() or "Anime"

                anime_obj = get_anime_for_video(v, anime_by_id)
                anilist_id = extract_anilist_id_from_anime(anime_obj) if anime_obj else None

                to_process.append((basename, title_fallback, anilist_id))
                if anilist_id:
                    collected_ids.append(anilist_id)

            print(f"[videos] page {page}: {len(videos)} items")
            # pagination
            links = payload.get("links") or {}
            if not links.get("next"):
                break
            page += 1
            if page > 200:  # garde-fou
                break

        # Enrichissement AniList
        print("→ AniList lookup…")
        mdict = await anilist_lookup(session, list(set(collected_ids))) if collected_ids else {}

        # Filtrage + téléchargement
        sem = asyncio.Semaphore(CONCURRENCY)
        async def worker(basename: str, title_fb: str, aid: Optional[int]):
            nonlocal total
            if total >= MAX_OPS:
                return
            m = mdict.get(aid) if aid else None
            if m and not allow_media(m):
                return

            # Choix du titre final
            if m:
                t = m.get("title") or {}
                title = t.get("romaji") or t.get("english") or t.get("native") or title_fb
                year  = m.get("seasonYear")
            else:
                title = title_fb
                year  = None

            safe = slugify(title)
            label = "OP"
            fname = f"{safe}_{label}.mp3"
            dest = OUT_DIR / fname
            if dest.exists():
                return

            url = f"https://animethemes.moe/audio/{basename}.mp3"
            ok = await download_file(session, url, dest)
            if not ok:
                return

            manifest[fname] = {
                "title": title,
                "label": label,
                "anilistId": aid,
                "year": year,
                "source": url,
                "type": "audio_direct"
            }
            save_manifest(manifest)
            total += 1

        print("→ Téléchargements…")
        tasks = []
        for basename, tfb, aid in to_process:
            if len(tasks) >= MAX_OPS:
                break
            tasks.append(asyncio.create_task(worker(basename, tfb, aid)))

        if tasks:
            await asyncio.gather(*tasks)

    print(f"Terminé. Nouveaux OP ajoutés : {total}")
    print(f"Dossier: {OUT_DIR.resolve()}")
    print(f"Manifest: {MANIFEST.resolve()}")

if __name__ == "__main__":
    asyncio.run(main())
