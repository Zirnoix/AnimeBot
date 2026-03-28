# cogs/airings_admin.py
from __future__ import annotations
from typing import List, Optional
import re

import discord
from discord import app_commands
from discord.ext import commands

from modules import core

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


class SelectModal(discord.ui.Modal, title="Sélection manuelle"):
    def __init__(self, view: "AllView", mode: str):
        super().__init__(timeout=180)
        self.view = view
        self.mode = mode  # "add" | "remove"
        self.input = discord.ui.TextInput(
            label="IDs AniList ou index de page (ex: 1,2,12345)",
            placeholder="Exemples : 1,3,7  ou  1535, 21087",
            required=True,
            max_length=200,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        text = str(self.input.value or "").replace(" ", "")
        if not text:
            await interaction.response.send_message("Entrée vide.", ephemeral=True)
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
            await interaction.response.send_message("Aucun ID/indice valide reconnu.", ephemeral=True)
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
        nv = _build_airings_view(self.view.guild_id, self.view.items, self.view.days, self.view.page)
        n = added if self.mode == "add" else removed
        try:
            await interaction.edit_original_response(embed=nv.build_embed(), view=nv)
        except (discord.HTTPException, discord.NotFound) as e:
            await interaction.followup.send(
                f"{'✅ Ajouté' if self.mode == 'add' else '🗑️ Retiré'} : **{n}** élément(s). "
                f"Impossible de rafraîchir la vue (`{e}`). Rouvre `/airings all`.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"{'✅ Ajouté' if self.mode == 'add' else '🗑️ Retiré'} : **{n}** élément(s).",
            ephemeral=True,
        )


def _build_airings_view(guild_id: int, items: List[dict], days: int, page: int) -> "AllView":
    """Recrée la vue (menus Select inclus) après changement de page ou de la liste du serveur."""
    return AllView(guild_id, items, days, page=page)


class PageAddSelect(discord.ui.Select):
    """Multi-sélection : ajouter des animés de la page à la liste du serveur."""

    def __init__(self, parent: "AllView"):
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
                    description=f"Ep. {ep} · id {mid}"[:100],
                    default=False,
                )
            )
        if not opts:
            opts = [discord.SelectOption(label="(rien sur cette page)", value="0")]
        super().__init__(
            placeholder="➕ Ajouter à la liste du serveur…",
            min_values=0,
            max_values=len(opts),
            options=opts,
            row=2,
        )
        # discord.ui.Item a une propriété `parent` en lecture seule — ne pas l'écraser.
        self.airings_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("❌ Utilisable seulement sur un serveur.", ephemeral=True)
            return
        vals = [v for v in self.values if v != "0"]
        if not vals:
            await interaction.response.send_message("Aucun animé sélectionné.", ephemeral=True)
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
        nv = _build_airings_view(self.airings_view.guild_id, self.airings_view.items, self.airings_view.days, self.airings_view.page)
        try:
            await interaction.edit_original_response(embed=nv.build_embed(), view=nv)
        except (discord.HTTPException, discord.NotFound) as e:
            await interaction.followup.send(
                f"✅ **{added}** ajout(s). Impossible de rafraîchir la vue (`{e}`). Rouvre `/airings all`.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(f"✅ **{added}** animé(s) ajouté(s) à la **liste du serveur**.", ephemeral=True)


class PageRemoveSelect(discord.ui.Select):
    """Multi-sélection : retirer de la liste du serveur les titres suivis sur cette page."""

    def __init__(self, parent: "AllView"):
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
            opts = [discord.SelectOption(label="(aucun suivi sur cette page)", value="0")]
        super().__init__(
            placeholder="🗑️ Retirer de la liste du serveur…",
            min_values=0,
            max_values=len(opts),
            options=opts,
            row=3,
        )
        self.airings_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("❌ Utilisable seulement sur un serveur.", ephemeral=True)
            return
        vals = [v for v in self.values if v != "0"]
        if not vals:
            await interaction.response.send_message("Aucune sélection.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        removed = 0
        for v in vals:
            if core.guild_whitelist_remove(self.airings_view.guild_id, int(v)):
                removed += 1
        self.airings_view.refresh_whitelist()
        nv = _build_airings_view(self.airings_view.guild_id, self.airings_view.items, self.airings_view.days, self.airings_view.page)
        try:
            await interaction.edit_original_response(embed=nv.build_embed(), view=nv)
        except (discord.HTTPException, discord.NotFound) as e:
            await interaction.followup.send(
                f"🗑️ **{removed}** retrait(s). Impossible de rafraîchir la vue (`{e}`). Rouvre `/airings all`.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(f"🗑️ **{removed}** animé(s) retiré(s) de la **liste du serveur**.", ephemeral=True)


class AllView(discord.ui.View):
    def __init__(self, guild_id: int, items: List[dict], days: int, page: int = 0, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.items = _dedupe_airings_by_media_id(items)
        self.days = days
        self.guild_id = guild_id
        self.per_page = 25
        pc = max(1, (len(self.items) + self.per_page - 1) // self.per_page)
        self.page = max(0, min(page, pc - 1))
        self.refresh_whitelist()
        self.add_item(PageAddSelect(self))
        self.add_item(PageRemoveSelect(self))

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
        e = discord.Embed(
            title=f"🎛️ Sorties à venir ({self.days} jours)",
            description=(
                "Liste **AniList** des prochains épisodes (non adulte). "
                "**✅** = déjà dans la **liste du serveur** (utilisée par `/next` et `/planning` en mode serveur).\n"
                "Menus pour ajouter ou retirer ; boutons **toute la page** ou **IDs manuels**."
            ),
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
            lines.append(f"**{i}.** {mark} [{link_txt}]({url}) — Ep **{ep}**")
        if not lines:
            lines = ["(aucun élément sur cette page)"]
        chunks = _chunk_lines_for_embed(lines)
        pc = self.pages_count()
        for ci, chunk in enumerate(chunks):
            if len(chunks) == 1:
                fname = f"Page {self.page + 1}/{pc} · {len(page_items)} animé(s)"
            else:
                fname = f"Page {self.page + 1}/{pc} · partie {ci + 1}/{len(chunks)}"
            e.add_field(name=fname, value=chunk[:1024], inline=False)
        e.set_footer(text="Liens → fiche AniList · jusqu’à 25 titres/page (plusieurs blocs si nécessaire)")
        return e

    # --- buttons ---
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.page = (self.page - 1) % self.pages_count()
        nv = _build_airings_view(self.guild_id, self.items, self.days, self.page)
        await interaction.response.edit_message(embed=nv.build_embed(), view=nv)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.page = (self.page + 1) % self.pages_count()
        nv = _build_airings_view(self.guild_id, self.items, self.days, self.page)
        await interaction.response.edit_message(embed=nv.build_embed(), view=nv)

    @discord.ui.button(label="Toute la page → liste", style=discord.ButtonStyle.success, row=1)
    async def add_page_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not interaction.guild_id:
            await interaction.response.send_message("❌ Commande utilisable seulement sur un serveur.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        count = 0
        for it in self.current_page_items():
            m = it.get("media") or {}
            if m.get("id") is not None and core.guild_whitelist_add_from_snapshot(self.guild_id, m):
                count += 1
        self.refresh_whitelist()
        nv = _build_airings_view(self.guild_id, self.items, self.days, self.page)
        try:
            await interaction.edit_original_response(embed=nv.build_embed(), view=nv)
        except (discord.HTTPException, discord.NotFound) as e:
            await interaction.followup.send(
                f"✅ **{count}** ajout(s), mais mise à jour de la vue impossible (`{e}`). Rouvre `/airings all`.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(f"✅ **{count}** nouvelle(s) entrée(s) ajoutée(s) (page entière).", ephemeral=True)

    @discord.ui.button(label="Toute la page → retirer", style=discord.ButtonStyle.danger, row=1)
    async def remove_page_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not interaction.guild_id:
            await interaction.response.send_message("❌ Commande utilisable seulement sur un serveur.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        count = 0
        for it in self.current_page_items():
            m = it.get("media") or {}
            mid = int(m.get("id"))
            if core.guild_whitelist_remove(self.guild_id, mid):
                count += 1
        self.refresh_whitelist()
        nv = _build_airings_view(self.guild_id, self.items, self.days, self.page)
        try:
            await interaction.edit_original_response(embed=nv.build_embed(), view=nv)
        except (discord.HTTPException, discord.NotFound) as e:
            await interaction.followup.send(
                f"🗑️ **{count}** retrait(s), mais mise à jour de la vue impossible (`{e}`). Rouvre `/airings all`.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(f"🗑️ **{count}** animé(s) retiré(s) (page entière).", ephemeral=True)

    @discord.ui.button(label="IDs manuels (ajout)", style=discord.ButtonStyle.primary, row=1)
    async def add_select_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(SelectModal(self, mode="add"))

    @discord.ui.button(label="IDs manuels (retrait)", style=discord.ButtonStyle.secondary, row=1)
    async def remove_select_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(SelectModal(self, mode="remove"))

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.secondary, row=1)
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
        description="Liste du serveur : quels animés suivre pour /next et /planning (admin).",
    )

    # ========= /airings all (remplace 'pick') =========
    # cogs/airings_admin.py (remplace uniquement la méthode all_)

    @group.command(
        name="all",
        description="Remplir la liste du serveur : menus, page entière ou IDs (admin).",
    )
    @app_commands.describe(jours="Fenêtre (1–14, défaut 7)")
    async def all_(self, interaction: discord.Interaction, jours: Optional[int] = 7):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Admin requis.", ephemeral=True)
            return

        # ✅ IMPORTANT: répondre dans les 3s
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        gid = interaction.guild_id
        if not gid:
            await interaction.followup.send("❌ Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return

        jours = max(1, min(14, int(jours or 7)))
        items = _dedupe_airings_by_media_id(core.get_airings_global(days=jours, limit=200))
        if not items:
            await interaction.followup.send(f"📭 Aucun épisode global sur {jours} jours.", ephemeral=True)
            return

        view = AllView(int(gid), items, days=jours)

        # après un defer, on doit utiliser followup
        await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)

    # ========= /airings list =========
    @group.command(name="list", description="Voir la liste du serveur (sélection /airings).")
    async def list_(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Admin requis.", ephemeral=True)
            return
        items = core.guild_whitelist_list(interaction.guild_id)
        if not items:
            await interaction.response.send_message("Aucun animé suivi. Utilise `/airings all` pour en ajouter.", ephemeral=True)
            return

        e = discord.Embed(
            title="✅ Liste du serveur (/next, /planning « serveur »)",
            description=(
                "Animés ajoutés par les admins via `/airings` (menus, page entière ou ID). "
                "Ce n’est **pas** toutes les sorties AniList — seulement ce que le serveur suit."
            ),
            color=discord.Color.green(),
        )
        lines = []
        for i, it in enumerate(items[:20], start=1):
            name = it.get("title_romaji") or "—"
            mid = it.get("media_id")
            url = it.get("siteUrl") or ""
            lines.append(f"{i}. **{name}** — ID `{mid}`  {(url)}")
        e.description = "\n".join(lines)
        leftover = max(0, len(items) - 20)
        if leftover:
            e.set_footer(text=f"... et {leftover} autres")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ========= /airings add =========
    @group.command(name="add", description="Ajouter un animé à la liste du serveur (URL AniList ou ID).")
    @app_commands.describe(anime="URL AniList (https://anilist.co/anime/12345) ou ID numérique")
    async def add(self, interaction: discord.Interaction, anime: str):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Admin requis.", ephemeral=True)
            return

        m = ANILIST_URL_RE.match(anime.strip())
        mid: Optional[int] = None
        if m:
            mid = int(m.group(2))
        elif anime.strip().isdigit():
            mid = int(anime.strip())

        if not mid:
            await interaction.response.send_message("Donne une **URL AniList** ou un **ID**.", ephemeral=True)
            return

        data = core.guild_whitelist_add(interaction.guild_id, mid)
        if not data:
            await interaction.response.send_message("Animé introuvable ou échec d’ajout.", ephemeral=True)
            return
        name = _pick_title_obj((data or {}).get("title"))
        await interaction.response.send_message(f"✅ Ajouté **{name}** (`{mid}`)", ephemeral=True)

    # ========= /airings remove =========
    @group.command(name="remove", description="Retirer un animé de la liste du serveur.")
    @app_commands.describe(media_id="ID AniList à retirer")
    async def remove(self, interaction: discord.Interaction, media_id: int):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Admin requis.", ephemeral=True)
            return
        ok = core.guild_whitelist_remove(interaction.guild_id, int(media_id))
        if ok:
            await interaction.response.send_message(f"🗑️ Retiré id `{media_id}`.", ephemeral=True)
        else:
            await interaction.response.send_message("Cet id n’était pas dans la liste du serveur.", ephemeral=True)

    # ========= /airings clear =========
    @group.command(name="clear", description="Vider la liste du serveur.")
    async def clear(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Admin requis.", ephemeral=True)
            return
        items = core.guild_whitelist_list(interaction.guild_id)
        n = 0
        for it in items:
            if core.guild_whitelist_remove(interaction.guild_id, int(it["media_id"])):
                n += 1
        await interaction.response.send_message(f"🧹 Whitelist vidée ({n} entrées supprimées).", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AiringsAdmin(bot))
