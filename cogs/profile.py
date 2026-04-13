# cogs/profile.py — /mycard (carte), /profile (détail), /mybadges (trophées)
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Dict, Iterable, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from modules import core, i18n
from modules.app_cmd_locale import ui_str
from modules import bug_report as bug_report_store
from modules.image import generate_mycard_image
from modules.badges import BADGES, BADGE_SECTION_TITLE_FR, evaluate_tier, iter_badges_sorted, tier_name_fr
from modules.badge_helpers import badge_count_for_spec
from modules.emoji_utils import get_emoji
from modules.text_bars import pct_bar_parallelogram

# Couleurs cohérentes (proche blurple Discord + or trophées)
_EMBED_OVERVIEW = discord.Color.from_rgb(88, 101, 242)
_EMBED_MINIS = discord.Color.from_rgb(52, 58, 64)
_EMBED_BADGES = discord.Color.from_rgb(155, 89, 182)
_LEADERBOARD_TTL_SEC = 120.0
_ANIMETOP_ACTIVE_UNTIL: dict[int, float] = {}

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


def _resolve_anime_favorite_input(raw: str, *, lg: str) -> Tuple[str, Any]:
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
            return ("error", i18n.t("profile.fav_err_id_anime", lg, mid=mid))
        return ("set", info)

    if s.isdigit():
        mid = int(s)
        info = core.get_anime_media_basic(mid)
        if not info:
            return ("error", i18n.t("profile.fav_err_id_short", lg, mid=mid))
        return ("set", info)

    hits = core.search_media(s, limit=8)
    if not hits:
        return ("error", i18n.t("profile.fav_err_search", lg, q=s[:100]))
    return ("set", _payload_from_search_hit(hits[0]))


def _tier_name_i18n(tier_index: int, lg: str) -> str:
    arr = i18n.value("profile.tier_ranks", lg)
    if isinstance(arr, list) and 0 <= tier_index < len(arr):
        return str(arr[tier_index])
    return tier_name_fr(tier_index)


def _animetop_game_label(key: str, lg: str) -> str:
    return i18n.t(f"profile.animetop_game_{key}", lg)


# Ordre d’affichage pour /animetop aperçu (clés mini_scores.json)
_ANITOP_GAME_KEYS: tuple[str, ...] = (
    "animequiz",
    "guessyear",
    "guessepisodes",
    "guesscharacter",
    "guesswho",
    "guessgenre",
    "higherlower",
    "chainquiz",
    "bossraid",
    "duel",
    "guessop",
    "guessopchain_streak",
    "mission_hardcore",
)


