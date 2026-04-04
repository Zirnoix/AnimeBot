#!/usr/bin/env python3
"""
Compare les clés des fichiers locales (ex. fr.json vs en.json).
Utile pour garder les langues alignées avant une release.

Usage : python scripts/check_locale_keys.py
        python scripts/check_locale_keys.py --lang de   # compare fr.json avec de.json si présent
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "modules" / "locales"


def _flatten(d: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            keys |= _flatten(v, full)
        else:
            keys.add(full)
    return keys


def main() -> int:
    ap = argparse.ArgumentParser(description="Vérifie l’alignement des clés entre fichiers locales.")
    ap.add_argument(
        "--base",
        default="fr",
        help="Fichier de référence (défaut: fr)",
    )
    ap.add_argument(
        "--lang",
        default="en",
        help="Langue à comparer (défaut: en)",
    )
    args = ap.parse_args()

    base_path = LOCALES / f"{args.base}.json"
    other_path = LOCALES / f"{args.lang}.json"
    if not base_path.is_file():
        print(f"Fichier manquant : {base_path}", file=sys.stderr)
        return 2
    if not other_path.is_file():
        print(f"Fichier manquant : {other_path}", file=sys.stderr)
        return 2

    base = json.loads(base_path.read_text(encoding="utf-8"))
    other = json.loads(other_path.read_text(encoding="utf-8"))
    if not isinstance(base, dict) or not isinstance(other, dict):
        print("Les fichiers locales doivent être des objets JSON à la racine.", file=sys.stderr)
        return 2

    kb = _flatten(base)
    ko = _flatten(other)
    only_base = sorted(kb - ko)
    only_other = sorted(ko - kb)

    if only_base:
        print(f"Clés dans {args.base}.json mais pas {args.lang}.json ({len(only_base)}):")
        for x in only_base:
            print(" ", x)
    if only_other:
        print(f"Clés dans {args.lang}.json mais pas {args.base}.json ({len(only_other)}):")
        for x in only_other:
            print(" ", x)
    if only_base or only_other:
        return 1
    print(f"OK — {args.base}.json et {args.lang}.json ont les mêmes clés ({len(kb)} feuilles).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
