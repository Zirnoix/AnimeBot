# cogs/help.py
from __future__ import annotations
import itertools
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands

EMBED_COLOR = 0x5865F2
MAX_FIELDS_PER_PAGE = 6          # nb de sections (thèmes) par page dans le HUB
MAX_CMDS_PER_SECTION = 10        # nb de commandes affichées par section (dans le HUB)
INLINE_CMDS_PER_LINE = 3         # nb de commandes par ligne (dans le HUB)
THEME_CMDS_PER_PAGE = 24         # nb de commandes par page dans la vue "Thème complet"

THEME_ORDER = [
    "Essentiels",
    "Quiz & Guess",
    "Profil & Stats",
    "Planning & Tracking",
    "Anime & Recherche",
    "Fun & Outils",
    "Autres",
]
THEME_EMOJI = {
    "Essentiels": "✨",
    "Quiz & Guess": "🎮",
    "Profil & Stats": "🧑‍🚀",
    "Planning & Tracking": "🗓️",
    "Anime & Recherche": "📚",
    "Fun & Outils": "🧰",
    "Admin": "🛠️",
    "Autres": "📦",
}

COG_THEME_HINTS = {
    "Help": "Essentiels",
    "Core": "Essentiels",
    "Utility": "Essentiels",
    "Fun": "Fun & Outils",
    "AnimeTools": "Anime & Recherche",
    "Anime": "Anime & Recherche",
    "Search": "Anime & Recherche",
    "Quiz": "Quiz & Guess",
    "Games": "Quiz & Guess",
    "Profile": "Profil & Stats",
    "Stats": "Profil & Stats",
    "Planning": "Planning & Tracking",
    "Tracker": "Planning & Tracking",
    "Watchdog": "Fun & Outils",
    "Shop": "Profil & Stats",
    "Admin": "Admin",
    "Moderation": "Admin",
}
ADMIN_NAME_HINTS = (
    "ban","kick","mute","slowmode","clear","purge","sync","reload","load","unload",
    "owner","admin","config","setchannel","toggle","clean","health"
)

def _theme_for_command(cmd: commands.Command) -> str:
    cog_name = (cmd.cog.qualified_name if cmd.cog else "") or ""
    for key, theme in COG_THEME_HINTS.items():
        if key.lower() in cog_name.lower():
            return theme
    name = cmd.qualified_name.lower()
    if any(h in name for h in ("quiz","guess","vf","vraifaux","speed","battle","opening")):
        return "Quiz & Guess"
    if any(h in name for h in ("mycard","monchart","rank","stats","xp","level","coins","themes","shop")):
        return "Profil & Stats"
    if any(h in name for h in ("next","monnext","planning","monplanning","track")):
        return "Planning & Tracking"
    if any(h in name for h in ("anime","compare","reco","search","personnage","character")):
        return "Anime & Recherche"
    return "Autres"

def _is_admin_like(cmd: commands.Command) -> bool:
    if getattr(cmd, "hidden", False):
        return True
    n = cmd.qualified_name.lower()
    if any(h in n for h in ADMIN_NAME_HINTS):
        return True
    cog_name = (cmd.cog.qualified_name if cmd.cog else "") or ""
    if "admin" in cog_name.lower() or "moderation" in cog_name.lower():
        return True
    return False

def _visible(cmd: commands.Command) -> bool:
    return not getattr(cmd, "hidden", False)

def _chunk(lst, n):
    it = iter(lst)
    while True:
        block = list(itertools.islice(it, n))
        if not block:
            break
        yield block

def _group_commands(bot: commands.Bot, include_admin: bool) -> Dict[str, List[commands.Command]]:
    cats: Dict[str, List[commands.Command]] = {k: [] for k in THEME_ORDER}
    if include_admin:
        cats["Admin"] = []

    for cmd in bot.walk_commands():
        if not isinstance(cmd, commands.Command):
            continue
        if not _visible(cmd):
            continue
        if _is_admin_like(cmd):
            if include_admin:
                cats["Admin"].append(cmd)
            continue
        theme = _theme_for_command(cmd)
        cats.setdefault(theme, []).append(cmd)

    for k in list(cats.keys()):
        cats[k] = sorted(cats[k], key=lambda c: c.qualified_name.lower())
    cats = {k: v for k, v in cats.items() if v}

    ordered = {}
    for k in THEME_ORDER:
        if k in cats:
            ordered[k] = cats[k]
    for k, v in cats.items():
        if k not in ordered:
            ordered[k] = v
    if include_admin and "Admin" in cats:
        ordered["Admin"] = cats["Admin"]
    return ordered

