"""
Vérifications locales sans Discord : imports + fonctions critiques.
Usage : python scripts/verify_local.py
"""
from __future__ import annotations

import os
import sys

# Permet d'importer bot.py sans quitter (token factice)
os.environ.setdefault("DISCORD_BOT_TOKEN", "0" * 50)


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    errors: list[str] = []

    # 1) modules.core
    try:
        from modules import core

        core.get_linked_anilist_usernames_bulk()
        core.normalize("Test Title")
        assert callable(core.generate_next_image)
        assert callable(core.generate_profile_card)
    except Exception as e:
        errors.append(f"modules.core: {e!r}")

    # 2) image
    try:
        from modules.image import generate_next_card

        generate_next_card({"title_romaji": "X", "episode": 1, "when": "?", "genres": []})
    except Exception as e:
        errors.append(f"modules.image: {e!r}")

    # 3) quiz helper
    try:
        from cogs import quiz as quiz_cog

        assert quiz_cog._is_jsp("jsp") is True
        assert quiz_cog._is_jsp("réponse") is False
    except Exception as e:
        errors.append(f"cogs.quiz _is_jsp: {e!r}")

    if errors:
        print("ÉCHECS :")
        for x in errors:
            print(" -", x)
        return 1

    print("OK — imports et smoke tests locaux passés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