async def _animetop_names_map(
    bot: commands.Bot,
    guild: Optional[discord.Guild],
    uids: Iterable[int],
    lg: str,
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
            out[uid] = i18n.t("profile.name_deleted", lg, uid=uid)
        except Exception:
            out[uid] = i18n.t("profile.name_user", lg, uid=uid)

    await asyncio.gather(*(one(u) for u in uniq))
    return out


def _animetop_valid_mode(mode: str) -> str:
    m = (mode or "all").strip().lower()
    if m in {"all", "overview"}:
        return m
    if any(m == k for k in _ANITOP_GAME_KEYS):
        return m
    return "all"


def _animetop_mode_label(mode: str, lg: str) -> str:
    m = _animetop_valid_mode(mode)
    if m == "all":
        return i18n.t("profile.animetop_mode_all", lg)
    if m == "overview":
        return i18n.t("profile.animetop_mode_overview", lg)
    return _animetop_game_label(m, lg)


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


def _animetop_select_placeholder(mode: str, lg: str) -> str:
    """Indique clairement la vue active (max 150 car. pour le Select Discord)."""
    s = i18n.t("profile.animetop_view_prefix", lg, label=_animetop_mode_label(mode, lg))
    return s if len(s) <= 150 else s[:147] + "…"


def _animetop_short_blurb(mode: str, lg: str) -> str:
    m = _animetop_valid_mode(mode)
    if m == "all":
        return i18n.t("profile.animetop_blurb_all", lg)
    return i18n.t(
        "profile.animetop_blurb_game",
        lg,
        label=_animetop_mode_label(m, lg),
    )


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
    """Même style ▰▱ que le reste du profil / ``get_xp_bar``."""
    return pct_bar_parallelogram(xp, max(1, int(next_xp)), seg)


def _append_badge_section_header(
    lines: list[str],
    state: list[str | None],
    category: str,
    lg: str,
) -> None:
    """Insère un titre de section (catégorie) avant la prochaine ligne, si besoin."""
    if category != state[0]:
        title = i18n.t(f"profile.badge_sec_{category}", lg)
        if title.startswith("profile.badge_sec_"):
            title = BADGE_SECTION_TITLE_FR.get(category, BADGE_SECTION_TITLE_FR["autre"])
        if lines:
            lines.append("")
        lines.append(f"**— {title} —**")
        state[0] = category


def _pct_bar_pretty(cur: int, total: int, width: int = 12) -> str:
    """Barre trophées / profil — délègue à `modules.text_bars.pct_bar_parallelogram`."""
    return pct_bar_parallelogram(cur, total, width)


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


def _mycard_score_hint(key: str, lg: str) -> str:
    """
    Ce que mesure réellement le compteur (d’après add_mini_score dans le code).
    Phrase courte pour carte / embed.
    """
    if key == "bossraid":
        return i18n.t("profile.hint_bossraid", lg)
    if key == "guessopchain_streak":
        return i18n.t("profile.hint_guessopchain_streak", lg)
    if key == "mission_hardcore":
        return i18n.t("profile.hint_mission_hardcore", lg)
    if key == "duel":
        return i18n.t("profile.hint_duel", lg)
    if key == "duel_victory":
        return i18n.t("profile.hint_duel_victory", lg)
    if key in ("animequiz", "animequizmulti"):
        return i18n.t("profile.hint_animequiz", lg)
    if key == "chainquiz":
        return i18n.t("profile.hint_chainquiz", lg)
    if key == "higherlower":
        return i18n.t("profile.hint_higherlower", lg)
    if key in _MYCARD_GUESS_KEYS or key == "guesswho":
        return i18n.t("profile.hint_guess", lg)
    if key == "topgg_vote":
        return i18n.t("profile.hint_topgg_vote", lg)
    return i18n.t("profile.hint_default", lg)


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


def _mycard_play_line(mini_scores: dict, lg: str) -> Optional[str]:
    """Une ligne pour la carte image : mini-jeu le plus actif + précision sur le compteur."""
    tp = _top_mini_game_play(mini_scores or {})
    if not tp:
        return None
    k, v = tp
    hint = _mycard_score_hint(k, lg)
    return i18n.t(
        "profile.mycard_line_play",
        lg,
        label=_mini_label(k, lg),
        v=_fmt_number(v),
        hint=hint,
    )


def _mycard_image_line1(mini_scores: dict, lg: str) -> Optional[str]:
    """Carte image : priorité au total Quiz (solo + multi), sinon ancien « plus joué »."""
    ms = mini_scores or {}
    q = int(ms.get("animequiz", 0) or 0) + int(ms.get("animequizmulti", 0) or 0)
    if q > 0:
        return i18n.t("profile.mycard_img_quiz", lg, n=_fmt_number(q))
    return _mycard_play_line(ms, lg)


def _mycard_image_line2(mini_scores: dict, lg: str) -> Optional[str]:
    """Carte image : priorité au total devinettes, sinon victoires / 2e activité."""
    ms = mini_scores or {}
    dev = _mycard_devinettes_total(ms)
    if dev > 0:
        return i18n.t("profile.mycard_img_dev", lg, n=_fmt_number(dev))
    return _mycard_record_line(ms, lg)


def _mycard_record_line(mini_scores: dict, lg: str) -> Optional[str]:
    """Victoires duels en priorité, sinon 2e meilleur mini-jeu (hors engagement)."""
    if not mini_scores:
        return None
    dv = int(mini_scores.get("duel_victory") or 0)
    if dv > 0:
        return i18n.t(
            "profile.mycard_line_duel",
            lg,
            n=_fmt_number(dv),
            hint=_mycard_score_hint("duel_victory", lg),
        )
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
        return i18n.t(
            "profile.mycard_line_2nd",
            lg,
            label=_mini_label(k, lg),
            v=_fmt_number(v),
            hint=_mycard_score_hint(k, lg),
        )
    return None


def _format_minis_compact(mini_scores: dict, lg: str) -> str:
    empty = i18n.t("profile.minis_empty", lg)
    if not mini_scores:
        return empty
    items = sorted(
        ((k, int(v)) for k, v in mini_scores.items() if int(v or 0) > 0),
        key=lambda x: -x[1],
    )[:20]
    if not items:
        return empty
    lines = [f"• **{_mini_label(k, lg)}** — {_fmt_number(v)}" for k, v in items]
    return "\n".join(lines)[:1020]


def _fmt_number(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _mini_label(key: str, lg: str) -> str:
    v = i18n.value(f"profile.mini_{key}", lg)
    if isinstance(v, str) and v:
        return v
    return key.replace("_", " ").title()


def _mini_bar_line(val: int, max_val: int, width: int = 8) -> str:
    """Même style ▰▱ que les trophées et les stats AniList."""
    return pct_bar_parallelogram(val, max_val, width)


def _mini_group_blocks(mini_scores: dict, lg: str) -> list[tuple[str, str, list[tuple[str, int]]]]:
    """
    Regroupe les stats par famille (Quiz / Devinettes / Duels / Autres), tri par score décroissant.
    Retourne [(titre_emoji, titre_texte, [(label, count), ...]), ...]
    """
    if not mini_scores:
        return []

    groups: list[tuple[str, str, frozenset[str]]] = [
        ("📅", i18n.t("profile.mini_grp_engagement", lg), frozenset({"mission_completed", "mission_hardcore", "checkin", "mycard_visits"})),
        ("🎯", i18n.t("profile.mini_grp_quiz", lg), frozenset({"animequiz", "animequizmulti"})),
        ("🎭", i18n.t("profile.mini_grp_guess", lg), frozenset({
            "guessyear", "guessepisodes", "guessgenre", "guesscharacter", "guesswho",
            "guessop",
            "guesspop", "guesspo", "guessspo", "guessopener",
            "guessopchain_streak",
        })),
        ("🐉", i18n.t("profile.mini_grp_community", lg), frozenset({"chainquiz", "bossraid"})),
        ("⚔️", i18n.t("profile.mini_grp_duels", lg), frozenset({"duel", "duel_victory"})),
    ]
    used: set[str] = set()
    out: list[tuple[str, str, list[tuple[str, int]]]] = []

    for emoji, title, keys in groups:
        rows: list[tuple[str, int]] = []
        for k in keys:
            if k in mini_scores:
                v = int(mini_scores[k])
                if v:
                    rows.append((_mini_label(k, lg), v))
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
            rest.append((_mini_label(k, lg), iv))
    rest.sort(key=lambda x: -x[1])
    if rest:
        out.append(("🎲", i18n.t("profile.mini_grp_other", lg), rest))

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


def _badge_mycard_summary(bot, counts: dict, lg: str) -> dict[str, Any]:
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
            rank = _tier_name_i18n(tier, lg)
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
    lg: str,
) -> discord.Embed:
    """Carte courte : pas de menu, pas de timeout."""
    e = discord.Embed(
        title=i18n.t("profile.mycard_title", lg, name=ctx.author.display_name),
        description=i18n.t("profile.mycard_desc", lg),
        color=_EMBED_OVERVIEW,
    )
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    aln = i18n.t("profile.mycard_anilist", lg)
    if al_name:
        e.add_field(name=aln, value=i18n.t("profile.mycard_anilist_linked", lg, name=al_name), inline=False)
    else:
        e.add_field(name=aln, value=i18n.t("profile.mycard_anilist_unlinked", lg), inline=False)
    if anime_fav:
        ft = (anime_fav.get("title") or "—").replace("[", "(").replace("]", ")")
        su = (anime_fav.get("site_url") or "").strip()
        fav_val = f"[{ft}]({su})" if su else f"**{ft}**"
        e.add_field(name=i18n.t("profile.mycard_fav", lg), value=fav_val, inline=False)
    tp = _top_mini_game_play(mini_scores or {})
    if tp:
        k, v = tp
        e.add_field(
            name=i18n.t("profile.mycard_top_play", lg),
            value=f"**{_mini_label(k, lg)}** · {_fmt_number(v)}\n_{_mycard_score_hint(k, lg)}_",
            inline=True,
        )
    tw = _top_mini_game_wins(mini_scores or {})
    if tw:
        kw, vw = tw
        e.add_field(
            name=i18n.t("profile.mycard_duels", lg),
            value=f"**{_fmt_number(vw)}** — {_mycard_score_hint(kw, lg)}",
            inline=True,
        )
    if bug_validated > 0:
        e.add_field(name=i18n.t("profile.mycard_bugs", lg), value=f"**{bug_validated}**", inline=True)
    e.set_footer(text=i18n.t("profile.mycard_footer", lg))
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
    lg: str,
) -> discord.Embed:
    """Profil détaillé : XP, streak, mini-jeux, sanctions, trophées (aperçu)."""
    bar = _xp_bar(xp, next_xp)
    e = discord.Embed(
        title=i18n.t("profile.profile_title", lg, name=ctx.author.display_name),
        description=i18n.t("profile.profile_desc", lg),
        color=_EMBED_MINIS,
    )
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    e.add_field(name=i18n.t("profile.profile_field_title", lg), value=f"**{title}**", inline=True)
    e.add_field(name=i18n.t("profile.profile_field_level", lg), value=f"**{level}**", inline=True)
    e.add_field(name=i18n.t("profile.profile_field_xp", lg), value=f"{_fmt_number(xp)} / {_fmt_number(next_xp)}", inline=True)
    e.add_field(name=i18n.t("profile.profile_field_xp_prog", lg), value=bar, inline=False)
    e.add_field(name=i18n.t("profile.profile_field_quiz", lg), value=str(_fmt_number(quiz_score)), inline=False)

    next_pal = None
    for t in sorted(BADGES.get("serie", {}).get("thresholds", [])):
        if streak_days < t:
            next_pal = t
            break
    next_seg = ""
    if next_pal:
        next_seg = i18n.t("profile.profile_streak_next", lg, cur=streak_days, need=next_pal)
    streak_line = i18n.t("profile.profile_streak_line", lg, n=streak_days, next=next_seg)
    e.add_field(name=i18n.t("profile.profile_streak", lg), value=streak_line, inline=False)

    if bug_validated > 0:
        e.add_field(
            name=i18n.t("profile.profile_bugs", lg),
            value=i18n.t("profile.profile_bugs_val", lg, n=bug_validated),
            inline=False,
        )

    al_name = core.get_linked_username(ctx.author.id)
    aln = i18n.t("profile.mycard_anilist", lg)
    if al_name:
        e.add_field(name=aln, value=i18n.t("profile.profile_al_linked", lg, name=al_name), inline=False)
    else:
        e.add_field(name=aln, value=i18n.t("profile.profile_al_unlinked", lg), inline=False)

    if anime_fav:
        ft = (anime_fav.get("title") or "—").replace("[", "(").replace("]", ")")
        su = (anime_fav.get("site_url") or "").strip()
        fav_val = f"[{ft}]({su})" if su else f"**{ft}**"
        e.add_field(name=i18n.t("profile.profile_fav", lg), value=fav_val, inline=False)

    gg_pen = core.get_guess_genre_penalty_count(ctx.author.id)
    e.add_field(name=i18n.t("profile.profile_sanctions", lg), value=str(gg_pen) if gg_pen else "0", inline=False)

    e.add_field(name=i18n.t("profile.profile_minis", lg), value=_format_minis_compact(mini_scores, lg), inline=False)

    s = _badge_mycard_summary(bot, counts, lg)
    vt = max(1, int(s["visible_total"] or 1))
    un = int(s["unlocked_n"] or 0)
    pct = min(100, int(round(100 * un / vt))) if s["visible_total"] else 0
    badge_line = i18n.t(
        "profile.profile_badges_line",
        lg,
        bar=_pct_bar_pretty(un, vt, 10),
        pct=pct,
        un=un,
        vt=s["visible_total"],
    )
    e.add_field(name=i18n.t("profile.profile_badges_preview", lg), value=badge_line[:1024], inline=False)

    e.set_footer(text=i18n.t("profile.profile_footer", lg))
    return e


