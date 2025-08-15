# scripts/fetch_openings.py
from __future__ import annotations
import os, re, json, asyncio, random
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.parse as urlparse

import aiohttp

OUT_DIR = Path("assets/audio/openings")
MANIFEST = Path("assets/audio/manifest.json")

# --- Filtres AniList (NOFILTER=1 pour tout désactiver rapidement) ---
NOFILTER = os.getenv("NOFILTER", "0") == "1"
MIN_YEAR = 1900 if NOFILTER else 2005
MIN_SCORE_10 = 0.0 if NOFILTER else 5.0
BANNED_GENRES = set() if NOFILTER else {"mahou shoujo", "kids"}
BANNED_FORMATS = set() if NOFILTER else {"MUSIC"}

MAX_OPS = 200
CONCURRENCY = 6

ANIMETHEMES_BASE = "https://api.animethemes.moe"
ANILIST_GQL      = "https://graphql.anilist.co"

def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s\-]", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+", " ", text)
    return (text.replace(" ", "_") or "untitled")[:100]

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

async def fetch_json(session: aiohttp.ClientSession, url: str, params: dict | None = None) -> dict | None:
    headers = {
        "Accept": "application/vnd.api+json",
        "User-Agent": "AnimeBot-OPFetcher/1.2",
    }
    for attempt in range(3):
        try:
            async with session.get(url, params=params, headers=headers, timeout=30) as resp:
                if resp.status == 200:
                    return await resp.json()
                body = await resp.text()
                print(f"[GET] {url} -> {resp.status} (try {attempt+1}/3) body[:200]={body[:200]!r}")
                await asyncio.sleep(1.0)
        except Exception as e:
            print(f"[GET] {url} EXC {e} (try {attempt+1}/3)")
            await asyncio.sleep(1.0)
    return None

async def post_json(session: aiohttp.ClientSession, url: str, payload: dict) -> dict | None:
    for _ in range(3):
        try:
            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            await asyncio.sleep(1.0)
    return None

# ---------- JSON:API helpers robustes ----------
def ja_attr(obj: dict, key: str, default=None):
    if key in obj:  # parfois à la racine
        return obj.get(key, default)
    return (obj.get("attributes") or {}).get(key, default)

def ja_rel(obj: dict) -> dict:
    return obj.get("relationships") or {}

def rel_block(obj: dict, *names: str) -> dict | None:
    r = ja_rel(obj)
    for n in names:
        if n in r:  # exact
            return r[n]
        # essaie des variantes communes
        for k in r.keys():
            if k.lower() == n.lower():
                return r[k]
    return None

def rel_items(obj: dict, index: dict[tuple[str,str], dict], *names: str) -> list[dict]:
    block = rel_block(obj, *names)
    if not block:
        return []
    data = block.get("data")
    if not data:
        return []
    out = []
    if isinstance(data, list):
        for ref in data:
            t = ref.get("type"); i = str(ref.get("id"))
            if t and i and (t, i) in index:
                out.append(index[(t, i)])
    else:
        t = data.get("type"); i = str(data.get("id"))
        if t and i and (t, i) in index:
            out.append(index[(t, i)])
    return out

def build_index(included: list[dict] | None) -> dict[tuple[str,str], dict]:
    idx: dict[tuple[str,str], dict] = {}
    for it in (included or []):
        t = it.get("type"); i = str(it.get("id"))
        if t and i:
            idx[(t, i)] = it
    return idx

def derive_basename_from_link(link: str) -> str | None:
    p = urlparse.urlparse(link or "")
    fname = os.path.basename(p.path)
    if not fname:
        return None
    base, _ = os.path.splitext(fname)
    return base or fname

# ---------- Extraction OP audio ----------
def pick_op_audio_links(anime: dict, index: dict[tuple[str,str], dict]) -> list[dict]:
    """
    Retourne des {url,label} d’OP en MP3 direct.
    Essaie via relationships (included) puis fallback via attributes inline.
    """
    out: list[dict] = []

    # 1) via relationships + included
    themes = rel_items(anime, index, "animethemes", "animetheme", "themes")
    if not themes:
        # 2) fallback: inline attributes (rare)
        themes = (ja_attr(anime, "animethemes") or ja_attr(anime, "themes") or [])
        # dans ce cas, “entries”/“videos” peuvent aussi être inline

    def iter_entries(theme_obj: dict) -> list[dict]:
        # via relationships
        ents = rel_items(theme_obj, index, "animethemeentries", "animethemeEntries", "entries")
        if ents:
            return ents
        # sinon inline
        return (ja_attr(theme_obj, "animethemeentries") or
                ja_attr(theme_obj, "animethemeEntries") or
                ja_attr(theme_obj, "entries") or [])

    def iter_videos(entry_obj: dict) -> list[dict]:
        vids = rel_items(entry_obj, index, "videos")
        if vids:
            return vids
        return ja_attr(entry_obj, "videos") or []

    for th in themes:
        ttype = str(ja_attr(th, "type", "")).upper()
        if ttype != "OP":
            continue
        label = (ja_attr(th, "slug") or ja_attr(th, "type") or "OP")
        label = label.upper()
        entries = iter_entries(th)
        for e in entries:
            videos = iter_videos(e)
            for v in videos:
                basename = ja_attr(v, "basename")
                if not basename:
                    link = ja_attr(v, "link") or v.get("link")
                    basename = derive_basename_from_link(link or "")
                if basename:
                    url = f"https://animethemes.moe/audio/{basename}.mp3"
                    out.append({"url": url, "label": label})
    return out

