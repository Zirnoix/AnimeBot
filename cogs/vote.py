# cogs/vote.py — Top.gg : /vote, rappels MP (webhook géré dans bot.py)
from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks
from discord.ui import Button, View

from modules import topgg_vote

LOG = logging.getLogger(__name__)


def _fmt_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "maintenant"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}min")
    if not parts and s:
        parts.append(f"{s}s")
    return " ".join(parts) if parts else "bientôt"


class VoteReminderView(View):
    """Active / désactive le MP « tu peux revoter »."""

    def __init__(self, user_id: int) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Ce panneau n’est pas pour toi.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔔 Activer rappel MP", style=discord.ButtonStyle.success, row=0)
    async def enable_reminder(self, interaction: discord.Interaction, button: Button) -> None:
        topgg_vote.set_reminder(interaction.user.id, True)
        await interaction.response.edit_message(
            content="✅ Rappel MP **activé** — tu recevras un message quand le cooldown Top.gg sera passé.",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="🔕 Désactiver le rappel", style=discord.ButtonStyle.secondary, row=0)
    async def disable_reminder(self, interaction: discord.Interaction, button: Button) -> None:
        topgg_vote.set_reminder(interaction.user.id, False)
        await interaction.response.edit_message(
            content="✅ Rappel MP **désactivé**.",
            embed=None,
            view=None,
        )


class Vote(commands.Cog):
    """Commande /vote + rappels MP quand le cooldown Top.gg est écoulé."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        if not self._vote_reminder_loop.is_running():
            self._vote_reminder_loop.start()

    async def cog_unload(self) -> None:
        self._vote_reminder_loop.cancel()

    @tasks.loop(minutes=2)
    async def _vote_reminder_loop(self) -> None:
        if not topgg_vote.webhook_secret():
            return
        if not self.bot.is_ready():
            return
        now = int(datetime.now(timezone.utc).timestamp())
        for uid, eligible_ts in topgg_vote.iter_reminder_candidates(now):
            url = topgg_vote.vote_page_url(self.bot.user.id)
            try:
                u = await self.bot.fetch_user(uid)
                await u.send(
                    "🗳️ Tu peux **revoter** pour **AnimeBot** sur Top.gg — "
                    f"ça aide le bot à être visible !\n{url}\n\n"
                    "_(Rappel désactivable avec `/vote` → bouton.)_"
                )
                topgg_vote.mark_reminder_sent(uid, eligible_ts)
            except discord.Forbidden:
                topgg_vote.set_reminder(uid, False)
                LOG.debug("vote reminder: MP fermés uid=%s, rappel désactivé", uid)
            except Exception as e:
                LOG.warning("vote reminder uid=%s: %s", uid, e)

    @_vote_reminder_loop.before_loop
    async def _vote_reminder_before(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="vote", description="Voter sur Top.gg, voir le cooldown et gérer le rappel MP.")
    async def vote_cmd(self, interaction: discord.Interaction) -> None:
        # Éphémère = pertinent en serveur uniquement ; en MP le salon est déjà privé.
        # 10062 = interaction expirée si > ~3s avant defer (latence hébergeur, etc.).
        ephemeral = interaction.guild is not None
        try:
            await interaction.response.defer(ephemeral=ephemeral)
        except discord.NotFound:
            LOG.info("/vote: interaction expirée ou invalide (10062) — réessaie.")
            return
        except discord.HTTPException as e:
            if getattr(e, "code", None) == 10062:
                LOG.info("/vote: interaction inconnue (10062) — réessaie.")
                return
            raise

        uid = interaction.user.id
        url = topgg_vote.vote_page_url(self.bot.user.id)
        cd = topgg_vote.cooldown_seconds()
        xp_amt = topgg_vote.vote_xp_amount()

        lv = topgg_vote.last_vote_ts(uid)
        now = int(datetime.now(timezone.utc).timestamp())
        next_ts = topgg_vote.next_vote_ts(uid)
        rem = topgg_vote.get_reminder(uid)
        stats = topgg_vote.get_vote_stats(uid)
        streak = stats["streak"]
        best = stats["best_streak"]
        total_v = stats["vote_count"]

        if lv <= 0:
            status = "Tu n’as pas encore de vote enregistré par le bot (après ton **premier** vote sur Top.gg, le cooldown s’affichera ici)."
            eta_txt = f"Cooldown Top.gg : **{_fmt_remaining(cd)}** après chaque vote."
        else:
            if now >= next_ts:
                status = "✅ Tu **peux voter** (cooldown écoulé)."
            else:
                wait = next_ts - now
                status = f"⏳ Prochain vote possible dans **{_fmt_remaining(wait)}**."
            eta_txt = f"Dernier vote enregistré : <t:{lv}:R>."

        secret_ok = bool(topgg_vote.webhook_secret())
        hook_hint = ""
        if not secret_ok:
            hook_hint = (
                "\n\n⚠️ Les récompenses automatiques nécessitent `TOPGG_WEBHOOK_SECRET` + URL webhook sur Top.gg "
                "(voir doc projet / `.env.example`)."
            )

        reward_hint = (
            f"🎁 **XP :** base **{xp_amt}** + bonus **série** (jours consécutifs) + **fidélité** (votes totaux) "
            f"· week-end possible selon Top.gg."
        )
        stats_line = (
            f"📊 **Tes stats :** {total_v} vote(s) enregistré(s) · série **{streak}** jour(s) · "
            f"record **{best}** · (mis à jour après chaque vote reçu par le bot)."
        )

        lines = [
            f"**[Voter sur Top.gg]({url})**",
            "",
            reward_hint,
            stats_line,
            "",
            status,
            eta_txt,
            "",
            f"🔔 Rappel MP : **{'activé' if rem else 'désactivé'}** — boutons ci-dessous.",
            hook_hint,
        ]
        em = discord.Embed(
            title="🗳️ Soutenir AnimeBot",
            description="\n".join(lines).strip(),
            color=discord.Color.blurple(),
        )
        em.set_footer(text="Bonus série + fidélité · Fuseau BOT_TIMEZONE · Cooldown configurable")

        recap = topgg_vote.pop_pending_vote_recap(uid)
        if recap:
            try:
                xp_r = int(recap.get("xp", 0))
                sub_r = int(recap.get("subtotal", 0))
                base_r = int(recap.get("base_xp", 0))
                sb_r = int(recap.get("streak_bonus", 0))
                lb_r = int(recap.get("loyalty_bonus", 0))
                st_r = int(recap.get("streak", 0))
                bst_r = int(recap.get("best_streak", 0))
                tv_r = int(recap.get("total_votes", 0))
                wk_txt = ""
                if recap.get("weekend"):
                    wk_txt = "\n_Bonus week-end appliqué sur le total._"
                recap_val = (
                    f"**+{xp_r} XP** ajoutés sur ta carte.\n"
                    f"{base_r} base + {sb_r} série + {lb_r} fidélité = **{sub_r}** XP avant multi.{wk_txt}\n"
                    f"Série **{st_r}** j · record **{bst_r}** · **{tv_r}** votes au total."
                )
                em.add_field(
                    name="🎉 Récap de ton dernier vote (toi seul·e le vois ici)",
                    value=recap_val,
                    inline=False,
                )
            except Exception as e:
                LOG.warning("vote recap embed: %s", e)

        await interaction.followup.send(embed=em, view=VoteReminderView(uid), ephemeral=ephemeral)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Vote(bot))