def _hub_section_lines(cmds: List[commands.Command], prefix: str, limit: int) -> str:
    parts = [f"`{prefix}{c.qualified_name}`" for c in cmds[:limit]]
    out_lines = [" ".join(row) for row in _chunk(parts, 3)]
    extra = len(cmds) - min(limit, len(cmds))
    if extra > 0:
        out_lines.append("… **Voir plus via le menu ci-dessous**")
    return "\n".join(out_lines) if out_lines else "—"

def _theme_page_embed(theme: str, commands_list: List[commands.Command], prefix: str, page_idx: int) -> discord.Embed:
    emoji = THEME_EMOJI.get(theme, "📦")
    title = f"{emoji} {theme} — commandes"
    start = page_idx * THEME_CMDS_PER_PAGE
    end = start + THEME_CMDS_PER_PAGE
    slice_cmds = commands_list[start:end]
    lines = []
    for c in slice_cmds:
        sig = f"`{prefix}{c.qualified_name}{(' ' + c.signature) if c.signature else ''}`"
        short = c.brief or (c.help.splitlines()[0] if c.help else "")
        lines.append(f"• {sig} — {short or '—'}")
    desc = "\n".join(lines) if lines else "—"
    e = discord.Embed(title=title, description=desc, color=EMBED_COLOR)
    return e

# -------------------- VUES --------------------

class ThemeView(discord.ui.View):
    """Vue paginée pour un thème (liste complète de ses commandes)."""
    def __init__(self, theme: str, cmds: List[commands.Command], prefix: str, author_id: int):
        super().__init__(timeout=180)
        self.theme = theme
        self.cmds = cmds
        self.prefix = prefix
        self.author_id = author_id
        self.page = 0
        total_pages = max(1, (len(self.cmds) + THEME_CMDS_PER_PAGE - 1) // THEME_CMDS_PER_PAGE)

        self.prev_btn = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary)
        self.next_btn = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary)
        self.back_btn = discord.ui.Button(label="⬅️ Retour au sommaire", style=discord.ButtonStyle.secondary)
        self.close_btn = discord.ui.Button(label="Fermer", style=discord.ButtonStyle.danger)

        self.prev_btn.callback = self.on_prev  # type: ignore
        self.next_btn.callback = self.on_next  # type: ignore
        self.back_btn.callback = self.on_back  # type: ignore
        self.close_btn.callback = self.on_close  # type: ignore

        self.add_item(self.prev_btn)
        self.add_item(self.next_btn)
        self.add_item(self.back_btn)
        self.add_item(self.close_btn)
        self._refresh()

    async def interaction_check(self, it: discord.Interaction) -> bool:
        if it.user and it.user.id != self.author_id:
            await it.response.send_message("Ce panneau ne t’appartient pas.", ephemeral=True)
            return False
        return True

    def _refresh(self):
        total_pages = max(1, (len(self.cmds) + THEME_CMDS_PER_PAGE - 1) // THEME_CMDS_PER_PAGE)
        self.prev_btn.disabled = (self.page == 0)
        self.next_btn.disabled = (self.page >= total_pages - 1)

    async def on_prev(self, it: discord.Interaction):
        if self.page > 0:
            self.page -= 1
        self._refresh()
        emb = _theme_page_embed(self.theme, self.cmds, self.prefix, self.page)
        emb.set_footer(text=f"Page {self.page+1}/{max(1, (len(self.cmds)+THEME_CMDS_PER_PAGE-1)//THEME_CMDS_PER_PAGE)}")
        await it.response.edit_message(embed=emb, view=self)

    async def on_next(self, it: discord.Interaction):
        total_pages = max(1, (len(self.cmds)+THEME_CMDS_PER_PAGE-1)//THEME_CMDS_PER_PAGE)
        if self.page < total_pages - 1:
            self.page += 1
        self._refresh()
        emb = _theme_page_embed(self.theme, self.cmds, self.prefix, self.page)
        emb.set_footer(text=f"Page {self.page+1}/{total_pages}")
        await it.response.edit_message(embed=emb, view=self)

    async def on_back(self, it: discord.Interaction):
        # Le hub est reconstruit par le handler parent (il remplace cette vue)
        await it.response.defer()  # le parent ré-édite derrière

    async def on_close(self, it: discord.Interaction):
        for item in self.children:
            item.disabled = True  # type: ignore
        await it.response.edit_message(view=self)

class HubView(discord.ui.View):
    """Vue du sommaire (sections par thèmes) avec pagination + select de thème."""
    def __init__(self, pages: List[discord.Embed], author_id: int, theme_map: Dict[str, List[commands.Command]], prefix: str):
        super().__init__(timeout=180)
        self.pages = pages
        self.i = 0
        self.author_id = author_id
        self.theme_map = theme_map
        self.prefix = prefix

        # Pagination : toujours visible (désactivée si 1 page)
        self.prev_btn = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary)
        self.next_btn = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary)
        self.close_btn = discord.ui.Button(label="Fermer", style=discord.ButtonStyle.danger)

        self.prev_btn.callback = self.on_prev  # type: ignore
        self.next_btn.callback = self.on_next  # type: ignore
        self.close_btn.callback = self.on_close  # type: ignore

        self.add_item(self.prev_btn)
        self.add_item(self.next_btn)

        # Select des thèmes (pour voir un thème en entier)
        options = []
        for theme in THEME_ORDER + [k for k in theme_map.keys() if k not in THEME_ORDER]:
            if theme not in theme_map: 
                continue
            emoji = THEME_EMOJI.get(theme, "📦")
            options.append(discord.SelectOption(label=theme, value=theme, emoji=emoji))
        self.select = discord.ui.Select(placeholder="Voir un thème en entier…", options=options, min_values=1, max_values=1)
        self.select.callback = self.on_select  # type: ignore
        self.add_item(self.select)

        self.add_item(self.close_btn)
        self._refresh()

    async def interaction_check(self, it: discord.Interaction) -> bool:
        if it.user and it.user.id != self.author_id:
            await it.response.send_message("Ce panneau ne t’appartient pas.", ephemeral=True)
            return False
        return True

    def _refresh(self):
        self.prev_btn.disabled = (self.i == 0)
        self.next_btn.disabled = (self.i >= len(self.pages) - 1)
        # même s'il n'y a qu'une page, on laisse les boutons visibles (mais disabled)

    async def on_prev(self, it: discord.Interaction):
        if self.i > 0:
            self.i -= 1
        self._refresh()
        await it.response.edit_message(embed=self.pages[self.i], view=self)

    async def on_next(self, it: discord.Interaction):
        if self.i < len(self.pages) - 1:
            self.i += 1
        self._refresh()
        await it.response.edit_message(embed=self.pages[self.i], view=self)

    async def on_select(self, it: discord.Interaction):
        theme = self.select.values[0]
        cmds = self.theme_map.get(theme, [])
        # Bascule vers la vue "thème complet"
        theme_view = ThemeView(theme, cmds, self.prefix, self.author_id)
        emb = _theme_page_embed(theme, cmds, self.prefix, theme_view.page)
        emb.set_footer(text=f"Page 1/{max(1,(len(cmds)+THEME_CMDS_PER_PAGE-1)//THEME_CMDS_PER_PAGE)}")
        await it.response.edit_message(embed=emb, view=theme_view)

    async def on_close(self, it: discord.Interaction):
        for item in self.children:
            item.disabled = True  # type: ignore
        await it.response.edit_message(view=self)

