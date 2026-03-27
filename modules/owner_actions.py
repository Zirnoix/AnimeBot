"""
Actions propriétaire (OWNER_ID) — utilisées par **`/owner`**.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import tempfile
from datetime import datetime

import discord
from discord.ext import commands

from modules import core
from modules.image import generate_next_card

LOG = logging.getLogger(__name__)


def _owner_id() -> int | None:
    raw = os.getenv("OWNER_ID", "").strip()
    return int(raw) if raw.isdigit() else None


async def run_debug_tree(bot: commands.Bot, interaction: discord.Interaction) -> None:
    cmds = interaction.client.tree.get_commands()
    lines: list[str] = []
    for c in cmds:
        if isinstance(c, discord.app_commands.Command):
            lines.append(f"/{c.name}")
        elif isinstance(c, discord.app_commands.Group):
            if c.commands:
                for sc in c.commands:
                    lines.append(f"/{c.name} {sc.name}")
            else:
                lines.append(f"/{c.name} (group vide)")
    chunk = "\n".join(lines) or "(aucune)"
    await interaction.followup.send(f"```\n{chunk[:1900]}\n```", ephemeral=True)


async def run_debug_pub(bot: commands.Bot, interaction: discord.Interaction) -> None:
    try:
        global_cmds = await interaction.client.tree.fetch_commands()
        guild_cmds = await interaction.client.tree.fetch_commands(guild=interaction.guild) if interaction.guild else []
        g_names = ["/" + c.name for c in global_cmds]
        gu_names: list[str] = []
        for c in guild_cmds:
            if isinstance(c, discord.app_commands.Command):
                gu_names.append("/" + c.name)
            else:
                for sc in c.commands:
                    gu_names.append(f"/{c.name} {sc.name}")
        txt = (
            f"GLOBAL ({len(g_names)}):\n" + "\n".join(sorted(g_names))[:900] +
            "\n\nGUILD ({len(gu_names)}):\n" + "\n".join(sorted(gu_names))[:900]
        )
        await interaction.followup.send(f"```\n{txt}\n```", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ debug_pub: {e}", ephemeral=True)


async def run_publish_global(bot: commands.Bot, interaction: discord.Interaction) -> None:
    try:
        cmds = await interaction.client.tree.sync()
        await interaction.followup.send(f"✅ Global sync OK — {len(cmds)} commande(s) publiées.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Global sync a échoué: {e}", ephemeral=True)


async def run_cogs(bot: commands.Bot, interaction: discord.Interaction) -> None:
    names = sorted(getattr(bot, "_loaded_cogs", None) or [])
    txt = "Aucun." if not names else "\n".join(names)
    await interaction.followup.send(f"```\n{txt}\n```", ephemeral=True)


async def run_test_alert(bot: commands.Bot, interaction: discord.Interaction) -> None:
    """Carte identique aux annonces salon ; envoi dans le salon `/setchannel` du serveur si défini."""
    if not interaction.guild:
        await interaction.followup.send(
            "❌ Utilise **`/owner` sur un serveur** pour tester l’envoi dans le salon des sorties (`/setchannel`).",
            ephemeral=True,
        )
        return
    try:
        item = core.get_my_next_airing_one()
        if not item:
            await interaction.followup.send(
                "Aucun prochain épisode à afficher (vérifie **`ANILIST_USERNAME`** dans `.env` / API AniList).",
                ephemeral=True,
            )
            return
        item["when"] = core.format_airing_datetime_fr(item.get("airingAt"), "Europe/Paris")
        c = item.get("cover")
        if c and not item.get("cover_urls"):
            item["cover_urls"] = [c]

        img_path = generate_next_card(
            item,
            out_path=os.path.join(tempfile.gettempdir(), "test_alert.png"),
            scale=1.2,
            padding=40,
        )

        gid = interaction.guild.id
        configured_id = core.resolve_guild_alert_channel_id(gid)
        target = await core.fetch_guild_alert_text_channel(bot, interaction.guild)
        if configured_id is not None and target is None:
            await interaction.followup.send(
                "❌ Le salon d’annonces configuré pour ce serveur est **introuvable** (supprimé ou bot sans accès). "
                "Refais **`/setchannel`** dans le bon salon, ou vérifie les permissions.",
                ephemeral=True,
            )
            return
        via_setchannel = target is not None
        if target is None:
            ch = interaction.channel
            target = ch if isinstance(ch, discord.TextChannel) else None
        if target is None:
            await interaction.followup.send("❌ Impossible de trouver un salon texte pour l’envoi.", ephemeral=True)
            return

        # Même format que `cogs/alerts` (fichier PNG seul) + ligne pour repérer le test.
        header = "📺 **Sortie** — l’épisode est disponible !\n`🧪 Test owner`"
        try:
            await target.send(
                header,
                file=discord.File(img_path, filename="test_alert.png"),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Envoi refusé dans {target.mention} — vérifie que le bot peut **écrire** et **joindre des fichiers**.",
                ephemeral=True,
            )
            return

        where = target.mention
        if not via_setchannel:
            where += " _(aucun salon `/setchannel` sur ce serveur — test dans le salon où tu as ouvert /owner)_"
        await interaction.followup.send(
            f"✅ Carte envoyée dans {where}.\n"
            "_L’image vient du **prochain épisode** de la liste **`ANILIST_USERNAME`** du bot — ce n’est pas forcément la même série que les annonces automatiques du serveur._",
            ephemeral=True,
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : `{type(e).__name__}: {e}`", ephemeral=True)


async def run_show_channel(bot: commands.Bot, interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.followup.send(
            "❌ Utilise cette action **sur un serveur** (pas en message privé).",
            ephemeral=True,
        )
        return
    try:
        summary = core.format_guild_channels_config_summary(interaction.client, interaction.guild.id)
        await interaction.followup.send(
            "**Salons de notification (ce serveur)**\n" + summary,
            ephemeral=True,
        )
    except Exception:
        await interaction.followup.send(
            "❌ Impossible de lire la config.",
            ephemeral=True,
        )


async def run_recap_mensuel(bot: commands.Bot, interaction: discord.Interaction) -> None:
    try:
        core.owner_telemetry_refresh_peaks(interaction.client)
    except Exception:
        pass
    data = core.owner_telemetry_summary()
    cur_m = data.get("current_month", "?")
    cur = data.get("current") or {}
    cmds_cur = cur.get("commands") or {}
    top_cur = sorted(cmds_cur.items(), key=lambda x: (-x[1], x[0]))[:15]
    lines = [
        f"**Mois courant** `{cur_m}`",
        f"· Pic **serveurs** : **{cur.get('peak_guilds', 0)}**",
        f"· Pic **membres** (somme des guilds, max vu) : **{cur.get('peak_members', 0)}**",
    ]
    if top_cur:
        lines.append("· **Top commandes slash** (comptage local, depuis la dernière rotation de mois) :")
        for k, v in top_cur:
            lines.append(f"  – `{k}` — **{v}**")
    else:
        lines.append(
            "· Aucun usage slash enregistré pour ce mois (le compteur démarre après mise à jour ; "
            "les membres rejoignent une guilde où le bot voit du trafic)."
        )
    prev_m = data.get("previous_month")
    prev = data.get("previous") or {}
    if prev_m and prev:
        pc = prev.get("commands") or {}
        ptop = sorted(pc.items(), key=lambda x: (-x[1], x[0]))[:10]
        lines.append("")
        lines.append(
            f"**Mois précédent** `{prev_m}` — pic serveurs **{prev.get('peak_guilds', 0)}**, "
            f"membres **{prev.get('peak_members', 0)}**"
        )
        if ptop:
            lines.append("· Top : " + " · ".join(f"`{a}`×{b}" for a, b in ptop))
    await interaction.followup.send("\n".join(lines)[:1950], ephemeral=True)


async def run_raid_owner_start(bot: commands.Bot, interaction: discord.Interaction) -> None:
    """Raid test sans consommer la limite /raidstart (logique identique à l’ancienne commande)."""
    from cogs.community_games import (  # noqa: PLC0415 — évite import circulaire au chargement
        _active_raids,
        _raid_target_channel,
        _week_key,
    )

    if not interaction.guild:
        await interaction.followup.send("❌ Serveur uniquement.", ephemeral=True)
        return
    if _active_raids.get(interaction.guild.id):
        await interaction.followup.send("Un raid est déjà en cours sur ce serveur.", ephemeral=True)
        return
    target = _raid_target_channel(interaction.guild)
    if target is None:
        await interaction.followup.send(
            "❌ Aucun salon de raid configuré. Utilise **`/raidconfig`** avec le paramètre **salon**.",
            ephemeral=True,
        )
        return
    cog = bot.get_cog("CommunityGames")
    if not cog:
        await interaction.followup.send("❌ Module CommunityGames indisponible.", ephemeral=True)
        return
    wk = _week_key(datetime.now(core.TIMEZONE))
    await cog._start_boss_raid(interaction.guild, target, wk)  # type: ignore[attr-defined]
    await interaction.followup.send(
        f"✅ **Raid lancé** (owner) dans {target.mention}.\n"
        "_La limite **`/raidstart`** des admins **n’est pas** consommée._",
        ephemeral=True,
    )


async def run_guessop_stats(_bot: commands.Bot, interaction: discord.Interaction) -> None:
    from modules import guessop_catalog as gopc  # noqa: PLC0415

    st = gopc.stats()
    lines = "\n".join(f"• **{s}** : {c}" for s, c in st.get("by_source", [])) or "—"
    top = gopc.top_used(5)
    top_txt = "\n".join(f"• {t} — {u}×" for t, u in top) if top else "—"
    em = discord.Embed(
        title="📚 Catalogue Guess OP",
        description=f"**{st['total']}** openings uniques (URL) — même base sur **tous** les serveurs.",
        color=discord.Color.blue(),
    )
    em.add_field(name="Par source", value=lines[:1024], inline=False)
    em.add_field(name="Plus tirés", value=top_txt[:1024], inline=False)
    await interaction.followup.send(embed=em, ephemeral=True)


async def run_guessop_harvest(bot: commands.Bot, interaction: discord.Interaction) -> None:
    from modules import animethemes  # noqa: PLC0415
    from modules import guessop_catalog as gopc  # noqa: PLC0415

    before = gopc.count()
    new_inserts = 0
    max_page = await animethemes.anime_catalog_max_page(35)
    if max_page <= 0:
        max_page = 1
    for _ in range(15):
        page = random.randint(1, max_page)
        try:
            items = await animethemes.harvest_openings_from_page(page, 35)
            for t, th, url in items:
                if url.startswith(("http://", "https://")):
                    _, ins = gopc.add_opening(t, th, url, "manual_page")
                    if ins:
                        new_inserts += 1
        except Exception:
            pass
        await asyncio.sleep(0.45)
    for _ in range(35):
        try:
            got = await animethemes.random_opening()
            if got:
                t, th, url = got
                if url.startswith(("http://", "https://")):
                    _, ins = gopc.add_opening(t, th, url, "manual_random")
                    if ins:
                        new_inserts += 1
        except Exception:
            pass
        await asyncio.sleep(1.0)
    after = gopc.count()
    await interaction.followup.send(
        f"✅ Catalogue : **{before}** → **{after}** openings.\n"
        f"**+{new_inserts}** nouvelles URLs (le reste était déjà en base — normal avec ~2000+ entrées).",
        ephemeral=True,
    )


async def run_help_dm(bot: commands.Bot, interaction: discord.Interaction) -> None:
    cog = bot.get_cog("Help")
    if not cog:
        await interaction.followup.send("❌ Module d’aide indisponible.", ephemeral=True)
        return
    try:
        pages, labels = cog._build_owner_pages()  # type: ignore[attr-defined]
        from cogs.help import HelpNavigator  # noqa: PLC0415

        nav = HelpNavigator(pages, labels)
        first = nav._with_footer(pages[0])
        await interaction.user.send(embed=first, view=nav)
        await interaction.followup.send("📬 Aide owner/admin envoyée en **message privé**.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Impossible d’envoyer un MP (paramètres).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : `{e}`", ephemeral=True)


async def run_setavatar_hint(_bot: commands.Bot, interaction: discord.Interaction) -> None:
    await interaction.followup.send(
        "**Avatar du bot** : envoie en **message privé** au bot une image avec la commande **`!setavatar`** "
        "(préfixe + pièce jointe sur le même message).",
        ephemeral=True,
    )


ACTIONS: list[tuple[str, str, str]] = [
    ("debug_tree", "Debug tree", "Liste locale des commandes slash (tree)"),
    ("debug_pub", "Debug publié", "GLOBAL vs GUILD sur ce serveur"),
    ("publish_global", "Sync globale", "Republie toutes les commandes en GLOBAL (rare)"),
    ("cogs", "Cogs chargés", "Liste des extensions Python chargées"),
    ("test_alert", "Test carte alerte", "Envoie la carte dans le salon /setchannel (sinon salon actuel)"),
    ("show_channel", "Salons config", "Récap salons alertes / XP / raid (ce serveur)"),
    ("recap_mensuel", "Stats internes", "Pics, usages slash, mois courant / précédent"),
    ("raid_owner_start", "Raid test (owner)", "Lance un raid sans consommer /raidstart"),
    ("guessop_stats", "Guess OP — stats", "Statistiques du catalogue openings"),
    ("guessop_harvest", "Guess OP — enrichir", "Harvest AnimeThemes (long, ~1–2 min)"),
    ("help_dm", "Aide owner (MP)", "Envoie l’aide restreinte owner/admin en MP"),
    ("setavatar_hint", "Changer l’avatar", "Rappel : !setavatar + image en MP"),
]

RUNNERS = {
    "debug_tree": run_debug_tree,
    "debug_pub": run_debug_pub,
    "publish_global": run_publish_global,
    "cogs": run_cogs,
    "test_alert": run_test_alert,
    "show_channel": run_show_channel,
    "recap_mensuel": run_recap_mensuel,
    "raid_owner_start": run_raid_owner_start,
    "guessop_stats": run_guessop_stats,
    "guessop_harvest": run_guessop_harvest,
    "help_dm": run_help_dm,
    "setavatar_hint": run_setavatar_hint,
}
