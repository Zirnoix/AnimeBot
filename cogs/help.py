# cogs/help.py
from __future__ import annotations
import itertools
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands

EMBED_COLOR = 0x5865F2
MAX_FIELDS_PER_PAGE = 6         # Nb de sections (thèmes) par page
MAX_CMDS_PER_SECTION = 10       # Nb de commandes listées par section
INLINE_CMDS_PER_LINE = 3        # Commands par ligne dans une section

# Emojis de thèmes (ordre d’affichage)
THEME_ORDER = [
    "Essentiels",
    "Anime & Recherche",
    "Quiz & Mini-jeux",
    "Profil & Stats",
    "Planning & Tracking",
    "Fun & Outils",
    "Autres",
]
THEME_EMOJI = {
    "Essentiels": "✨",
    "Anime & Recherche": "📚",
    "Quiz & Mini-jeux": "🎮",
    "Profil & Stats": "🧑‍🚀",
    "Planning & Tracking": "🗓️",
    "Fun & Outils": "🧰",
    "Admin": "🛠️",
    "Autres": "📦",
}

# Heuristiques de classement par COG / nom de commande (souple)
COG_THEME_HINTS = {
    "Help": "Essentiels",
    "Core": "Essentiels",
    "Utility": "Essentiels",
    "Fun": "Fun & Outils",
    "AnimeTools": "Anime & Recherche",
    "Anime": "Anime & Recherche",
    "Search": "Anime & Recherche",
    "Quiz": "Quiz & Mini-jeux",
    "Games": "Quiz & Mini-jeux",
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
    "ban", "kick", "mute", "slowmode", "clear", "purge", "sync", "reload", "load", "unload",
    "owner", "admin", "config", "setchannel", "toggle", "clean", "health",
)

def _theme_for_command(cmd: commands.Command) -> str:
    cog_name = (cmd.cog.qualified_name if cmd.cog else "") or ""
    for key, theme in COG_THEME_HINTS.items():
        if key.lower() in cog_name.lower():
            return theme
    # Fallback par nom
    name = cmd.qualified_name.lower()
    if any(h in name for h in ("quiz", "guess", "battle", "speed", "vf", "vraifaux", "opening")):
        return "Quiz & Mini-jeux"
    if any(h in name for h in ("mycard", "rank", "stats", "xp", "level", "coins", "themes", "shop")):
        return "Profil & Stats"
    if any(h in name for h in ("next", "planning", "track", "monnext", "monplanning")):
        return "Planning & Tracking"
    if any(h in name for h in ("anime", "compare", "reco", "search", "personnage", "character")):
        return "Anime & Recherche"
    return "Autres"

def _is_admin_like(cmd: commands.Command) -> bool:
    # Heuristique prudente : cacher les trucs sensibles en public
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

def _cmd_sig(cmd: commands.Command, prefix: str) -> str:
    sig = f"{prefix}{cmd.qualified_name}"
    if cmd.signature:
        sig += f" {cmd.signature}"
    return f"`{sig}`"

def _chunk(lst, n):
    it = iter(lst)
    while True:
        block = list(itertools.islice(it, n))
        if not block:
            break
        yield block

def _group_commands(bot: commands.Bot, include_admin: bool, prefix: str) -> Dict[str, List[commands.Command]]:
    cats: Dict[str, List[commands.Command]] = {k: [] for k in THEME_ORDER}
    # Admin catégorie à part si on la veut
    if include_admin:
        cats["Admin"] = []

    for cmd in bot.walk_commands():
        if not isinstance(cmd, commands.Command):
            continue
        if not _visible(cmd):
            continue

        # Slash/app_commands ne sont pas listés ici (seulement prefix commands)
        # On garde simple : on les ignore si non Command
        if _is_admin_like(cmd):
            if include_admin:
                cats["Admin"].append(cmd)
            continue

        theme = _theme_for_command(cmd)
        if theme not in cats:
            cats["Autres"].append(cmd)
        else:
            cats[theme].append(cmd)

    # Tri alphabétique par thème
    for k in list(cats.keys()):
        cats[k] = sorted(cats[k], key=lambda c: c.qualified_name.lower())

    # Supprimer les thèmes vides
    cats = {k: v for k, v in cats.items() if v}

    # Reclasser selon THEME_ORDER + Admin à la fin si présent
    ordered = {}
    for k in THEME_ORDER:
        if k in cats:
            ordered[k] = cats[k]
    if include_admin and "Admin" in cats:
        ordered["Admin"] = cats["Admin"]
    # Ajouter tout thème inattendu restant
    for k, v in cats.items():
        if k not in ordered:
            ordered[k] = v
    return ordered

