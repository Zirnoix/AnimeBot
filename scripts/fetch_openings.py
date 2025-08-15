# scripts/fetch_openings.py
# Télécharge des OP (audio MP3) depuis AnimeThemes via /anime + included (videos, resources)
# Sauvegarde dans assets/audio/openings et écrit un manifest.json
#
# Dépendances:
#   pip install aiohttp
#
from __future__ import annotations
import json, re, asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse as _urlparse
import aiohttp

# ========= CONFIG =========
OUT_DIR   = Path("assets/audio/openings")
MANIFEST  = Path("assets/audio/manifest.json")
MAX_OPS   = 300           # combien d’OP au total (augmente si tu veux)
PAGE_SIZE = 50            # 50 est sûr; 100 fonctionne souvent aussi
CONCURRENCY = 6           # téléchargements simultanés

# Filtres AniList (mets True plus tard, une fois que tu vois des fichiers arriver)
USE_ANILIST_FILTERS = False
MIN_YEAR      = 2005
MIN_SCORE_10  = 5.0
BANNED_GENRES = {"mahou shoujo", "kids"}
BANNED_FORMATS = {"MUSIC"}

# Endpoints
AT_BASE   = "https://api.animethemes.moe"
AT_ANIME  = f"{AT_BASE}/anime"
ANILIST_GQL = "https://graphql.anilist.co"

# ========= UTILS =========
def derive_basename_from_link(link: str) -> str | None:
    """
    Essaie d'extraire un basename exploitable depuis une URL vidéo d'AnimeThemes.
    Ex: https://.../video/Naruto-OP1.webm -> Naruto-OP1
        https://.../video/Naruto-OP1?foo=bar -> Naruto-OP1
    """
    if not link:
        return None
    p = _urlparse.urlparse(link)
    fname = os.path.basename(p.path)  # "Naruto-OP1.webm" ou "Naruto-OP1"
    if not fname:
        return None
    base, ext = os.path.splitext(fname)
    return base or fname
    
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
    headers = {"Accept": "application/vnd.api+json", "User-Agent": "AnimeBot-OPFetcher/3.0"}
    for attempt in range(3):
        try:
            async with session.get(url, params=params, headers=headers, timeout=50) as resp:
                if resp.status == 200:
                    return await resp.json()
                txt = await resp.text()
                print(f"[fetch_json] {url} -> {resp.status} (try {attempt+1}/3)")
                print(f"[fetch_json] body: {txt[:240]!r}")
                await asyncio.sleep(1.0)
        except Exception as e:
            print(f"[fetch_json] Exception: {e} (try {attempt+1}/3)")
            await asyncio.sleep(1.0)
    return None

async def iter_animethemes(session: aiohttp.ClientSession):
    """
    Itère /anime avec include=animethemes.animethemeentries.videos,resources.
    Affiche des logs de debug pour suivre la collecte.
    """
    page_number = 1
    total_candidates_seen = 0
    while True:
        params = {
            "page[number]": page_number,
            "page[size]": 50,
            "include": "animethemes.animethemeentries.videos,resources",
            # "filter[year]": f"{MIN_YEAR}..",  # tu peux tester ça si besoin
        }

        data = await fetch_json(session, f"{ANIMETHEMES_BASE}/anime", params=params)
        if not data:
            print(f"[anime] page {page_number}: no payload (stop).")
            break

        anime_list = data.get("anime")
        if anime_list is None:
            print(f"[anime] page {page_number}: clé 'anime' absente. Clés: {list(data.keys())}")
            break
        if not anime_list:
            print(f"[anime] page {page_number}: liste vide. Fin.")
            break

        # comptage “potentiel”: combien ont au moins un theme OP avec entries/videos ?
        page_candidates = 0
        for a in anime_list:
            themes = a.get("animethemes") or []
            # compte rough pour debug
            for th in themes:
                if str(th.get("type", "")).upper() == "OP":
                    entries = th.get("animethemeentries") or th.get("animethemeEntries") or []
                    for e in entries:
                        vids = e.get("videos") or []
                        if vids:
                            page_candidates += 1
                            break

            yield a

        total_candidates_seen += page_candidates
        nxt = (data.get("links") or {}).get("next")
        print(f"[anime] page {page_number}: {len(anime_list)} animes • candidats cumulés: {total_candidates_seen}")
        if not nxt:
            break
        page_number += 1

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
    if not ids:
        return out
    for i in range(0, len(ids), 50):
        chunk = ids[i:i+50]
        try:
            async with session.post(ANILIST_GQL, json={"query": ANILIST_QUERY, "variables": {"ids": chunk}}, timeout=50) as resp:
                data = await resp.json()
            for m in data["data"]["Page"]["media"]:
                out[int(m["id"])] = m
        except Exception:
            pass
    return out

