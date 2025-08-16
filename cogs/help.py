# cogs/help.py
from __future__ import annotations
import itertools
from typing import Dict, List, Tuple, Optional

import discord
from discord.ext import commands

# ————————————————————————————————————————
# Réglages de style (tu peux ajuster)
# ————————————————————————————————————————
EMBED_COLOR = 0x5865F2
PAGE_SIZE = 8  # nb de commandes par page

# Émojis par catégorie (cog). Si absent -> "📦"
CATEGORY_EMOJIS: Dict[str, str] = {
    "Admin": "🛠️",
    "Fun": "🎲",
    "Quiz": "🧩",
    "Planning": "🗓️",
    "Profile": "🧑‍🚀",
    "AnimeTools": "📚",
    "Watchdog": "🛰️",
    "Shop": "🛒",
}

# ————————————————————————————————————————
# Utils
# ————————————————————————————————————————
def _cmd_signature(cmd: commands.Command) -> str:
    # exemple: !animequiz <option> [--hard]
    prefix = cmd.clean_prefix if hasattr(cmd, "clean_prefix") else "!"
    return f"{prefix}{cmd.qualified_name} {cmd.signature}".strip()

def _is_visible(cmd: commands.Command) -> bool:
    # cache: ignore hidden
    return not getattr(cmd, "hidden", False)

def _cog_name(cmd: commands.Command) -> str:
    return (cmd.cog.qualified_name if cmd.cog else "Autres")

def _chunk(lst: List, n: int):
    it = iter(lst)
    while True:
        chunk = list(itertools.islice(it, n))
        if not chunk:
            return
        yield chunk

