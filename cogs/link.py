
"""
Module de commandes pour la liaison des comptes AniList et les comparaisons de statistiques.

Ce cog permet aux utilisateurs de :
- Lier leur compte AniList à leur ID Discord
- Délier leur compte à tout moment
- Comparer leurs statistiques avec d'autres utilisateurs

Les liens entre comptes sont persistés via le module core et les statistiques
sont récupérées en temps réel depuis l'API AniList.
"""

from __future__ import annotations

import secrets
import time
from typing import Any, Dict, List, Tuple

import discord
from discord.ext import commands
from discord import app_commands
from modules import core
from modules import i18n
from modules import user_reply
from modules.app_cmd_locale import ui_str


def _anime_status_count(statuses: List[Dict[str, Any]] | None, key: str) -> int:
    ku = key.upper()
    for s in statuses or []:
        st = str(s.get("status") or "").upper().replace(" ", "_")
        if st == ku:
            return int(s.get("count") or 0)
    return 0


def _fmt_stat(x: float) -> str:
    if abs(float(x) - round(float(x))) < 1e-6:
        return str(int(round(x)))
    return f"{float(x):.1f}"


def _duel_compact(
    label: str,
    a: float,
    b: float,
    name_a: str,
    name_b: str,
    *,
    higher_wins: bool = True,
) -> Tuple[str, int, int]:
    """Une ligne courte + points (1,0) / (0,1) / (0,0)."""
    fa, fb = _fmt_stat(a), _fmt_stat(b)
    if a == b:
        return f"▸ **{label}**  `{fa}` vs `{fb}`  🟰", 0, 0
    if higher_wins:
        if a > b:
            return f"▸ **{label}**  `{fa}` vs `{fb}`  🏆 {name_a}", 1, 0
        return f"▸ **{label}**  `{fa}` vs `{fb}`  🏆 {name_b}", 0, 1
    if a < b:
        return f"▸ **{label}**  `{fa}` vs `{fb}`  🏆 {name_a}", 1, 0
    return f"▸ **{label}**  `{fa}` vs `{fb}`  🏆 {name_b}", 0, 1


def _mean_bonus_ok(m1: float, m2: float) -> bool:
    """Manche « note » seulement si les deux ont une moyenne entre 0 et 100 (exclu)."""
    return 0 < float(m1) < 100 and 0 < float(m2) < 100


