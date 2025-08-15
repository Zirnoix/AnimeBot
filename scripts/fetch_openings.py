# scripts/fetch_openings.py
# --------------------------------------------
# Télécharge des OP depuis AnimeThemes, filtre via AniList,
# extrait 20s en MP3 avec ffmpeg, et sauvegarde dans assets/audio/openings/.
#
# Dépendances:
#   pip install aiohttp
#   ffmpeg présent dans le PATH (ffmpeg --version)
#
# Paramètres modifiables (voir la section CONFIG).
# --------------------------------------------

from __future__ import annotations
import os, re, json, asyncio, shutil, random, string
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import asyncio.subprocess as asp

# ============ CONFIG ============
OUT_DIR = Path("assets/audio/openings")
TMP_DIR = Path("assets/_tmp_openings")
MANIFEST = Path("assets/audio/manifest.json")

# Filtres
MIN_YEAR = 2005
MIN_SCORE_10 = 5.0                          # 5/10
BANNED_GENRES = {"mahou shoujo", "kids"}    # à adapter
BANNED_FORMATS = {"MUSIC"}                  # ex: {"MUSIC", "ONA"} si tu veux
MAX_OPS = 200                               # limite totale à récupérer
CONCURRENCY = 4                             # téléchargements simultanés

# Endpoints
ANIMETHEMES_API = "https://api.animethemes.moe/anime"
ANILIST_GQL = "https://graphql.anilist.co"

# ============ UTILS ============
def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s\-]", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" ", "_")
    return text[:100] or "untitled"

def clean_title_from_filename(name: str) -> str:
    base = Path(name).stem
    base = re.sub(r"[\[\(].*?[\]\)]", "", base, flags=re.IGNORECASE)
    base = re.sub(r"\b(OP|OPENING|ED|ENDING)\s*\d*\b", "", base, flags=re.IGNORECASE)
    base = re.sub(r"[_\-]+", " ", base)
    base = re.sub(r"\s{2,}", " ", base).strip()
    return base or Path(name).stem

