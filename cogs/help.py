# cogs/help.py
from __future__ import annotations
from typing import Optional, Dict, List, Tuple
import inspect
import re

import discord
from discord.ext import commands
from discord import app_commands

PER_PAGE = 24
OWNER_HINTS = ("owner", "admin", "dev", "maintenance")
SUMMARY_MAX_CHARS = 140

# ===== Résumés 1-ligne par défaut (fallbacks FR) =====
DESC_OVERRIDE: Dict[str, str] = {
    # Episodes
    "next": "Prochain épisode — mode **serveur** = ta liste du serveur (`/airings`) ; mode **global** = toutes les sorties.",
    "planning": "Planning de la semaine — mode **serveur** = liste du serveur ; **global** = toutes les sorties.",
    "decouverte": "Découvre un anime (suggestion ou fiche).",
    "monnext": "Ton prochain épisode (compte AniList lié requis).",
    "monplanning": "Ton planning hebdomadaire (compte AniList lié).",

    # Minigames
    "animequiz": "Quiz anime (solo).",
    "animequizmulti": "Quiz anime multi-joueurs.",
    "duel": "Duel de quiz entre 2 joueurs.",
    "guess": "Alias historique : utilise **`/guessyear`**, **`/guessepisodes`**, **`/guessgenre`**, **`/guesscharacter`** ou **`/minijeux`**.",
    "guessop": "Devine l’opening (vocal) — catalogue global SQLite + récolte auto AnimeThemes.",
    "guessyear": "Devine l’année de diffusion (image + réponse dans le salon).",
    "guessepisodes": "Devine le nombre d’épisodes (image + réponse dans le salon).",
    "guessgenre": "Trouve un des genres (image + réponse texte).",
    "guesscharacter": "Choisis le bon personnage (4 boutons).",
    "guesswho": "Devine le personnage sur une image floutée — choix Facile / Normal / Difficile (flou + XP).",
    "chainquiz": "Enchaîne des quiz solo : la difficulté monte à chaque bonne réponse.",
    "raidconfig": "Groupe admin : salon, horaire hebdo, activer/désactiver le raid boss.",
    "raidconfig canal": "Définit le salon des alertes et du combat de raid boss.",
    "raidconfig horaire": "Jour (menu : lundi…dimanche) et heure du raid auto (fuseau BOT_TIMEZONE / Europe/Paris par défaut).",
    "raidconfig activer": "Oui/Non : lancer le raid automatiquement chaque semaine à l’horaire (sinon seulement /raidstart).",
    "raidconfig statut": "Affiche la configuration du raid et le prochain créneau.",
    "raidstart": "Lance un raid boss tout de suite dans ce salon (admin).",
    "raidalerttest": "Envoie un message de test type « raid dans 1 h » (admin).",
    "minijeux": "Deux menus : **Devinettes (Guess)** et **Autres** — choix = lance la partie (duel → /duel @membre).",
    "higherlower": "Jeu Higher/Lower version anime.",
    "year": "Guess : deviner l’année.",
    "character": "Guess : deviner le personnage.",
    "episodes": "Guess : deviner le nombre d’épisodes.",
    "genre": "Guess : deviner le genre.",
    "op": "Guess : deviner l’opening.",

    # Link / extra
    "linkanilist": "Étape 1 : lie ton AniList avec un code à mettre dans la bio, puis /verifyanilist.",
    "verifyanilist": "Étape 2 : confirme le lien après avoir collé le code dans « About » sur AniList.",
    "unlink": "Délie ton compte AniList.",
    "checkin": "Fais ton check-in quotidien (streak) et gagne de l’XP.",
    "streak": "Affiche ta série quotidienne (streak) et ton record.",
    "mission": "Ta mission du jour : récupère l’XP ou reroll (1/sem.).",

    # Stats
    "mycard": "Carte profil AniList (stats, badges, streak).",
    "mystats": "Stats AniList (vus, jours, score moyen, genre favori).",
    "mybadges": "Liste tes badges et ta progression.",
    "duelstats": "Duel d’engagement AniList : complétés, en cours, épisodes, temps (+ note si les deux notent).",
    "quiztop": "Top du classement quiz + podium du mois dernier et récompenses.",
    "animetop": "Classement mini-jeux : total, aperçu multi-jeux, ou un jeu précis (noms via Discord si hors serveur).",
    "quizlevels": "Paliers quiz (score du mois) et rangs XP : **un menu** pour choisir quoi afficher.",
    "myrank": "Ton rang, ton XP et ton titre.",
    "stats": "Stats AniList d’un utilisateur spécifié.",

    # Tracker
    "track": "Gestion de suivi (add/remove/list/clear).",
    "add": "Ajoute un anime au suivi.",
    "remove": "Retire un anime du suivi.",
    "list": "Liste les animes suivis.",
    "clear": "Efface le suivi.",

    # Utils
    "setchannel": "Salon des annonces « sortie d’épisode » pour ce serveur (même liste que /airings).",
    "botinfo": "Infos sur le bot (versions, créateur, etc.).",
    "ping": "Latence du bot.",
    "reminder": "Récap quotidien en MP (/reminder + /setalert), basé sur ton AniList si lié. Indépendant du récap « préférences ».",
    "setalert": "Régler l’heure du rappel quotidien (HH:MM).",
    "source": "Lien vers le dépôt GitHub du bot.",
    "uptime": "Depuis combien de temps le bot tourne.",

    # Admin / Owner (groupe airings)
    "airings": "Liste du serveur : choisir les animés suivis pour /next et /planning (admin).",
    "all": "Parcourir les sorties AniList et remplir la liste du serveur (admin).",
    "airings_list": "Afficher la liste du serveur (admin).",
    "airings_search": "Rechercher un anime sur AniList (admin).",
    "airings_add": "Ajouter un anime à la liste du serveur (admin).",
    "airings_remove": "Retirer un anime de la liste du serveur (admin).",
    "airings add": "Ajouter à la liste du serveur (admin).",
    "airings remove": "Retirer de la liste du serveur (admin).",
    "airings list": "Voir la liste du serveur (admin).",
    "airings clear": "Vider la liste du serveur (admin).",

    # Help
    "help": "Aide du bot. /help [commande] pour le détail.",

    # Owner — /admin (bot.py)
    "admin": "Owner uniquement : debug slash, sync globale, cogs, test d’alerte, salon /setchannel.",
    "admin debug_tree": "Liste les commandes slash du tree local.",
    "admin debug_pub": "Compare commandes publiées GLOBAL vs GUILD.",
    "admin publish_global": "Sync globale (rarement ; risque 429).",
    "admin cogs": "Liste des extensions chargées.",
    "admin test_alert": "Envoie une carte d’alerte test dans le salon courant.",
    "admin show_channel": "Affiche le salon enregistré pour les alertes (/setchannel).",
    "admin recap_mensuel": "(Owner) Récap stats internes : usages slash, pics serveurs/membres, mois courant et précédent.",
}