def _section_lines(cmds: List[commands.Command], prefix: str, limit: int) -> str:
    # Présentation compacte en lignes de commandes : `!cmd` `!cmd2` `!cmd3`
    parts = []
    for c in cmds[:limit]:
        parts.append(f"`{prefix}{c.qualified_name}`")
    # regrouper par lignes
    out_lines = []
    for row in _chunk(parts, INLINE_CMDS_PER_LINE):
        out_lines.append(" ".join(row))
    extra = len(cmds) - min(limit, len(cmds))
    if extra > 0:
        out_lines.append(f"… +{extra} autres")
    return "\n".join(out_lines) if out_lines else "—"

class SimplePager(discord.ui.View):
    def __init__(self, pages: List[discord.Embed], author_id: int, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.i = 0
        self.author_id = author_id

        self.prev_btn = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary)
        self.next_btn = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary)
        self.close_btn = discord.ui.Button(label="Fermer", style=discord.ButtonStyle.danger)

        self.prev_btn.callback = self.on_prev  # type: ignore
        self.next_btn.callback = self.on_next  # type: ignore
        self.close_btn.callback = self.on_close  # type: ignore

        self.add_item(self.prev_btn)
        self.add_item(self.next_btn)
        self.add_item(self.close_btn)
        self._refresh()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce panneau ne t’appartient pas.", ephemeral=True)
            return False
        return True

    def _refresh(self):
        self.prev_btn.disabled = (self.i == 0)
        self.next_btn.disabled = (self.i >= len(self.pages) - 1)

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

    async def on_close(self, it: discord.Interaction):
        for item in self.children:
            item.disabled = True  # type: ignore
        await it.response.edit_message(view=self)

