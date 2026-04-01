"""
Une seule mini-jeu / interaction « en attente de réponse » par utilisateur à la fois.
Évite de lancer plusieurs /guessgenre (etc.) et de répondre une fois pour toutes.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from modules import user_reply

# user_id -> nom court du jeu (debug / messages)
_PENDING: Dict[int, str] = {}
_PENDING_LOCK = threading.Lock()

_BUSY_MSG = (
    "Tu as déjà une partie ou une question en attente — réponds-y (ou attends la fin) "
    "avant d’en lancer une autre."
)


def try_begin(user_id: int, game_key: str) -> bool:
    """True si la session est ouverte pour cet utilisateur."""
    with _PENDING_LOCK:
        if user_id in _PENDING:
            return False
        _PENDING[user_id] = game_key
        return True


def end(user_id: int) -> None:
    with _PENDING_LOCK:
        _PENDING.pop(user_id, None)


def active_game(user_id: int) -> Optional[str]:
    with _PENDING_LOCK:
        return _PENDING.get(user_id)


async def reply_busy(ctx: Any) -> None:
    """Réponse « partie déjà en cours » — éphémère / privée (pas de spam salon)."""
    await user_reply.send_ephemeral_or_private(ctx, _BUSY_MSG)


async def reply_guessgenre_cooldown(ctx: Any, user_id: int, remaining: int) -> None:
    """Cooldown guess genre : éphémère / privé (user_id conservé pour l’API)."""
    _ = user_id
    text = (
        f"⏳ Attends encore **{remaining}s** avant de relancer le **Guess genre** "
        f"(`/guessgenre` ou `/minijeux`)."
    )
    await user_reply.send_ephemeral_or_private(ctx, text)
