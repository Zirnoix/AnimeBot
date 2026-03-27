#!/usr/bin/env python3
"""Charge les cogs sans connexion Discord et inventorie les commandes.

Vérifie la cohérence entre l’arbre slash (`bot.tree`) et l’index utilisé par `/help`
(`cogs.help._all_slash_commands`).

Usage (depuis la racine du dépôt)::

    python scripts/verify_bot_commands.py

Limites : aucune exécution réelle des handlers (pas de salon, pas d’API Discord).
Pour tester chaque commande en conditions réelles, il faut un serveur de dev et un token.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import TYPE_CHECKING

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("DISCORD_BOT_TOKEN", "0" * 50)
os.environ.setdefault("OWNER_ID", "180389173985804288")
os.environ.setdefault("LOG_LEVEL", "ERROR")
os.environ.pop("DEV_GUILD_IDS", None)

if TYPE_CHECKING:
    from discord import app_commands


def _iter_slash_lineages(c: "app_commands.Command | app_commands.Group", parents: list[str]) -> list[str]:
    from discord import app_commands

    if isinstance(c, app_commands.Group):
        out: list[str] = []
        for child in c.commands:
            out.extend(_iter_slash_lineages(child, parents + [c.name]))
        return out
    return [" ".join(parents + [c.name]).lower()]


def _parent_slash_group_names(bot) -> set[str]:
    from discord import app_commands

    out: set[str] = set()
    for c in bot.tree.get_commands():
        if isinstance(c, app_commands.Group):
            out.add(c.name.lower())
    return out


async def _async_main() -> int:
    # Les cogs démarrent des @tasks.loop qui appellent wait_until_ready : sans login, bruit asyncio.
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    from discord import app_commands

    import bot as bot_module
    from cogs.help import _all_slash_commands

    b = bot_module.bot
    b.AUTO_GLOBAL_SYNC = False
    await b._load_extensions()

    slash_lineages: list[str] = []
    for c in b.tree.get_commands():
        slash_lineages.extend(_iter_slash_lineages(c, []))

    slash_set = set(slash_lineages)
    slash_sorted = sorted(slash_set)

    help_map = _all_slash_commands(b)
    help_keys = set(help_map.keys())
    parents = _parent_slash_group_names(b)

    missing_in_help = sorted(s for s in slash_set if s not in help_keys)
    # Clés d’aide « parent de groupe » (/airings, /raid) : pas de slash feuille seul
    stale_in_help = sorted(
        k
        for k in help_keys
        if k not in slash_set and k not in parents and not k.startswith("owner ")
    )

    prefix_qnames = sorted({x.qualified_name for x in b.walk_commands()})

    print("=== AnimeBot — inventaire commandes (sans Discord) ===\n")
    print(f"Cogs chargés: {len(b._loaded_cogs)}")
    for ext in sorted(b._loaded_cogs):
        print(f"  - {ext}")
    print()
    print(f"Slash feuilles / lineages (tree): {len(slash_sorted)}")
    for name in slash_sorted:
        print(f"  /{name}")
    print()
    print(f"Commandes (walk_commands, qualifiées): {len(prefix_qnames)}")
    for qn in prefix_qnames:
        print(f"  {qn}")
    print()

    if missing_in_help:
        print("⚠️  Slash présent dans le tree mais absent de l’index /help :")
        for m in missing_in_help:
            print(f"    - /{m}")
        print()
    else:
        print("OK — tout slash du tree est référencé par _all_slash_commands.\n")

    if stale_in_help:
        print("⚠️  Clés /help sans slash correspondant (ni groupe parent) :")
        for m in stale_in_help:
            print(f"    - {m!r}")
        print()
    else:
        print("OK — pas de clé d’aide orpheline (hors groupes parents et sous-owner).\n")

    if missing_in_help or stale_in_help:
        return 1
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
