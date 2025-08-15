# scripts/fetch_openings.py
# --------------------------------------------
# Télécharge des OP au format MP3 depuis AnimeThemes (audio direct),
# filtre via AniList (année/score/genres/formats),
# et sauvegarde dans assets/audio/openings/.
#
# Dépendances:
#   pip install aiohttp
#
# Lancement:
#   python scripts/fetch_openings.py
# --------------------------------------------

from __future__ import annotations
import os, re, json, asyncio, random
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.parse as _urlparse

import aiohttp

# ============ CONFIG ============
OUT_DIR = Path("assets/audio/openings")
MANIFEST = Path("assets/audio/manifest.json")

# Filtres AniList (tu peux assouplir pour tester)
MIN_YEAR = 2005
MIN_SCORE_10 = 5.0                          # 5/10 (AniList est /100)
BANNED_GENRES = {"mahou shoujo", "kids"}    # ajoute ce que tu veux
BANNED_FORMATS = {"MUSIC"}                  # ex: {"MUSIC", "ONA"} si tu veux

MAX_OPS = 200          # nombre total de MP3 à récupérer
CONCURRENCY = 6        # téléchargements simultanés

# Endpoints
ANIMETHEMES_BASE = "https://api.animethemes.moe"
ANILIST_GQL      = "https://graphql.anilist.co"

# ============ UTILS ============
def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s\-]", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" ", "_")
    return text[:100] or "untitled"

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

# ============ HTTP ============
async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    accept_header: str = "application/vnd.api+json",
) -> Optional[Dict[str, Any]]:
    headers = {
        "Accept": accept_header,
        "User-Agent": "AnimeBot-OPFetcher/1.1 (+https://github.com/Zirnoix/AnimeBot)"
    }
    for attempt in range(3):
        try:
            async with session.get(url, params=params, headers=headers, timeout=30) as resp:
                if resp.status == 200:
                    return await resp.json()
                body = await resp.text()
                print(f"[fetch_json] {url} -> {resp.status} (try {attempt+1}/3)")
                print(f"[fetch_json] body: {body[:200]!r}")
                await asyncio.sleep(1.0)
        except Exception as e:
            print(f"[fetch_json] EXC {url}: {e} (try {attempt+1}/3)")
            await asyncio.sleep(1.0)
    return None

async def post_json(session: aiohttp.ClientSession, url: str, payload: Dict[str, Any]) -> Any:
    for _ in range(3):
        try:
            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            await asyncio.sleep(1.0)
    return None

# ============ JSON:API HELPERS ============
def ja_attr(obj: dict, key: str, default=None):
    if key in obj:
        return obj.get(key, default)
    return (obj.get("attributes") or {}).get(key, default)

def ja_type_id(obj: dict):
    return (obj.get("type"), str(obj.get("id")))

class JAIndex:
    def __init__(self, included: List[dict] | None):
        self.idx: Dict[tuple[str, str], dict] = {}
        for it in (included or []):
            t, i = ja_type_id(it)
            if t and i:
                self.idx[(t, i)] = it

    def get(self, t: str, i: str) -> dict | None:
        return self.idx.get((t, i))

def ja_rel_items(obj: dict, index: JAIndex, rel_name: str) -> list[dict]:
    rel = (obj.get("relationships") or {}).get(rel_name) or {}
    data = rel.get("data")
    if not data:
        return []
    out = []
    if isinstance(data, list):
        for ref in data:
            t = ref.get("type"); i = str(ref.get("id"))
            if t and i:
                found = index.get(t, i)
                if found:
                    out.append(found)
    else:
        t = data.get("type"); i = str(data.get("id"))
        if t and i:
            found = index.get(t, i)
            if found:
                out.append(found)
    return out

def derive_basename_from_link(link: str) -> str | None:
    p = _urlparse.urlparse(link or "")
    fname = os.path.basename(p.path)
    if not fname:
        return None
    base, _ext = os.path.splitext(fname)
    return base or fname

# ============ ANIMETHEMES ============

