import re
import sys
import pathlib

COGS_DIR = pathlib.Path(__file__).resolve().parents[1] / "cogs"

# couvre : commands.command, command, alias style dcmd.command, bot.command (rare en cog)
PATTERNS = [
    # groupes -> hybrid_group
    (re.compile(r"@commands\.group\s*\("), "@commands.hybrid_group("),
    (re.compile(r"@group\s*\("), "@hybrid_group("),
    (re.compile(r"@(\w+)\.group\s*\("), r"@\1.hybrid_group("),  # alias.group -> alias.hybrid_group

    # commandes -> hybrid_command
    (re.compile(r"@commands\.command\s*\("), "@commands.hybrid_command("),
    (re.compile(r"@command\s*\("), "@hybrid_command("),
    (re.compile(r"@(\w+)\.command\s*\("), r"@\1.hybrid_command("),  # alias.command -> alias.hybrid_command
]

def convert_text(src: str) -> str:
    out = src
    for pat, repl in PATTERNS:
        out = pat.sub(repl, out)
    return out

def convert_file(path: pathlib.Path) -> bool:
    src = path.read_text(encoding="utf-8")
    new = convert_text(src)
    if new != src:
        path.write_text(new, encoding="utf-8")
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
    print(f"[DONE] {changed} fichier(s) mis à jour.")

if __name__ == "__main__":
    main()
