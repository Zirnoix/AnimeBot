"""
Une seule mini-jeu / interaction « en attente de réponse » par utilisateur à la fois.
Évite de lancer plusieurs /guessgenre (etc.) et de répondre une fois pour toutes.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

# user_id -> nom court du jeu (debug / messages)
_PENDING: Dict[int, str] = {}
_PENDING_LOCK = threading.Lock()

# Dernier message public « cooldown » (préfixe) pour ne pas spammer le salon
_LAST_COOLDOWN_PUBLIC: Dict[int, float] = {}

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
    """Réponse « partie déjà en cours » (ephemeral si slash)."""
    if getattr(ctx, "interaction", None):
        if not ctx.interaction.response.is_done():
            await ctx.interaction.response.send_message(_BUSY_MSG, ephemeral=True)
        else:
            await ctx.interaction.followup.send(_BUSY_MSG, ephemeral=True)
    else:
        await ctx.send(_BUSY_MSG)


async def reply_guessgenre_cooldown(ctx: Any, user_id: int, remaining: int) -> None:
    """
    Cooldown guess genre : slash = toujours ephemeral ; préfixe = 1 message / 12 s max.
    """
    text = (
        f"⏳ Attends encore **{remaining}s** avant de relancer le **Guess genre** "
        f"(`/guessgenre` ou `/minijeux`)."
    )
    if getattr(ctx, "interaction", None):
        if not ctx.interaction.response.is_done():
            await ctx.interaction.response.send_message(text, ephemeral=True)
        else:
            await ctx.interaction.followup.send(text, ephemeral=True)
        return
    now = time.monotonic()
    last = _LAST_COOLDOWN_PUBLIC.get(user_id, 0.0)
    if now - last >= 12.0:
        _LAST_COOLDOWN_PUBLIC[user_id] = now
        await ctx.send(text)