async def iter_animethemes(session: aiohttp.ClientSession):
    """
    Itère l’API /anime en résolvant les relations via 'included'.
    Rend (anime, index) pour pouvoir retrouver entries/videos/resources.
    """
    page_number = 1
    total_candidates_seen = 0
    while True:
        params = {
            "page[number]": page_number,
            "page[size]": 50,
            "include": "animethemes.animethemeentries.videos,resources",
        }
        data = await fetch_json(session, f"{ANIMETHEMES_BASE}/anime", params=params)
        if not data:
            print(f"[anime] page {page_number}: no payload (stop).")
            break

        anime_list = data.get("anime") or data.get("data")
        included = data.get("included") or []
        if anime_list is None:
            print(f"[anime] page {page_number}: clé 'anime'/'data' absente. Clés: {list(data.keys())}")
            break
        if not anime_list:
            print(f"[anime] page {page_number}: liste vide. Fin.")
            break

        index = JAIndex(included)

        page_candidates = 0
        for a in anime_list:
            themes = ja_rel_items(a, index, "animethemes") or ja_rel_items(a, index, "animetheme")
            has_op = False
            for th in themes:
                ttype = str(ja_attr(th, "type", "")).upper()
                if ttype != "OP":
                    continue
                entries = ja_rel_items(th, index, "animethemeentries") or ja_rel_items(th, index, "animethemeEntries")
                for e in entries:
                    vids = ja_rel_items(e, index, "videos")
                    if vids:
                        has_op = True
                        break
                if has_op:
                    break
            if has_op:
                page_candidates += 1

            yield a, index

        total_candidates_seen += page_candidates
        nxt = (data.get("links") or {}).get("next")
        print(f"[anime] page {page_number}: {len(anime_list)} animes • candidats cumulés: {total_candidates_seen}")
        if not nxt:
            break
        page_number += 1

def extract_anilist_id(anime: Dict[str, Any], index: JAIndex) -> Optional[int]:
    aid = anime.get("anilistId") or ja_attr(anime, "anilist_id")
    if aid:
        try:
            return int(aid)
        except Exception:
            pass
    for r in ja_rel_items(anime, index, "resources"):
        site = (ja_attr(r, "site", "") or "").lower()
        ext  = ja_attr(r, "external_id") or r.get("externalId")
        if "anilist" in site and ext:
            try:
                return int(ext)
            except Exception:
                pass
    return None

def pick_op_audio_links(anime: Dict[str, Any], index: JAIndex) -> List[Dict[str, str]]:
    """
    Liste de candidates {url, label} pour les OP au format MP3 direct.
    Construit l’URL https://animethemes.moe/audio/{basename}.mp3
    à partir de video.basename (ou bascule depuis video.link).
    """
    out = []
    themes = ja_rel_items(anime, index, "animethemes") or ja_rel_items(anime, index, "animetheme")
    for th in themes:
        if str(ja_attr(th, "type", "")).upper() != "OP":
            continue
        label = (ja_attr(th, "slug") or ja_attr(th, "type") or "OP").upper()
        entries = ja_rel_items(th, index, "animethemeentries") or ja_rel_items(th, index, "animethemeEntries")
        for e in entries:
            vids = ja_rel_items(e, index, "videos")
            for v in vids:
                basename = ja_attr(v, "basename")
                if not basename:
                    link = ja_attr(v, "link") or v.get("link")
                    basename = derive_basename_from_link(link or "")
                if basename:
                    url = f"https://animethemes.moe/audio/{basename}.mp3"
                    out.append({"url": url, "label": label})
    return out

# ============ ANILIST ============
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
        data = await post_json(session, ANILIST_GQL, {"query": ANILIST_QUERY, "variables": {"ids": chunk}})
        try:
            medias = data["data"]["Page"]["media"]
            for m in medias:
                out[int(m["id"])] = m
        except Exception:
            pass
    return out

def choose_title(m: Dict[str, Any]) -> str:
    t = m.get("title") or {}
    return t.get("romaji") or t.get("english") or t.get("native") or "Titre inconnu"

