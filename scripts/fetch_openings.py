# scripts/fetch_openings.py
# --------------------------------------------
# Télécharge des OP depuis AnimeThemes, filtre via AniList,
# extrait 20s en MP3 avec ffmpeg, et sauvegarde dans assets/audio/openings/.
#
# Dépendances:
#   pip install aiohttp
#   ffmpeg présent dans le PATH (ffmpeg --version)
#
# Lancer:
#   python scripts/fetch_openings.py
# --------------------------------------------

from __future__ import annotations
import os, re, json, asyncio, random
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import asyncio.subprocess as asp

# ============ CONFIG ============
OUT_DIR   = Path("assets/audio/openings")
TMP_DIR   = Path("assets/_tmp_openings")
MANIFEST  = Path("assets/audio/manifest.json")

# Interrupteurs
USE_ANILIST_FILTERS = True          # coupe à False pour valider le flux brut
LOG_EVERY_OP_FOUND  = False         # True = log chaque OP trouvé côté AnimeThemes

# Filtres (si USE_ANILIST_FILTERS = True)
MIN_YEAR      = 2005
MIN_SCORE_10  = 5.0                 # 5/10 (AniList est /100)
BANNED_GENRES = {"mahou shoujo", "kids"}
BANNED_FORMATS = {"MUSIC"}          # ajoute "ONA" si besoin

MAX_OPS      = 200                  # limite totale à récupérer
CONCURRENCY  = 4                    # téléchargements simultanés

# Endpoints
ANIMETHEMES_BASE = "https://api.animethemes.moe"
ANILIST_GQL      = "https://graphql.anilist.co"

# ============ UTILS ============
def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s\-]", "", str(text), flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+", " ", text)
    return (text.replace(" ", "_") or "untitled")[:100]

def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

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

def pick_seek(max_seconds: int = 60) -> int:
    return random.randint(0, max_seconds)

# ============ HTTP ============

async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    accept_header: str = "application/vnd.api+json",
) -> Optional[Dict[str, Any]]:
    headers = {
        "Accept": accept_header,
        "User-Agent": "AnimeBot-OPFetcher/1.0 (+https://github.com/Zirnoix/AnimeBot)"
    }
    for attempt in range(3):
        try:
            async with session.get(url, params=params, headers=headers, timeout=30) as resp:
                if resp.status == 200:
                    return await resp.json()
                text = await resp.text()
                print(f"[fetch_json] {url} -> HTTP {resp.status} (try {attempt+1}/3)")
                print(f"[fetch_json] Body preview: {text[:300]!r}")
                await asyncio.sleep(1.0)
        except Exception as e:
            print(f"[fetch_json] Exception: {e} (try {attempt+1}/3)")
            await asyncio.sleep(1.2)
    return None

async def post_json(session: aiohttp.ClientSession, url: str, payload: Dict[str, Any]) -> Any:
    for attempt in range(3):
        try:
            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    return await resp.json()
                text = await resp.text()
                print(f"[post_json] {url} -> HTTP {resp.status} (try {attempt+1}/3)")
                print(f"[post_json] Body preview: {text[:300]!r}")
        except Exception as e:
            print(f"[post_json] Exception: {e} (try {attempt+1}/3)")
        await asyncio.sleep(1.0)
    return None

# ============ ANIMETHEMES ============
async def iter_animethemes(session: aiohttp.ClientSession):
    """
    Itère les pages /anime en important thèmes + vidéos.
    Pagination JSON:API: page[number], page[size]
    """
    page_number = 1
    while True:
        params = {
            "page[number]": page_number,
            "page[size]": 50,  # max 100
            "include": "animethemes.animethemeentries.videos,resources",
        }
        data = await fetch_json(session, f"{ANIMETHEMES_BASE}/anime", params=params)
        if not data:
            print(f"[iter_animethemes] Page {page_number}: pas de données JSON.")
            break

        anime_list = data.get("anime")
        if anime_list is None:
            print(f"[iter_animethemes] Page {page_number}: clé 'anime' absente. Clés: {list(data.keys())}")
            break
        if not anime_list:
            print(f"[iter_animethemes] Page {page_number}: liste vide. Fin.")
            break

        for a in anime_list:
            yield a

        links = data.get("links") or {}
        nxt = links.get("next")
        print(f"[iter_animethemes] Page {page_number}: {len(anime_list)} animes — next={bool(nxt)}")
        if not nxt:
            break
        page_number += 1

def extract_anilist_id(anime: Dict[str, Any]) -> Optional[int]:
    """
    AnimeThemes fournit parfois anilistId directement,
    sinon via resources (site: anilist).
    """
    aid = anime.get("anilistId")
    if aid:
        try:
            return int(aid)
        except Exception:
            pass
    for r in anime.get("resources") or []:
        site = (r.get("site") or "").lower()
        if "anilist" in site and r.get("externalId"):
            try:
                return int(r["externalId"])
            except Exception:
                pass
    return None

def extract_op_audio_urls(anime: dict) -> list[dict]:
    """
    Retourne une liste de {url, label} pour les OP sous forme AUDIO direct
    via https://animethemes.moe/audio/{basename}.mp3.
    Si basename indisponible, on essaie 'link' vidéo en fallback.
    """
    out = []
    themes = anime.get("animethemes") or []
    for th in themes:
        if (th.get("type") or "").upper() != "OP":
            continue
        label = (th.get("slug") or th.get("type") or "OP").upper()
        entries = th.get("animethemeentries") or []
        for e in entries:
            videos = e.get("videos") or []
            for v in videos:
                basename = v.get("basename")
                if basename:
                    url = f"https://animethemes.moe/audio/{basename}.mp3"
                    out.append({"url": url, "label": label})
                elif v.get("link"):  # fallback très rare
                    # on pourra encore extraire l'audio depuis la vidéo si tu veux
                    out.append({"url": v["link"], "label": label})
    return out

