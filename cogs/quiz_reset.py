# cogs/quiz_reset.py
from __future__ import annotations
from datetime import datetime, timezone
import asyncio
import logging

import discord
from discord.ext import commands, tasks

from modules import core

LOG = logging.getLogger(__name__)

STATE_PATH = core.os.path.join(core.DATA_DIR, "quiz_last_reset.json")

def _load_state() -> dict:
    return core.load_json(STATE_PATH, {})

def _save_state(data: dict) -> None:
    core.save_json(STATE_PATH, data or {})

class QuizMonthlyReset(commands.Cog):
    """
    Surveille le changement de mois (timezone bot) et :
      - écrit le vainqueur du MOIS PRÉCÉDENT dans FileConfig.WINNER
      - remet à zéro quiz_scores.json
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._lock = asyncio.Lock()
        self.loop_check.start()

    def cog_unload(self):
        try:
            self.loop_check.cancel()
        except Exception:
            pass

    @tasks.loop(minutes=10)
    async def loop_check(self):
        if self._lock.locked():
            return
        async with self._lock:
            try:
                tz = getattr(core, "TIMEZONE", timezone.utc)
                now = datetime.now(tz)
                state = _load_state()
                last_done_for = state.get("last_done_for")  # ex: "2025-09" (mois courant déjà reseté ?)

                # On veut faire le reset au tout début d'un mois, et une seule fois :
                # - dès qu'on est le 1er du mois, on vérifie si last_done_for != current month.
                #   Si différent => on fige le vainqueur du mois PRÉCÉDENT et on reset.
                current_month = core._month_key(now)

                if now.day == 1 and last_done_for != current_month:
                    data = core.record_month_winner_and_reset(now=now)
                    LOG.info("[quiz_reset] Reset mensuel effectué — winner: %s", data)
                    mini_data = core.record_mini_month_winners_and_reset(now=now)
                    try:
                        await core.grant_monthly_podium_rewards(self.bot, data, mini_data)
                    except Exception as e:
                        LOG.exception("[quiz_reset] grant podium: %s", e)
                    _save_state({"last_done_for": current_month})
            except Exception as e:
                LOG.exception("[quiz_reset] Erreur: %s", e)

    @loop_check.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(QuizMonthlyReset(bot))
