"""Racine du projet + variables d’environnement minimales pour les tests."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("DISCORD_BOT_TOKEN", "0" * 50)
os.environ.setdefault("OWNER_ID", "180389173985804288")