class Link(commands.Cog):
    """Cog gérant la liaison des comptes et les comparaisons de statistiques.

    Ce cog fournit trois commandes principales :
    - /linkanilist : lier un compte AniList
    - /unlink : supprimer la liaison
    - /duelstats : comparer ses stats avec un autre utilisateur

    Attributes:
        bot: L'instance du bot Discord
    """

    def __init__(self, bot: commands.Bot) -> None:
        """Initialise le cog Link.

        Args:
            bot: L'instance du bot Discord auquel attacher ce cog
        """
        self.bot = bot

    @commands.hybrid_command(name="linkanilist", description=ui_str("slash.link_linkanilist"))
    @app_commands.describe(pseudo=ui_str("slash.link_param_pseudo"))
    async def link_anilist(self, ctx: commands.Context, pseudo: str) -> None:
        # Anti-timeout côté slash
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        lg = i18n.ctx_lang(ctx)
        # 1) Vérifier que le compte existe sur AniList (et récupérer la casse exacte)
        user = core.query_anilist_user(pseudo.strip())
        if not user:
            # Réponse propre dans les deux modes
            msg = i18n.t("link.not_found", lg)
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        resolved = user["name"]
        existing = core.get_linked_username(ctx.author.id)
        if existing:
            if existing.lower() == resolved.lower():
                msg = i18n.t("link.already_same", lg, existing=existing)
                if ctx.interaction:
                    await ctx.interaction.followup.send(msg, ephemeral=True)
                else:
                    await ctx.reply(msg, mention_author=False)
                return
            msg = i18n.t("link.already_other", lg, existing=existing)
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        other = core.discord_id_for_linked_anilist_username(resolved)
        if other is not None and other != ctx.author.id:
            msg = i18n.t("link.taken_other_discord", lg)
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        token = f"ANBOT-{secrets.token_hex(4).upper()}"
        core.anilist_set_link_pending(ctx.author.id, resolved, token)

        msg = i18n.t("link.step1_body", lg, resolved=resolved, token=token)
        if ctx.interaction:
            await ctx.interaction.followup.send(msg, ephemeral=True)
        else:
            await ctx.reply(msg, mention_author=False)

    @commands.hybrid_command(
        name="verifyanilist",
        description=ui_str("slash.link_verifyanilist"),
    )
    async def verify_anilist(self, ctx: commands.Context) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        lg = i18n.ctx_lang(ctx)
        pending = core.anilist_get_link_pending(ctx.author.id)
        if not pending:
            msg = i18n.t("link.verify_none", lg)
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        username, token, created = pending

        if time.time() - created > 1800:
            core.anilist_clear_link_pending(ctx.author.id)
            msg = i18n.t("link.verify_expired", lg)
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        about = core.fetch_anilist_user_about(username) or ""
        if token not in about:
            msg = i18n.t("link.verify_not_in_bio", lg, token=token, username=username)
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        try:
            core.set_linked_username(ctx.author.id, username)
        except ValueError as e:
            code = str(e)
            if "anilist_username_taken" in code or "taken" in code.lower():
                msg = i18n.t("link.error_taken", lg)
            else:
                msg = i18n.t("link.error_save", lg)
            core.anilist_clear_link_pending(ctx.author.id)
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        core.anilist_clear_link_pending(ctx.author.id)
        ok = i18n.t("link.step2_ok", lg, username=username)
        if ctx.interaction:
            await ctx.interaction.followup.send(ok, ephemeral=True)
        else:
            await ctx.reply(ok, mention_author=False)

    @commands.hybrid_command(name="unlink", description=ui_str("slash.link_unlink"))
    async def unlink(self, ctx: commands.Context) -> None:
        """Supprime la liaison entre le compte Discord et AniList.

        Retire l'association entre l'ID Discord et le pseudo AniList
        précédemment enregistrée. L'utilisateur devra refaire la liaison
        pour utiliser les fonctionnalités nécessitant un compte AniList.

        Args:
            ctx: Le contexte de la commande
        """
        lg = i18n.ctx_lang(ctx)
        core.anilist_clear_link_pending(ctx.author.id)
        if core.unlink_linked_username(ctx.author.id):
            msg = i18n.t("link.unlink_ok", lg)
        else:
            msg = i18n.t("link.unlink_none", lg)
        await user_reply.send_ephemeral_or_private(ctx, msg)

    @commands.hybrid_command(
        name="duelstats",
        description=ui_str("slash.link_duelstats"),
    )
    @commands.cooldown(1, 15, commands.BucketType.user)
    @app_commands.describe(adversaire=ui_str("slash.link_param_adversaire"))
    async def duelstats(self, ctx: commands.Context, adversaire: discord.Member | None = None) -> None:
        """Compare l’engagement AniList (complétés, en cours, temps, épisodes) — pas le genre ni un score vide."""
        lg = i18n.ctx_lang(ctx)
        opponent = adversaire
        if opponent is None:
            await ctx.send(i18n.t("link.duel_usage", lg))
            return
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

        user1 = core.get_linked_username(ctx.author.id)
        user2 = core.get_linked_username(opponent.id)
        if not user1 or not user2:
            await ctx.send(i18n.t("link.duel_both_link", lg))
            return

        query = """
        query ($name: String) {
          User(name: $name) {
            statistics {
              anime {
                count
                episodesWatched
                minutesWatched
                meanScore
                statuses { status count }
              }
            }
          }
        }
        """
        stats: dict[str, dict] = {}
        for u in [user1, user2]:
            res = await core.query_anilist_async(query, {"name": u}, queue_ctx=ctx)
            try:
                a = res["data"]["User"]["statistics"]["anime"]
                st = a.get("statuses") or []
                stats[u] = {
                    "completed": _anime_status_count(st, "COMPLETED"),
                    "watching": _anime_status_count(st, "CURRENT"),
                    "episodes": int(a.get("episodesWatched") or 0),
                    "days": round((a.get("minutesWatched") or 0) / 1440, 1),
                    "mean": round(float(a.get("meanScore") or 0), 1),
                }
            except Exception:
                await ctx.send(i18n.t("link.duel_fetch_error", lg))
                return

        s1, s2 = stats[user1], stats[user2]
        n_a = ctx.author.display_name[:32]
        n_b = opponent.display_name[:32]

        lines: List[str] = []
        pts_a = pts_b = 0

        for label, key in (
            (i18n.t("link.duel_l_completed", lg), "completed"),
            (i18n.t("link.duel_l_watching", lg), "watching"),
            (i18n.t("link.duel_l_episodes", lg), "episodes"),
            (i18n.t("link.duel_l_days", lg), "days"),
        ):
            va, vb = s1[key], s2[key]
            text, pa, pb = _duel_compact(label, float(va), float(vb), n_a, n_b, higher_wins=True)
            lines.append(text)
            pts_a += pa
            pts_b += pb

        if _mean_bonus_ok(s1["mean"], s2["mean"]):
            text, pa, pb = _duel_compact(
                i18n.t("link.duel_l_mean_bonus", lg),
                float(s1["mean"]),
                float(s2["mean"]),
                n_a,
                n_b,
                higher_wins=True,
            )
            lines.append(text)
            pts_a += pa
            pts_b += pb

        if pts_a > pts_b:
            verdict = i18n.t("link.duel_win", lg, winner=n_a, hi=pts_a, lo=pts_b)
            color = discord.Color.from_rgb(220, 90, 90)
        elif pts_b > pts_a:
            verdict = i18n.t("link.duel_win", lg, winner=n_b, hi=pts_b, lo=pts_a)
            color = discord.Color.from_rgb(90, 130, 220)
        else:
            verdict = i18n.t("link.duel_draw", lg, p=pts_a, p2=pts_b)
            color = discord.Color.from_rgb(180, 140, 60)

        board = "\n".join(lines)
        if len(board) > 1000:
            board = board[:997] + "…"

        embed = discord.Embed(
            title=i18n.t("link.duel_title", lg),
            description=i18n.t("link.duel_desc", lg, n_a=n_a, user1=user1, n_b=n_b, user2=user2),
            color=color,
        )
        embed.add_field(name=i18n.t("link.duel_field_board", lg), value=board, inline=False)
        embed.add_field(name=i18n.t("link.duel_field_verdict", lg), value=verdict, inline=False)
        embed.set_footer(text=i18n.t("link.duel_footer", lg))
        embed.set_author(name=i18n.t("link.duel_author", lg), icon_url=ctx.author.display_avatar.url)
        embed.set_thumbnail(url=opponent.display_avatar.url)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Configure le cog Link pour le bot.

    Args:
        bot: L'instance du bot Discord auquel ajouter le cog
    """
    await bot.add_cog(Link(bot))