def allow_media(m: Dict[str, Any]) -> bool:
    # année
    year = m.get("seasonYear") or 0
    if year and year < MIN_YEAR:
        return False
    # score (/100 -> /10)
    score = m.get("averageScore")
    if score is not None and (score / 10.0) < MIN_SCORE_10:
        return False
    # format
    fmt = (m.get("format") or "").upper()
    if fmt in BANNED_FORMATS:
        return False
    # genres
    lg = {str(g).lower() for g in (m.get("genres") or [])}
    if lg & BANNED_GENRES:
        return False
    return True

# ============ TÉLÉCHARGEMENT ============
async def download_file(session: aiohttp.ClientSession, url: str, dest: Path) -> bool:
    try:
        async with session.get(url, timeout=60) as resp:
            if resp.status != 200:
                return False
            with dest.open("wb") as f:
                async for chunk in resp.content.iter_chunked(1 << 14):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception:
        return False

def unique_path(base: Path) -> Path:
    """Évite d’écraser : ajoute un suffixe -2, -3… si nécessaire."""
    if not base.exists():
        return base
    stem, suf = base.stem, base.suffix
    i = 2
    while True:
        p = base.with_name(f"{stem}-{i}{suf}")
        if not p.exists():
            return p
        i += 1

# ============ PIPELINE ============
async def process_one(session: aiohttp.ClientSession,
                      anime_at: Dict[str, Any],
                      at_index: JAIndex,
                      media: Dict[str, Any],
                      manifest: Dict[str, Any]) -> int:
    """
    Pour un anime (déjà filtré), télécharge 1..n OPs → MP3 direct.
    """
    added = 0
    title = choose_title(media)
    ops = pick_op_audio_links(anime_at, at_index)
    if not ops:
        return 0

    for op in ops:
        if len(manifest) >= MAX_OPS:
            break
        url = op["url"]
        label = op["label"] or "OP"

        safe_title = slugify(title)
        base_name = f"{safe_title}_{label}.mp3"
        final_mp3 = OUT_DIR / base_name
        final_mp3 = unique_path(final_mp3)

        ok = await download_file(session, url, final_mp3)
        if not ok:
            continue

        # vérif taille > 0
        try:
            if final_mp3.stat().st_size <= 0:
                final_mp3.unlink(missing_ok=True)
                continue
        except Exception:
            continue

        manifest[final_mp3.name] = {
            "title": title,
            "label": label,
            "anilistId": media.get("id"),
            "year": media.get("seasonYear"),
            "source": "AnimeThemes(audio)",
        }
        save_manifest(manifest)
        added += 1

    return added

async def main():
    print("→ Préparation des dossiers…")
    ensure_dirs()
    manifest = load_manifest()

    total_added = 0

    async with aiohttp.ClientSession() as session:
        # 1) Parcourir AnimeThemes
        print("→ Récupération AnimeThemes…")
        candidates: List[Dict[str, Any]] = []
        anilist_ids: List[int] = []

        async for anime_at, at_index in iter_animethemes(session):
            aid = extract_anilist_id(anime_at, at_index)
            if not aid:
                continue
            anilist_ids.append(aid)
            candidates.append({"at": anime_at, "idx": at_index, "aid": aid})

        if not candidates:
            print("Aucun anime trouvé côté AnimeThemes.")
            return

        # 2) Lookup AniList
        print("→ AniList lookup…")
        mdict = await anilist_lookup(session, anilist_ids)

        # 3) Téléchargements avec filtres
        print("→ Téléchargements…")
        sem = asyncio.Semaphore(CONCURRENCY)

        async def worker(item):
            nonlocal total_added
            at = item["at"]
            idx = item["idx"]
            aid = item["aid"]
            m = mdict.get(aid)
            if not m:
                return
            if not allow_media(m):
                return
            async with sem:
                if len(manifest) >= MAX_OPS:
                    return
                added = await process_one(session, at, idx, m, manifest)
                total_added += added

        # on stoppe quand on atteint MAX_OPS même si on a créé toutes les tasks
        tasks = [asyncio.create_task(worker(c)) for c in candidates]
        await asyncio.gather(*tasks)

    print(f"Terminé. Nouveaux OP ajoutés : {total_added}")
    print(f"Dossier:  {OUT_DIR.resolve()}")
    print(f"Manifest: {MANIFEST.resolve()}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrompu.")
