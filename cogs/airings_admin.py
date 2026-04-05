# cogs/airings_admin.py
from __future__ import annotations
from typing import List, Optional
import re

import discord
from discord import app_commands
from discord.ext import commands

from modules import core
from modules import i18n
from modules.app_cmd_locale import ui_str

ANILIST_URL_RE = re.compile(r"https?://(www\.)?anilist\.co/anime/(\d+)", re.I)

def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild


def _pick_title_obj(t: dict | None) -> str:
    t = t or {}
    return t.get("english") or t.get("romaji") or t.get("native") or "—"


def _anilist_anime_url(mid: int) -> str:
    return f"https://anilist.co/anime/{mid}"


def _md_link_title(s: str, max_len: int = 72) -> str:
    """Titre affiché dans un lien Markdown (évite [] qui cassent le rendu)."""
    t = (s or "—").replace("[", "(").replace("]", ")")
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def _chunk_lines_for_embed(lines: List[str], max_chars: int = 1020) -> List[str]:
    """Découpe en plusieurs blocs ≤ ~1024 car. (limite d’un field Discord)."""
    chunks: List[str] = []
    buf: List[str] = []
    size = 0
    for line in lines:
        add = len(line) + (1 if buf else 0)
        if buf and size + add > max_chars:
            chunks.append("\n".join(buf))
            buf = [line]
            size = len(line)
        else:
            buf.append(line)
            size += add
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def _dedupe_airings_by_media_id(items: List[dict]) -> List[dict]:
    """
    Discord interdit deux options StringSelect avec la même `value` (même media_id).
    AniList peut renvoyer plusieurs créneaux pour le même anime : on garde la 1re occurrence.
    """
    seen: set[int] = set()
    out: List[dict] = []
    for it in items or []:
        m = it.get("media") or {}
        mid = m.get("id")
        if mid is None:
            continue
        try:
            k = int(mid)
        except (TypeError, ValueError):
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