def allow_media(m: Dict[str, Any]) -> bool:
    if not USE_ANILIST_FILTERS:
        return True
    year = m.get("seasonYear") or 0
    if year and year < MIN_YEAR:
        return False
    score = m.get("averageScore")
    if score is not None and (score/10.0) < MIN_SCORE_10:
        return False
    fmt = (m.get("format") or "").upper()
    if fmt in BANNED_FORMATS:
        return False
    lg = {g.lower() for g in (m.get("genres") or [])}
    if lg & BANNED_GENRES:
        return False
    return True

# ========= JSON:API HELPERS =========
def build_included_maps(included: List[dict]) -> Dict[str, Dict[str, dict]]:
    """
    Retourne un dict de maps par type: {"videos": {id:obj}, "animethemes": {...}, "animethemeentries": {...}, "anime": {...}}
    """
    out: Dict[str, Dict[str, dict]] = {}
    for obj in included or []:
        t = obj.get("type")
        if not t:
            continue
        out.setdefault(t, {})
        out[t][str(obj.get("id"))] = obj
    return out

def get_rel_ids(obj: dict, rel_name: str) -> List[str]:
    rel = (obj.get("relationships") or {}).get(rel_name) or {}
    data = rel.get("data")
    if isinstance(data, list):
        return [str(d.get("id")) for d in data if d.get("id") is not None]
    if isinstance(data, dict) and data.get("id") is not None:
        return [str(data["id"])]
    return []

def video_basename(video_obj: dict) -> Optional[str]:
    return (video_obj.get("attributes") or {}).get("basename")

def anime_title(anime_obj: dict) -> str:
    attrs = anime_obj.get("attributes") or {}
    return attrs.get("name") or attrs.get("slug") or "Anime"

def anime_anilist_id(anime_obj: dict) -> Optional[int]:
    attrs = anime_obj.get("attributes") or {}
    # souvent anilist_id est présent
    aid = attrs.get("anilist_id") or attrs.get("anilistId")
    if aid:
        try:
            return int(aid)
        except Exception:
            pass
    # sinon, parfois 'resources' imbriqués
    resources = attrs.get("resources") or []
    for r in resources:
        site = (r.get("site") or "").lower()
        if "anilist" in site and r.get("external_id"):
            try:
                return int(r["external_id"])
            except Exception:
                pass
    return None

