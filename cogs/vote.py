# cogs/vote.py — Top.gg : /vote, rappels MP (webhook géré dans bot.py)
from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks
from discord.ui import Button, View

from modules import i18n, topgg_vote

LOG = logging.getLogger(__name__)
_VOTE_CMD_DESC = i18n.t("vote.cmd_desc", "fr")


def _fmt_remaining(seconds: int, lg: str) -> str:
    if seconds <= 0:
        return i18n.t("vote.fmt_now", lg)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}min")
    if not parts and s:
        parts.append(f"{s}s")
    return " ".join(parts) if parts else i18n.t("vote.fmt_soon", lg)


VOTE_EMBED_COLOR = 0xFEE75C


class VoteReminderView(View):
    """Bouton lien Top.gg + rappels MP."""

    def __init__(self, user_id: int, vote_url: str, lang: str) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.lang = lang
        self.add_item(
            discord.ui.Button(
                label=i18n.t("vote.btn_vote", lang)[:80],
                style=discord.ButtonStyle.link,
                url=vote_url,
                row=0,
            )
        )
        b_on = Button(
            label=i18n.t("vote.btn_rem_on", lang)[:80],
            style=discord.ButtonStyle.success,
            row=1,
        )
        b_on.callback = self._enable_reminder  # type: ignore[method-assign]
        self.add_item(b_on)
        b_off = Button(
            label=i18n.t("vote.btn_rem_off", lang)[:80],
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        b_off.callback = self._disable_reminder  # type: ignore[method-assign]
        self.add_item(b_off)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                i18n.t("vote.not_for_you", self.lang),
                ephemeral=True,
            )
            return False
        return True

    async def _enable_reminder(self, interaction: discord.Interaction) -> None:
        topgg_vote.set_reminder(interaction.user.id, True)
        await interaction.response.edit_message(
            content=i18n.t("vote.rem_on", self.lang),
            embed=None,
            view=None,
        )

    async def _disable_reminder(self, interaction: discord.Interaction) -> None:
        topgg_vote.set_reminder(interaction.user.id, False)
        await interaction.response.edit_message(
            content=i18n.t("vote.rem_off", self.lang),
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
                    i18n.t("vote.dm_reminder", "fr", url=url),
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

    @app_commands.command(
        name="vote",
        description=_VOTE_CMD_DESC,
    )
    async def vote_cmd(self, interaction: discord.Interaction) -> None:
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

        lg = i18n.guild_lang(interaction.guild)
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
            status = i18n.t("vote.status_none", lg)
            eta_txt = i18n.t("vote.eta_cooldown", lg, remaining=_fmt_remaining(cd, lg))
        else:
            if now >= next_ts:
                status = i18n.t("vote.status_ready", lg)
            else:
                wait = next_ts - now
                status = i18n.t(
                    "vote.status_wait",
                    lg,
                    remaining=_fmt_remaining(wait, lg),
                )
            eta_txt = i18n.t("vote.last_vote", lg, ts=lv)

        secret_ok = bool(topgg_vote.webhook_secret())
        hook_hint = ""
        if not secret_ok:
            hook_hint = i18n.t("vote.hook_warn", lg)

        reward_hint = i18n.t("vote.reward_line", lg, xp=xp_amt)
        stats_line = i18n.t(
            "vote.stats_line",
            lg,
            total=total_v,
            streak=streak,
            best=best,
        )

        intro = i18n.t("vote.intro", lg)
        rem_state = i18n.t(
            "vote.rem_state",
            lg,
            state=i18n.t("vote.rem_on_state", lg)
            if rem
            else i18n.t("vote.rem_off_state", lg),
        )
        desc_parts = [intro, "", reward_hint, "", stats_line, "", f"**Statut**\n{status}\n{eta_txt}", "", rem_state]
        if hook_hint:
            desc_parts.extend(["", hook_hint.strip()])
        em = discord.Embed(
            title=i18n.t("vote.embed_title", lg),
            description="\n".join(desc_parts).strip(),
            color=discord.Color(VOTE_EMBED_COLOR),
            url=url,
        )
        try:
            u = interaction.client.user
            if u and u.display_avatar:
                em.set_thumbnail(url=u.display_avatar.url)
        except Exception:
            pass
        em.set_footer(text=i18n.t("vote.embed_footer", lg))

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
                    wk_txt = i18n.t("vote.recap_weekend", lg)
                recap_val = i18n.t(
                    "vote.recap_body",
                    lg,
                    xp=xp_r,
                    base=base_r,
                    sb=sb_r,
                    lb=lb_r,
                    sub=sub_r,
                    wk=wk_txt,
                    st=st_r,
                    bst=bst_r,
                    tv=tv_r,
                )
                em.add_field(
                    name=i18n.t("vote.recap_title", lg),
                    value=recap_val,
                    inline=False,
                )
            except Exception as e:
                LOG.warning("vote recap embed: %s", e)

        await interaction.followup.send(
            embed=em,
            view=VoteReminderView(uid, url, lg),
            ephemeral=ephemeral,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Vote(bot))