# ===== Sections curatées (ordre d’affichage) =====
CURATED_SECTIONS: List[Tuple[str, List[str]]] = [
    ("📺 Pages Episodes", [
        "next", "planning", "decouverte", "monnext", "monplanning"
    ]),
    ("🎯 Pages MiniGames", [
        "animequiz", "animequizmulti", "duel",
        "guessyear", "guessepisodes", "guessgenre", "guesscharacter",
        "guesswho", "chainquiz",
        "guessop",
        "higherlower", "minijeux",
        "raidconfig", "raidconfig canal", "raidconfig horaire", "raidconfig activer", "raidconfig statut",
        "raidstart", "raidalerttest",
    ]),
    ("🔗 Pages Link", [
        "linkanilist", "verifyanilist", "unlink"
    ]),
    ("📊 Pages Statistiques", [
        "mycard", "mystats", "mybadges", "duelstats", "quiztop", "animetop", "quizlevels", "myrank", "stats"
    ]),
    ("🧭 Pages Tracker", [
        "track", "track add", "track list", "track remove", "track clear"
    ]),
    ("🧰 Pages Utils", [
        "setchannel", "botinfo", "ping", "reminder", "setalert", "source", "uptime"
    ]),
]

# ===== Utils =====
def _is_ownerish_name(name: str) -> bool:
    low = (name or "").lower()
    return any(h in low for h in OWNER_HINTS)

