"""
Une seule mini-jeu / interaction « en attente de réponse » par utilisateur à la fois.
Évite de lancer plusieurs /guessgenre (etc.) et de répondre une fois pour toutes.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from modules import i18n
from modules import user_reply

# user_id -> nom court du jeu (debug / messages)
_PENDING: Dict[int, str] = {}
_PENDING_LOCK = threading.Lock()


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
    lg = i18n.ctx_lang(ctx)
    await user_reply.send_ephemeral_or_private(ctx, i18n.t("common.minigame_busy", lg))


async def reply_guessgenre_cooldown(ctx: Any, user_id: int, remaining: int) -> None:
    """Cooldown guess genre : éphémère / privé (user_id conservé pour l’API)."""
    _ = user_id
    lg = i18n.ctx_lang(ctx)
    text = i18n.t("common.guessgenre_cooldown", lg, remaining=remaining)
    await user_reply.send_ephemeral_or_private(ctx, text)
