# cogs/profile.py — mycard en onglets + mybadges
from __future__ import annotations

import json
from typing import Dict, Any

import discord
from discord.ext import commands

from modules import core
from modules.badges import BADGES, evaluate_tier
from modules.badge_helpers import badge_count_for_spec
from modules.emoji_utils import get_emoji

# Couleurs cohérentes (proche blurple Discord + or trophées)
_EMBED_OVERVIEW = discord.Color.from_rgb(88, 101, 242)
_EMBED_MINIS = discord.Color.from_rgb(52, 58, 64)
_EMBED_BADGES = discord.Color.from_rgb(212, 168, 67)


# ---------- HELPERS BADGES ----------
def _get_user_counts(user_id: int) -> dict:
    """
    Agrège les compteurs utilisés par les badges :
    - mini-jeux: via core.get_mini_scores(user_id)
    - streak:    via data/streaks.json
    - anilist:   via compte AniList lié
    - time:      via data/time_counters.json (facultatif)
    """
    counts = core.get_mini_scores(user_id) or {}

    # --- STREAK ---
    try:
        with open("data/streaks.json", "r", encoding="utf-8") as f:
            streaks = json.load(f)
        entry = streaks.get(str(user_id), {})
        counts["streak_days"] = int(entry.get("streak", 0))
    except Exception:
        counts["streak_days"] = 0
    counts["streak_year"] = counts["streak_days"]  # pour 'streak:year'

    # --- ANILIST ---
    username = None
    try:
        username = core.get_linked_username(user_id)
    except Exception:
        username = None
    counts["anilist_linked"] = 1 if username else 0  # pour 'anilist:linked'

    if username:
        stats: Dict[str, Any] = {}
        for fn_name in ("get_anilist_stats", "fetch_anilist_stats"):
            fn = getattr(core, fn_name, None)
            if callable(fn):
                try:
                    stats = fn(username) or {}
                    break
                except Exception:
                    pass
        if not stats:
            try:
                query = """
                query($userName:String){
                  MediaListCollection(userName:$userName, type: ANIME){
                    lists { entries { status } }
                  }
                }
                """
                data = core.query_anilist(query, {"userName": username})
                lists = (data or {}).get("data", {}).get("MediaListCollection", {}).get("lists", []) or []
                total_entries = sum(len(l.get("entries", [])) for l in lists)
                completed = sum(
                    1 for l in lists for e in l.get("entries", []) if str(e.get("status","")).upper()=="COMPLETED"
                )
                watching = sum(
                    1 for l in lists for e in l.get("entries", []) if str(e.get("status","")).upper()=="CURRENT"
                )
                stats = {"total_entries": total_entries, "completed": completed, "current": watching}
            except Exception:
                stats = {}

        counts["anilist_completed"] = int(stats.get("completed", 0))
        counts["anilist_entries"]   = int(stats.get("total_entries", 0))
        counts["anilist_current"]   = int(stats.get("current", 0))

    # --- TIME WINDOWS (facultatif)
    try:
        with open("data/time_counters.json", "r", encoding="utf-8") as f:
            tdata = json.load(f)
        u = tdata.get(str(user_id), {})
        counts["time_morning"] = int(u.get("morning", 0))  # 6h-10h
        counts["time_night"]   = int(u.get("night", 0))    # 0h-4h
    except Exception:
        counts.setdefault("time_morning", 0)
        counts.setdefault("time_night", 0)

    return counts


# ---------- HELPERS D'AFFICHAGE ----------
def _xp_bar(xp: int, next_xp: int, seg: int = 20) -> str:
    if next_xp <= 0:
        return "⬛" * seg
    progress = max(0, min(seg, int((xp / next_xp) * seg)))
    return "🟦" * progress + "⬛" * (seg - progress)


def _pct_bar(cur: int, total: int, width: int = 14) -> str:
    """Barre texte compacte (cur/total)."""
    if total <= 0:
        return "░" * width
    p = max(0.0, min(1.0, cur / total))
    filled = int(round(p * width))
    return "█" * filled + "░" * (width - filled)


def _fmt_number(n: int) -> str:
    return f"{n:,}".replace(",", " ")