def _compact_one_line(text: str, *, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    if not text:
        return "—"
    t = str(text)
    markers = [
        "\nArgs:", "\nArguments:", "\nParameters:", "\nParamètres:",
        "\nReturns:", "\nReturn:", "\nNote:", "\nNotes:", "\nRemarques:",
        "\nExample:", "\nExamples:", "\nExemple:", "\nExemples:",
        "\nUsage:", "\nUsages:"
    ]
    cut = len(t)
    for m in markers:
        i = t.find(m)
        if i != -1:
            cut = min(cut, i)
    t = t[:cut]
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = t.replace("•", "-").replace("—", "-")
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    t = lines[0] if lines else ""
    if len(t) > max_chars:
        for sep in [". ", "! ", "? "]:
            j = t.find(sep)
            if 0 < j <= max_chars:
                t = t[:j+1]; break
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_chars:
        t = t[:max_chars-1].rstrip() + "…"
    return t or "—"

def _split_fields(fields: List[Tuple[str, str]], per_page: int = PER_PAGE) -> List[List[Tuple[str,str]]]:
    chunks, cur = [], []
    for f in fields:
        cur.append(f)
        if len(cur) >= per_page:
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    return chunks

def _normalize_query(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lstrip("/!").lower())

# ===== inventaire SLASH =====
def _all_slash_commands(bot: commands.Bot) -> Dict[str, app_commands.Command]:
    out: Dict[str, app_commands.Command] = {}
    try:
        for c in bot.tree.get_commands():  # type: ignore[attr-defined]
            if isinstance(c, app_commands.Command):
                out[c.name.lower()] = c
            elif isinstance(c, app_commands.Group):
                # indexer /groupe et /groupe sous
                out[c.name.lower()] = c  # utile pour la fiche /airings
                for sc in c.commands:
                    out[f"{c.name.lower()} {sc.name.lower()}"] = sc
    except Exception:
        pass
    return out

# ===== Autocomplete /help <commande> : SLASH ONLY =====
async def _ac_help_command(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    bot = interaction.client  # type: ignore
    cur = _normalize_query(current)

    pool: List[Tuple[str, str]] = []
    try:
        for full in _all_slash_commands(bot).keys():
            pool.append((f"/{full}", full))
    except Exception:
        pass

    seen: set[str] = set()
    out: List[app_commands.Choice[str]] = []

    def match(v: str) -> bool:
        if not cur:
            return True
        v = v.lower()
        return v.startswith(cur) or cur in v

    for disp, value in pool:
        key = _normalize_query(value)
        if key in seen:
            continue
        if match(key):
            out.append(app_commands.Choice(name=disp[:100], value=value))
            seen.add(key)
        if len(out) >= 20:
            break

    if not out:
        for disp, value in pool[:10]:
            key = _normalize_query(value)
            if key in seen:
                continue
            out.append(app_commands.Choice(name=disp[:100], value=value))
            if len(out) >= 10:
                break
    return out

# ===== Vues (navigation) =====
class HelpNavigator(discord.ui.View):
    def __init__(self, pages: List[discord.Embed], labels: List[str], *, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.labels = labels
        self.index = 0
        options = [discord.SelectOption(label=lbl, value=str(i)) for i, lbl in enumerate(self.labels[:25])]
        self.jump_select.options = options
        if len(self.pages) <= 1:
            self.prev_button.disabled = True
            self.next_button.disabled = True
            self.jump_select.disabled = True

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self._with_footer(self.pages[self.index]), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self._with_footer(self.pages[self.index]), view=self)

    @discord.ui.select(placeholder="Aller à…")
    async def jump_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        try:
            self.index = int(select.values[0])
        except Exception:
            self.index = 0
        await interaction.response.edit_message(embed=self._with_footer(self.pages[self.index]), view=self)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

    def _with_footer(self, em: discord.Embed) -> discord.Embed:
        em = em.copy()
        em.set_footer(text=f"Page {self.index+1}/{len(self.pages)} — /help <commande> pour le détail.")
        return em

class CoreHelpView(discord.ui.View):
    def __init__(self, build_curated_pages_cb, *, ephemeral: bool):
        super().__init__(timeout=180.0)
        self.build_curated_pages_cb = build_curated_pages_cb
        self.ephemeral = ephemeral

    @discord.ui.button(label="Voir tout (MP)", style=discord.ButtonStyle.primary)
    async def show_all_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            pages, labels = self.build_curated_pages_cb()
            nav = HelpNavigator(pages, labels)
            first = nav._with_footer(pages[0])
            await interaction.user.send(embed=first, view=nav)
            await interaction.followup.send("📬 Aide complète envoyée en message privé.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Impossible d’envoyer un MP (vérifie tes paramètres).", ephemeral=True)
        except Exception:
            await interaction.followup.send("❌ MP non envoyé (erreur inconnue).", ephemeral=True)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

# ===== Cog =====
class Help(commands.Cog):
    """Aide du bot : /help (Essentiel + MP curaté), /help <commande>, /helpowner (owner/admin)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- pages curatées (ordre défini par CURATED_SECTIONS)
    def _build_curated_pages(self) -> Tuple[List[discord.Embed], List[str]]:
        slash_map = _all_slash_commands(self.bot)
        pages: List[discord.Embed] = []
        labels: List[str] = []

        def has_slash(key: str) -> bool:
            k = key.lower()
            return k in slash_map

        for section_title, keys in CURATED_SECTIONS:
            fields: List[Tuple[str, str]] = []

            # Dans la section Tracker on choisit d’afficher explicitement les sous-commandes
            show_children_individually = ("Tracker" in section_title)

            for raw in keys:
                disp = f"/{raw}"
                leaf = raw.split()[-1].lower()

                # cas d’une sous-commande explicite (ex: "track add")
                if " " in raw:
                    if show_children_individually:
                        desc = _compact_one_line(DESC_OVERRIDE.get(raw.lower(), DESC_OVERRIDE.get(leaf, "—")))
                        if has_slash(raw):
                            fields.append((disp, desc))
                        else:
                            fields.append((disp, f"{desc}  *(non dispo en slash)*"))
                    continue

                # parent (ex: "track", "guess", "airings" si on l’ajoute plus tard aux sections publiques)
                desc_parent = _compact_one_line(DESC_OVERRIDE.get(raw.lower(), DESC_OVERRIDE.get(leaf, "—")))
                if show_children_individually:
                    if has_slash(raw):
                        fields.append((disp, desc_parent))
                    else:
                        fields.append((disp, f"{desc_parent}  *(non dispo en slash)*"))
                else:
                    # agrège ses enfants listés dans cette section
                    children = [k for k in keys if k.startswith(raw + " ")]
                    subs = [c.split()[-1] for c in children if has_slash(c)]
                    if has_slash(raw):
                        if subs:
                            fields.append((disp, _compact_one_line(f"{desc_parent} · Sous-commandes: {', '.join(subs)}")))
                        else:
                            fields.append((disp, desc_parent))
                    else:
                        fields.append((disp, f"{desc_parent}  *(non dispo en slash)*"))

            if not fields:
                continue
            chunks = _split_fields(fields)
            for idx, chunk in enumerate(chunks):
                em = discord.Embed(
                    title=section_title,
                    description="Tape `/help <commande>` pour une fiche détaillée.",
                    color=discord.Color.blurple() if "Pages" in section_title else discord.Color.purple()
                )
                for n, v in chunk:
                    em.add_field(name=n, value=v, inline=False)
                pages.append(em)
                labels.append(section_title if len(chunks) == 1 else f"{section_title} ({idx+1}/{len(chunks)})")

        if not pages:
            pages = [discord.Embed(title="Aide", description="Aucune commande slash détectée.", color=discord.Color.red())]
        return pages, [p.title or "Aide" for p in pages]

    # --- pages owner/admin (slash only)
    def _build_owner_pages(self) -> Tuple[List[discord.Embed], List[str]]:
        def _is_ownerish_appcmd(full_name: str, sc: app_commands.Command) -> bool:
            # 1) tag explicite
            if getattr(sc, "extras", {}).get("owner_only"):
                return True
            # 2) heuristique nom
            if _is_ownerish_name(full_name):
                return True
            # 3) checks (owner / admin / has_permissions)
            for check in (getattr(sc, "checks", []) or []):
                meta = (getattr(check, "__name__", "") + " " + getattr(check, "__qualname__", "")).lower()
                if "owner" in meta or "is_owner" in meta:
                    return True
                if "administrator" in meta or "has_permissions" in meta or "manage_guild" in meta:
                    return True
                try:
                    src = inspect.getsource(check).lower()
                    if "owner" in src or "is_owner" in src:
                        return True
                    if "administrator" in src or "has_permissions" in src or "manage_guild" in src:
                        return True
                except Exception:
                    pass
            return False

        slash_map = _all_slash_commands(self.bot)
        owner_slash = [(full, sc) for full, sc in slash_map.items() if _is_ownerish_appcmd(full, sc)]
        owner_slash.sort(key=lambda x: x[0])

        if not owner_slash:
            return [discord.Embed(title="🔐 Aide — Owner/Admin", description="Aucune commande restreinte détectée.", color=discord.Color.red())], ["Owner"]

        fields = []
        for full, sc in owner_slash:
            desc = (sc.description or "").strip() or DESC_OVERRIDE.get(full.lower(), DESC_OVERRIDE.get(sc.name.lower(), "—"))
            fields.append((f"/{full}", _compact_one_line(desc)))

        pages: List[discord.Embed] = []
        labels: List[str] = []
        split = _split_fields(fields)
        for idx, chunk in enumerate(split):
            em = discord.Embed(
                title="🔐 Aide — Owner/Admin",
                description="Commandes réservées au propriétaire du bot ou aux administrateurs (slash).",
                color=discord.Color.dark_gold()
            )
            for n, v in chunk:
                em.add_field(name=n, value=v, inline=False)
            pages.append(em)
            labels.append("Owner" if len(split) == 1 else f"Owner ({idx+1}/{len(split)})")
        return pages, labels

    async def _send_embed_ctx_or_itx(self, ctx_or_itx, *, embed: discord.Embed = None, view: discord.ui.View = None, content: str = None, ephemeral: bool = False):
        if hasattr(ctx_or_itx, "response"):
            await ctx_or_itx.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)
        else:
            await ctx_or_itx.send(content=content, embed=embed, view=view)

    # --- Détail /help <commande> (privilégie slash)
    async def _send_command_help(self, ctx_or_itx, raw_name: str, ephemeral: bool):
        q = _normalize_query(raw_name)
        if not q:
            return await self._send_embed_ctx_or_itx(ctx_or_itx, content="Commande inconnue.", ephemeral=ephemeral)

        slash_map = _all_slash_commands(self.bot)

        # 1) correspondance exacte
        sc = slash_map.get(q)
        # 2) heuristique (startswith / suffix token)
        if not sc:
            for full, cmd in slash_map.items():
                if full == q or full.startswith(q) or full.endswith(" " + q):
                    sc = cmd
                    q = full
                    break

        if sc:
            shown = f"/{q}"
            desc = (sc.description or "").strip() or DESC_OVERRIDE.get(q, DESC_OVERRIDE.get(sc.name.lower(), "—"))
            em = discord.Embed(title=f"🛈 Aide — {shown}", description=desc, color=discord.Color.blurple())
            try:
                params = getattr(sc, "parameters", None)
                if params:
                    lines = []
                    for p in params:
                        opt = f"[{p.display_name}]" if p.required is False else f"<{p.display_name}>"
                        typ = getattr(p, 'type', None)
                        typname = getattr(typ, 'name', None) or str(typ)
                        lines.append(f"• {opt} — {p.description or typname}")
                    if lines:
                        em.add_field(name="Paramètres", value="\n".join(lines)[:1024], inline=False)
                ex = shown
                if params:
                    ex += " " + " ".join(f"<{p.display_name}>" if p.required else f"[{p.display_name}]" for p in params)
                em.add_field(name="Exemple", value=f"`{ex}`", inline=False)
            except Exception:
                pass
            return await self._send_embed_ctx_or_itx(ctx_or_itx, embed=em, ephemeral=ephemeral)

        # Pas de slash correspondant
        return await self._send_embed_ctx_or_itx(
            ctx_or_itx,
            content="❌ Commande slash introuvable. Vérifie l’orthographe ou tape `/help` pour la liste. "
                    "Tu peux aussi utiliser le préfixe **!** si la commande existe en hybrid.",
            ephemeral=ephemeral
        )

    # --- Commandes publiques d’aide
    @commands.hybrid_command(name="help", description="Aide Essentiel. /help [commande] pour le détail.")
    @app_commands.describe(commande="Nom d'une commande slash pour l'aide détaillée (auto-complétion).")
    @app_commands.autocomplete(commande=_ac_help_command)
    async def help(self, ctx: commands.Context, commande: Optional[str] = None):
        is_slash = bool(getattr(ctx, "interaction", None))
        target = ctx.interaction if is_slash else ctx
        # En MP, l’éphémère slash peut provoquer une erreur API ; on le réserve aux salons.
        ephemeral_ok = is_slash and ctx.guild is not None

        if commande:
            await self._send_command_help(target, commande, ephemeral=ephemeral_ok)
            return

        em = discord.Embed(
            title="📖 Aide — Essentiel",
            description=(
                "Commandes principales.\n"
                "• **Slash** `/…` recommandé ; **`!`** marche aussi sur les commandes hybrid.\n"
                "• `/help <commande>` : détail · bouton **Voir tout** : liste complète en MP (depuis un serveur)."
            ),
            color=discord.Color.blurple()
        )
        picks = [
            ("/minijeux", DESC_OVERRIDE["minijeux"]),
            ("/next", DESC_OVERRIDE["next"]),
            ("/planning", DESC_OVERRIDE["planning"]),
            ("/mystats", DESC_OVERRIDE["mystats"]),
            ("/linkanilist", DESC_OVERRIDE["linkanilist"]),
            ("/reminder", DESC_OVERRIDE["reminder"]),
            ("/setalert", DESC_OVERRIDE["setalert"]),
            ("/botinfo", DESC_OVERRIDE["botinfo"]),
        ]
        for name, desc in picks:
            em.add_field(name=name, value=_compact_one_line(desc), inline=False)
        em.set_footer(text="/help <commande> · slash ou ! sur les hybrid")

        # En MP avec préfixe, les vues (boutons) ont parfois un comportement capricieux selon le client.
        if ctx.guild is None and not is_slash:
            em.add_field(
                name="ℹ️ MP",
                value="Pour le bouton **Voir tout**, utilise `/help` dans un serveur.",
                inline=False,
            )
            await ctx.send(embed=em)
            return

        view = CoreHelpView(self._build_curated_pages, ephemeral=ephemeral_ok)
        await self._send_embed_ctx_or_itx(target, embed=em, view=view, ephemeral=ephemeral_ok)

    @commands.hybrid_command(name="helpowner", description="(Owner/Admin) Aide restreinte en MP (commandes limitées).")
    @commands.is_owner()
    async def help_owner(self, ctx: commands.Context):
        try:
            if getattr(ctx, "interaction", None):
                await ctx.interaction.response.defer(ephemeral=True)
            pages, labels = self._build_owner_pages()
            nav = HelpNavigator(pages, labels)
            first = nav._with_footer(pages[0])
            await ctx.author.send(embed=first, view=nav)
            if getattr(ctx, "interaction", None):
                await ctx.interaction.followup.send("📬 Aide owner/admin envoyée en MP.", ephemeral=True)
            else:
                await ctx.send("📬 Aide owner/admin envoyée en MP.")
        except discord.Forbidden:
            if getattr(ctx, "interaction", None):
                await ctx.interaction.followup.send("❌ Impossible d’envoyer un MP (paramètres).", ephemeral=True)
            else:
                await ctx.send("❌ Impossible d’envoyer un MP (paramètres).")
        except Exception:
            if getattr(ctx, "interaction", None):
                await ctx.interaction.followup.send("❌ Erreur inconnue à l’envoi du MP.", ephemeral=True)
            else:
                await ctx.send("❌ Erreur inconnue à l’envoi du MP.")

async def setup(bot: commands.Bot):
    # retirer toute ancienne commande textuelle `help` si présente
    try:
        bot.remove_command("help")
    except Exception:
        pass
    try:
        bot.tree.remove_command("help")
    except Exception:
        pass

    await bot.add_cog(Help(bot))
    # Optionnel : forcer la synchro des slash ici
    # try:
    #     await bot.tree.sync()
    # except Exception:
    #     pass