# -------------------- COG --------------------

def _build_hub_pages(cats: Dict[str, List[commands.Command]], prefix: str, title: str) -> List[discord.Embed]:
    sections: List[Tuple[str, str]] = []
    for theme in THEME_ORDER + [k for k in cats.keys() if k not in THEME_ORDER]:
        if theme not in cats:
            continue
        cmds = cats[theme]
        emoji = THEME_EMOJI.get(theme, "📦")
        title_sec = f"{emoji} {theme}"
        body = _hub_section_lines(cmds, prefix, MAX_CMDS_PER_SECTION)
        sections.append((title_sec, body))

    pages: List[discord.Embed] = []
    for chunk in _chunk(sections, MAX_FIELDS_PER_PAGE):
        e = discord.Embed(
            title=title,
            description="Astuce : `!help <commande>` pour l’aide détaillée. `!help admin` pour les commandes propriétaire.",
            color=EMBED_COLOR,
        )
        for (sec_title, body) in chunk:
            e.add_field(name=sec_title, value=body, inline=False)
        pages.append(e)

    for i, emb in enumerate(pages, start=1):
        emb.set_footer(text=f"Page {i}/{len(pages)}")
    return pages

class PrettyHelp(commands.Cog):
    """
    Help compact, thématisé, avec :
    - HUB paginé + boutons visibles
    - Select pour ouvrir un thème complet (pagination par thème)
    - !help, !help all, !help admin, !help <commande>, !help theme <nom>
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        try:
            bot.remove_command("help")
        except Exception:
            pass

    @commands.command(name="help")
    async def help_cmd(self, ctx: commands.Context, *, arg: Optional[str] = None):
        prefix = getattr(ctx, "clean_prefix", "!")

        # Détail d’une commande
        if arg and not arg.lower().startswith("theme") and arg.lower() not in ("all","admin"):
            cmd = self.bot.get_command(arg)
            if cmd and _visible(cmd):
                return await self._send_command_help(ctx, cmd, prefix)

        # Un thème précis (texte)
        if arg and arg.lower().startswith("theme"):
            parts = arg.split(maxsplit=1)
            if len(parts) == 1:
                return await ctx.send("Utilise : `!help theme <nom>` (ex: `!help theme Quiz & Guess`).")
            target_theme = parts[1].strip()

            cats = _group_commands(self.bot, include_admin=False)
            match = next((t for t in cats.keys() if t.lower() == target_theme.lower()), None)
            if not match:
                return await ctx.send("❓ Thème introuvable. Essaie: `Essentiels`, `Quiz & Guess`, `Profil & Stats`, `Planning & Tracking`, `Anime & Recherche`, `Fun & Outils`.")
            # Ouvre directement la vue thème
            view = ThemeView(match, cats[match], prefix, ctx.author.id)
            emb = _theme_page_embed(match, cats[match], prefix, 0)
            emb.set_footer(text=f"Page 1/{max(1,(len(cats[match])+THEME_CMDS_PER_PAGE-1)//THEME_CMDS_PER_PAGE)}")
            return await ctx.send(embed=emb, view=view)

        # ALL public
        if arg and arg.lower() == "all":
            cats = _group_commands(self.bot, include_admin=False)
            pages = _build_hub_pages(cats, prefix, "📖 Aide — commandes principales")
            view = HubView(pages, ctx.author.id, cats, prefix)
            return await ctx.send(embed=pages[0], view=view)

        # ADMIN
        if arg and arg.lower() == "admin":
            is_owner = False
            try:
                is_owner = await self.bot.is_owner(ctx.author)
            except Exception:
                pass
            if not is_owner and ctx.guild and ctx.guild.owner_id != ctx.author.id:
                return await ctx.send("🛡️ Cette section est réservée au propriétaire.")
            cats = _group_commands(self.bot, include_admin=True)
            cats = {"Admin": cats.get("Admin", [])}
            if not cats["Admin"]:
                return await ctx.send("Aucune commande admin détectée.")
            pages = _build_hub_pages(cats, prefix, "🛠️ Aide — Admin")
            view = HubView(pages, ctx.author.id, cats, prefix)
            return await ctx.send(embed=pages[0], view=view)

        # Par défaut → HUB public
        cats = _group_commands(self.bot, include_admin=False)
        pages = _build_hub_pages(cats, prefix, "📖 Aide — commandes principales")
        view = HubView(pages, ctx.author.id, cats, prefix)
        await ctx.send(embed=pages[0], view=view)

    async def _send_command_help(self, ctx: commands.Context, cmd: commands.Command, prefix: str):
        theme = _theme_for_command(cmd)
        emoji = THEME_EMOJI.get(theme, "📦")
        e = discord.Embed(title=f"{emoji} Aide — {cmd.qualified_name}", color=EMBED_COLOR)
        sig = f"`{prefix}{cmd.qualified_name}{(' ' + cmd.signature) if cmd.signature else ''}`"
        e.add_field(name="Utilisation", value=sig, inline=False)
        if cmd.help:
            e.add_field(name="Description", value=cmd.help, inline=False)
        if cmd.aliases:
            e.add_field(name="Alias", value=", ".join(f"`{a}`" for a in cmd.aliases), inline=False)
        # Sous-commandes
        if isinstance(cmd, commands.Group) and cmd.commands:
            subs = [c for c in cmd.commands if _visible(c)]
            if subs:
                lines = []
                for sc in subs[:12]:
                    s = f"`{prefix}{sc.qualified_name}{(' ' + sc.signature) if sc.signature else ''}`"
                    short = sc.brief or (sc.help.splitlines()[0] if sc.help else "")
                    lines.append(f"• {s} — {short or '—'}")
                extra = len(subs) - 12
                if extra > 0:
                    lines.append("… et d’autres")
                e.add_field(name="Sous-commandes", value="\n".join(lines), inline=False)
        e.set_footer(text=f"Thème : {theme}")
        await ctx.send(embed=e)

async def setup(bot: commands.Bot):
    await bot.add_cog(PrettyHelp(bot))