_MINI_LABELS: Dict[str, str] = {
    "mission_completed": "Missions du jour",
    "checkin": "Check-ins",
    "mycard_visits": "Carte (/mycard)",
    "animequiz": "Anime quiz (solo)",
    "animequizmulti": "Anime quiz (multi)",
    "higherlower": "Higher / Lower",
    "guessyear": "Guess — année",
    "guessepisodes": "Guess — épisodes",
    "guessgenre": "Guess — genre",
    "guesscharacter": "Guess — perso",
    "guesswho": "Qui est-ce ?",
    "chainquiz": "Chain quiz",
    "bingo": "Bingo anime",
    "bossraid": "Raid boss",
    "guessop": "Guess OP",
    "duel": "Duel lancés",
    "duel_victory": "Duels gagnés",
    "guesspop": "GuessPop",
    "guesspo": "GuessPo",
    "guessspo": "GuessSpo",
    "guessopener": "OP Challenger",
}


def _mini_label(key: str) -> str:
    return _MINI_LABELS.get(key, key.replace("_", " ").title())


def _mini_bar_line(val: int, max_val: int, width: int = 8) -> str:
    if max_val <= 0:
        return "░" * width
    p = max(0.0, min(1.0, val / max_val))
    filled = int(round(p * width))
    return "█" * filled + "░" * (width - filled)


def _mini_group_blocks(mini_scores: dict) -> list[tuple[str, str, list[tuple[str, int]]]]:
    """
    Regroupe les stats par famille (Quiz / Devinettes / Duels / Autres), tri par score décroissant.
    Retourne [(titre_emoji, titre_texte, [(label, count), ...]), ...]
    """
    if not mini_scores:
        return []

    groups: list[tuple[str, str, frozenset[str]]] = [
        ("📅", "Engagement", frozenset({"mission_completed", "checkin", "mycard_visits"})),
        ("🎯", "Quiz", frozenset({"animequiz", "animequizmulti"})),
        ("🎭", "Devinettes", frozenset({
            "guessyear", "guessepisodes", "guessgenre", "guesscharacter", "guesswho",
            "guessop",
            "guesspop", "guesspo", "guessspo", "guessopener",
        })),
        ("🐉", "Communauté", frozenset({"chainquiz", "bingo", "bossraid"})),
        ("⚔️", "Duels", frozenset({"duel", "duel_victory"})),
    ]
    used: set[str] = set()
    out: list[tuple[str, str, list[tuple[str, int]]]] = []

    for emoji, title, keys in groups:
        rows: list[tuple[str, int]] = []
        for k in keys:
            if k in mini_scores:
                v = int(mini_scores[k])
                if v:
                    rows.append((_mini_label(k), v))
                    used.add(k)
        rows.sort(key=lambda x: -x[1])
        if rows:
            out.append((emoji, title, rows))

    rest: list[tuple[str, int]] = []
    for k, v in mini_scores.items():
        if k in used:
            continue
        iv = int(v)
        if iv:
            rest.append((_mini_label(k), iv))
    rest.sort(key=lambda x: -x[1])
    if rest:
        out.append(("🎲", "Autres", rest))

    return out


def _format_mini_group(emoji: str, title: str, rows: list[tuple[str, int]]) -> str:
    if not rows:
        return ""
    max_v = max(c for _, c in rows) or 1
    lines_out: list[str] = []
    for label, val in rows[:12]:
        bar = _mini_bar_line(val, max_v)
        lines_out.append(f"`{bar}` · **{_fmt_number(val)}** — {label}")
    return f"**{emoji} {title}**\n" + "\n".join(lines_out)