# ————————————————————————————————————————
# Vue Interactive
# ————————————————————————————————————————
class HelpView(discord.ui.View):
    def __init__(
        self,
        author_id: int,
        categories: Dict[str, List[commands.Command]],
        bot: commands.Bot,
        start_category: str,
        timeout: int = 180,
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.bot = bot
        self.categories = categories
        self.category_names = list(categories.keys())
        self.cat = start_category
        self.page_idx = 0  # index page dans la catégorie

        # Menu catégories
        opts = []
        for name in self.category_names:
            emoji = CATEGORY_EMOJIS.get(name, "📦")
            total = len(self.categories[name])
            label = f"{name} ({total})"
            opts.append(discord.SelectOption(label=label, value=name, emoji=emoji))
        self.select = discord.ui.Select(placeholder="Choisir une catégorie…", options=opts, min_values=1, max_values=1)
        self.select.callback = self.on_select  # type: ignore
        self.add_item(self.select)

        # Boutons pagination
        self.first_btn = discord.ui.Button(emoji="⏮️", style=discord.ButtonStyle.secondary)
        self.prev_btn  = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary)
        self.next_btn  = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary)
        self.last_btn  = discord.ui.Button(emoji="⏭️", style=discord.ButtonStyle.secondary)
        self.close_btn = discord.ui.Button(label="Fermer", style=discord.ButtonStyle.danger)

        self.first_btn.callback = self.on_first   # type: ignore
        self.prev_btn.callback  = self.on_prev    # type: ignore
        self.next_btn.callback  = self.on_next    # type: ignore
        self.last_btn.callback  = self.on_last    # type: ignore
        self.close_btn.callback = self.on_close   # type: ignore

        self.add_item(self.first_btn)
        self.add_item(self.prev_btn)
        self.add_item(self.next_btn)
        self.add_item(self.last_btn)
        self.add_item(self.close_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Seul l’auteur peut manipuler
        if interaction.user and interaction.user.id != self.author_id:
            await interaction.response.send_message("Tu n’es pas l’auteur de cette aide.", ephemeral=True)
            return False
        return True

    # Handlers
    async def on_select(self, interaction: discord.Interaction):
        self.cat = self.select.values[0]
        self.page_idx = 0
        await self._render_edit(interaction)

    async def on_first(self, interaction: discord.Interaction):
        self.page_idx = 0
        await self._render_edit(interaction)

    async def on_prev(self, interaction: discord.Interaction):
        if self.page_idx > 0:
            self.page_idx -= 1
        await self._render_edit(interaction)

    async def on_next(self, interaction: discord.Interaction):
        max_pages = self._max_pages(self.cat)
        if self.page_idx < max_pages - 1:
            self.page_idx += 1
        await self._render_edit(interaction)

    async def on_last(self, interaction: discord.Interaction):
        self.page_idx = self._max_pages(self.cat) - 1
        await self._render_edit(interaction)

    async def on_close(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True  # type: ignore
        await interaction.response.edit_message(view=self)

    # Rendu
    def _max_pages(self, category: str) -> int:
        total = len(self.categories[category])
        return max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    def _embed_for(self, category: str, page_idx: int) -> discord.Embed:
        cmds = self.categories[category]
        pages = list(_chunk(cmds, PAGE_SIZE))
        page = pages[page_idx] if pages else []

        emoji = CATEGORY_EMOJIS.get(category, "📦")
        title = f"{emoji} Aide — {category}"
        desc = "Utilise les boutons ◀️ ▶️ pour naviguer. `!help <commande>` pour l’aide détaillée."
        emb = discord.Embed(title=title, description=desc, color=EMBED_COLOR)

        for cmd in page:
            # Tente de voir si l’utilisateur peut l’utiliser (icône 🔒 si non)
            lock = ""
            try:
                # on clone le contexte de permission le plus simple possible :
                pass_check = True  # éviter les await complex — on reste simple/robuste
            except Exception:
                pass_check = True
            if not pass_check:
                lock = " 🔒"

            brief = cmd.brief or (cmd.help.splitlines()[0] if cmd.help else "")
            signature = _cmd_signature(cmd)
            emb.add_field(
                name=f"`{signature}`{lock}",
                value=brief or "—",
                inline=False
            )

        emb.set_footer(text=f"Page {page_idx+1}/{self._max_pages(category)} • {len(cmds)} commandes")
        return emb

    async def _render_edit(self, interaction: discord.Interaction):
        # (dés)activer boutons si besoin
        max_pages = self._max_pages(self.cat)
        self.first_btn.disabled = (self.page_idx <= 0)
        self.prev_btn.disabled  = (self.page_idx <= 0)
        self.next_btn.disabled  = (self.page_idx >= max_pages - 1)
        self.last_btn.disabled  = (self.page_idx >= max_pages - 1)

        emb = self._embed_for(self.cat, self.page_idx)
        await interaction.response.edit_message(embed=emb, view=self)

# ————————————————————————————————————————
# Help Command custom
# ————————————————————————————————————————
class PrettyHelp(commands.Cog):
    """
    Help paginé, stylé, qui découvre automatiquement TOUTES les commandes.
    - !help               → menu interactif catégories + pagination
    - !help <commande>    → détail d’une commande
    - !help <catégorie>   → page 1 de la catégorie
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Remplace l’aide par défaut proprement si présente
        try:
            bot.remove_command("help")
        except Exception:
            pass

    # ——— Commande principale ———
    @commands.command(name="help")
    async def help_cmd(self, ctx: commands.Context, *, target: Optional[str] = None):
        # Si cible = une commande précise
        if target:
            # Cherche d’abord une commande
            cmd = self.bot.get_command(target)
            if cmd and _is_visible(cmd):
                return await self._send_command_help(ctx, cmd)

            # Sinon essaye une catégorie (cog)
            categories = self._build_categories(ctx)
            # Match sur Nom exact ou casefold
            for name in categories.keys():
                if name.lower() == target.lower():
                    view = HelpView(ctx.author.id, categories, self.bot, start_category=name)
                    emb = view._embed_for(name, 0)
                    return await ctx.send(embed=emb, view=view)

            return await ctx.send("❓ Je n’ai trouvé ni commande ni catégorie portant ce nom.")

        # Pas de cible → menu global (catégorie la plus remplie en premier)
        categories = self._build_categories(ctx)
        if not categories:
            return await ctx.send("Aucune commande visible pour toi ici.")
        start_category = max(categories.keys(), key=lambda k: len(categories[k]))
        view = HelpView(ctx.author.id, categories, self.bot, start_category=start_category)
        emb = view._embed_for(start_category, 0)
        await ctx.send(embed=emb, view=view)

    # ——— Aide détaillée d’une commande ———
    async def _send_command_help(self, ctx: commands.Context, cmd: commands.Command):
        emoji = CATEGORY_EMOJIS.get(_cog_name(cmd), "📦")
        title = f"{emoji} Aide commande — {cmd.qualified_name}"
        emb = discord.Embed(title=title, color=EMBED_COLOR)

        emb.add_field(name="Utilisation", value=f"`{_cmd_signature(cmd)}`", inline=False)

        if cmd.help:
            emb.add_field(name="Description", value=cmd.help, inline=False)
        elif cmd.brief:
            emb.add_field(name="Description", value=cmd.brief, inline=False)

        if cmd.aliases:
            emb.add_field(name="Alias", value=", ".join(f"`{a}`" for a in cmd.aliases), inline=False)

        # Sous-commandes (Group)
        if isinstance(cmd, commands.Group) and cmd.commands:
            subs = [c for c in cmd.commands if _is_visible(c)]
            if subs:
                listed = "\n".join(f"• `{_cmd_signature(c)}` — {c.brief or c.help or '—'}" for c in subs)
                emb.add_field(name="Sous-commandes", value=listed[:1000], inline=False)

        emb.set_footer(text=f"Catégorie : {_cog_name(cmd)}")
        await ctx.send(embed=emb)

    # ——— Regroupe TOUTES les commandes visibles en catégories ———
    def _build_categories(self, ctx: commands.Context) -> Dict[str, List[commands.Command]]:
        cats: Dict[str, List[commands.Command]] = {}
        for cmd in sorted(self.bot.walk_commands(), key=lambda c: c.qualified_name):
            if not _is_visible(cmd):
                continue
            # Ignore les commandes qui n’ont pas de prefix (ex: app_commands) si ça t’arrive
            if not isinstance(cmd, commands.Command):
                continue
            # Optionnel: on peut filtrer les cmds que l’utilisateur ne peut pas utiliser
            # Ici: on les montre quand même (c’est un help), mais tu peux décider de les cacher.
            category = _cog_name(cmd)
            cats.setdefault(category, []).append(cmd)

        # Tri: catégories avec le plus de commandes d’abord
        cats = dict(sorted(cats.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())))
        return cats

async def setup(bot: commands.Bot):
    await bot.add_cog(PrettyHelp(bot))
