# tools/make_hybrid.py
import re
import sys
import pathlib

COGS_DIR = pathlib.Path(__file__).resolve().parents[1] / "cogs"

# regex robustes (gèrent espaces et paramètres)
REPLACEMENTS = [
    # commandes simples
    (re.compile(r"@commands\.command\s*\("), "@commands.hybrid_command("),
    # groupes
    (re.compile(r"@commands\.group\s*\("), "@commands.hybrid_group("),
    # sous-commandes de groupes (pattern le plus courant)
    (re.compile(r"@(\w+)\.command\s*\("), r"@\1.hybrid_command("),
]

def convert_file(path: pathlib.Path) -> bool:
    src = path.read_text(encoding="utf-8")
    original = src

    for pat, repl in REPLACEMENTS:
        src = pat.sub(repl, src)

    if src != original:
        path.write_text(src, encoding="utf-8")
        return True
    return False

def main():
    if not COGS_DIR.exists():
        print(f"[ERREUR] Dossier cogs introuvable: {COGS_DIR}")
        sys.exit(1)

    changed = 0
    for py in COGS_DIR.glob("*.py"):
        if py.name.startswith("_"):
            continue
        if convert_file(py):
            print(f"[OK] Converti: {py.name}")
            changed += 1

    if changed == 0:
        print("[INFO] Aucun fichier modifié (peut-être déjà hybride ?)")
    else:
        print(f"[DONE] {changed} fichier(s) mis à jour.")

if __name__ == "__main__":
    main()