# ---------- AniList ----------
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
            for m in data["data"]["Page"]["media"]:
                out[int(m["id"])] = m
        except Exception:
            pass
    return out

def choose_title(m: Dict[str, Any]) -> str:
    t = m.get("title") or {}
    return t.get("romaji") or t.get("english") or t.get("native") or "Titre inconnu"

def allow_media(m: Dict[str, Any]) -> bool:
    year = m.get("seasonYear") or 0
    if year and year < MIN_YEAR:
        return False
    score = m.get("averageScore")
    if score is not None and (score / 10.0) < MIN_SCORE_10:
        return False
    fmt = (m.get("format") or "").upper()
    if fmt in BANNED_FORMATS:
        return False
    lg = {str(g).lower() for g in (m.get("genres") or [])}
    if lg & BANNED_GENRES:
        return False
    return True

# ---------- Pagination AnimeThemes ----------
async def iter_animethemes(session: aiohttp.ClientSession):
    page = 1
    total_candidates = 0
    while True:
        params = {
            "page[number]": page,
            "page[size]": 50,
            "include": "animethemes.animethemeentries.videos,resources",
        }
        data = await fetch_json(session, f"{ANIMETHEMES_BASE}/anime", params=params)
        if not data:
            print(f"[anime] page {page}: no payload (stop).")
            break

        anime_list = data.get("anime") or data.get("data")
        included   = data.get("included") or []
        if anime_list is None:
            print(f"[anime] page {page}: pas de clé 'anime'/'data'. keys={list(data.keys())}")
            break
        if not anime_list:
            print(f"[anime] page {page}: liste vide (stop).")
            break

        index = build_index(included)

        # log debug: combien d'OP détectés sur cette page
        page_with_ops = 0
        for a in anime_list:
            if pick_op_audio_links(a, index):
                page_with_ops += 1

        total_candidates += page_with_ops
        print(f"[anime] page {page}: {len(anime_list)} animes • avec OP détecté: {page_with_ops} • cumul: {total_candidates}")

        for a in anime_list:
            yield a, index

        if not (data.get("links") or {}).get("next"):
            break
        page += 1

def extract_anilist_id(anime: dict, index: dict[tuple[str,str], dict]) -> int | None:
    aid = anime.get("anilistId") or ja_attr(anime, "anilist_id")
    if aid:
        try:
            return int(aid)
        except Exception:
            pass
    # via resources
    res = rel_items(anime, index, "resources") or ja_attr(anime, "resources") or []
    for r in res:
        site = (ja_attr(r, "site", "") or "").lower()
        ext  = ja_attr(r, "external_id") or r.get("externalId")
        if "anilist" in site and ext:
            try:
                return int(ext)
            except Exception:
                pass
    return None

# ---------- Download ----------
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

def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    i = 2
    base, suf = p.stem, p.suffix
    while True:
        q = p.with_name(f"{base}-{i}{suf}")
        if not q.exists():
            return q
        i += 1

async def process_one(session: aiohttp.ClientSession,
                      anime_at: dict,
                      at_index: dict[tuple[str,str], dict],
                      media: dict,
                      manifest: dict) -> int:
    added = 0
    title = choose_title(media)
    ops = pick_op_audio_links(anime_at, at_index)
    if not ops:
        return 0

    for op in ops:
        if len(manifest) >= MAX_OPS:
            break
        url = op["url"]
        label = (op.get("label") or "OP").upper()
        name = unique_path(OUT_DIR / f"{slugify(title)}_{label}.mp3")

        ok = await download_file(session, url, name)
        if not ok:
            continue

        try:
            if name.stat().st_size <= 0:
                name.unlink(missing_ok=True); continue
        except Exception:
            continue

        manifest[name.name] = {
            "title": title,
            "label": label,
            "anilistId": media.get("id"),
            "year": media.get("seasonYear"),
            "source": "AnimeThemes(audio)",
        }
        save_manifest(manifest)
        added += 1
    return added

# ---------- Main ----------
ANILIST_QUERY_IDS = """
query($ids:[Int]) {
  Page(perPage: 50) {
    media(id_in: $ids, type: ANIME) { id title { romaji english native } averageScore format genres seasonYear }
  }
}
"""

async def main():
    print("→ Préparation des dossiers…")
    ensure_dirs()
    manifest = load_manifest()

    total_added = 0

    async with aiohttp.ClientSession() as session:
        print("→ Récupération AnimeThemes…")
        candidates: list[dict] = []
        ids: list[int] = []

        async for a, idx in iter_animethemes(session):
            # ne garde que ceux où on détecte au moins un OP (audio) sur l’anime
            if not pick_op_audio_links(a, idx):
                continue
            aid = extract_anilist_id(a, idx)
            if not aid:
                continue
            ids.append(aid)
            candidates.append({"at": a, "idx": idx, "aid": aid})

        if not candidates:
            print("Aucun anime exploitable (OP audio non détecté).")
            return

        print(f"→ Candidats: {len(candidates)} — lookup AniList…")
        mdict = await anilist_lookup(session, ids)

        print("→ Téléchargements…")
        sem = asyncio.Semaphore(CONCURRENCY)

        async def worker(item):
            nonlocal total_added
            m = mdict.get(item["aid"])
            if not m or not allow_media(m):
                return
            async with sem:
                if len(manifest) >= MAX_OPS:
                    return
                total_added += await process_one(session, item["at"], item["idx"], m, manifest)

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