def choose_op_label(theme: dict) -> str:
    # ex: "OP", "OP1", "OP2"…
    slug = (theme.get("slug") or "").upper()
    typ  = (theme.get("type") or "OP").upper()
    return slug or typ or "OP"

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

def allow_media(m: Dict[str, Any]) -> bool:
    if not USE_ANILIST_FILTERS:
        return True
    # année
    year = m.get("seasonYear") or 0
    if year and year < MIN_YEAR:
        return False
    # score (/100 sur AniList)
    score = m.get("averageScore")
    if score is not None and MIN_SCORE_10 is not None:
        if (score / 10.0) < float(MIN_SCORE_10):
            return False
    # format
    fmt = (m.get("format") or "").upper()
    if fmt in {s.upper() for s in BANNED_FORMATS}:
        return False
    # genres
    lg = {g.lower() for g in (m.get("genres") or [])}
    if lg & {g.lower() for g in BANNED_GENRES}:
        return False
    return True

def choose_title(m: Dict[str, Any]) -> str:
    t = m.get("title") or {}
    return t.get("romaji") or t.get("english") or t.get("native") or "Titre inconnu"

# ============ DL & FFMPEG ============
async def download_file(session: aiohttp.ClientSession, url: str, dest: Path) -> bool:
    try:
        async with session.get(url, timeout=90) as resp:
            if resp.status != 200:
                print(f"[download] {url} -> HTTP {resp.status}")
                return False
            with dest.open("wb") as f:
                async for chunk in resp.content.iter_chunked(1 << 14):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception as e:
        print(f"[download] {url} -> exception {e}")
        return False

async def ffmpeg_extract_20s(src: Path, dest_mp3: Path, seek: int = 0) -> bool:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(seek),
        "-i", str(src),
        "-t", "20",
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", "192k",
        str(dest_mp3),
    ]
    try:
        proc = await asp.create_subprocess_exec(*cmd, stdout=asp.PIPE, stderr=asp.PIPE)
        _out, _err = await proc.communicate()
        if proc.returncode != 0:
            print(f"[ffmpeg] returncode={proc.returncode} on {src.name}")
        return proc.returncode == 0
    except Exception as e:
        print(f"[ffmpeg] exception {e}")
        return False

# ============ PIPELINE ============
async def process_one(session: aiohttp.ClientSession,
                      anime_at: Dict[str, Any],
                      media: Dict[str, Any],
                      manifest: Dict[str, Any]) -> int:
    """
    Télécharge des OP AUDIO prêts à l’emploi (MP3 complet) via /audio/{basename}.mp3.
    Pas d’extraction ffmpeg nécessaire ici.
    """
    added = 0
    title = choose_title(media)
    safe_title = slugify(title)

    ops = extract_op_audio_urls(anime_at)
    if not ops:
        return 0

    for op in ops:
        if len(manifest) >= MAX_OPS:
            break

        url = op["url"]
        label = op.get("label") or "OP"
        base_name = f"{safe_title}_{label}.mp3"
        final_mp3 = OUT_DIR / base_name

        if final_mp3.exists():
            continue

        ok = await download_file(session, url, final_mp3)
        if not ok:
            # si l’audio direct échoue et que c’était une vidéo fallback,
            # tu pourrais ici tenter la voie ffmpeg -> mp3 (optionnel)
            continue

        # garde une trace
        manifest[base_name] = {
            "title": title,
            "label": label,
            "anilistId": media.get("id"),
            "year": media.get("seasonYear"),
            "source": url,
            "type": "audio_direct"
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
        # 1) Parcourir AnimeThemes (pages)
        print("→ Récupération AnimeThemes…")
        candidates: List[Dict[str, Any]] = []
        anilist_ids: List[int] = []

        async for anime_at in iter_animethemes(session):
            aid = extract_anilist_id(anime_at)
            if not aid:
                continue
            # Vérifie qu'on a bien des OP vidéos
            op_urls = extract_op_audio_urls(anime_at)
            if not op_urls:
                continue
            anilist_ids.append(aid)
            candidates.append({"at": anime_at, "aid": aid})

        if not candidates:
            print("Aucun anime exploitable (pas d’OP vidéo trouvée).")
            return

        print(f"→ Candidats AnimeThemes (avec OP vidéo): {len(candidates)}")

        # 2) Lookup AniList en batch
        print("→ Lookup AniList…")
        mdict = await anilist_lookup(session, anilist_ids)
        print(f"→ Medias AniList récupérés: {len(mdict)}")

        # 3) Filtrage + traitement concurrent
        sem = asyncio.Semaphore(CONCURRENCY)

        async def worker(item):
            nonlocal total_added
            at = item["at"]
            aid = item["aid"]
            m = mdict.get(aid)
            if not m:
                return
            if not allow_media(m):
                return
            async with sem:
                added = await process_one(session, at, m, manifest)
                total_added += added

        print("→ Téléchargements / conversions…")
        tasks = [asyncio.create_task(worker(c)) for c in candidates]
        await asyncio.gather(*tasks)

    print(f"Terminé. Nouveaux OP ajoutés : {total_added}")
    print(f"Fichiers disponibles dans: {OUT_DIR.resolve()}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrompu.")
