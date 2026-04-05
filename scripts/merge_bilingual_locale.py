#!/usr/bin/env python3
"""Fusionne scripts/patch_{fr,en}/*.json dans modules/locales/fr.json et en.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "modules" / "locales"
SCRIPT_DIR = Path(__file__).resolve().parent


def deep_merge(base: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _apply_fragments(lang: str) -> None:
    frag_dir = SCRIPT_DIR / f"patch_{lang}"
    if not frag_dir.is_dir():
        print(f"Manquant: {frag_dir}", file=sys.stderr)
        sys.exit(2)
    paths = sorted(frag_dir.glob("*.json"))
    if not paths:
        print(f"Aucun fragment dans {frag_dir}", file=sys.stderr)
        sys.exit(2)
    path = LOCALES / f"{lang}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for p in paths:
        frag = json.loads(p.read_text(encoding="utf-8"))
        deep_merge(data, frag)
        print(f"  + {lang}: {p.name}")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    for lang in ("fr", "en"):
        _apply_fragments(lang)
        print(f"OK -> {lang}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
