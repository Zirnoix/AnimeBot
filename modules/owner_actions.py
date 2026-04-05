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

from modules import bug_report as bug_report_store
from modules import core
from modules import i18n
from modules.image import generate_next_card

LOG = logging.getLogger(__name__)

ACTION_IDS = [
    "debug_tree",
    "debug_pub",
    "publish_global",
    "cogs",
    "test_alert",
    "show_channel",
    "recap_mensuel",
    "raid_reset_week",
    "raid_owner_start",
    "guessop_stats",
    "guessop_harvest",
    "help_dm",
    "setavatar_hint",
    "reportbug_blacklist",
]


def _owner_id() -> int | None:
    raw = os.getenv("OWNER_ID", "").strip()
    return int(raw) if raw.isdigit() else None


async def run_debug_tree(bot: commands.Bot, interaction: discord.Interaction) -> None:
    lg = i18n.interaction_lang(interaction)
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
                lines.append(f"/{c.name}{i18n.t('owner.runner.tree_group_empty', lg)}")
    chunk = "\n".join(lines) or i18n.t("owner.runner.tree_none", lg)
    await interaction.followup.send(f"```\n{chunk[:1900]}\n```", ephemeral=True)


async def run_debug_pub(bot: commands.Bot, interaction: discord.Interaction) -> None:
    lg = i18n.interaction_lang(interaction)
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
        await interaction.followup.send(
            i18n.t("owner.runner.pub_err", lg, err=e),
            ephemeral=True,
        )


async def run_publish_global(bot: commands.Bot, interaction: discord.Interaction) -> None:
    lg = i18n.interaction_lang(interaction)
    try:
        cmds = await interaction.client.tree.sync()
        await interaction.followup.send(
            i18n.t("owner.runner.sync_ok", lg, n=len(cmds)),
            ephemeral=True,
        )
    except Exception as e:
        await interaction.followup.send(
            i18n.t("owner.runner.sync_fail", lg, err=e),
            ephemeral=True,
        )


async def run_cogs(bot: commands.Bot, interaction: discord.Interaction) -> None:
    lg = i18n.interaction_lang(interaction)
    names = sorted(getattr(bot, "_loaded_cogs", None) or [])
    txt = i18n.t("owner.runner.cogs_empty", lg) if not names else "\n".join(names)
    await interaction.followup.send(f"```\n{txt}\n```", ephemeral=True)


async def run_test_alert(bot: commands.Bot, interaction: discord.Interaction) -> None:
    """Carte identique aux annonces salon ; envoi dans le salon `/setchannel` du serveur si défini."""
    lg = i18n.interaction_lang(interaction)
    if not interaction.guild:
        await interaction.followup.send(
            i18n.t("owner.runner.test_need_guild", lg),
            ephemeral=True,
        )
        return
    try:
        item = core.get_my_next_airing_one()
        if not item:
            await interaction.followup.send(
                i18n.t("owner.runner.test_no_episode", lg),
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
                i18n.t("owner.runner.test_channel_gone", lg),
                ephemeral=True,
            )
            return
        via_setchannel = target is not None
        if target is None:
            ch = interaction.channel
            target = ch if isinstance(ch, discord.TextChannel) else None
        if target is None:
            await interaction.followup.send(
                i18n.t("owner.runner.test_no_text", lg),
                ephemeral=True,
            )
            return

        # Même format que `cogs/alerts` (fichier PNG seul) + ligne pour repérer le test.
        header = i18n.t("owner.runner.test_header", lg)
        try:
            await target.send(
                header,
                file=discord.File(img_path, filename="test_alert.png"),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                i18n.t("owner.runner.test_forbidden", lg, ch=target.mention),
                ephemeral=True,
            )
            return

        where = target.mention
        if not via_setchannel:
            where += i18n.t("owner.runner.test_ok_extra", lg)
        await interaction.followup.send(
            i18n.t("owner.runner.test_ok", lg, where=where),
            ephemeral=True,
        )
    except Exception as e:
        await interaction.followup.send(
            i18n.t("owner.runner.test_err", lg, err=f"{type(e).__name__}: {e}"),
            ephemeral=True,
        )


async def run_show_channel(bot: commands.Bot, interaction: discord.Interaction) -> None:
    lg = i18n.interaction_lang(interaction)
    if not interaction.guild:
        await interaction.followup.send(
            i18n.t("owner.runner.show_need_guild", lg),
            ephemeral=True,
        )
        return
    try:
        summary = core.format_guild_channels_config_summary(interaction.client, interaction.guild.id)
        await interaction.followup.send(
            i18n.t("owner.runner.show_header", lg) + summary,
            ephemeral=True,
        )
    except Exception:
        await interaction.followup.send(
            i18n.t("owner.runner.show_fail", lg),
            ephemeral=True,
        )