def _build_mybadges_payload(bot: commands.Bot, counts: dict, lg: str) -> dict[str, Any]:
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
            rank = _tier_name_i18n(tier, lg)
            prog = f"{count}/{next_th}" if next_th else "**max**"
            _append_badge_section_header(unlocked, sec_u, cat, lg)
            unlocked.append(
                f"{icon} **{spec['name']}** · _{rank}_ · {prog}\n"
                f"_{spec['desc']}_"
            )
        elif thresholds:
            need = int(thresholds[0])
            rest = max(0, need - count)
            pct = min(100, int(round(100 * count / need))) if need else 0
            bar = _pct_bar_pretty(count, need, 10)
            _append_badge_section_header(locked, sec_l, cat, lg)
            locked.append(
                f"{bar} **{spec['name']}** — {count}/{need} ({pct}%) · reste **{rest}**\n"
                f"_{spec['desc']}_"
            )

    s = _badge_mycard_summary(bot, counts, lg)
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


def _embed_mybadges(
    ctx: commands.Context,
    bot: commands.Bot,
    payload: dict[str, Any],
    section: str,
    lg: str,
) -> discord.Embed:
    """section: summary | unlocked | locked | mystery"""
    s = payload["summary"]
    vt = max(1, int(s["visible_total"] or 1))
    un = int(s["unlocked_n"] or 0)
    pct = min(100, int(round(100 * un / vt))) if s["visible_total"] else 0
    bar = _pct_bar_pretty(un, vt, 14)
    col = _mybadges_embed_color(section)
    nm = ctx.author.display_name

    if section == "summary":
        e = discord.Embed(
            title=i18n.t("profile.mybadges_summary_title", lg, name=nm),
            description=i18n.t(
                "profile.mybadges_summary_desc",
                lg,
                bar=bar,
                pct=pct,
                un=un,
                vt=s["visible_total"],
            ),
            color=col,
        )
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        if s["next_lines"]:
            e.add_field(
                name=i18n.t("profile.mybadges_field_next", lg),
                value="\n".join(f"• {x}" for x in s["next_lines"])[:1024],
                inline=False,
            )
        else:
            e.add_field(
                name=i18n.t("profile.mybadges_field_next", lg),
                value=i18n.t("profile.mybadges_field_next_empty", lg),
                inline=False,
            )
        if s["unlocked_lines"]:
            snap = "\n".join(f"• {x}" for x in s["unlocked_lines"][:6])
            if s["unlocked_extra"] > 0:
                snap += i18n.t("profile.mybadges_snap_more", lg, n=s["unlocked_extra"])
            e.add_field(name=i18n.t("profile.mybadges_field_snap", lg), value=snap[:1024], inline=False)
        e.set_footer(text=i18n.t("profile.mybadges_footer_summary", lg))
        return e

    if section == "unlocked":
        lines = payload["unlocked"]
        chunks = _chunk_text_blocks(lines)
        e = discord.Embed(
            title=i18n.t("profile.mybadges_unlocked_title", lg, name=nm),
            description=i18n.t("profile.mybadges_unlocked_desc", lg, n=len(lines)),
            color=col,
        )
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        if not chunks:
            e.add_field(name="—", value=i18n.t("profile.mybadges_unlocked_empty", lg), inline=False)
        else:
            for i, ch in enumerate(chunks[:6]):
                name = i18n.t("profile.mybadges_field_list", lg) if i == 0 else i18n.t("profile.mybadges_field_cont", lg, i=i + 1)
                e.add_field(name=name, value=ch[:1024], inline=False)
            if len(chunks) > 6:
                e.add_field(name="…", value=i18n.t("profile.mybadges_trunc", lg), inline=False)
        e.set_footer(text=i18n.t("profile.mybadges_footer_unlocked", lg))
        return e

    if section == "locked":
        lines = payload["locked"]
        chunks = _chunk_text_blocks(lines)
        e = discord.Embed(
            title=i18n.t("profile.mybadges_locked_title", lg, name=nm),
            description=i18n.t("profile.mybadges_locked_desc", lg, n=len(lines)),
            color=col,
        )
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        if not chunks:
            e.add_field(name="—", value=i18n.t("profile.mybadges_locked_empty", lg), inline=False)
        else:
            for i, ch in enumerate(chunks[:6]):
                name = i18n.t("profile.mybadges_field_progress", lg) if i == 0 else i18n.t("profile.mybadges_field_cont", lg, i=i + 1)
                e.add_field(name=name, value=ch[:1024], inline=False)
        e.set_footer(text=i18n.t("profile.mybadges_footer_locked", lg))
        return e

    # mystery
    lines = payload["mystery"]
    e = discord.Embed(
        title=i18n.t("profile.mybadges_mystery_title", lg, name=nm),
        description=i18n.t("profile.mybadges_mystery_desc", lg),
        color=col,
    )
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    if not lines:
        e.add_field(name="—", value=i18n.t("profile.mybadges_mystery_empty", lg), inline=False)
    else:
        e.add_field(name=i18n.t("profile.mybadges_mystery_field", lg), value="\n".join(lines)[:1024], inline=False)
    e.set_footer(text=i18n.t("profile.mybadges_footer_mystery", lg))
    return e


