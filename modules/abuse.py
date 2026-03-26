"""
Limitation d’abus (spam) : compteurs en mémoire, thread-safe (callbacks asyncio + lock partagé).

Redémarrage du bot : les compteurs repartent à zéro (acceptable pour anti-spam « soft »).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Tuple

LOG = logging.getLogger(__name__)

_LOCK = threading.Lock()
# (user_id, guild_id) -> timestamps monotonic dans la fenêtre
_SLASH_BUCKETS: Dict[Tuple[int, int], Deque[float]] = {}
# (user_id, clé composant) -> timestamps (boutons raid, etc.)
_COMPONENT_BUCKETS: Dict[Tuple[int, str], Deque[float]] = {}

# Fenêtre glissante : suffisamment large pour un usage normal, serrée pour le spam massif.
SLASH_BURST_LIMIT = 14
SLASH_BURST_WINDOW_SEC = 10.0

# Boutons / menus (plus permissif que les slash car moins coûteux côté API commandes)
COMPONENT_BURST_LIMIT = 18
COMPONENT_BURST_WINDOW_SEC = 8.0


def _sliding_window_allow(
    key: Tuple[Any, ...],
    *,
    limit: int,
    window_sec: float,
    buckets: Dict[Tuple[Any, ...], Deque[float]],
) -> Tuple[bool, float]:
    now = time.monotonic()
    with _LOCK:
        dq = buckets.setdefault(key, deque())
        while dq and dq[0] < now - window_sec:
            dq.popleft()
        if len(dq) >= limit:
            oldest = dq[0]
            retry_after = window_sec - (now - oldest)
            return False, max(0.0, retry_after)
        dq.append(now)
        return True, 0.0


def allow_slash_burst(user_id: int, guild_id: int) -> Tuple[bool, float]:
    """
    Retourne (autorisé, secondes à attendre avant un nouvel essai si refusé).
    guild_id=0 pour les interactions hors serveur (DM).
    """
    key = (user_id, int(guild_id))
    ok, retry = _sliding_window_allow(
        key,
        limit=SLASH_BURST_LIMIT,
        window_sec=SLASH_BURST_WINDOW_SEC,
        buckets=_SLASH_BUCKETS,
    )
    if not ok:
        LOG.debug("slash burst limit user=%s guild=%s", user_id, guild_id)
    return ok, retry


def allow_component_burst(user_id: int, component_key: str) -> Tuple[bool, float]:
    """
    Anti-spam pour boutons / sélecteurs (ex. hub raid « recevoir ma manche »).
    `component_key` doit être stable par contexte (ex. ``raid_hub:{guild_id}``).
    """
    key = (user_id, component_key[:160])
    ok, retry = _sliding_window_allow(
        key,
        limit=COMPONENT_BURST_LIMIT,
        window_sec=COMPONENT_BURST_WINDOW_SEC,
        buckets=_COMPONENT_BUCKETS,
    )
    if not ok:
        LOG.debug("component burst limit user=%s key=%s", user_id, component_key[:40])
    return ok, retry