async def run_recap_mensuel(bot: commands.Bot, interaction: discord.Interaction) -> None:
    lg = i18n.interaction_lang(interaction)
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
        i18n.t("owner.runner.recap_cur", lg, m=cur_m),
        i18n.t("owner.runner.recap_peak_g", lg, n=cur.get("peak_guilds", 0)),
        i18n.t("owner.runner.recap_peak_m", lg, n=cur.get("peak_members", 0)),
    ]
    if top_cur:
        lines.append(i18n.t("owner.runner.recap_top_head", lg))
        for k, v in top_cur:
            lines.append(i18n.t("owner.runner.recap_top_line", lg, k=k, v=v))
    else:
        lines.append(i18n.t("owner.runner.recap_no_slash", lg))
    prev_m = data.get("previous_month")
    prev = data.get("previous") or {}
    if prev_m and prev:
        pc = prev.get("commands") or {}
        ptop = sorted(pc.items(), key=lambda x: (-x[1], x[0]))[:10]
        lines.append("")
        lines.append(
            i18n.t(
                "owner.runner.recap_prev",
                lg,
                m=prev_m,
                pg=prev.get("peak_guilds", 0),
                pm=prev.get("peak_members", 0),
            )
        )
        if ptop:
            joiner = i18n.t("owner.runner.recap_prev_top_join", lg)
            items = joiner.join(f"`{a}`×{b}" for a, b in ptop)
            lines.append(i18n.t("owner.runner.recap_prev_top", lg, items=items))
    await interaction.followup.send("\n".join(lines)[:1950], ephemeral=True)


async def run_raid_reset_week(_bot: commands.Bot, interaction: discord.Interaction) -> None:
    """Efface les compteurs hebdo raid (alerte 1 h, auto, /raidstart) pour le serveur courant."""
    lg = i18n.interaction_lang(interaction)
    if not interaction.guild:
        await interaction.followup.send(
            i18n.t("owner.runner.raid_reset_need_guild", lg),
            ephemeral=True,
        )
        return
    gk = str(interaction.guild.id)
    keys = (
        "alert_sent_for_week",
        "alert_sent_message_id",
        "raid_started_for_week",
        "raidstart_week_key",
    )
    removed: list[str] = []
    missing_entry = False
    with core.DATA_JSON_LOCK:
        cfg = core.load_json(core.FileConfig.BOSS_RAID, {})
        ent = cfg.get(gk)
        if not isinstance(ent, dict):
            missing_entry = True
        else:
            for k in keys:
                if k in ent:
                    ent.pop(k, None)
                    removed.append(k)
            cfg[gk] = ent
            core.save_json(core.FileConfig.BOSS_RAID, cfg)
    if missing_entry:
        await interaction.followup.send(
            i18n.t("owner.runner.raid_reset_no_entry", lg),
            ephemeral=True,
        )
        return
    if not removed:
        await interaction.followup.send(
            i18n.t("owner.runner.raid_reset_no_state", lg),
            ephemeral=True,
        )
        return
    keys_join = "`, `".join(removed)
    await interaction.followup.send(
        i18n.t(
            "owner.runner.raid_reset_ok",
            lg,
            guild=interaction.guild.name,
            keys=keys_join,
        ),
        ephemeral=True,
    )


async def run_raid_owner_start(bot: commands.Bot, interaction: discord.Interaction) -> None:
    """Raid test sans consommer la limite /raidstart (logique identique à l’ancienne commande)."""
    from cogs.community_games import (  # noqa: PLC0415 — évite import circulaire au chargement
        _active_raids,
        _raid_target_channel,
        _week_key,
    )

    lg = i18n.interaction_lang(interaction)
    if not interaction.guild:
        await interaction.followup.send(
            i18n.t("owner.runner.raid_start_need_guild", lg),
            ephemeral=True,
        )
        return
    if _active_raids.get(interaction.guild.id):
        await interaction.followup.send(
            i18n.t("owner.runner.raid_start_busy", lg),
            ephemeral=True,
        )
        return
    target = _raid_target_channel(interaction.guild)
    if target is None:
        await interaction.followup.send(
            i18n.t("owner.runner.raid_start_no_ch", lg),
            ephemeral=True,
        )
        return
    cog = bot.get_cog("CommunityGames")
    if not cog:
        await interaction.followup.send(
            i18n.t("owner.runner.raid_start_no_cog", lg),
            ephemeral=True,
        )
        return
    wk = _week_key(datetime.now(core.TIMEZONE))
    await cog._start_boss_raid(interaction.guild, target, wk)  # type: ignore[attr-defined]
    await interaction.followup.send(
        i18n.t("owner.runner.raid_start_ok", lg, ch=target.mention),
        ephemeral=True,
    )