class SelectModal(discord.ui.Modal):
    def __init__(self, view: "AllView", mode: str):
        lg = view.lang
        super().__init__(title=i18n.t("airings_admin.modal_title", lg)[:45], timeout=180)
        self.view = view
        self.mode = mode  # "add" | "remove"
        self.input = discord.ui.TextInput(
            label=i18n.t("airings_admin.modal_label", lg)[:45],
            placeholder=i18n.t("airings_admin.modal_ph", lg)[:100],
            required=True,
            max_length=200,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lg = self.view.lang
        text = str(self.input.value or "").replace(" ", "")
        if not text:
            await interaction.response.send_message(i18n.t("airings_admin.modal_empty", lg), ephemeral=True)
            return

        ids: set[int] = set()
        # map des index => media_id pour la page courante
        page_items = self.view.current_page_items()
        index_map = {i + 1: int((it.get("media") or {}).get("id")) for i, it in enumerate(page_items)}

        for token in re.split(r"[,\s]+", text):
            if not token:
                continue
            if token.isdigit():
                n = int(token)
                # index local (1..nb) -> ID
                if 1 <= n <= len(index_map):
                    ids.add(index_map[n])
                else:
                    # on considère que c'est un ID AniList direct
                    ids.add(n)

        if not ids:
            await interaction.response.send_message(i18n.t("airings_admin.no_valid_id", lg), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild_id
        added = removed = 0
        if self.mode == "add":
            for mid in ids:
                if core.guild_whitelist_add(guild_id, int(mid)):
                    added += 1
        else:
            for mid in ids:
                if core.guild_whitelist_remove(guild_id, int(mid)):
                    removed += 1

        self.view.refresh_whitelist()
        nv = _build_airings_view(self.view.guild_id, self.view.items, self.view.days, self.view.page, lg)
        n = added if self.mode == "add" else removed
        verb = i18n.t("airings_admin.verb_add", lg) if self.mode == "add" else i18n.t("airings_admin.verb_rm", lg)
        try:
            await interaction.edit_original_response(embed=nv.build_embed(), view=nv)
        except (discord.HTTPException, discord.NotFound) as e:
            await interaction.followup.send(
                i18n.t("airings_admin.manual_refresh_fail", lg, verb=verb, n=n, err=e),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            i18n.t("airings_admin.manual_ok", lg, verb=verb, n=n),
            ephemeral=True,
        )


def _build_airings_view(guild_id: int, items: List[dict], days: int, page: int, lang: str) -> "AllView":
    """Recrée la vue (menus Select inclus) après changement de page ou de la liste du serveur."""
    return AllView(guild_id, items, days, page=page, lang=lang)


class PageAddSelect(discord.ui.Select):
    """Multi-sélection : ajouter des animés de la page à la liste du serveur."""

    def __init__(self, parent: "AllView"):
        lg = parent.lang
        page_items = parent.current_page_items()
        opts: List[discord.SelectOption] = []
        for it in page_items[:25]:
            m = it.get("media") or {}
            mid = int(m.get("id"))
            name = _pick_title_obj(m.get("title"))
            ep = core.format_episode_line_part(it.get("episode"), m)
            in_wl = mid in parent.wl_ids
            label = (f"✓ {name}" if in_wl else name)[:100]
            opts.append(
                discord.SelectOption(
                    label=label,
                    value=str(mid),
                    description=i18n.t("airings_admin.opt_ep_id", lg, ep=ep, mid=mid)[:100],
                    default=False,
                )
            )
        if not opts:
            opts = [discord.SelectOption(label=i18n.t("airings_admin.opt_empty_page", lg)[:100], value="0")]
        super().__init__(
            placeholder=i18n.t("airings_admin.ph_add", lg)[:150],
            min_values=0,
            max_values=len(opts),
            options=opts,
            row=2,
        )
        self.airings_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        lg = self.airings_view.lang
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("airings_admin.guild_only_short", lg), ephemeral=True)
            return
        vals = [v for v in self.values if v != "0"]
        if not vals:
            await interaction.response.send_message(i18n.t("airings_admin.select_none", lg), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild_id = self.airings_view.guild_id
        page_items = self.airings_view.current_page_items()
        mid_to_media: dict[int, dict] = {}
        for it in page_items:
            m = it.get("media") or {}
            if m.get("id") is not None:
                mid_to_media[int(m["id"])] = m
        added = 0
        for v in vals:
            m = mid_to_media.get(int(v))
            if m and core.guild_whitelist_add_from_snapshot(guild_id, m):
                added += 1
        self.airings_view.refresh_whitelist()
        nv = _build_airings_view(
            self.airings_view.guild_id, self.airings_view.items, self.airings_view.days, self.airings_view.page, lg,
        )
        try:
            await interaction.edit_original_response(embed=nv.build_embed(), view=nv)
        except (discord.HTTPException, discord.NotFound) as e:
            await interaction.followup.send(
                i18n.t("airings_admin.add_refresh_fail", lg, n=added, err=e),
                ephemeral=True,
            )
            return
        await interaction.followup.send(i18n.t("airings_admin.add_many_ok", lg, n=added), ephemeral=True)


class PageRemoveSelect(discord.ui.Select):
    """Multi-sélection : retirer de la liste du serveur les titres suivis sur cette page."""

    def __init__(self, parent: "AllView"):
        lg = parent.lang
        page_items = parent.current_page_items()
        opts: List[discord.SelectOption] = []
        for it in page_items[:25]:
            m = it.get("media") or {}
            mid = int(m.get("id"))
            if mid not in parent.wl_ids:
                continue
            name = _pick_title_obj(m.get("title"))[:100]
            opts.append(discord.SelectOption(label=name, value=str(mid)))
        if not opts:
            opts = [discord.SelectOption(label=i18n.t("airings_admin.opt_none_tracked", lg)[:100], value="0")]
        super().__init__(
            placeholder=i18n.t("airings_admin.ph_remove", lg)[:150],
            min_values=0,
            max_values=len(opts),
            options=opts,
            row=3,
        )
        self.airings_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        lg = self.airings_view.lang
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("airings_admin.guild_only_short", lg), ephemeral=True)
            return
        vals = [v for v in self.values if v != "0"]
        if not vals:
            await interaction.response.send_message(i18n.t("airings_admin.select_none_rm", lg), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        removed = 0
        for v in vals:
            if core.guild_whitelist_remove(self.airings_view.guild_id, int(v)):
                removed += 1
        self.airings_view.refresh_whitelist()
        nv = _build_airings_view(
            self.airings_view.guild_id, self.airings_view.items, self.airings_view.days, self.airings_view.page, lg,
        )
        try:
            await interaction.edit_original_response(embed=nv.build_embed(), view=nv)
        except (discord.HTTPException, discord.NotFound) as e:
            await interaction.followup.send(
                i18n.t("airings_admin.remove_refresh_fail", lg, n=removed, err=e),
                ephemeral=True,
            )
            return
        await interaction.followup.send(i18n.t("airings_admin.remove_many_ok", lg, n=removed), ephemeral=True)


class AllView(discord.ui.View):
    def __init__(self, guild_id: int, items: List[dict], days: int, page: int = 0, timeout: int = 300, *, lang: str):
        super().__init__(timeout=timeout)
        self.lang = lang
        self.items = _dedupe_airings_by_media_id(items)
        self.days = days
        self.guild_id = guild_id
        self.per_page = 25
        pc = max(1, (len(self.items) + self.per_page - 1) // self.per_page)
        self.page = max(0, min(page, pc - 1))
        self.refresh_whitelist()
        self.add_item(PageAddSelect(self))
        self.add_item(PageRemoveSelect(self))
        self.add_page_btn.label = i18n.t("airings_admin.btn_page_add", lang)[:80]
        self.remove_page_btn.label = i18n.t("airings_admin.btn_page_rm", lang)[:80]
        self.add_select_btn.label = i18n.t("airings_admin.btn_manual_add", lang)[:80]
        self.remove_select_btn.label = i18n.t("airings_admin.btn_manual_rm", lang)[:80]
        self.close_btn.label = i18n.t("airings_admin.btn_close", lang)[:80]

    # --- helpers ---
    def refresh_whitelist(self) -> None:
        wl = core.guild_whitelist_list(self.guild_id)
        self.wl_ids = {int(x["media_id"]) for x in wl}

    def pages_count(self) -> int:
        return max(1, (len(self.items) + self.per_page - 1) // self.per_page)

    def current_page_items(self) -> List[dict]:
        start = self.page * self.per_page
        end = start + self.per_page
        return self.items[start:end]

    def build_embed(self) -> discord.Embed:
        lg = self.lang
        e = discord.Embed(
            title=i18n.t("airings_admin.embed_title", lg, days=self.days),
            description=i18n.t("airings_admin.embed_desc", lg),
            color=discord.Color.blurple(),
        )
        page_items = self.current_page_items()
        lines = []
        for i, it in enumerate(page_items, start=1):
            m = it.get("media") or {}
            mid = int(m.get("id"))
            mark = "✅" if mid in self.wl_ids else "➕"
            name = _pick_title_obj(m.get("title"))
            ep = core.format_episode_line_part(it.get("episode"), m)
            link_txt = _md_link_title(name)
            url = _anilist_anime_url(mid)
            lines.append(
                i18n.t(
                    "airings_admin.line_entry",
                    lg, i=i, mark=mark, title=link_txt, url=url, ep=ep,
                )
            )
        if not lines:
            lines = [i18n.t("airings_admin.page_empty", lg)]
        chunks = _chunk_lines_for_embed(lines)
        pc = self.pages_count()
        for ci, chunk in enumerate(chunks):
            if len(chunks) == 1:
                fname = i18n.t(
                    "airings_admin.field_page",
                    lg, cur=self.page + 1, total=pc, n=len(page_items),
                )
            else:
                fname = i18n.t(
                    "airings_admin.field_part",
                    lg, cur=self.page + 1, total=pc, ci=ci + 1, parts=len(chunks),
                )
            e.add_field(name=fname, value=chunk[:1024], inline=False)
        e.set_footer(text=i18n.t("airings_admin.embed_footer", lg))
        return e

    # --- buttons ---
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.page = (self.page - 1) % self.pages_count()
        nv = _build_airings_view(self.guild_id, self.items, self.days, self.page, self.lang)
        await interaction.response.edit_message(embed=nv.build_embed(), view=nv)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.page = (self.page + 1) % self.pages_count()
        nv = _build_airings_view(self.guild_id, self.items, self.days, self.page, self.lang)
        await interaction.response.edit_message(embed=nv.build_embed(), view=nv)

    @discord.ui.button(label="Add whole page", style=discord.ButtonStyle.success, row=1)
    async def add_page_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        lg = self.lang
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("airings_admin.guild_only_cmd", lg), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        count = 0
        for it in self.current_page_items():
            m = it.get("media") or {}
            if m.get("id") is not None and core.guild_whitelist_add_from_snapshot(self.guild_id, m):
                count += 1
        self.refresh_whitelist()
        nv = _build_airings_view(self.guild_id, self.items, self.days, self.page, lg)
        try:
            await interaction.edit_original_response(embed=nv.build_embed(), view=nv)
        except (discord.HTTPException, discord.NotFound) as e:
            await interaction.followup.send(
                i18n.t("airings_admin.page_add_fail", lg, n=count, err=e),
                ephemeral=True,
            )
            return
        await interaction.followup.send(i18n.t("airings_admin.page_add_ok", lg, n=count), ephemeral=True)

    @discord.ui.button(label="Remove whole page", style=discord.ButtonStyle.danger, row=1)
    async def remove_page_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        lg = self.lang
        if not interaction.guild_id:
            await interaction.response.send_message(i18n.t("airings_admin.guild_only_cmd", lg), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        count = 0
        for it in self.current_page_items():
            m = it.get("media") or {}
            mid = int(m.get("id"))
            if core.guild_whitelist_remove(self.guild_id, mid):
                count += 1
        self.refresh_whitelist()
        nv = _build_airings_view(self.guild_id, self.items, self.days, self.page, lg)
        try:
            await interaction.edit_original_response(embed=nv.build_embed(), view=nv)
        except (discord.HTTPException, discord.NotFound) as e:
            await interaction.followup.send(
                i18n.t("airings_admin.page_rm_fail", lg, n=count, err=e),
                ephemeral=True,
            )
            return
        await interaction.followup.send(i18n.t("airings_admin.page_rm_ok", lg, n=count), ephemeral=True)

    @discord.ui.button(label="Manual IDs (add)", style=discord.ButtonStyle.primary, row=1)
    async def add_select_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(SelectModal(self, mode="add"))

    @discord.ui.button(label="Manual IDs (remove)", style=discord.ButtonStyle.secondary, row=1)
    async def remove_select_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(SelectModal(self, mode="remove"))

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary, row=1)
    async def close_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class AiringsAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(
        name="airings",
        description=ui_str("slash.airings_group"),
    )

    # ========= /airings all (remplace 'pick') =========
    # cogs/airings_admin.py (remplace uniquement la méthode all_)

    @group.command(
        name="all",
        description=ui_str("slash.airings_all"),
    )
    @app_commands.describe(jours=ui_str("slash.airings_param_jours"))
    async def all_(self, interaction: discord.Interaction, jours: Optional[int] = 7):
        lg = i18n.interaction_lang(interaction)
        if not is_admin(interaction.user):
            await interaction.response.send_message(i18n.t("airings_admin.admin_required", lg), ephemeral=True)
            return

        # ✅ IMPORTANT: répondre dans les 3s
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        gid = interaction.guild_id
        if not gid:
            await interaction.followup.send(i18n.t("airings_admin.need_guild", lg), ephemeral=True)
            return

        jours = max(1, min(14, int(jours or 7)))
        items = _dedupe_airings_by_media_id(core.get_airings_global(days=jours, limit=200))
        if not items:
            await interaction.followup.send(
                i18n.t("airings_admin.no_episodes_window", lg, days=jours),
                ephemeral=True,
            )
            return

        view = AllView(int(gid), items, days=jours, lang=lg)

        # après un defer, on doit utiliser followup
        await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)

    # ========= /airings list =========
    @group.command(name="list", description=ui_str("slash.airings_list"))
    async def list_(self, interaction: discord.Interaction):
        lg = i18n.interaction_lang(interaction)
        if not is_admin(interaction.user):
            await interaction.response.send_message(i18n.t("airings_admin.admin_required", lg), ephemeral=True)
            return
        items = core.guild_whitelist_list(interaction.guild_id)
        if not items:
            await interaction.response.send_message(i18n.t("airings_admin.list_empty", lg), ephemeral=True)
            return

        lines = []
        for i, it in enumerate(items[:20], start=1):
            name = it.get("title_romaji") or "—"
            mid = it.get("media_id")
            url = it.get("siteUrl") or ""
            lines.append(i18n.t("airings_admin.list_line", lg, i=i, name=name, mid=mid, url=url))
        body = "\n".join(lines)
        e = discord.Embed(
            title=i18n.t("airings_admin.list_title", lg),
            description=i18n.t("airings_admin.list_desc", lg) + "\n\n" + body,
            color=discord.Color.green(),
        )
        leftover = max(0, len(items) - 20)
        if leftover:
            e.set_footer(text=i18n.t("airings_admin.list_footer_more", lg, n=leftover))
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ========= /airings add =========
    @group.command(name="add", description=ui_str("slash.airings_add"))
    @app_commands.describe(anime=ui_str("slash.airings_param_anime"))
    async def add(self, interaction: discord.Interaction, anime: str):
        lg = i18n.interaction_lang(interaction)
        if not is_admin(interaction.user):
            await interaction.response.send_message(i18n.t("airings_admin.admin_required", lg), ephemeral=True)
            return

        m = ANILIST_URL_RE.match(anime.strip())
        mid: Optional[int] = None
        if m:
            mid = int(m.group(2))
        elif anime.strip().isdigit():
            mid = int(anime.strip())

        if not mid:
            await interaction.response.send_message(i18n.t("airings_admin.add_need_url", lg), ephemeral=True)
            return

        data = core.guild_whitelist_add(interaction.guild_id, mid)
        if not data:
            await interaction.response.send_message(i18n.t("airings_admin.add_not_found", lg), ephemeral=True)
            return
        name = _pick_title_obj((data or {}).get("title"))
        await interaction.response.send_message(
            i18n.t("airings_admin.add_one_ok", lg, name=name, mid=mid),
            ephemeral=True,
        )

    # ========= /airings remove =========
    @group.command(name="remove", description=ui_str("slash.airings_remove"))
    @app_commands.describe(media_id=ui_str("slash.airings_param_media_id"))
    async def remove(self, interaction: discord.Interaction, media_id: int):
        lg = i18n.interaction_lang(interaction)
        if not is_admin(interaction.user):
            await interaction.response.send_message(i18n.t("airings_admin.admin_required", lg), ephemeral=True)
            return
        ok = core.guild_whitelist_remove(interaction.guild_id, int(media_id))
        if ok:
            await interaction.response.send_message(
                i18n.t("airings_admin.remove_one_ok", lg, mid=media_id),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(i18n.t("airings_admin.remove_not_in", lg), ephemeral=True)

    # ========= /airings clear =========
    @group.command(name="clear", description=ui_str("slash.airings_clear"))
    async def clear(self, interaction: discord.Interaction):
        lg = i18n.interaction_lang(interaction)
        if not is_admin(interaction.user):
            await interaction.response.send_message(i18n.t("airings_admin.admin_required", lg), ephemeral=True)
            return
        items = core.guild_whitelist_list(interaction.guild_id)
        n = 0
        for it in items:
            if core.guild_whitelist_remove(interaction.guild_id, int(it["media_id"])):
                n += 1
        await interaction.response.send_message(i18n.t("airings_admin.clear_ok", lg, n=n), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AiringsAdmin(bot))