def ensure_dirs():
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
async def fetch_json(session: aiohttp.ClientSession, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    for _ in range(3):
        try:
            async with session.get(url, params=params, timeout=30) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
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
    """Retourne {anilistId: mediaDict}."""
    out: Dict[int, Dict] = {}
    # batch par 50
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

# ============ ANIMETHEMES ============
async def iter_animethemes(session: aiohttp.ClientSession):
    """
    Itère sur les entrées AnimeThemes avec leurs animethemes + videos.
    On demande year>=MIN_YEAR côté AnimeThemes pour limiter.
    """
    page = 1
    while True:
        params = {
            "page": page,
            "perPage": 25,
            "include": "animethemes.animethemeentries.videos,resources",
            "filter[year]": f">={MIN_YEAR}",
            # on pourrait aussi filtrer has=resources pour avoir anilist id, mais parfois c'est ailleurs
        }
        data = await fetch_json(session, ANIMETHEMES_API, params=params)
        if not data or "anime" not in data:
            break
        anime_list = data.get("anime") or []
        if not anime_list:
            break
        for a in anime_list:
            yield a
        # pagination
        pag = data.get("links", {})
        if not pag.get("next"):
            break
        page += 1

def extract_anilist_id(anime: Dict[str, Any]) -> Optional[int]:
    """
    AnimeThemes fournit parfois anilistId directement,
    sinon dans resources (site: anilist.co).
    """
    aid = anime.get("anilistId")
    if aid:
        return int(aid)
    for r in anime.get("resources") or []:
        site = (r.get("site") or "").lower()
        if "anilist" in site and r.get("externalId"):
            try:
                return int(r["externalId"])
            except Exception:
                pass
    return None

def choose_title(m: Dict[str, Any]) -> str:
    t = m.get("title") or {}
    return t.get("romaji") or t.get("english") or t.get("native") or "Titre inconnu"

def allow_media(m: Dict[str, Any]) -> bool:
    # année
    year = m.get("seasonYear") or 0
    if year and year < MIN_YEAR:
        return False
    # score
    score = m.get("averageScore")
    if score is not None:
        if (score / 10.0) < MIN_SCORE_10:  # AniList est /100
            return False
    # format
    fmt = (m.get("format") or "").upper()
    if fmt in BANNED_FORMATS:
        return False
    # genres
    gset = set((m.get("genres") or []))
    lg = {g.lower() for g in gset}
    if lg & BANNED_GENRES:
        return False
    return True

def pick_op_videolink(animethemes_anime: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Retourne une liste de candidates {url, label} à télécharger (OPs uniquement).
    On récupère le premier 'video.link' par entry, ou celui marqué 'audio' si dispo.
    """
    out = []
    themes = animethemes_anime.get("animethemes") or []
    for th in themes:
        if (th.get("type") or "").upper() != "OP":
            continue
        entries = th.get("animethemeentries") or []
        for e in entries:
            videos = e.get("videos") or []
            # priorité aux vidéos avec audio, sinon fallback au premier lien
            candidate = None
            for v in videos:
                if v.get("link"):
                    candidate = v
                    if v.get("audio") is True:
                        break
            if candidate and candidate.get("link"):
                # label ex: OP1, OP2
                suffix = th.get("slug") or th.get("type") or "OP"
                label = suffix.upper()
                out.append({"url": candidate["link"], "label": label})
    return out

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

async def ffmpeg_extract_20s(src: Path, dest_mp3: Path, seek: int = 0) -> bool:
    """
    Utilise ffmpeg pour extraire 20s en MP3.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(seek),     # seek
        "-i", str(src),
        "-t", "20",
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", "192k",
        str(dest_mp3),
    ]
    try:
        proc = await asp.create_subprocess_exec(
            *cmd, stdout=asp.PIPE, stderr=asp.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False

# ============ PIPELINE ============
async def process_one(session: aiohttp.ClientSession,
                      anime_at: Dict[str, Any],
                      media: Dict[str, Any],
                      manifest: Dict[str, Any]) -> int:
    """
    Traite un anime (déjà filtré), télécharge 1..n OPs -> MP3 20s.
    Retourne le nombre de MP3 ajoutés.
    """
    added = 0
    title = choose_title(media)
    ops = pick_op_videolink(anime_at)
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

        # déjà présent ?
        if final_mp3.exists():
            continue

        # download vidéo → tmp
        ext = "webm" if ".webm" in url else "mp4"
        tmp_video = TMP_DIR / f"tmp_{safe_title}_{label}.{ext}"
        ok = await download_file(session, url, tmp_video)
        if not ok:
            # tentative: parfois lien expire → on skip
            continue

        # extract 20s
        seek = pick_seek(60)
        ok2 = await ffmpeg_extract_20s(tmp_video, final_mp3, seek=seek)
        # cleanup
        try:
            tmp_video.unlink(missing_ok=True)
        except Exception:
            pass

        if ok2 and final_mp3.exists() and final_mp3.stat().st_size > 0:
            manifest[base_name] = {
                "title": title,
                "label": label,
                "anilistId": media.get("id"),
                "year": media.get("seasonYear"),
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
        # 1) Parcourir AnimeThemes (par pages)
        print("→ Récupération AnimeThemes…")
        candidates: List[Dict[str, Any]] = []
        anilist_ids: List[int] = []

        async for anime_at in iter_animethemes(session):
            aid = extract_anilist_id(anime_at)
            if not aid:
                continue
            anilist_ids.append(aid)
            candidates.append({"at": anime_at, "aid": aid})

        if not candidates:
            print("Aucun anime trouvé côté AnimeThemes.")
            return

        # 2) Lookup AniList en batch
        print("→ Lookup AniList…")
        mdict = await anilist_lookup(session, anilist_ids)

        # 3) Filtrage et traitement concurrent
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
        # Limite globale par MAX_OPS
        # (arrêt grossier si on dépasse pendant la boucle)
        await asyncio.gather(*tasks)

    print(f"Terminé. Nouveaux OP ajoutés : {total_added}")
    print(f"Fichiers disponibles dans: {OUT_DIR.resolve()}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrompu.")
