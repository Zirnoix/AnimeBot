
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

from typing import Any, Dict, List, Tuple

import discord
from discord.ext import commands
from discord import app_commands
from modules import core


def _anime_status_count(statuses: List[Dict[str, Any]] | None, key: str) -> int:
    ku = key.upper()
    for s in statuses or []:
        st = str(s.get("status") or "").upper().replace(" ", "_")
        if st == ku:
            return int(s.get("count") or 0)
    return 0


def _duel_row(
    label: str,
    a: float,
    b: float,
    name_a: str,
    name_b: str,
    *,
    higher_wins: bool = True,
) -> Tuple[str, int, int]:
    """Une ligne de comparaison + points (1,0) ou (0,1) ou (0,0)."""
    if a == b:
        return f"**{label}**\n`{a}` · `{b}`\n🟰 Égalité", 0, 0
    if higher_wins:
        if a > b:
            return f"**{label}**\n`{a}` · `{b}`\n🏆 **{name_a}**", 1, 0
        return f"**{label}**\n`{a}` · `{b}`\n🏆 **{name_b}**", 0, 1
    if a < b:
        return f"**{label}**\n`{a}` · `{b}`\n🏆 **{name_a}**", 1, 0
    return f"**{label}**\n`{a}` · `{b}`\n🏆 **{name_b}**", 0, 1


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

        # 2) Écrire le lien en DB (source unique)
        core.set_linked_username(ctx.author.id, resolved)

        # 3) Confirmer
        ok = f"✅ Ton compte AniList **{resolved}** est maintenant lié."
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
        if core.unlink_linked_username(ctx.author.id):
            await ctx.send("🔗 Ton lien AniList a bien été supprimé.")
        else:
            await ctx.send("❌ Aucun compte AniList n'était lié à ce profil.")

    @commands.hybrid_command(
        name="duelstats",
        description="Compare ton engagement AniList avec un ami (complétés, en cours, temps, épisodes).",
    )
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
            res = core.query_anilist(query, {"name": u})
            try:
                a = res["data"]["User"]["statistics"]["anime"]
                st = a.get("statuses") or []
                stats[u] = {
                    "total_list": int(a.get("count") or 0),
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
            ("✅ Complétés (vraiment finis)", "completed"),
            ("📡 En cours (suivis actifs)", "watching"),
            ("📺 Épisodes vus (total)", "episodes"),
            ("⏱️ Jours de visionnage", "days"),
        ):
            va, vb = s1[key], s2[key]
            text, pa, pb = _duel_row(label, float(va), float(vb), n_a, n_b, higher_wins=True)
            lines.append(text)
            pts_a += pa
            pts_b += pb

        # Bonus : score moyen seulement si les deux notent vraiment
        mean_note = ""
        if s1["mean"] > 0 and s2["mean"] > 0:
            text, pa, pb = _duel_row(
                "⭐ Note moyenne (bonus, les deux notent)",
                float(s1["mean"]),
                float(s2["mean"]),
                n_a,
                n_b,
                higher_wins=True,
            )
            lines.append(text)
            pts_a += pa
            pts_b += pb
            mean_note = " · bonus **note moyenne** (si les deux en ont une)"

        if pts_a > pts_b:
            verdict = f"**{n_a}** mène **{pts_a}**–**{pts_b}**"
            color = discord.Color.from_rgb(220, 90, 90)
        elif pts_b > pts_a:
            verdict = f"**{n_b}** mène **{pts_b}**–**{pts_a}**"
            color = discord.Color.from_rgb(90, 130, 220)
        else:
            verdict = f"**Égalité** **{pts_a}**–**{pts_b}** — match nul"
            color = discord.Color.from_rgb(180, 140, 60)

        embed = discord.Embed(
            title="⚔️ Arène AniList",
            description=(
                f"*{n_a}* · `{user1}`\n"
                f"*{n_b}* · `{user2}`\n\n"
                "On compare **l’engagement** (titres complétés, ce que tu regardes, volume d’épisodes, temps).\n"
                "Pas de « duel » sur un genre favori ni sur une moyenne vide."
                f"{mean_note}"
            ),
            color=color,
        )
        embed.add_field(
            name="📊 Manches",
            value="\n\n".join(lines),
            inline=False,
        )
        embed.add_field(
            name="🏁 Verdict",
            value=verdict,
            inline=False,
        )
        embed.set_footer(text="AniList · /linkanilist requis des deux côtés")
        embed.set_author(name="Duel de profils", icon_url=ctx.author.display_avatar.url)
        embed.set_thumbnail(url=opponent.display_avatar.url)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Configure le cog Link pour le bot.

    Args:
        bot: L'instance du bot Discord auquel ajouter le cog
    """
    await bot.add_cog(Link(bot))
