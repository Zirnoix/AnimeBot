# cogs/profile.py — /mycard (carte), /profile (détail), /mybadges (trophées)
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Iterable, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from modules import core
from modules import bug_report as bug_report_store
from modules.image import generate_mycard_image
from modules.badges import BADGES, BADGE_SECTION_TITLE_FR, evaluate_tier, iter_badges_sorted, tier_name_fr
from modules.badge_helpers import badge_count_for_spec
from modules.emoji_utils import get_emoji

# Couleurs cohérentes (proche blurple Discord + or trophées)
_EMBED_OVERVIEW = discord.Color.from_rgb(88, 101, 242)
_EMBED_MINIS = discord.Color.from_rgb(52, 58, 64)
_EMBED_BADGES = discord.Color.from_rgb(155, 89, 182)

_ANILIST_ANIME_URL_RE = re.compile(r"https?://(www\.)?anilist\.co/anime/(\d+)", re.I)
_ANIME_FAV_CLEAR_WORDS = frozenset(
    {"clear", "none", "retirer", "enlever", "supprimer", "-", "reset", "effacer"}
)


def _title_from_anilist_hit(m: dict) -> str:
    t = m.get("title") or {}
    return t.get("english") or t.get("romaji") or t.get("native") or str(m.get("id") or "")


def _payload_from_search_hit(hit: dict) -> dict:
    mid = int(hit["id"])
    return {
        "media_id": mid,
        "title": _title_from_anilist_hit(hit),
        "site_url": hit.get("siteUrl") or f"https://anilist.co/anime/{mid}",
    }


def _resolve_anime_favorite_input(raw: str) -> Tuple[str, Any]:
    """
    Retourne (kind, data) :
    - ("help", None) entrée vide
    - ("clear", None) retirer le favori
    - ("set", dict) enregistrer
    - ("error", str) message d’erreur
    """
    s = (raw or "").strip()
    if not s:
        return ("help", None)
    low = s.lower()
    if low in _ANIME_FAV_CLEAR_WORDS:
        return ("clear", None)

    m = _ANILIST_ANIME_URL_RE.search(s)
    if m:
        mid = int(m.group(2))
        info = core.get_anime_media_basic(mid)
        if not info:
            return ("error", f"Aucun anime trouvé pour l’ID **`{mid}`** (vérifie que c’est bien une fiche **anime** sur AniList).")
        return ("set", info)

    if s.isdigit():
        mid = int(s)
        info = core.get_anime_media_basic(mid)
        if not info:
            return ("error", f"Aucun anime trouvé pour l’ID **`{mid}`**.")
        return ("set", info)

    hits = core.search_media(s, limit=8)
    if not hits:
        return ("error", f"Aucun résultat pour **{s[:100]}**. Essaie un autre titre ou colle l’URL AniList.")
    return ("set", _payload_from_search_hit(hits[0]))


# Ordre d’affichage pour /animetop aperçu (clé mini_scores.json → libellé)
_ANITOP_GAME_LABELS: list[tuple[str, str]] = [
    ("animequiz", "Anime quiz"),
    ("guessyear", "Guess année"),
    ("guessepisodes", "Guess épisodes"),
    ("guesscharacter", "Guess personnage"),
    ("guesswho", "Guess who"),
    ("guessgenre", "Guess genre"),
    ("higherlower", "Higher / Lower"),
    ("chainquiz", "Chain quiz"),
    ("bossraid", "Boss raid (dégâts)"),
    ("duel", "Duel"),
    ("guessop", "Guess OP"),
    ("guessopchain_streak", "Guess OP chaîne (série max)"),
    ("mission_hardcore", "Missions Hardcore"),
]


async def _animetop_names_map(
    bot: commands.Bot,
    guild: Optional[discord.Guild],
    uids: Iterable[int],
) -> dict[int, str]:
    """Pseudo affiché : membre du serveur si présent, sinon nom Discord global (fetch_user)."""
    uniq = {int(u) for u in uids}
    out: dict[int, str] = {}

    async def one(uid: int) -> None:
        if guild:
            m = guild.get_member(uid)
            if m:
                out[uid] = m.display_name
                return
        try:
            u = await bot.fetch_user(uid)
            out[uid] = ((u.global_name or u.name or "")).strip() or str(uid)
        except discord.NotFound:
            out[uid] = f"Compte supprimé ({uid})"
        except Exception:
            out[uid] = f"Utilisateur {uid}"

    await asyncio.gather(*(one(u) for u in uniq))
    return out


def _animetop_valid_mode(mode: str) -> str:
    m = (mode or "all").strip().lower()
    if m in {"all", "overview"}:
        return m
    if any(m == k for k, _ in _ANITOP_GAME_LABELS):
        return m
    return "all"


def _animetop_mode_label(mode: str) -> str:
    m = _animetop_valid_mode(mode)
    if m == "all":
        return "Total — tous mini-jeux"
    if m == "overview":
        return "Aperçu multi-jeux"
    return dict(_ANITOP_GAME_LABELS).get(m, m)