class MyBadgesNavigator(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        author: discord.abc.User,
        bot: commands.Bot,
        payload: dict[str, Any],
        section: str = "summary",
        *,
        lang: str,
    ):
        super().__init__(timeout=3600.0)
        self.ctx = ctx
        self.author = author
        self.bot = bot
        self.payload = payload
        self.section = section
        self.lang = lang
        self.add_item(MyBadgesSectionSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                i18n.t("profile.mybadges_panel_nope", self.lang),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for c in self.children:
            if isinstance(c, (discord.ui.Button, discord.ui.Select)):
                c.disabled = True


class MyBadgesSectionSelect(discord.ui.Select):
    def __init__(self, nav: MyBadgesNavigator):
        self.nav = nav
        lg = nav.lang
        sec = nav.section
        opts = [
            discord.SelectOption(
                label=i18n.t("profile.mybadges_opt_summary_l", lg)[:100],
                value="summary",
                emoji="📊",
                description=i18n.t("profile.mybadges_opt_summary_d", lg)[:100],
                default=(sec == "summary"),
            ),
            discord.SelectOption(
                label=i18n.t("profile.mybadges_opt_unlocked_l", lg)[:100],
                value="unlocked",
                emoji="✅",
                description=i18n.t("profile.mybadges_opt_unlocked_d", lg)[:100],
                default=(sec == "unlocked"),
            ),
            discord.SelectOption(
                label=i18n.t("profile.mybadges_opt_locked_l", lg)[:100],
                value="locked",
                emoji="🎯",
                description=i18n.t("profile.mybadges_opt_locked_d", lg)[:100],
                default=(sec == "locked"),
            ),
            discord.SelectOption(
                label=i18n.t("profile.mybadges_opt_mystery_l", lg)[:100],
                value="mystery",
                emoji="🔒",
                description=i18n.t("profile.mybadges_opt_mystery_d", lg)[:100],
                default=(sec == "mystery"),
            ),
        ]
        ph = {
            "summary": i18n.t("profile.mybadges_ph_summary", lg),
            "unlocked": i18n.t("profile.mybadges_ph_unlocked", lg),
            "locked": i18n.t("profile.mybadges_ph_locked", lg),
            "mystery": i18n.t("profile.mybadges_ph_mystery", lg),
        }.get(sec, i18n.t("profile.mybadges_ph_pick", lg))
        super().__init__(placeholder=ph, min_values=1, max_values=1, options=opts, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        sec = self.values[0]
        lg = self.nav.lang
        emb = _embed_mybadges(self.nav.ctx, self.nav.bot, self.nav.payload, sec, lg)
        nv = MyBadgesNavigator(
            self.nav.ctx,
            self.nav.author,
            self.nav.bot,
            self.nav.payload,
            section=sec,
            lang=lg,
        )
        await interaction.response.edit_message(embed=emb, view=nv)


# ---------- COG ----------
class Profile(commands.Cog):
    """Carte courte (/mycard), profil détaillé (/profile), trophées (/mybadges)."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="mycard",
        description=ui_str("slash.profile_mycard"),
    )
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def mycard(self, ctx: commands.Context) -> None:
        await core.maybe_defer_hybrid(ctx)
        lg = i18n.ctx_lang(ctx)
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
        play_line = _mycard_image_line1(mini_scores, lg)
        record_line = _mycard_image_line2(mini_scores, lg)
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
                lg=lg,
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="profile",
        description=ui_str("slash.profile_profile"),
    )
    @commands.cooldown(1, 25, commands.BucketType.user)
    async def profile_cmd(self, ctx: commands.Context) -> None:
        lg = i18n.ctx_lang(ctx)
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
        title = core.get_title_for_global_level(level, i18n.guild_lang(ctx.guild))

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
            lg=lg,
        )
        ep = is_slash and ctx.guild is not None
        if is_slash and ctx.interaction:
            await ctx.interaction.followup.send(embed=embed, ephemeral=ep)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="animefav",
        description=ui_str("slash.profile_animefav"),
    )
    @app_commands.describe(
        anime=ui_str("slash.profile_animefav_param"),
    )
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def animefav(self, ctx: commands.Context, anime: Optional[str] = None):
        """Enregistre un animé favori pour l’aperçu /mycard (AniList)."""
        lg = i18n.ctx_lang(ctx)
        is_slash = bool(getattr(ctx, "interaction", None))
        uid = ctx.author.id

        async def _send_help() -> None:
            cur = core.get_anime_favorite(uid)
            if cur:
                desc = i18n.t(
                    "profile.animefav_help_current",
                    lg,
                    title=cur["title"],
                    url=cur["site_url"],
                )
            else:
                desc = i18n.t("profile.animefav_help_none", lg)
            em = discord.Embed(
                title=i18n.t("profile.animefav_title", lg),
                description=desc,
                color=_EMBED_OVERVIEW,
            )
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
        kind, data = _resolve_anime_favorite_input(anime, lg=lg)
        if kind == "help":
            hint = i18n.t("profile.animefav_hint_empty", lg)
            if is_slash and ctx.interaction:
                await ctx.interaction.followup.send(hint, ephemeral=True)
            else:
                await ctx.reply(hint)
            return
        if kind == "error":
            err = str(data) if data else i18n.t("profile.animefav_err_generic", lg)
            if is_slash and ctx.interaction:
                await ctx.interaction.followup.send(err, ephemeral=True)
            else:
                await ctx.reply(err)
            return
        if kind == "clear":
            core.clear_anime_favorite(uid)
            msg = i18n.t("profile.animefav_cleared", lg)
            if is_slash and ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.reply(msg)
            return

        assert kind == "set" and isinstance(data, dict)
        core.set_anime_favorite(uid, data)
        msg = i18n.t("profile.animefav_set_ok", lg, title=data["title"])
        if is_slash and ctx.interaction:
            await ctx.interaction.followup.send(msg, ephemeral=True)
        else:
            await ctx.reply(msg)

    @commands.hybrid_command(
        name="animetop",
        description=ui_str("slash.profile_animetop"),
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @app_commands.describe(
        classement=ui_str("slash.profile_animetop_param"),
    )
    @app_commands.choices(
        classement=[
            app_commands.Choice(name=ui_str("slash.choice_animetop_all"), value="all"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_overview"), value="overview"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_animequiz"), value="animequiz"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_guessyear"), value="guessyear"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_guessepisodes"), value="guessepisodes"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_guessgenre"), value="guessgenre"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_guesscharacter"), value="guesscharacter"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_guesswho"), value="guesswho"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_higherlower"), value="higherlower"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_chainquiz"), value="chainquiz"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_bossraid"), value="bossraid"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_duel"), value="duel"),
            app_commands.Choice(name=ui_str("slash.choice_animetop_guessop"), value="guessop"),
        ]
    )
    async def animetop(self, ctx: commands.Context, classement: str = "all") -> None:
        lg = i18n.ctx_lang(ctx)
        key = _animetop_valid_mode((classement or "all").strip().lower())
        scope_key = int(ctx.guild.id) if ctx.guild else int(ctx.author.id)
        now = time.monotonic()
        exp = float(_ANIMETOP_ACTIVE_UNTIL.get(scope_key, 0.0))
        if exp > now:
            left = int(exp - now) + 1
            msg = (
                f"⏳ `/animetop` déjà actif. Réessaie dans **{left}s**."
                if lg != "en"
                else f"⏳ `/animetop` is already active. Try again in **{left}s**."
            )
            is_slash_busy = bool(getattr(ctx, "interaction", None))
            if is_slash_busy and ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(msg, ephemeral=True)
            elif is_slash_busy and ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return
        is_slash = bool(getattr(ctx, "interaction", None))
        if is_slash and ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        if not core.mini_game_activity_leaderboard(n=1):
            msg = i18n.t("profile.animetop_no_scores", lg)
            if is_slash and ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return

        emb = await self._animetop_make_embed(self.bot, ctx.guild, key, lg)
        _ANIMETOP_ACTIVE_UNTIL[scope_key] = now + _LEADERBOARD_TTL_SEC
        view = AnimetopLeaderboardView(
            self,
            ctx.author.id,
            ctx.guild,
            key,
            lg,
            lock_store=_ANIMETOP_ACTIVE_UNTIL,
            lock_key=scope_key,
        )
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
        lg: str,
    ) -> discord.Embed:
        m = _animetop_valid_mode(mode)
        if m == "overview":
            return await self._animetop_overview_embed(bot, guild, lg)

        n = 15
        if m == "all":
            rows = core.mini_game_activity_leaderboard(n=n)
        else:
            rows = core.mini_game_leaderboard(m, n=n)

        color = _animetop_embed_color(m)
        label = _animetop_mode_label(m, lg)

        if not rows:
            emb = discord.Embed(
                title=f"🏆 {label}",
                description=i18n.t("profile.animetop_empty_lb", lg),
                color=color,
            )
            emb.set_footer(text=i18n.t("profile.animetop_footer_names", lg))
            return emb

        names = await _animetop_names_map(bot, guild, (u for u, _ in rows), lg)
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
            description=_animetop_short_blurb(m, lg),
            color=color,
        )
        emb.add_field(name=i18n.t("profile.animetop_field_lb", lg), value=block, inline=False)
        emb.set_footer(text=i18n.t("profile.animetop_footer_defeats", lg))
        return emb

    async def _animetop_overview_embed(
        self,
        bot: commands.Bot,
        guild: Optional[discord.Guild],
        lg: str,
    ) -> discord.Embed:
        rows = core.mini_game_activity_leaderboard(n=8)
        if not rows:
            return discord.Embed(
                title=i18n.t("profile.animetop_overview_title", lg),
                description=i18n.t("profile.animetop_overview_empty", lg),
                color=_EMBED_MINIS,
            )

        uid_collect: list[int] = [u for u, _ in rows]
        sections: list[tuple[str, list[tuple[int, int]]]] = [("__total__", rows)]
        for gk in _ANITOP_GAME_KEYS:
            sub = core.mini_game_leaderboard(gk, n=3)
            if sub:
                uid_collect.extend(u for u, _ in sub)
                sections.append((gk, sub))

        names = await _animetop_names_map(bot, guild, uid_collect, lg)
        color = _animetop_embed_color("overview")
        emb = discord.Embed(
            title=i18n.t("profile.animetop_overview_title", lg),
            description=i18n.t("profile.animetop_overview_desc", lg),
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
        emb.add_field(
            name=i18n.t("profile.animetop_field_total", lg),
            value=val_total or "—",
            inline=False,
        )

        per_game_chunks: list[str] = []
        for gk, sub in sections[1:]:
            glabel = _animetop_game_label(gk, lg)
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
                name=i18n.t("profile.animetop_field_per_game", lg),
                value=per_game_block,
                inline=False,
            )

        emb.set_footer(text=i18n.t("profile.animetop_footer_defeats", lg))
        return emb

    @commands.hybrid_command(
        name="mybadges",
        description=ui_str("slash.profile_mybadges"),
    )
    async def mybadges(self, ctx: commands.Context) -> None:
        lg = i18n.ctx_lang(ctx)
        is_slash = bool(getattr(ctx, "interaction", None))
        ephemeral = bool(is_slash and ctx.guild is not None)
        await core.maybe_defer_hybrid(ctx, ephemeral=ephemeral)

        user_id = ctx.author.id
        counts = _get_user_counts(user_id)
        payload = _build_mybadges_payload(self.bot, counts, lg)
        embed = _embed_mybadges(ctx, self.bot, payload, "summary", lg)
        view = MyBadgesNavigator(ctx, ctx.author, self.bot, payload, section="summary", lang=lg)
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
        lang: str,
    ):
        self.cog = cog
        self.author_id = author_id
        self.guild = guild
        self.lang = lang
        lg = lang
        ini = _animetop_valid_mode(initial)
        opts: list[discord.SelectOption] = [
            discord.SelectOption(
                label=i18n.t("profile.animetop_sel_total_l", lg)[:100],
                value="all",
                emoji="📊",
                description=i18n.t("profile.animetop_sel_total_d", lg)[:100],
                default=(ini == "all"),
            ),
            discord.SelectOption(
                label=i18n.t("profile.animetop_sel_overview_l", lg)[:100],
                value="overview",
                emoji="🧩",
                description=i18n.t("profile.animetop_sel_overview_d", lg)[:100],
                default=(ini == "overview"),
            ),
        ]
        for key in _ANITOP_GAME_KEYS:
            opts.append(
                discord.SelectOption(
                    label=_animetop_game_label(key, lg)[:100],
                    value=key,
                    emoji="🎮",
                    description=i18n.t("profile.animetop_sel_game_d", lg)[:100],
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
        lg = self.lang
        mode = self.values[0]
        emb = await self.cog._animetop_make_embed(interaction.client, self.guild, mode, lg)
        parent = self.view
        lock_store = parent.lock_store if isinstance(parent, AnimetopLeaderboardView) else None
        lock_key = parent.lock_key if isinstance(parent, AnimetopLeaderboardView) else None
        new_view = AnimetopLeaderboardView(
            self.cog,
            self.author_id,
            self.guild,
            mode,
            lg,
            lock_store=lock_store,
            lock_key=lock_key,
        )
        await interaction.response.edit_message(embed=emb, view=new_view)
        new_view._message = interaction.message


class AnimetopLeaderboardView(discord.ui.View):
    def __init__(
        self,
        cog: Profile,
        author_id: int,
        guild: Optional[discord.Guild],
        initial: str,
        lang: str,
        *,
        lock_store: Optional[dict[int, float]] = None,
        lock_key: Optional[int] = None,
    ):
        super().__init__(timeout=_LEADERBOARD_TTL_SEC)
        ph = _animetop_select_placeholder(initial, lang)
        self.lock_store = lock_store
        self.lock_key = lock_key
        self.add_item(
            AnimetopCategorySelect(
                cog,
                author_id,
                guild,
                initial,
                placeholder=ph,
                lang=lang,
            )
        )
        self._message: Optional[discord.Message] = None

    async def on_timeout(self) -> None:
        if self.lock_store is not None and self.lock_key is not None:
            self.lock_store.pop(self.lock_key, None)
        if self._message:
            try:
                await self._message.delete()
            except Exception:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