def _badge_mycard_summary(bot, counts: dict) -> dict[str, Any]:
    """Résumé lisible pour l’onglet Trophées (pas la liste détaillée de /mybadges)."""
    unlocked_lines: list[str] = []
    next_rows: list[tuple[float, str, int, int]] = []  # ratio, name, count, need

    unlocked_n = 0
    visible_total = 0

    for _bid, spec in BADGES.items():
        count = badge_count_for_spec(spec, counts)

        thresholds = spec["thresholds"]
        icon_list = spec["icons"]
        tier, next_th = evaluate_tier(count, thresholds)
        hidden = spec.get("hidden", False)

        if hidden and (tier is None or tier < 0):
            continue

        if not hidden:
            visible_total += 1

        if tier is not None and tier >= 0:
            unlocked_n += 1
            icon = icon_list[tier] if tier < len(icon_list) else "🎖️"
            custom = spec.get("icons_custom")
            if custom and tier < len(custom):
                resolved = get_emoji(bot, custom[tier], fallback=None)
                if resolved:
                    icon = resolved
            paliers = len(thresholds)
            unlocked_lines.append(f"{icon} **{spec['name']}** · palier **{tier + 1}/{paliers}**")
        elif not hidden and thresholds:
            need = int(thresholds[0])
            ratio = (count / need) if need else 0.0
            next_rows.append((ratio, spec["name"], count, need))

    next_rows.sort(key=lambda x: -x[0])
    next_lines: list[str] = []
    for ratio, name, c, need in next_rows[:4]:
        pct = min(100, int(round(ratio * 100)))
        rest = max(0, need - c)
        next_lines.append(f"**{name}** — {c}/{need} ({pct}%) · reste **{rest}**")

    return {
        "unlocked_n": unlocked_n,
        "visible_total": visible_total,
        "unlocked_lines": unlocked_lines[:10],
        "unlocked_extra": max(0, len(unlocked_lines) - 10),
        "next_lines": next_lines,
    }