async def run_guessop_stats(_bot: commands.Bot, interaction: discord.Interaction) -> None:
    from modules import guessop_catalog as gopc  # noqa: PLC0415

    lg = i18n.interaction_lang(interaction)
    st = gopc.stats()
    dash = i18n.t("owner.runner.gop_dash", lg)
    lines = "\n".join(
        i18n.t("owner.runner.gop_line", lg, s=s, c=c) for s, c in st.get("by_source", [])
    ) or dash
    top = gopc.top_used(5)
    top_txt = "\n".join(
        i18n.t("owner.runner.gop_top_line", lg, t=t, u=u) for t, u in top
    ) or dash
    em = discord.Embed(
        title=i18n.t("owner.runner.gop_title", lg),
        description=i18n.t("owner.runner.gop_desc", lg, n=st["total"]),
        color=discord.Color.blue(),
    )
    em.add_field(name=i18n.t("owner.runner.gop_field_src", lg), value=lines[:1024], inline=False)
    em.add_field(name=i18n.t("owner.runner.gop_field_top", lg), value=top_txt[:1024], inline=False)
    await interaction.followup.send(embed=em, ephemeral=True)


async def run_guessop_harvest(bot: commands.Bot, interaction: discord.Interaction) -> None:
    from modules import animethemes  # noqa: PLC0415
    from modules import guessop_catalog as gopc  # noqa: PLC0415

    lg = i18n.interaction_lang(interaction)
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
        i18n.t(
            "owner.runner.harvest_ok",
            lg,
            before=before,
            after=after,
            ins=new_inserts,
        ),
        ephemeral=True,
    )


async def run_help_dm(bot: commands.Bot, interaction: discord.Interaction) -> None:
    lg = i18n.interaction_lang(interaction)
    cog = bot.get_cog("Help")
    if not cog:
        await interaction.followup.send(i18n.t("owner.runner.help_no_cog", lg), ephemeral=True)
        return
    try:
        pages, labels = cog._build_owner_pages(lg)  # type: ignore[attr-defined]
        from cogs.help import HelpNavigator  # noqa: PLC0415

        nav = HelpNavigator(pages, labels, help_cmd="help", lang=lg)
        first = nav._with_footer(pages[0])
        await interaction.user.send(embed=first, view=nav)
        await interaction.followup.send(i18n.t("owner.runner.help_sent", lg), ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(i18n.t("owner.runner.help_dm_block", lg), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(
            i18n.t("owner.runner.help_err", lg, err=f"{e}"),
            ephemeral=True,
        )


async def run_reportbug_blacklist(_bot: commands.Bot, interaction: discord.Interaction) -> None:
    """Récap blacklist /reportbug + rappel des commandes slash."""
    lg = i18n.interaction_lang(interaction)
    bl = bug_report_store.get_blacklist()
    n = len(bl)
    preview = ", ".join(f"`{x}`" for x in bl[:15]) or "—"
    if n > 15:
        preview += i18n.t("owner.runner.bl_more", lg, n=n - 15)
    await interaction.followup.send(
        i18n.t("owner.runner.bl_title", lg)
        + i18n.t("owner.runner.bl_body", lg, n=n, preview=preview),
        ephemeral=True,
    )


async def run_setavatar_hint(_bot: commands.Bot, interaction: discord.Interaction) -> None:
    lg = i18n.interaction_lang(interaction)
    await interaction.followup.send(
        i18n.t("owner.runner.avatar_hint", lg),
        ephemeral=True,
    )


RUNNERS = {
    "debug_tree": run_debug_tree,
    "debug_pub": run_debug_pub,
    "publish_global": run_publish_global,
    "cogs": run_cogs,
    "test_alert": run_test_alert,
    "show_channel": run_show_channel,
    "recap_mensuel": run_recap_mensuel,
    "raid_reset_week": run_raid_reset_week,
    "raid_owner_start": run_raid_owner_start,
    "guessop_stats": run_guessop_stats,
    "guessop_harvest": run_guessop_harvest,
    "help_dm": run_help_dm,
    "setavatar_hint": run_setavatar_hint,
    "reportbug_blacklist": run_reportbug_blacklist,
}
