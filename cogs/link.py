
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
from modules import user_reply


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

    @commands.hybrid_command(name="linkanilist", description="Lie ton compte AniList à ton compte Discord.")
    @app_commands.describe(pseudo="Ton pseudo AniList (respecte la casse si possible)")
    async def link_anilist(self, ctx: commands.Context, pseudo: str) -> None:
        # Anti-timeout côté slash
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        # 1) Vérifier que le compte existe sur AniList (et récupérer la casse exacte)
        user = core.query_anilist_user(pseudo.strip())
        if not user:
            # Réponse propre dans les deux modes
            msg = "❌ Aucun compte AniList trouvé avec ce pseudo."
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        resolved = user["name"]
        existing = core.get_linked_username(ctx.author.id)
        if existing:
            if existing.lower() == resolved.lower():
                msg = f"ℹ️ Ton compte est déjà lié à **{existing}**."
                if ctx.interaction:
                    await ctx.interaction.followup.send(msg, ephemeral=True)
                else:
                    await ctx.reply(msg, mention_author=False)
                return
            msg = (
                f"Tu es déjà lié à **{existing}**.\n"
                "Utilise **`/unlink`**, puis refais **`/linkanilist`** pour changer de pseudo AniList."
            )
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        other = core.discord_id_for_linked_anilist_username(resolved)
        if other is not None and other != ctx.author.id:
            msg = (
                "❌ Ce pseudo AniList est **déjà lié** à un autre compte Discord.\n"
                "Si c’est bien ton profil, contacte le support du bot : le lien doit être libéré."
            )
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        token = f"ANBOT-{secrets.token_hex(4).upper()}"
        core.anilist_set_link_pending(ctx.author.id, resolved, token)

        msg = (
            f"**Étape 1/2** — pseudo **{resolved}** reconnu sur AniList.\n\n"
            f"1. Ouvre ton profil AniList → **Paramètres** → colle exactement ce code dans "
            f"**« About » / « À propos »** (bio publique) :\n```{token}```\n"
            "2. Enregistre, puis lance **`/verifyanilist`** ici.\n\n"
            "_Le code expire après **30 minutes**. Tu peux le retirer de ta bio une fois lié._"
        )
        if ctx.interaction:
            await ctx.interaction.followup.send(msg, ephemeral=True)
        else:
            await ctx.reply(msg, mention_author=False)

    @commands.hybrid_command(
        name="verifyanilist",
        description="Après /linkanilist : confirme que la bio AniList contient le code.",
    )
    async def verify_anilist(self, ctx: commands.Context) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        pending = core.anilist_get_link_pending(ctx.author.id)
        if not pending:
            msg = "❌ Aucune vérification en cours. Commence par **`/linkanilist <pseudo>`**."
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        username, token, created = pending

        if time.time() - created > 1800:
            core.anilist_clear_link_pending(ctx.author.id)
            msg = "❌ Code expiré (30 min). Relance **`/linkanilist`** avec ton pseudo."
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        about = core.fetch_anilist_user_about(username) or ""
        if token not in about:
            msg = (
                f"❌ Je ne vois pas encore le code **`{token}`** sur le profil **{username}**.\n"
                "Vérifie la section **About** (publique), enregistre, attends quelques secondes, réessaie."
            )
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
                msg = "❌ Ce pseudo AniList vient d’être lié ailleurs. Réessaie ou contacte un admin."
            else:
                msg = "❌ Impossible d’enregistrer le lien pour le moment."
            core.anilist_clear_link_pending(ctx.author.id)
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        core.anilist_clear_link_pending(ctx.author.id)
        ok = f"✅ **Étape 2/2** — compte **{username}** confirmé et lié à ton Discord !"
        if ctx.interaction:
            await ctx.interaction.followup.send(ok, ephemeral=True)
        else:
            await ctx.reply(ok, mention_author=False)

    @commands.hybrid_command(name="unlink")
    async def unlink(self, ctx: commands.Context) -> None:
        """Supprime la liaison entre le compte Discord et AniList.

        Retire l'association entre l'ID Discord et le pseudo AniList
        précédemment enregistrée. L'utilisateur devra refaire la liaison
        pour utiliser les fonctionnalités nécessitant un compte AniList.

        Args:
            ctx: Le contexte de la commande
        """
        core.anilist_clear_link_pending(ctx.author.id)
        if core.unlink_linked_username(ctx.author.id):
            msg = "🔗 Ton lien AniList a bien été supprimé."
        else:
            msg = "❌ Aucun compte AniList n'était lié à ce profil."
        await user_reply.send_ephemeral_or_private(ctx, msg)

    @commands.hybrid_command(
        name="duelstats",
        description="Compare ton engagement AniList avec un ami (complétés, en cours, temps, épisodes).",
    )
    @commands.cooldown(1, 15, commands.BucketType.user)
    @app_commands.describe(adversaire="Le membre à affronter (compte AniList lié)")
    async def duelstats(self, ctx: commands.Context, adversaire: discord.Member | None = None) -> None:
        """Compare l’engagement AniList (complétés, en cours, temps, épisodes) — pas le genre ni un score vide."""
        opponent = adversaire
        if opponent is None:
            await ctx.send("❌ Utilise : **`/duelstats @ami`** pour lancer un duel de stats.")
            return
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

        user1 = core.get_linked_username(ctx.author.id)
        user2 = core.get_linked_username(opponent.id)
        if not user1 or not user2:
            await ctx.send("❗ Les deux joueurs doivent avoir lié leur compte avec `/linkanilist`.")
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
                await ctx.send("❌ Impossible de récupérer les statistiques AniList.")
                return

        s1, s2 = stats[user1], stats[user2]
        n_a = ctx.author.display_name[:32]
        n_b = opponent.display_name[:32]

        lines: List[str] = []
        pts_a = pts_b = 0

        for label, key in (
            ("Complétés", "completed"),
            ("En cours", "watching"),
            ("Épisodes vus", "episodes"),
            ("Jours visionnés", "days"),
        ):
            va, vb = s1[key], s2[key]
            text, pa, pb = _duel_compact(label, float(va), float(vb), n_a, n_b, higher_wins=True)
            lines.append(text)
            pts_a += pa
            pts_b += pb

        if _mean_bonus_ok(s1["mean"], s2["mean"]):
            text, pa, pb = _duel_compact(
                "Note moy. (bonus)",
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
            verdict = f"**{n_a}** gagne **{pts_a}**–**{pts_b}**"
            color = discord.Color.from_rgb(220, 90, 90)
        elif pts_b > pts_a:
            verdict = f"**{n_b}** gagne **{pts_b}**–**{pts_a}**"
            color = discord.Color.from_rgb(90, 130, 220)
        else:
            verdict = f"**Match nul** · **{pts_a}**–**{pts_b}**"
            color = discord.Color.from_rgb(180, 140, 60)

        board = "\n".join(lines)
        if len(board) > 1000:
            board = board[:997] + "…"

        embed = discord.Embed(
            title="⚔️ Duel AniList",
            description=(
                f"**{n_a}** · `{user1}`  ×  **{n_b}** · `{user2}`\n"
                "Engagement réel (pas genre / pas moyenne biaisée)."
            ),
            color=color,
        )
        embed.add_field(name="🎮 Tableau", value=board, inline=False)
        embed.add_field(name="🏆 Verdict", value=verdict, inline=False)
        embed.set_footer(text="AniList · /linkanilist · note bonus si 0 < moy. < 100 pour les deux")
        embed.set_author(name="Arène stats", icon_url=ctx.author.display_avatar.url)
        embed.set_thumbnail(url=opponent.display_avatar.url)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Configure le cog Link pour le bot.

    Args:
        bot: L'instance du bot Discord auquel ajouter le cog
    """
    await bot.add_cog(Link(bot))
