"""
Limitation d’abus (spam) : compteurs en mémoire, thread-safe (callbacks asyncio + lock partagé).

Redémarrage du bot : les compteurs repartent à zéro (acceptable pour anti-spam « soft »).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

LOG = logging.getLogger(__name__)

_LOCK = threading.Lock()
# (user_id, guild_id) -> timestamps monotonic dans la fenêtre
_SLASH_BUCKETS: Dict[Tuple[int, int], Deque[float]] = {}

# Fenêtre glissante : suffisamment large pour un usage normal, serrée pour le spam massif.
SLASH_BURST_LIMIT = 14
SLASH_BURST_WINDOW_SEC = 10.0


def allow_slash_burst(user_id: int, guild_id: int) -> Tuple[bool, float]:
    """
    Retourne (autorisé, secondes à attendre avant un nouvel essai si refusé).
    guild_id=0 pour les interactions hors serveur (DM).
    """
    key = (user_id, int(guild_id))
    now = time.monotonic()
    with _LOCK:
        dq = _SLASH_BUCKETS.setdefault(key, deque())
        while dq and dq[0] < now - SLASH_BURST_WINDOW_SEC:
            dq.popleft()
        if len(dq) >= SLASH_BURST_LIMIT:
            oldest = dq[0]
            retry_after = SLASH_BURST_WINDOW_SEC - (now - oldest)
            LOG.debug("slash burst limit user=%s guild=%s", user_id, guild_id)
            return False, max(0.0, retry_after)
        dq.append(now)
        return True, 0.0