# ---------- VUE À ONGLETS (menu déroulant : pas de saut de boutons) ----------
class MyCardNavigator(discord.ui.View):
    """Menu déroulant : reste aligné ; l’onglet actif est coché dans la liste."""

    def __init__(self, ctx: commands.Context, author: discord.abc.User, data: dict, bot: commands.Bot, active: str = "overview"):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.author = author
        self.data = data
        self.bot = bot
        self.active = active
        self.add_item(MyCardTabSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Ce panneau n’est pas pour toi.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for c in self.children:
            if isinstance(c, (discord.ui.Button, discord.ui.Select)):
                c.disabled = True


class MyCardTabSelect(discord.ui.Select):
    def __init__(self, nav: MyCardNavigator):
        self.nav = nav
        act = nav.active
        opts = [
            discord.SelectOption(
                label="Aperçu",
                value="overview",
                emoji="📋",
                description="Niveau, XP, quiz, streak",
                default=(act == "overview"),
            ),
            discord.SelectOption(
                label="Mini-jeux",
                value="minis",
                emoji="🎮",
                description="Scores par catégorie",
                default=(act == "minis"),
            ),
            discord.SelectOption(
                label="Trophées",
                value="badges",
                emoji="🏅",
                description="Progression des trophées",
                default=(act == "badges"),
            ),
        ]
        ph = {
            "overview": "📋 Aperçu — carte",
            "minis": "🎮 Mini-jeux",
            "badges": "🏅 Trophées",
        }.get(act, "Choisir un onglet…")
        super().__init__(placeholder=ph, min_values=1, max_values=1, options=opts, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        tab = self.values[0]
        ctx = self.nav.ctx
        d = self.nav.data
        bot = self.nav.bot
        if tab == "overview":
            emb = _embed_overview(ctx, *d["overview"])
        elif tab == "minis":
            emb = _embed_minis(ctx, d["minis"])
        else:
            emb = _embed_badges(ctx, bot, d["counts"])
        nv = MyCardNavigator(ctx, self.nav.author, d, bot, active=tab)
        await interaction.response.edit_message(embed=emb, view=nv)


# ---------- BUILD DES EMBEDS ----------
def _embed_overview(ctx, level, xp, next_xp, title, quiz_score, streak_days):
    bar = _xp_bar(xp, next_xp)
    e = discord.Embed(
        title=f"🎴 Profil de {ctx.author.display_name}",
        color=_EMBED_OVERVIEW,
    )
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    # Trois colonnes : évite le débordement titre+niveau dans une seule ligne + quiz à côté de la barre
    e.add_field(name="🏅 Titre", value=f"**{title}**", inline=True)
    e.add_field(name="🧬 Niveau", value=f"**{level}**", inline=True)
    e.add_field(name="🧪 XP", value=f"{_fmt_number(xp)} / {_fmt_number(next_xp)}", inline=True)
    e.add_field(name="📈 Progression", value=bar, inline=False)
    e.add_field(name="🏆 Score Quiz", value=str(_fmt_number(quiz_score)), inline=False)

    # Streak
    next_pal = None
    for t in sorted(BADGES.get("serie", {}).get("thresholds", [])):
        if streak_days < t:
            next_pal = t
            break
    streak_line = f"🔥 Série actuelle : **{streak_days}** jour(s)"
    if next_pal:
        streak_line += f" • Prochain palier : **{streak_days}/{next_pal}**"
    e.add_field(name="🔥 Streak", value=streak_line, inline=False)
    gg_pen = core.get_guess_genre_penalty_count(ctx.author.id)
    e.add_field(
        name="⚠️ Sanctions Guess genre",
        value=str(gg_pen) if gg_pen else "0",
        inline=False,
    )
    e.set_footer(text="Onglet : menu ci-dessous")
    return e


def _embed_minis(ctx, mini_scores):
    e = discord.Embed(
        title="🎮 Mini-jeux",
        description=(
            "Barres **relatives** au meilleur score **dans chaque bloc** (pas des records globaux)."
        ),
        color=_EMBED_MINIS,
    )
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    blocks = _mini_group_blocks(mini_scores)
    if not blocks:
        e.add_field(name="Stats", value="— Aucune partie enregistrée pour l’instant.", inline=False)
        e.set_footer(text="Onglet : menu ci-dessous")
    else:
        total = sum(int(v) for v in mini_scores.values())
        for emoji, title, rows in blocks:
            block_txt = _format_mini_group(emoji, title, rows)
            if len(block_txt) < 1024:
                e.add_field(name="\u200b", value=block_txt, inline=False)
            else:
                # Discord embed field limit
                e.add_field(name="\u200b", value=block_txt[:1020] + "…", inline=False)
        e.set_footer(text=f"Total compté : {_fmt_number(total)} · Onglet : menu ci-dessous")
    return e


def _embed_badges(ctx, bot, counts):
    s = _badge_mycard_summary(bot, counts)
    vt = max(1, int(s["visible_total"] or 1))
    un = int(s["unlocked_n"] or 0)
    pct = min(100, int(round(100 * un / vt))) if s["visible_total"] else 0
    bar = _pct_bar(un, vt, 14)
    e = discord.Embed(
        title="🏅 Trophées",
        description=(
            f"{bar} **{pct}%** · **{un}** / **{s['visible_total']}** pistes avec au moins un palier\n"
            f"_Détail, paliers et secrets : **`/mybadges`**_"
        ),
        color=_EMBED_BADGES,
    )
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    if s["unlocked_lines"]:
        body = "\n".join(f"• {line}" for line in s["unlocked_lines"])
        if s["unlocked_extra"] > 0:
            body += f"\n_… **+{s['unlocked_extra']}** autre(s) dans `/mybadges`_"
        e.add_field(name="En poche", value=body[:1024], inline=False)
    else:
        e.add_field(
            name="En poche",
            value="— Aucun palier encore. Lance des mini-jeux ou entretiens ta série !",
            inline=False,
        )

    if s["next_lines"]:
        nxt = "\n".join(f"• {line}" for line in s["next_lines"])
        e.add_field(name="Les plus proches", value=nxt[:1024], inline=False)
    else:
        e.add_field(
            name="Les plus proches",
            value="— Rien en attente côté pistes visibles (ou déjà au max).",
            inline=False,
        )

    e.set_footer(text="Onglet : menu ci-dessous")
    return e


def _build_mybadges_payload(bot: commands.Bot, counts: dict) -> dict[str, Any]:
    """Données pour /mybadges : listes de lignes + résumé."""
    unlocked: list[str] = []
    locked: list[str] = []
    mystery: list[str] = []

    for _bid, spec in BADGES.items():
        count = badge_count_for_spec(spec, counts)
        thresholds = spec["thresholds"]
        icon_list = spec["icons"]
        tier, next_th = evaluate_tier(count, thresholds)

        if spec.get("hidden", False) and (tier is None or tier < 0):
            if thresholds:
                need = int(thresholds[0])
                rest = max(0, need - count)
                mystery.append(f"🔒 **???** — {count}/{need} · reste **{rest}**")
            continue

        if tier is not None and tier >= 0:
            icon = icon_list[tier] if tier < len(icon_list) else "🎖️"
            custom = spec.get("icons_custom")
            if custom and tier < len(custom):
                resolved = get_emoji(bot, custom[tier], fallback=None)
                if resolved:
                    icon = resolved
            paliers = len(thresholds)
            prog = f"{count}/{next_th}" if next_th else "MAX"
            unlocked.append(
                f"{icon} **{spec['name']}** · palier **{tier + 1}/{paliers}** ({prog})\n"
                f"_{spec['desc']}_"
            )
        elif thresholds:
            need = int(thresholds[0])
            rest = max(0, need - count)
            pct = min(100, int(round(100 * count / need))) if need else 0
            bar = _pct_bar(count, need, 10)
            locked.append(
                f"{bar} **{spec['name']}** — {count}/{need} ({pct}%) · reste **{rest}**\n"
                f"_{spec['desc']}_"
            )

    s = _badge_mycard_summary(bot, counts)
    return {
        "unlocked": unlocked,
        "locked": locked,
        "mystery": mystery,
        "summary": s,
    }


def _chunk_text_blocks(lines: list[str], max_len: int = 950) -> list[str]:
    """Découpe une liste de paragraphes en blocs < max_len caractères."""
    if not lines:
        return []
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for line in lines:
        add = len(line) + (1 if cur else 0)
        if cur_len + add > max_len and cur:
            chunks.append("\n".join(cur))
            cur = [line]
            cur_len = len(line)
        else:
            cur.append(line)
            cur_len += add
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def _embed_mybadges(ctx: commands.Context, bot: commands.Bot, payload: dict[str, Any], section: str) -> discord.Embed:
    """section: summary | unlocked | locked | mystery"""
    s = payload["summary"]
    vt = max(1, int(s["visible_total"] or 1))
    un = int(s["unlocked_n"] or 0)
    pct = min(100, int(round(100 * un / vt))) if s["visible_total"] else 0
    bar = _pct_bar(un, vt, 14)

    if section == "summary":
        e = discord.Embed(
            title=f"🏅 Trophées — {ctx.author.display_name}",
            description=(
                f"{bar} **{pct}%** · **{un}** pistes avec au moins un palier sur **{s['visible_total']}** visibles\n"
                f"_Utilise le menu pour le détail._"
            ),
            color=_EMBED_BADGES,
        )
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        if s["next_lines"]:
            e.add_field(
                name="Prochains paliers (les plus proches)",
                value="\n".join(f"• {x}" for x in s["next_lines"])[:1024],
                inline=False,
            )
        else:
            e.add_field(name="Prochains paliers", value="— Rien en attente.", inline=False)
        if s["unlocked_lines"]:
            snap = "\n".join(f"• {x}" for x in s["unlocked_lines"][:6])
            if s["unlocked_extra"] > 0:
                snap += f"\n_… **+{s['unlocked_extra']}** dans l’onglet « Débloqués »_"
            e.add_field(name="Aperçu des obtenus", value=snap[:1024], inline=False)
        e.set_footer(text="Menu : changer de section sans nouvelle commande")
        return e

    if section == "unlocked":
        lines = payload["unlocked"]
        chunks = _chunk_text_blocks(lines)
        e = discord.Embed(
            title=f"✅ Débloqués — {ctx.author.display_name}",
            description=f"**{len(lines)}** trophée(s) avec au moins un palier.",
            color=_EMBED_BADGES,
        )
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        if not chunks:
            e.add_field(name="—", value="Aucun pour l’instant.", inline=False)
        else:
            for i, ch in enumerate(chunks[:6]):
                name = "Liste" if i == 0 else f"Suite ({i + 1})"
                e.add_field(name=name, value=ch[:1024], inline=False)
            if len(chunks) > 6:
                e.add_field(name="…", value="Trop de texte — affichage tronqué.", inline=False)
        e.set_footer(text="Menu : section « Résumé » pour la vue d’ensemble")
        return e

    if section == "locked":
        lines = payload["locked"]
        chunks = _chunk_text_blocks(lines)
        e = discord.Embed(
            title=f"🎯 À débloquer — {ctx.author.display_name}",
            description=f"**{len(lines)}** piste(s) en cours.",
            color=_EMBED_BADGES,
        )
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        if not chunks:
            e.add_field(name="—", value="Rien à afficher (ou tout est déjà débloqué côté visible).", inline=False)
        else:
            for i, ch in enumerate(chunks[:6]):
                name = "Progression" if i == 0 else f"Suite ({i + 1})"
                e.add_field(name=name, value=ch[:1024], inline=False)
        e.set_footer(text="Les badges secrets apparaissent dans « Mystères » tant qu’ils sont cachés.")
        return e

    # mystery
    lines = payload["mystery"]
    e = discord.Embed(
        title=f"🔒 Badges secrets — {ctx.author.display_name}",
        description="Tant que le palier n’est pas atteint, le nom reste masqué.",
        color=discord.Color.dark_gray(),
    )
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    if not lines:
        e.add_field(name="—", value="Aucun secret en attente (ou déjà révélé).", inline=False)
    else:
        e.add_field(name="Indices", value="\n".join(lines)[:1024], inline=False)
    e.set_footer(text="Après déblocage, le trophée apparaît dans « Débloqués ».")
    return e


class MyBadgesNavigator(discord.ui.View):
    def __init__(self, ctx: commands.Context, author: discord.abc.User, bot: commands.Bot, payload: dict[str, Any], section: str = "summary"):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.author = author
        self.bot = bot
        self.payload = payload
        self.section = section
        self.add_item(MyBadgesSectionSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Ce panneau n’est pas pour toi.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for c in self.children:
            if isinstance(c, (discord.ui.Button, discord.ui.Select)):
                c.disabled = True


class MyBadgesSectionSelect(discord.ui.Select):
    def __init__(self, nav: MyBadgesNavigator):
        self.nav = nav
        sec = nav.section
        opts = [
            discord.SelectOption(
                label="Résumé",
                value="summary",
                emoji="📊",
                description="Vue d’ensemble et prochains paliers",
                default=(sec == "summary"),
            ),
            discord.SelectOption(
                label="Débloqués",
                value="unlocked",
                emoji="✅",
                description="Tous les trophées obtenus",
                default=(sec == "unlocked"),
            ),
            discord.SelectOption(
                label="À débloquer",
                value="locked",
                emoji="🎯",
                description="Pistes en cours avec barres",
                default=(sec == "locked"),
            ),
            discord.SelectOption(
                label="Mystères",
                value="mystery",
                emoji="🔒",
                description="Badges cachés non obtenus",
                default=(sec == "mystery"),
            ),
        ]
        ph = {
            "summary": "📊 Résumé",
            "unlocked": "✅ Débloqués",
            "locked": "🎯 À débloquer",
            "mystery": "🔒 Mystères",
        }.get(sec, "Choisir une section…")
        super().__init__(placeholder=ph, min_values=1, max_values=1, options=opts, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        sec = self.values[0]
        emb = _embed_mybadges(self.nav.ctx, self.nav.bot, self.nav.payload, sec)
        nv = MyBadgesNavigator(self.nav.ctx, self.nav.author, self.nav.bot, self.nav.payload, section=sec)
        await interaction.response.edit_message(embed=emb, view=nv)


# ---------- COG ----------
class Profile(commands.Cog):
    """Profil + stats + badges (onglets) + commande mybadges dédiée."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="mycard", description="Affiche ta carte de membre (onglets)")
    async def mycard(self, ctx: commands.Context) -> None:
        user_id = ctx.author.id
        user_id_str = str(user_id)

        try:
            core.add_mini_score(user_id, "mycard_visits", 1)
        except Exception:
            pass

        # Données globales
        levels = core.load_levels()
        user_data = levels.get(user_id_str, {"xp": 0, "level": 0})
        xp = int(user_data.get("xp", 0))
        level = int(user_data.get("level", 0))
        next_xp = core.xp_for_next_level(level)
        title = core.get_title_for_global_level(level)

        scores = core.load_scores()
        quiz_score = int(scores.get(user_id_str, 0))
        mini_scores = core.get_mini_scores(user_id) or {}

        counts = _get_user_counts(user_id)
        streak_days = int(counts.get("streak_days", 0))

        # Page 1 par défaut
        embed = _embed_overview(ctx, level, xp, next_xp, title, quiz_score, streak_days)
        view = MyCardNavigator(
            ctx,
            ctx.author,
            {
                "overview": (level, xp, next_xp, title, quiz_score, streak_days),
                "minis": mini_scores,
                "counts": counts,
            },
            self.bot,
            active="overview",
        )

        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="mybadges", description="Liste tes badges et ta progression")
    async def mybadges(self, ctx: commands.Context) -> None:
        user_id = ctx.author.id
        counts = _get_user_counts(user_id)
        payload = _build_mybadges_payload(self.bot, counts)
        embed = _embed_mybadges(ctx, self.bot, payload, "summary")
        view = MyBadgesNavigator(ctx, ctx.author, self.bot, payload, section="summary")
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