def _animetop_embed_color(mode: str) -> discord.Color:
    m = _animetop_valid_mode(mode)
    if m == "all":
        return _EMBED_OVERVIEW
    if m == "overview":
        return discord.Color.from_rgb(114, 137, 218)
    h = sum((i + 1) * ord(c) for i, c in enumerate(m))
    return discord.Color.from_rgb(62 + (h % 70), 108 + ((h // 3) % 90), 168 + ((h // 7) % 70))


def _animetop_trunc_display(s: str, max_len: int = 20) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _animetop_medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"`#{rank}`")


def _animetop_select_placeholder(mode: str) -> str:
    """Indique clairement la vue active (max 150 car. pour le Select Discord)."""
    s = f"Vue : {_animetop_mode_label(mode)}"
    return s if len(s) <= 150 else s[:147] + "…"


def _animetop_short_blurb(mode: str) -> str:
    m = _animetop_valid_mode(mode)
    if m == "all":
        return "Somme des compteurs de **tous** les mini-jeux."
    return f"Compteur **{_animetop_mode_label(m)}** dans les stats du bot."


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
        fn = getattr(core, "fetch_anilist_list_stats", None)
        if callable(fn):
            try:
                stats = fn(username) or {}
            except Exception:
                stats = {}
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
                    1 for l in lists for e in l.get("entries", []) if str(e.get("status", "")).upper() == "COMPLETED"
                )
                watching = sum(
                    1 for l in lists for e in l.get("entries", []) if str(e.get("status", "")).upper() == "CURRENT"
                )
                stats = {"total_entries": total_entries, "completed": completed, "current": watching}
            except Exception:
                stats = {}

        counts["anilist_completed"] = int(stats.get("completed", 0))
        counts["anilist_entries"] = int(stats.get("total_entries", 0))
        counts["anilist_current"] = int(stats.get("current", 0))

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


def _append_badge_section_header(lines: list[str], state: list[str | None], category: str) -> None:
    """Insère un titre de section (catégorie) avant la prochaine ligne, si besoin."""
    if category != state[0]:
        title = BADGE_SECTION_TITLE_FR.get(category, BADGE_SECTION_TITLE_FR["autre"])
        if lines:
            lines.append("")
        lines.append(f"**— {title} —**")
        state[0] = category


def _pct_bar(cur: int, total: int, width: int = 14) -> str:
    """Barre texte compacte (cur/total)."""
    if total <= 0:
        return "░" * width
    p = max(0.0, min(1.0, cur / total))
    filled = int(round(p * width))
    return "█" * filled + "░" * (width - filled)


# Barre embed : uniquement 🟪 (violet) → 🟦 (bleu), comme les bords de la bande /mycard.
# Le « dégradé » est simulé par tramage de Bayer (évite les gros blocs d’une seule couleur
# et les 🟥🟧🟨🟩 hors thème qu’imposait le plus proche RGB sur la palette Unicode).


def _smoothstep01(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


# Matrice 4×4 classique (0–15), ordre ligne-major pour une barre gauche → droite.
_MYCARD_BAR_BAYER4: tuple[tuple[int, ...], ...] = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def _gradient_square_at(i: int, n_filled: int) -> str:
    """i-ième carré rempli : transition douce violet → bleu (tramage, pas de carrés arc-en-ciel)."""
    if n_filled <= 0:
        return "⬜"
    if n_filled == 1:
        return "🟪"
    raw = i / (n_filled - 1)
    t = _smoothstep01(raw)
    row = (i // 4) % 4
    col = i % 4
    thr = _MYCARD_BAR_BAYER4[row][col]
    return "🟦" if t * 16 > thr else "🟪"


def _pct_bar_pretty(cur: int, total: int, width: int = 12) -> str:
    """Barre badges (embed) : 🟪→🟦 façon /mycard, lissée par tramage."""
    if total <= 0:
        return "⬜" * width
    p = max(0.0, min(1.0, cur / total))
    filled = int(round(p * width))
    if filled <= 0:
        return "⬜" * width
    return "".join(_gradient_square_at(i, filled) for i in range(filled)) + "⬜" * (width - filled)


_ENGAGE_MINI_KEYS = frozenset({"mission_completed", "mission_hardcore", "checkin", "mycard_visits"})

# Agrégats pour la carte /mycard (image)
_MYCARD_GUESS_KEYS = frozenset({
    "guessyear",
    "guessepisodes",
    "guessgenre",
    "guesscharacter",
    "guesswho",
    "guessop",
    "guesspop",
    "guesspo",
    "guessspo",
    "guessopener",
})


def _mycard_devinettes_total(mini_scores: dict) -> int:
    """Somme des compteurs « devinettes » + Higher/Lower."""
    ms = mini_scores or {}
    s = int(ms.get("higherlower", 0) or 0)
    for k in _MYCARD_GUESS_KEYS:
        s += int(ms.get(k, 0) or 0)
    return s


def _mycard_score_hint(key: str) -> str:
    """
    Ce que mesure réellement le compteur (d’après add_mini_score dans le code).
    Phrase courte pour carte / embed.
    """
    if key == "bossraid":
        return "dégâts cumulés au raid boss"
    if key == "guessopchain_streak":
        return "meilleure série de bonnes réponses d’affilée (chaîne)"
    if key == "mission_hardcore":
        return "missions quotidiennes Hardcore terminées"
    if key == "duel":
        return "manches où tu marques le point (duel)"
    if key == "duel_victory":
        return "duels remportés (match gagné)"
    if key in ("animequiz", "animequizmulti"):
        return "bonnes réponses (questions justes)"
    if key == "chainquiz":
        return "bonnes réponses (chaîne)"
    if key == "higherlower":
        return "comparaisons gagnées (H/L)"
    if key in _MYCARD_GUESS_KEYS or key == "guesswho":
        return "bonnes réponses (devinette réussie)"
    if key == "topgg_vote":
        return "votes Top.gg"
    return "activité (compteur bot)"


def _top_mini_game_play(mini_scores: dict) -> tuple[str, int] | None:
    """Mini-jeu le plus « actif » : (clé interne, valeur max hors engagement)."""
    if not mini_scores:
        return None
    best_k = None
    best_v = -1
    for k, raw in mini_scores.items():
        if k in _ENGAGE_MINI_KEYS:
            continue
        try:
            v = int(raw)
        except (TypeError, ValueError):
            continue
        if v > best_v:
            best_v = v
            best_k = k
    if best_k is None or best_v <= 0:
        return None
    return (best_k, best_v)


def _top_mini_game_wins(mini_scores: dict) -> tuple[str, int] | None:
    """(clé, valeur) si victoires duels > 0."""
    if not mini_scores:
        return None
    dv = int(mini_scores.get("duel_victory") or 0)
    if dv > 0:
        return ("duel_victory", dv)
    return None


def _mycard_play_line(mini_scores: dict) -> Optional[str]:
    """Une ligne pour la carte image : mini-jeu le plus actif + précision sur le compteur."""
    tp = _top_mini_game_play(mini_scores or {})
    if not tp:
        return None
    k, v = tp
    hint = _mycard_score_hint(k)
    return f"Plus joué · {_mini_label(k)} — {_fmt_number(v)} · {hint}"


def _mycard_image_line1(mini_scores: dict) -> Optional[str]:
    """Carte image : priorité au total Quiz (solo + multi), sinon ancien « plus joué »."""
    ms = mini_scores or {}
    q = int(ms.get("animequiz", 0) or 0) + int(ms.get("animequizmulti", 0) or 0)
    if q > 0:
        return f"Quiz — {_fmt_number(q)} bonnes réponses (solo + multi)"
    return _mycard_play_line(ms)


def _mycard_image_line2(mini_scores: dict) -> Optional[str]:
    """Carte image : priorité au total devinettes, sinon victoires / 2e activité."""
    ms = mini_scores or {}
    dev = _mycard_devinettes_total(ms)
    if dev > 0:
        return f"Devinettes — {_fmt_number(dev)} bonnes réponses (guess + H/L)"
    return _mycard_record_line(ms)


def _mycard_record_line(mini_scores: dict) -> Optional[str]:
    """Victoires duels en priorité, sinon 2e meilleur mini-jeu (hors engagement)."""
    if not mini_scores:
        return None
    dv = int(mini_scores.get("duel_victory") or 0)
    if dv > 0:
        return f"Duels — {_fmt_number(dv)} {_mycard_score_hint('duel_victory')}"
    items: list[tuple[str, int]] = []
    for k, raw in mini_scores.items():
        if k in _ENGAGE_MINI_KEYS:
            continue
        try:
            v = int(raw)
        except (TypeError, ValueError):
            continue
        if v > 0:
            items.append((k, v))
    items.sort(key=lambda x: -x[1])
    if len(items) >= 2:
        k, v = items[1]
        return f"2e activité · {_mini_label(k)} — {_fmt_number(v)} · {_mycard_score_hint(k)}"
    return None


def _format_minis_compact(mini_scores: dict) -> str:
    if not mini_scores:
        return "— Aucune activité enregistrée."
    items = sorted(
        ((k, int(v)) for k, v in mini_scores.items() if int(v or 0) > 0),
        key=lambda x: -x[1],
    )[:20]
    if not items:
        return "— Aucune activité enregistrée."
    lines = [f"• **{_mini_label(k)}** — {_fmt_number(v)}" for k, v in items]
    return "\n".join(lines)[:1020]


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
    "bossraid": "Raid boss",
    "guessop": "Guess OP",
    "guessopchain_streak": "Guess OP chaîne (série max)",
    "mission_hardcore": "Missions Hardcore",
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
        ("📅", "Engagement", frozenset({"mission_completed", "mission_hardcore", "checkin", "mycard_visits"})),
        ("🎯", "Quiz", frozenset({"animequiz", "animequizmulti"})),
        ("🎭", "Devinettes", frozenset({
            "guessyear", "guessepisodes", "guessgenre", "guesscharacter", "guesswho",
            "guessop",
            "guesspop", "guesspo", "guessspo", "guessopener",
            "guessopchain_streak",
        })),
        ("🐉", "Communauté", frozenset({"chainquiz", "bossraid"})),
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

    for _bid, spec in iter_badges_sorted():
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
            rank = tier_name_fr(tier)
            unlocked_lines.append(f"{icon} **{spec['name']}** · _{rank}_ ({tier + 1}/{paliers})")
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


# ---------- BUILD DES EMBEDS (carte / profil) ----------
def _embed_mycard_simple(
    ctx: commands.Context,
    *,
    anime_fav: Optional[dict],
    al_name: Optional[str],
    mini_scores: dict,
    bug_validated: int,
) -> discord.Embed:
    """Carte courte : pas de menu, pas de timeout."""
    e = discord.Embed(
        title=f"🎴 {ctx.author.display_name}",
        description="Vue rapide — tout le détail : **`/profile`**",
        color=_EMBED_OVERVIEW,
    )
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    if al_name:
        e.add_field(name="🔗 AniList", value=f"`{al_name}`", inline=False)
    else:
        e.add_field(name="🔗 AniList", value="Non lié · `/linkanilist`", inline=False)
    if anime_fav:
        ft = (anime_fav.get("title") or "—").replace("[", "(").replace("]", ")")
        su = (anime_fav.get("site_url") or "").strip()
        fav_val = f"[{ft}]({su})" if su else f"**{ft}**"
        e.add_field(name="⭐ Anime favori", value=fav_val, inline=False)
    tp = _top_mini_game_play(mini_scores or {})
    if tp:
        k, v = tp
        e.add_field(
            name="🎮 Le plus actif",
            value=f"**{_mini_label(k)}** · {_fmt_number(v)}\n_{_mycard_score_hint(k)}_",
            inline=True,
        )
    tw = _top_mini_game_wins(mini_scores or {})
    if tw:
        kw, vw = tw
        e.add_field(
            name="🏆 Duels",
            value=f"**{_fmt_number(vw)}** — {_mycard_score_hint(kw)}",
            inline=True,
        )
    if bug_validated > 0:
        e.add_field(name="🐞 Bugs validés (staff)", value=f"**{bug_validated}**", inline=True)
    e.set_footer(text="/profile · /mybadges · /animefav")
    return e


def _embed_profile_full(
    ctx: commands.Context,
    bot: commands.Bot,
    *,
    level: int,
    xp: int,
    next_xp: int,
    title: str,
    quiz_score: int,
    streak_days: int,
    bug_validated: int,
    anime_fav: Optional[dict],
    mini_scores: dict,
    counts: dict,
) -> discord.Embed:
    """Profil détaillé : XP, streak, mini-jeux, sanctions, trophées (aperçu)."""
    bar = _xp_bar(xp, next_xp)
    e = discord.Embed(
        title=f"📋 Profil — {ctx.author.display_name}",
        description="Stats complètes sur le bot (niveau, activité, trophées…).",
        color=_EMBED_MINIS,
    )
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    e.add_field(name="🏅 Titre", value=f"**{title}**", inline=True)
    e.add_field(name="🧬 Niveau", value=f"**{level}**", inline=True)
    e.add_field(name="🧪 XP", value=f"{_fmt_number(xp)} / {_fmt_number(next_xp)}", inline=True)
    e.add_field(name="📈 Progression XP", value=bar, inline=False)
    e.add_field(name="🏆 Score quiz", value=str(_fmt_number(quiz_score)), inline=False)

    next_pal = None
    for t in sorted(BADGES.get("serie", {}).get("thresholds", [])):
        if streak_days < t:
            next_pal = t
            break
    streak_line = f"**{streak_days}** jour(s)"
    if next_pal:
        streak_line += f" · prochain palier série : **{streak_days}/{next_pal}**"
    e.add_field(name="🔥 Streak (check-in)", value=streak_line, inline=False)

    if bug_validated > 0:
        e.add_field(
            name="🐞 Bugs validés",
            value=f"**{bug_validated}** — _signaler : `/reportbug`_",
            inline=False,
        )

    al_name = core.get_linked_username(ctx.author.id)
    if al_name:
        e.add_field(name="🔗 AniList", value=f"Compte lié : **`{al_name}`**", inline=False)
    else:
        e.add_field(name="🔗 AniList", value="Non lié — `/linkanilist`", inline=False)

    if anime_fav:
        ft = (anime_fav.get("title") or "—").replace("[", "(").replace("]", ")")
        su = (anime_fav.get("site_url") or "").strip()
        fav_val = f"[{ft}]({su})" if su else f"**{ft}**"
        e.add_field(name="⭐ Anime favori", value=fav_val, inline=False)

    gg_pen = core.get_guess_genre_penalty_count(ctx.author.id)
    e.add_field(name="⚠️ Sanctions Guess genre", value=str(gg_pen) if gg_pen else "0", inline=False)

    e.add_field(name="🎮 Activité (compteurs)", value=_format_minis_compact(mini_scores), inline=False)

    s = _badge_mycard_summary(bot, counts)
    vt = max(1, int(s["visible_total"] or 1))
    un = int(s["unlocked_n"] or 0)
    pct = min(100, int(round(100 * un / vt))) if s["visible_total"] else 0
    badge_line = (
        f"{_pct_bar_pretty(un, vt, 10)} **{pct}%** — **{un}/{s['visible_total']}** séries\n"
        f"_Rangs : Initié → Confirmé → Vétéran → Élite → Mythe · détail : `/mybadges`_"
    )
    e.add_field(name="🏅 Trophées (aperçu)", value=badge_line[:1024], inline=False)

    e.set_footer(text="/mybadges · /mycard")
    return e


def _build_mybadges_payload(bot: commands.Bot, counts: dict) -> dict[str, Any]:
    """Données pour /mybadges : listes de lignes + résumé."""
    unlocked: list[str] = []
    locked: list[str] = []
    mystery: list[str] = []
    sec_u: list[str | None] = [None]
    sec_l: list[str | None] = [None]

    for _bid, spec in iter_badges_sorted():
        count = badge_count_for_spec(spec, counts)
        thresholds = spec["thresholds"]
        icon_list = spec["icons"]
        tier, next_th = evaluate_tier(count, thresholds)
        cat = spec.get("category", "autre")

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
            rank = tier_name_fr(tier)
            prog = f"{count}/{next_th}" if next_th else "**max**"
            _append_badge_section_header(unlocked, sec_u, cat)
            unlocked.append(
                f"{icon} **{spec['name']}** · _{rank}_ · {prog}\n"
                f"_{spec['desc']}_"
            )
        elif thresholds:
            need = int(thresholds[0])
            rest = max(0, need - count)
            pct = min(100, int(round(100 * count / need))) if need else 0
            bar = _pct_bar_pretty(count, need, 10)
            _append_badge_section_header(locked, sec_l, cat)
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


def _mybadges_embed_color(section: str) -> discord.Color:
    if section == "summary":
        return discord.Color.from_rgb(163, 89, 255)
    if section == "unlocked":
        return discord.Color.from_rgb(46, 204, 113)
    if section == "locked":
        return discord.Color.from_rgb(241, 196, 15)
    return discord.Color.dark_gray()


def _embed_mybadges(ctx: commands.Context, bot: commands.Bot, payload: dict[str, Any], section: str) -> discord.Embed:
    """section: summary | unlocked | locked | mystery"""
    s = payload["summary"]
    vt = max(1, int(s["visible_total"] or 1))
    un = int(s["unlocked_n"] or 0)
    pct = min(100, int(round(100 * un / vt))) if s["visible_total"] else 0
    bar = _pct_bar_pretty(un, vt, 14)
    col = _mybadges_embed_color(section)

    if section == "summary":
        e = discord.Embed(
            title=f"🏅 Trophées — {ctx.author.display_name}",
            description=(
                f"{bar}  **{pct}%** complété\n"
                f"**{un}** / **{s['visible_total']}** séries avec au moins un rang\n\n"
                "**Rangs :** 🌱 Initié → **Confirmé** → **Vétéran** → **Élite** → **Mythe** ✨"
            ),
            color=col,
        )
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        if s["next_lines"]:
            e.add_field(
                name="🎯 Prochains paliers",
                value="\n".join(f"• {x}" for x in s["next_lines"])[:1024],
                inline=False,
            )
        else:
            e.add_field(name="🎯 Prochains paliers", value="— Rien en attente.", inline=False)
        if s["unlocked_lines"]:
            snap = "\n".join(f"• {x}" for x in s["unlocked_lines"][:6])
            if s["unlocked_extra"] > 0:
                snap += f"\n_… **+{s['unlocked_extra']}** dans « Débloqués »_"
            e.add_field(name="✨ En poche (aperçu)", value=snap[:1024], inline=False)
        e.set_footer(text="Menu : changer de section sans nouvelle commande")
        return e

    if section == "unlocked":
        lines = payload["unlocked"]
        chunks = _chunk_text_blocks(lines)
        e = discord.Embed(
            title=f"✅ Débloqués — {ctx.author.display_name}",
            description=f"**{len(lines)}** trophée(s) avec au moins un palier.",
            color=col,
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
            description=f"**{len(lines)}** piste(s) en cours — barres **rose → bleu** (comme /mycard) = progression vers le palier.",
            color=col,
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
        color=col,
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
        super().__init__(timeout=3600.0)
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
    """Carte courte (/mycard), profil détaillé (/profile), trophées (/mybadges)."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="mycard",
        description="Image panoramique (niveau, XP, AniList, favori, mini-jeux) — sans embed.",
    )
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def mycard(self, ctx: commands.Context) -> None:
        await core.maybe_defer_hybrid(ctx)
        user_id = ctx.author.id

        try:
            core.add_mini_score(user_id, "mycard_visits", 1)
        except Exception:
            pass

        mini_scores = core.get_mini_scores(user_id) or {}
        try:
            bug_validated = bug_report_store.count_confirmed_reports_for_user(user_id)
        except Exception:
            bug_validated = 0
        anime_fav = core.get_anime_favorite(user_id)
        al_name = core.get_linked_username(user_id)

        levels = core.load_levels()
        ud = levels.get(str(user_id), {"xp": 0, "level": 0})
        xp = int(ud.get("xp", 0))
        level = int(ud.get("level", 0))
        next_xp = core.xp_for_next_level(level)
        play_line = _mycard_image_line1(mini_scores)
        record_line = _mycard_image_line2(mini_scores)
        fav_plain: Optional[str] = None
        if anime_fav:
            fav_plain = (anime_fav.get("title") or "—").replace("[", "(").replace("]", ")")

        try:
            buf = await asyncio.to_thread(
                lambda: generate_mycard_image(
                    display_name=ctx.author.display_name,
                    avatar_url=str(ctx.author.display_avatar.url),
                    level=level,
                    xp=xp,
                    next_xp=next_xp,
                    anilist_username=al_name,
                    anime_fav=fav_plain,
                    line_play=play_line,
                    line_record=record_line,
                )
            )
            await ctx.send(file=discord.File(buf, filename="mycard.png"))
        except Exception:
            embed = _embed_mycard_simple(
                ctx,
                anime_fav=anime_fav,
                al_name=al_name,
                mini_scores=mini_scores,
                bug_validated=bug_validated,
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="profile",
        description="Profil détaillé : XP, streak, mini-jeux, sanctions, trophées (aperçu).",
    )
    @commands.cooldown(1, 25, commands.BucketType.user)
    async def profile_cmd(self, ctx: commands.Context) -> None:
        is_slash = bool(getattr(ctx, "interaction", None))
        if is_slash and ctx.guild is not None:
            await core.maybe_defer_hybrid(ctx, ephemeral=True)
        else:
            await core.maybe_defer_hybrid(ctx)

        user_id = ctx.author.id
        user_id_str = str(user_id)

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

        try:
            bug_validated = bug_report_store.count_confirmed_reports_for_user(user_id)
        except Exception:
            bug_validated = 0

        anime_fav = core.get_anime_favorite(user_id)

        embed = _embed_profile_full(
            ctx,
            self.bot,
            level=level,
            xp=xp,
            next_xp=next_xp,
            title=title,
            quiz_score=quiz_score,
            streak_days=streak_days,
            bug_validated=bug_validated,
            anime_fav=anime_fav,
            mini_scores=mini_scores,
            counts=counts,
        )
        ep = is_slash and ctx.guild is not None
        if is_slash and ctx.interaction:
            await ctx.interaction.followup.send(embed=embed, ephemeral=ep)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="animefav",
        description="Définis ton anime préféré — affiché sur ta carte /mycard.",
    )
    @app_commands.describe(
        anime="Titre (recherche), ID ou URL anilist.co/anime/… — « clear » pour retirer — vide = aide",
    )
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def animefav(self, ctx: commands.Context, anime: Optional[str] = None):
        """Enregistre un animé favori pour l’aperçu /mycard (AniList)."""
        is_slash = bool(getattr(ctx, "interaction", None))
        uid = ctx.author.id

        async def _send_help() -> None:
            cur = core.get_anime_favorite(uid)
            if cur:
                desc = (
                    f"⭐ Actuellement : **{cur['title']}**\n{cur['site_url']}\n\n"
                    "Pour changer : indique un **titre**, un **ID** ou une **URL** AniList. "
                    "**`clear`** pour retirer."
                )
            else:
                desc = (
                    "Indique un **nom** (recherche sur AniList), un **ID** ou une **URL** "
                    "`https://anilist.co/anime/...`. "
                    "Ce sera affiché sur **`/mycard`**. "
                    "Écris **`clear`** pour retirer un favori déjà enregistré."
                )
            em = discord.Embed(title="⭐ Anime favori", description=desc, color=_EMBED_OVERVIEW)
            if is_slash and ctx.interaction:
                ep = ctx.guild is not None
                if not ctx.interaction.response.is_done():
                    await ctx.interaction.response.send_message(embed=em, ephemeral=ep)
                else:
                    await ctx.interaction.followup.send(embed=em, ephemeral=ep)
            else:
                await ctx.reply(embed=em)

        if anime is None or not str(anime).strip():
            await _send_help()
            return

        await core.maybe_defer_hybrid(ctx, ephemeral=True)
        kind, data = _resolve_anime_favorite_input(anime)
        if kind == "help":
            if is_slash and ctx.interaction:
                await ctx.interaction.followup.send(
                    "Indique un titre, un ID ou une URL — ou **`/animefav`** sans argument pour l’aide.",
                    ephemeral=True,
                )
            else:
                await ctx.reply(
                    "Indique un titre, un ID ou une URL — ou **`/animefav`** sans argument pour l’aide."
                )
            return
        if kind == "error":
            err = str(data) if data else "Erreur."
            if is_slash and ctx.interaction:
                await ctx.interaction.followup.send(err, ephemeral=True)
            else:
                await ctx.reply(err)
            return
        if kind == "clear":
            core.clear_anime_favorite(uid)
            msg = "✅ Animé favori retiré — ta **`/mycard`** sera mise à jour."
            if is_slash and ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg)
            return

        assert kind == "set" and isinstance(data, dict)
        core.set_anime_favorite(uid, data)
        msg = f"✅ **{data['title']}** est enregistré comme favori — voir **`/mycard`**."
        if is_slash and ctx.interaction:
            await ctx.interaction.followup.send(msg, ephemeral=True)
        else:
            await ctx.reply(msg)

    @commands.hybrid_command(
        name="animetop",
        description="Classement des mini-jeux (participations enregistrées dans les stats du bot).",
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @app_commands.describe(
        classement=(
            "Vue au départ (total, aperçu ou un jeu) — modifiable ensuite avec le menu déroulant sous le message."
        ),
    )
    @app_commands.choices(
        classement=[
            app_commands.Choice(name="Toute activité (tous mini-jeux)", value="all"),
            app_commands.Choice(name="Aperçu : total + top 3 par jeu", value="overview"),
            app_commands.Choice(name="Anime quiz", value="animequiz"),
            app_commands.Choice(name="Guess année", value="guessyear"),
            app_commands.Choice(name="Guess épisodes", value="guessepisodes"),
            app_commands.Choice(name="Guess genre", value="guessgenre"),
            app_commands.Choice(name="Guess personnage", value="guesscharacter"),
            app_commands.Choice(name="Guess who", value="guesswho"),
            app_commands.Choice(name="Higher / Lower", value="higherlower"),
            app_commands.Choice(name="Chain quiz", value="chainquiz"),
            app_commands.Choice(name="Boss raid (coups)", value="bossraid"),
            app_commands.Choice(name="Duel", value="duel"),
            app_commands.Choice(name="Guess OP", value="guessop"),
        ]
    )
    async def animetop(self, ctx: commands.Context, classement: str = "all") -> None:
        key = _animetop_valid_mode((classement or "all").strip().lower())
        is_slash = bool(getattr(ctx, "interaction", None))
        if is_slash and ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        if not core.mini_game_activity_leaderboard(n=1):
            msg = "Pas encore de scores dans data/mini_scores.json."
            if is_slash and ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return

        emb = await self._animetop_make_embed(self.bot, ctx.guild, key)
        view = AnimetopLeaderboardView(self, ctx.author.id, ctx.guild, key)
        if is_slash and ctx.interaction:
            msg = await ctx.interaction.followup.send(embed=emb, view=view, wait=True)
        else:
            msg = await ctx.send(embed=emb, view=view)
        view._message = msg

    async def _animetop_make_embed(
        self,
        bot: commands.Bot,
        guild: Optional[discord.Guild],
        mode: str,
    ) -> discord.Embed:
        m = _animetop_valid_mode(mode)
        if m == "overview":
            return await self._animetop_overview_embed(bot, guild)

        n = 15
        if m == "all":
            rows = core.mini_game_activity_leaderboard(n=n)
        else:
            rows = core.mini_game_leaderboard(m, n=n)

        color = _animetop_embed_color(m)
        label = _animetop_mode_label(m)

        if not rows:
            emb = discord.Embed(
                title=f"🏆 {label}",
                description=(
                    "Aucune entrée pour ce classement.\n"
                    "Choisis un autre mode dans le **menu** ci-dessous."
                ),
                color=color,
            )
            emb.set_footer(text="mini_scores.json · noms : serveur ou profil Discord")
            return emb

        names = await _animetop_names_map(bot, guild, (u for u, _ in rows))
        lines = []
        for i, (uid, sc) in enumerate(rows, start=1):
            nm = _animetop_trunc_display(names.get(uid, str(uid)), 22)
            if i <= 3:
                prefix = f"{_animetop_medal(i)} **{nm}**"
            else:
                prefix = f"`{i:>2}.` **{nm}**"
            lines.append(f"{prefix} — {_fmt_number(int(sc))}")
        block = "\n".join(lines)
        if len(block) > 1024:
            block = block[:1021] + "…"

        emb = discord.Embed(
            title=f"🏆 {label}",
            description=_animetop_short_blurb(m),
            color=color,
        )
        emb.add_field(name="Classement", value=block, inline=False)
        emb.set_footer(text="mini_scores.json · défaites pas toujours comptées selon le jeu")
        return emb

    async def _animetop_overview_embed(
        self,
        bot: commands.Bot,
        guild: Optional[discord.Guild],
    ) -> discord.Embed:
        rows = core.mini_game_activity_leaderboard(n=8)
        if not rows:
            return discord.Embed(
                title="🧩 Aperçu multi-jeux",
                description="Pas encore de scores.",
                color=_EMBED_MINIS,
            )

        uid_collect: list[int] = [u for u, _ in rows]
        sections: list[tuple[str, list[tuple[int, int]]]] = [("__total__", rows)]
        for gk, _lbl in _ANITOP_GAME_LABELS:
            sub = core.mini_game_leaderboard(gk, n=3)
            if sub:
                uid_collect.extend(u for u, _ in sub)
                sections.append((gk, sub))

        names = await _animetop_names_map(bot, guild, uid_collect)
        label_by_key = dict(_ANITOP_GAME_LABELS)
        color = _animetop_embed_color("overview")
        emb = discord.Embed(
            title="🧩 Aperçu multi-jeux",
            description=(
                "Vue **résumé** : le menu indique **« Vue : Aperçu multi-jeux »**. "
                "Pour un classement détaillé par jeu, choisis un mini-jeu dans la liste."
            ),
            color=color,
        )

        tot_rows = sections[0][1]
        total_lines = [
            f"{_animetop_medal(i)} **{_animetop_trunc_display(names.get(uid, str(uid)))}** — {_fmt_number(int(sc))}"
            for i, (uid, sc) in enumerate(tot_rows, start=1)
        ]
        val_total = "\n".join(total_lines)
        if len(val_total) > 1024:
            val_total = val_total[:1021] + "…"
        emb.add_field(name="📊 Total (tous jeux)", value=val_total or "—", inline=False)

        per_game_chunks: list[str] = []
        for gk, sub in sections[1:]:
            glabel = label_by_key.get(gk, gk)
            slines = [
                f"{_animetop_medal(i)} **{_animetop_trunc_display(names.get(uid, str(uid)))}** — {_fmt_number(int(sc))}"
                for i, (uid, sc) in enumerate(sub, start=1)
            ]
            per_game_chunks.append(f"**{glabel}**\n" + "\n".join(slines))
        per_game_block = "\n\n".join(per_game_chunks)
        if len(per_game_block) > 1024:
            per_game_block = per_game_block[:1021] + "…"
        if per_game_block:
            emb.add_field(
                name="Par mini-jeu (top 3 si activité)",
                value=per_game_block,
                inline=False,
            )

        emb.set_footer(text="mini_scores.json · défaites pas toujours comptées selon le jeu")
        return emb

    @commands.hybrid_command(
        name="mybadges",
        description="Trophées par catégorie (rangs Initié→Mythe) et progression.",
    )
    async def mybadges(self, ctx: commands.Context) -> None:
        is_slash = bool(getattr(ctx, "interaction", None))
        ephemeral = bool(is_slash and ctx.guild is not None)
        await core.maybe_defer_hybrid(ctx, ephemeral=ephemeral)

        user_id = ctx.author.id
        counts = _get_user_counts(user_id)
        payload = _build_mybadges_payload(self.bot, counts)
        embed = _embed_mybadges(ctx, self.bot, payload, "summary")
        view = MyBadgesNavigator(ctx, ctx.author, self.bot, payload, section="summary")
        if is_slash and ctx.interaction:
            await ctx.interaction.followup.send(embed=embed, view=view, ephemeral=ephemeral)
        else:
            await ctx.send(embed=embed, view=view)


class AnimetopCategorySelect(discord.ui.Select):
    def __init__(
        self,
        cog: Profile,
        author_id: int,
        guild: Optional[discord.Guild],
        initial: str,
        *,
        placeholder: str,
    ):
        self.cog = cog
        self.author_id = author_id
        self.guild = guild
        ini = _animetop_valid_mode(initial)
        opts: list[discord.SelectOption] = [
            discord.SelectOption(
                label="Total — tous mini-jeux",
                value="all",
                emoji="📊",
                description="Somme de tous les compteurs",
                default=(ini == "all"),
            ),
            discord.SelectOption(
                label="Aperçu multi-jeux",
                value="overview",
                emoji="🧩",
                description="Top global + podium par jeu",
                default=(ini == "overview"),
            ),
        ]
        for key, label in _ANITOP_GAME_LABELS:
            opts.append(
                discord.SelectOption(
                    label=label[:100],
                    value=key,
                    emoji="🎮",
                    description="Classement pour ce mini-jeu",
                    default=(ini == key),
                )
            )
        super().__init__(
            placeholder=placeholder[:150],
            min_values=1,
            max_values=1,
            options=opts,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Ce menu est réservé à la personne qui a lancé la commande.",
                ephemeral=True,
            )
            return
        mode = self.values[0]
        emb = await self.cog._animetop_make_embed(interaction.client, self.guild, mode)
        new_view = AnimetopLeaderboardView(self.cog, self.author_id, self.guild, mode)
        await interaction.response.edit_message(embed=emb, view=new_view)
        new_view._message = interaction.message


class AnimetopLeaderboardView(discord.ui.View):
    def __init__(self, cog: Profile, author_id: int, guild: Optional[discord.Guild], initial: str):
        super().__init__(timeout=300.0)
        ph = _animetop_select_placeholder(initial)
        self.add_item(
            AnimetopCategorySelect(
                cog,
                author_id,
                guild,
                initial,
                placeholder=ph,
            )
        )
        self._message: Optional[discord.Message] = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self._message:
            try:
                await self._message.edit(view=self)
            except Exception:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
