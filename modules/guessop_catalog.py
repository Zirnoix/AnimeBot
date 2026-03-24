"""
Catalogue persistant des openings pour Guess OP (SQLite).

- Stockage global (même base sur tout le monde, pas par serveur)
- Enrichissement : import JSON legacy, ajout à chaque partie réussie, tâche de récolte AnimeThemes
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from typing import Any, Optional, Tuple

LOG = logging.getLogger(__name__)

DB_PATH = os.path.join("data", "guessop_catalog.sqlite3")
# Ancien fichier animethemes (compat)
LEGACY_JSON = os.path.join("assets", "animethemes_cache.json")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _connect() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS openings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                theme_label TEXT,
                video_url TEXT NOT NULL UNIQUE,
                source TEXT,
                created_at INTEGER NOT NULL,
                last_used_at INTEGER,
                use_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_openings_used ON openings(use_count)")


def count() -> int:
    with _connect() as c:
        row = c.execute("SELECT COUNT(*) FROM openings").fetchone()
        return int(row[0]) if row else 0


def add_opening(
    title: str,
    theme_label: str,
    video_url: str,
    source: str,
) -> Optional[int]:
    """
    Enregistre une opening (URL unique). Retourne l'id (existant ou nouveau).
    """
    if not video_url or not title:
        return None
    now = int(time.time())
    try:
        with _connect() as c:
            c.execute(
                """
                INSERT OR IGNORE INTO openings (title, theme_label, video_url, source, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title.strip(), (theme_label or "").strip(), video_url.strip(), source, now),
            )
            row = c.execute(
                "SELECT id FROM openings WHERE video_url = ? LIMIT 1",
                (video_url.strip(),),
            ).fetchone()
            return int(row[0]) if row else None
    except Exception as e:
        LOG.warning("guessop_catalog add_opening: %s", e)
        return None


def pick_random() -> Optional[Tuple[int, str, str, str]]:
    """(id, title, theme_label, video_url) ou None."""
    with _connect() as c:
        row = c.execute(
            """
            SELECT id, title, theme_label, video_url
            FROM openings
            ORDER BY RANDOM()
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        return (
            int(row["id"]),
            str(row["title"]),
            str(row["theme_label"] or "OP"),
            str(row["video_url"]),
        )


def record_used(opening_id: int) -> None:
    if opening_id <= 0:
        return
    now = int(time.time())
    try:
        with _connect() as c:
            c.execute(
                """
                UPDATE openings
                SET use_count = use_count + 1, last_used_at = ?
                WHERE id = ?
                """,
                (now, opening_id),
            )
    except Exception as e:
        LOG.debug("record_used: %s", e)


def import_legacy_json() -> int:
    """Importe assets/animethemes_cache.json si présent. Retourne le nombre de lignes présentes après import."""
    if not os.path.exists(LEGACY_JSON):
        return 0
    before = count()
    try:
        with open(LEGACY_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return count()
        for item in data:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            title = item.get("title") or "?"
            theme = item.get("theme") or "OP"
            if url:
                add_opening(title, theme, url, "legacy_json")
    except Exception as e:
        LOG.warning("import_legacy_json: %s", e)
    return count() - before


def stats() -> dict[str, Any]:
    with _connect() as c:
        total = c.execute("SELECT COUNT(*) FROM openings").fetchone()[0]
        src = c.execute(
            "SELECT source, COUNT(*) FROM openings GROUP BY source ORDER BY COUNT(*) DESC"
        ).fetchall()
    return {"total": int(total), "by_source": [(r[0], int(r[1])) for r in src]}


def top_used(limit: int = 5) -> list[Tuple[str, int]]:
    with _connect() as c:
        rows = c.execute(
            """
            SELECT title, use_count FROM openings
            ORDER BY use_count DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [(str(r[0]), int(r[1])) for r in rows]