def pick_op_videolink(animethemes_anime: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Retourne des candidates {url, label} en se basant sur le 'basename' si présent,
    sinon en le déduisant du champ 'link'. On ne récupère que des OP.
    """
    out = []
    themes = animethemes_anime.get("animethemes") or []
    for th in themes:
        th_type = str(th.get("type", "")).upper()
        if th_type != "OP":
            continue

        label = (th.get("slug") or th.get("type") or "OP").upper()
        entries = th.get("animethemeentries") or th.get("animethemeEntries") or []
        for e in entries:
            videos = e.get("videos") or []
            for v in videos:
                # priorité au 'basename' si présent
                basename = v.get("basename")
                if not basename:
                    # fallback: essayer de dériver depuis 'link'
                    basename = derive_basename_from_link(v.get("link", ""))

                if basename:
                    url = f"https://animethemes.moe/audio/{basename}.mp3"
                    out.append({"url": url, "label": label})
                else:
                    # Debug utile: voir à quoi ressemblent les videos sans basename
                    # (commente si trop verbeux)
                    # print("[debug] video sans basename:", {k: v.get(k) for k in ("link", "filename", "audio")})
                    pass

    return out

def is_op_theme(animetheme_obj: dict) -> bool:
    attrs = animetheme_obj.get("attributes") or {}
    return (attrs.get("type") or "").upper() == "OP"

# ========= MAIN =========
async def main():
    ensure_dirs()
    manifest = load_manifest()
    total = 0

    async with aiohttp.ClientSession() as session:
        page = 1
        collected_aids: List[int] = []
        candidates: List[Tuple[str, str, Optional[int]]] = []
        # (basename, title_fallback, anilistId)

        while True:
            if total >= MAX_OPS:
                break

            params = {
                "page[number]": page,
                "page[size]": PAGE_SIZE,
                "include": "animethemes.animethemeentries.videos,resources",
            }
            payload = await fetch_json(session, AT_ANIME, params=params)
            if not payload:
                print(f"[anime] page {page}: no payload, stop.")
                break

            # primary data: “anime” (JSON:API pluralized dans cette API)
            anime_list = payload.get("anime")
            if anime_list is None:
                print(f"[anime] page {page}: clé 'anime' absente. keys={list(payload.keys())}")
                break
            if not anime_list:
                print(f"[anime] page {page}: vide, stop.")
                break

            maps = build_included_maps(payload.get("included") or [])
            animethemes_map = maps.get("animethemes", {})
            entries_map     = maps.get("animethemeentries", {})
            videos_map      = maps.get("videos", {})
            anime_map       = maps.get("anime", {})

            for anime_primary in anime_list:
                # l’anime lui-même est dans primary (souvent aussi dupliqué dans included)
                # on récupère sa version included si dispo pour avoir attributes complets
                anime_id = str(anime_primary.get("id"))
                anime_obj = anime_map.get(anime_id, anime_primary)

                # tous les animethemes liés à cet anime
                theme_ids = get_rel_ids(anime_obj, "animethemes")
                if not theme_ids:
                    continue

                # filtre OPs
                op_theme_ids = [tid for tid in theme_ids if is_op_theme(animethemes_map.get(tid, {}))]
                if not op_theme_ids:
                    continue

                # pour chaque theme OP -> entries -> videos -> basename
                for tid in op_theme_ids:
                    th = animethemes_map.get(tid)
                    if not th:
                        continue
                    entry_ids = get_rel_ids(th, "animethemeentries")
                    if not entry_ids:
                        continue
                    for eid in entry_ids:
                        entry = entries_map.get(eid)
                        if not entry:
                            continue
                        vid_ids = get_rel_ids(entry, "videos")
                        if not vid_ids:
                            continue
                        for vid_id in vid_ids:
                            vobj = videos_map.get(vid_id)
                            if not vobj:
                                continue
                            basename = video_basename(vobj)
                            if not basename:
                                continue

                            title_fb = anime_title(anime_obj)
                            aid = anime_anilist_id(anime_obj)
                            candidates.append((basename, title_fb, aid))
                            if aid:
                                collected_aids.append(aid)

            print(f"[anime] page {page}: {len(anime_list)} animes • candidats cumulés: {len(candidates)}")

            links = payload.get("links") or {}
            if not links.get("next"):
                break
            page += 1
            if page > 200:  # garde-fou
                break

        # Lookup AniList
        print("→ AniList lookup…")
        mdict = await anilist_lookup(session, list(set(collected_aids)))

        # Téléchargements
        print("→ Téléchargements…")
        sem = asyncio.Semaphore(CONCURRENCY)
        downloaded = 0

        async def worker(basename: str, title_fb: str, aid: Optional[int]):
            nonlocal downloaded
            if downloaded >= MAX_OPS:
                return
            m = mdict.get(aid) if aid else None
            if m and not allow_media(m):
                return

            if m:
                t = m.get("title") or {}
                title = t.get("romaji") or t.get("english") or t.get("native") or title_fb
                year  = m.get("seasonYear")
            else:
                title = title_fb
                year  = None

            safe = slugify(title)
            fname = f"{safe}_OP.mp3"
            dest = OUT_DIR / fname
            if dest.exists():
                return

            url = f"https://animethemes.moe/audio/{basename}.mp3"

            async with sem:
                ok = await download_file(session, url, dest)
            if not ok:
                return

            manifest[fname] = {
                "title": title,
                "label": "OP",
                "anilistId": aid,
                "year": year,
                "source": url,
                "type": "audio_direct"
            }
            save_manifest(manifest)
            downloaded += 1

        tasks = [asyncio.create_task(worker(b, t, a)) for (b, t, a) in candidates]
        if tasks:
            await asyncio.gather(*tasks)

    print(f"Terminé. Nouveaux OP ajoutés : {sum(1 for k in load_manifest().keys())}")
    print(f"Dossier:  {OUT_DIR.resolve()}")
    print(f"Manifest: {MANIFEST.resolve()}")

if __name__ == "__main__":
    asyncio.run(main())