class PrettyHelpCompact(commands.Cog):
    """
    Help compact & thématisé :
    - !help                  → pages publiques (sans Admin)
    - !help all              → tout (sauf Admin), pages
    - !help admin            → réservé owner/bot owner
    - !help <commande>       → aide détaillée
    - !help theme <nom>      → affiche uniquement un thème (si trop long)
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

        # Détail d’une commande directe
        if arg and not arg.lower().startswith("theme") and arg.lower() not in ("all","admin"):
            cmd = self.bot.get_command(arg)
            if cmd and _visible(cmd):
                return await self._send_command_help(ctx, cmd, prefix)
            # Peut-être un thème exact ?
            cats = _group_commands(self.bot, include_admin=False, prefix=prefix)
            for theme in cats.keys():
                if theme.lower() == arg.lower():
                    pages = self._build_pages(cats, prefix, only_theme=theme)
                    return await self._send_pages(ctx, pages)
            return await ctx.send("❓ Je n’ai trouvé ni commande ni thème portant ce nom.")

        # Mode thème ciblé
        if arg and arg.lower().startswith("theme"):
            parts = arg.split(maxsplit=1)
            if len(parts) == 1:
                return await ctx.send("Utilise : `!help theme <nom>` (ex: `!help theme Quiz & Mini-jeux`)")
            target_theme = parts[1].strip()
            cats = _group_commands(self.bot, include_admin=False, prefix=prefix)
            # match souple
            match = None
            for theme in cats.keys():
                if theme.lower() == target_theme.lower():
                    match = theme
                    break
            if not match:
                return await ctx.send("❓ Thème introuvable. Essaie: `Essentiels`, `Anime & Recherche`, `Quiz & Mini-jeux`, `Profil & Stats`, `Planning & Tracking`, `Fun & Outils`.")
            pages = self._build_pages(cats, prefix, only_theme=match)
            return await self._send_pages(ctx, pages)

        # Mode ALL (public, sans admin caché)
        if arg and arg.lower() == "all":
            cats = _group_commands(self.bot, include_admin=False, prefix=prefix)
            pages = self._build_pages(cats, prefix)
            return await self._send_pages(ctx, pages)

        # Mode ADMIN (owner seulement)
        if arg and arg.lower() == "admin":
            is_owner = False
            try:
                is_owner = await self.bot.is_owner(ctx.author)
            except Exception:
                pass
            if not is_owner and ctx.guild and ctx.guild.owner_id != ctx.author.id:
                return await ctx.send("🛡️ Cette section est réservée au propriétaire.")
            cats = _group_commands(self.bot, include_admin=True, prefix=prefix)
            # On ne garde **que** Admin
            cats = {"Admin": cats.get("Admin", [])}
            if not cats["Admin"]:
                return await ctx.send("Aucune commande admin détectée.")
            pages = self._build_pages(cats, prefix, title_override="🛠️ Aide — Admin")
            return await self._send_pages(ctx, pages)

        # Par défaut : affichage **compact** des thèmes publics, 1–3 pages max
        cats = _group_commands(self.bot, include_admin=False, prefix=prefix)
        pages = self._build_pages(cats, prefix)
        await self._send_pages(ctx, pages)

    # ---------- helpers ----------
    async def _send_pages(self, ctx: commands.Context, pages: List[discord.Embed]):
        if not pages:
            return await ctx.send("Aucune commande à afficher.")
        if len(pages) == 1:
            return await ctx.send(embed=pages[0])
        view = SimplePager(pages, author_id=ctx.author.id)
        await ctx.send(embed=pages[0], view=view)

    def _build_pages(
        self,
        cats: Dict[str, List[commands.Command]],
        prefix: str,
        only_theme: Optional[str] = None,
        title_override: Optional[str] = None,
    ) -> List[discord.Embed]:
        # Compose des sections (thèmes) en 1–3 pages max
        sections: List[Tuple[str, str]] = []  # (title, body)
        for theme in THEME_ORDER + [k for k in cats.keys() if k not in THEME_ORDER]:
            if theme not in cats: continue
            if only_theme and theme != only_theme: continue
            cmds = cats[theme]
            if not cmds: continue
            emoji = THEME_EMOJI.get(theme, "📦")
            title = f"{emoji} {theme} — {len(cmds)} cmd"
            body = _section_lines(cmds, prefix, MAX_CMDS_PER_SECTION)
            sections.append((title, body))

        # Construire les embeds, MAX_FIELDS_PER_PAGE sections par page
        pages: List[discord.Embed] = []
        title_global = title_override or "📖 Aide — commandes principales"
        for chunk in _chunk(sections, MAX_FIELDS_PER_PAGE):
            e = discord.Embed(title=title_global, description="Conseil : `!help <commande>` pour l’aide détaillée.", color=EMBED_COLOR)
            for (sec_title, body) in chunk:
                e.add_field(name=sec_title, value=body, inline=False)
            pages.append(e)

        # Footer de pagination
        for i, emb in enumerate(pages, start=1):
            emb.set_footer(text=f"Page {i}/{len(pages)} — {sum(len(v) for v in cats.values())} commandes")
        return pages

    async def _send_command_help(self, ctx: commands.Context, cmd: commands.Command, prefix: str):
        theme = _theme_for_command(cmd)
        emoji = THEME_EMOJI.get(theme, "📦")
        e = discord.Embed(title=f"{emoji} Aide — {cmd.qualified_name}", color=EMBED_COLOR)
        e.add_field(name="Utilisation", value=_cmd_sig(cmd, prefix), inline=False)
        if cmd.help:
            e.add_field(name="Description", value=cmd.help, inline=False)
        if cmd.aliases:
            e.add_field(name="Alias", value=", ".join(f"`{a}`" for a in cmd.aliases), inline=False)
        # Sous-commandes si Group
        if isinstance(cmd, commands.Group) and cmd.commands:
            subs = [c for c in cmd.commands if not getattr(c, "hidden", False)]
            if subs:
                lines = []
                for sc in subs[:10]:
                    lines.append(f"• `{prefix}{sc.qualified_name} {sc.signature}` — {sc.brief or (sc.help.splitlines()[0] if sc.help else '')}")
                extra = len(subs) - 10
                if extra > 0:
                    lines.append(f"… +{extra} sous-commandes")
                e.add_field(name="Sous-commandes", value="\n".join(lines), inline=False)
        e.set_footer(text=f"Thème : {theme}")
        await ctx.send(embed=e)

async def setup(bot: commands.Bot):
    await bot.add_cog(PrettyHelpCompact(bot))
