"""
Mini-jeux communautaires : raid boss (planning hebdo + alerte admin), chain quiz,
« qui est-ce » (image floutée).

Commandes en slash (hybrid désactivé pour le préfixe sur les groupes admin — utiliser /).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from time import monotonic
from typing import Any, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, Select, View
from PIL import Image, ImageFilter

from modules import core
from modules import minigame_lock
from modules.core import normalize

LOG = logging.getLogger(__name__)


def _raid_guesswho_name_match(guess: str, correct_name: str, qz: Any) -> bool:
    """Accepte prénom/nom dans un ordre ou l’autre (ex. Kageyama Tobio vs Tobio Kageyama)."""
    if qz and getattr(qz, "title_matcher", None):
        if qz.title_matcher.find_matches(guess, {correct_name}):  # type: ignore[attr-defined]
            return True
    if normalize(guess) == normalize(correct_name):
        return True
    tg = tuple(sorted(normalize(guess).split()))
    tc = tuple(sorted(normalize(correct_name).split()))
    return bool(tg) and tg == tc

SLASH_ONLY_MSG = "Cette commande est réservée au **slash** : utilise `/{}` dans la barre de commandes."


async def _require_slash(ctx: commands.Context, name: str) -> bool:
    """True si on peut continuer (invocation slash)."""
    if ctx.interaction is None:
        await ctx.send(SLASH_ONLY_MSG.format(name))
        return False
    return True


RAID_DATA_PATH = os.path.join("data", "boss_raid.json")
SORT_CHAIN = ("easy", "medium", "hard")
SORT_TO_ANILIST = {
    "easy": "POPULARITY_DESC",
    "medium": "SCORE_DESC",
    "hard": "TRENDING_DESC",
}

# guesswho : division taille, flou gaussien, timeout (s), XP si victoire
GUESSWHO_MODES: dict[str, tuple[int, float, float, int]] = {
    "easy": (5, 4.0, 55.0, 18),
    "medium": (8, 6.0, 45.0, 28),
    "hard": (12, 9.0, 38.0, 42),
}

_active_raids: dict[int, bool] = {}  # guild_id -> running

# ---------- Raid boss v2 (inscription + défis perso + journal) ----------
RAID_JOIN_SECONDS = 120.0
RAID_ROUND_SECONDS = 95.0
RAID_MAX_ROUNDS = 12
# PV du boss = nombre d’inscrits × ce coefficient (ex. 2 joueurs → 12 000 HP)
RAID_HP_PER_PLAYER = 6000
# Dégâts par coup selon le mode choisi à l’inscription (min, max) — tirage aléatoire chaque manche
RAID_DAMAGE_BY_MODE: dict[str, tuple[int, int]] = {
    "guesscharacter": (400, 720),
    "guessyear": (520, 880),
    "guessepisodes": (520, 880),
    "guessgenre": (400, 720),
    "higherlower": (540, 900),
    "animequiz": (640, 1000),
    "guesswho": (660, 1020),
}
RAID_MODE_DEFAULT = "guesscharacter"
# XP bonus « coup final » (s’ajoute à la part dégâts / MVP / temps), selon difficulté du mode choisi
RAID_XP_FINISHER_BY_MODE: dict[str, int] = {
    "guesscharacter": 12,
    "guessyear": 22,
    "guessepisodes": 22,
    "guessgenre": 12,
    "higherlower": 24,
    "animequiz": 38,
    "guesswho": 40,
}
RAID_MODE_LABEL_FR: dict[str, str] = {
    "guesscharacter": "Personnage (4 choix)",
    "guessyear": "Année de diffusion",
    "guessepisodes": "Nombre d’épisodes",
    "guessgenre": "Genre",
    "higherlower": "Plus populaire (2 animés)",
    "animequiz": "Anime — affiche",
    "guesswho": "Qui est-ce ? (flou + nom)",
}
# Ajustement gameplay : facile = plus de pistes / logique simple ; difficile = guesswho / affiche
RAID_MODE_DIFFICULTY_FR: dict[str, str] = {
    "guesscharacter": "Facile",
    "guessyear": "Moyen",
    "guessepisodes": "Moyen",
    "guessgenre": "Facile",
    "higherlower": "Moyen",
    "animequiz": "Difficile",
    "guesswho": "Difficile",
}

# Ordre du menu d’inscription : facile → moyen → difficile (pas l’ordre arbitraire du dict).
RAID_MODE_SELECT_ORDER: tuple[str, ...] = (
    "guesscharacter",
    "guessgenre",
    "guessyear",
    "guessepisodes",
    "higherlower",
    "animequiz",
    "guesswho",
)


def _raid_max_hp_for_players(n: int) -> int:
    """Échelle les PV selon l’équipe (minimum 1 joueur)."""
    n = max(1, int(n))
    return RAID_HP_PER_PLAYER * n
# XP hebdo : base + bonus dégâts + MVP + meilleur temps sur une manche + coup final
RAID_XP_BASE_EACH = 110
RAID_XP_DAMAGE_POOL = 320
RAID_XP_MVP_BONUS = 55
RAID_XP_FASTEST_BONUS = 40


@dataclass
class RaidBattleState:
    guild_id: int
    channel_id: int
    hp: int
    max_hp: int
    round_n: int
    max_rounds: int
    participants: set[int]
    player_modes: dict[int, str] = field(default_factory=dict)
    damage_by_user: dict[int, int] = field(default_factory=dict)
    hits_by_user: dict[int, int] = field(default_factory=dict)
    wrong_by_user: dict[int, int] = field(default_factory=dict)
    best_time_ms: dict[int, int] = field(default_factory=dict)
    final_blow: Optional[tuple[int, str]] = None
    answered_this_round: set[int] = field(default_factory=set)
    round_finished_users: set[int] = field(default_factory=set)
    round_early_scheduled: bool = False
    open_challenge_users: set[int] = field(default_factory=set)
    log_lines: list[str] = field(default_factory=list)
    hub_message: Optional[discord.Message] = None
    hub_view: Any = None
    round_start_ts: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Timer de manche indépendant du View (évite le reset du timeout à chaque edit du message)
    round_timer_task: Optional[asyncio.Task] = field(default=None)
    round_timer_generation: int = 0
    raid_start_ts: float = 0.0


def _load_raid_cfg() -> dict[str, Any]:
    try:
        with open(RAID_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_raid_cfg(data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(RAID_DATA_PATH) or ".", exist_ok=True)
    with open(RAID_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _raid_target_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """Salon configuré pour le raid (`/raidconfig canal`), sinon None."""
    cfg = _load_raid_cfg().get(str(guild.id), {})
    cid = cfg.get("channel_id")
    if not cid:
        return None
    ch = guild.get_channel(int(cid))
    if isinstance(ch, discord.TextChannel):
        return ch
    return None


def _next_raid_moment(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    """Prochaine occurrence weekday (0=lun) + heure:minute après `now`."""
    tz = now.tzinfo or core.TIMEZONE
    wd = int(weekday) % 7
    for delta in range(14):
        day = (now + timedelta(days=delta)).date()
        if day.weekday() != wd:
            continue
        cand = datetime.combine(day, time(hour, minute), tzinfo=tz)
        if cand > now:
            return cand
    return now + timedelta(days=7)


# ---------- Boss raid : combat (v2) ----------


def _raid_hp_bar(hp: int, max_hp: int, width: int = 14) -> str:
    if max_hp <= 0:
        return "░" * width
    filled = int(round(width * hp / max_hp))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


class RaidModeSelect(Select):
    """Menu : mode de défi pour tout le raid (une fois choisi, inchangé)."""

    def __init__(self, host: "RaidModeSelectView") -> None:
        self.host = host
        opts = []
        for k in RAID_MODE_SELECT_ORDER:
            if k not in RAID_DAMAGE_BY_MODE:
                continue
            tier = RAID_MODE_DIFFICULTY_FR.get(k, "")
            lbl = RAID_MODE_LABEL_FR.get(k, k)
            label = f"{tier} · {lbl}"[:100]
            lo, hi = RAID_DAMAGE_BY_MODE[k]
            fin = RAID_XP_FINISHER_BY_MODE.get(k, 0)
            desc = f"~{lo}–{hi} dmg · coup final +{fin} XP"[:100]
            opts.append(discord.SelectOption(label=label, value=k, description=desc))
        super().__init__(
            placeholder="🎯 Type de mini-jeu pour ce raid…",
            min_values=1,
            max_values=1,
            options=opts,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.host.picker_id:
            await interaction.response.send_message("❌ Ce menu n’est pas pour toi.", ephemeral=True)
            return
        mode = (self.values[0] if self.values else RAID_MODE_DEFAULT) or RAID_MODE_DEFAULT
        self.host.join_view.mode_by_user[self.host.picker_id] = mode
        label = RAID_MODE_LABEL_FR.get(mode, mode)
        tier = RAID_MODE_DIFFICULTY_FR.get(mode, "")
        lo, hi = RAID_DAMAGE_BY_MODE.get(mode, (400, 720))
        fin = RAID_XP_FINISHER_BY_MODE.get(mode, 12)
        await interaction.response.edit_message(
            content=(
                f"✅ Mode enregistré : **{label}** ({tier})\n"
                f"• Dégâts par bonne réponse (tirage) : **~{lo}–{hi}**\n"
                f"• Bonus **XP coup final** si tu achèves le boss : **+{fin}** (hors répartition dégâts / MVP / temps)."
            ),
            embed=None,
            view=None,
        )
        self.host.stop()


class RaidModeSelectView(View):
    def __init__(self, join_view: "RaidJoinView", picker_id: int) -> None:
        super().__init__(timeout=RAID_JOIN_SECONDS)
        self.join_view = join_view
        self.picker_id = picker_id
        self.add_item(RaidModeSelect(self))


class RaidJoinView(View):
    """Inscription avant le combat (salon public)."""

    def __init__(self, cog: "CommunityGames", guild_id: int, channel_id: int) -> None:
        super().__init__(timeout=RAID_JOIN_SECONDS)
        self.cog = cog
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.joined: set[int] = set()
        self.mode_by_user: dict[int, str] = {}
        self.message: Optional[discord.Message] = None
        self.promo_message: Optional[discord.Message] = None

    @discord.ui.button(label="✅ S'inscrire au raid", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: Button) -> None:
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("❌ Mauvais serveur.", ephemeral=True)
            return
        uid = interaction.user.id
        self.joined.add(uid)
        n = len(self.joined)
        await interaction.response.send_message(
            f"Tu es enregistré(e) pour ce raid. **{n}** participants pour l’instant.",
            ephemeral=True,
        )
        em = discord.Embed(
            title="🎮 Choix du mini-jeu (visible par toi seul)",
            description=(
                "Sélectionne le **type de défi** pour **toutes** tes manches.\n"
                "• **Facile** = personnage (4 choix) et **genre**. **Moyen** = année, épisodes, plus populaire. "
                "**Difficile** = affiche (anime quiz) et qui est-ce flou.\n"
                "• Modes plus durs → **dégâts** et **bonus coup final** plus élevés.\n"
                "• _Sans choix avant la fin du timer d’inscription → mode **"
                + RAID_MODE_LABEL_FR.get(RAID_MODE_DEFAULT, "Personnage")
                + "**._"
            ),
            color=discord.Color.dark_red(),
        )
        await interaction.followup.send(
            embed=em,
            view=RaidModeSelectView(self, uid),
            ephemeral=True,
        )

    async def on_timeout(self) -> None:
        ch = self.cog.bot.get_channel(self.channel_id)
        if isinstance(ch, discord.TextChannel):
            await self.cog._raid_after_join(self.guild_id, ch, self)


class RaidRoundHubView(View):
    """Message public : bouton pour recevoir un défi perso (éphemeral)."""

    def __init__(self, cog: "CommunityGames", state: RaidBattleState) -> None:
        # Pas de timeout sur le View : le délai de manche est géré par asyncio (voir _raid_round_timer)
        super().__init__(timeout=None)
        self.cog = cog
        self.state = state
        self.ended = False

    @discord.ui.button(label="🎯 Recevoir ma manche (défi perso)", style=discord.ButtonStyle.secondary)
    async def get_challenge(self, interaction: discord.Interaction, button: Button) -> None:
        if self.ended or self.state.hp <= 0:
            await interaction.response.send_message("Cette manche est terminée.", ephemeral=True)
            return
        if not interaction.guild or interaction.guild.id != self.state.guild_id:
            await interaction.response.send_message("❌ Mauvais serveur.", ephemeral=True)
            return
        uid = interaction.user.id
        if uid not in self.state.participants:
            await interaction.response.send_message(
                "Tu n’étais pas inscrit(e) au début du raid. Tu peux regarder le combat dans le salon.",
                ephemeral=True,
            )
            return
        if uid in self.state.round_finished_users:
            await interaction.response.send_message(
                "Tu as déjà terminé ta manche (réponse donnée ou temps écoulé).",
                ephemeral=True,
            )
            return
        if uid in self.state.open_challenge_users:
            await interaction.response.send_message(
                "Tu as déjà un défi en cours — regarde tes messages **éphémères** au-dessus.",
                ephemeral=True,
            )
            return

        mode = self.state.player_modes.get(uid, RAID_MODE_DEFAULT)
        quiz, attach = await self.cog._raid_build_challenge(mode, self.state.round_n, self.state.max_rounds)
        if not quiz:
            await interaction.response.send_message("❌ Impossible de charger un défi. Réessaie.", ephemeral=True)
            return

        lo, hi = RAID_DAMAGE_BY_MODE.get(mode, RAID_DAMAGE_BY_MODE[RAID_MODE_DEFAULT])
        damage = random.randint(lo, hi)
        async with self.state.lock:
            self.state.open_challenge_users.add(uid)

        try:
            if str(quiz.get("kind") or "") == "guesswho_text":
                emb = discord.Embed(
                    title="🕵️ Qui est-ce ? (raid)",
                    description=quiz.get("prompt", "").strip() or "Tape le nom du personnage dans ce salon.",
                    color=discord.Color.dark_red(),
                )
                if quiz.get("image_url"):
                    emb.set_image(url=quiz["image_url"])
                send_kw: dict[str, Any] = {"embed": emb, "ephemeral": True}
                if attach is not None:
                    send_kw["file"] = attach
                await interaction.response.send_message(**send_kw)
                asyncio.create_task(
                    self.cog._raid_run_guesswho_text(
                        interaction,
                        self.state,
                        self,
                        uid,
                        quiz,
                        damage,
                        mode,
                    )
                )
                return

            pv = PersonalRaidChallengeView(
                cog=self.cog,
                state=self.state,
                hub=self,
                user_id=uid,
                quiz=quiz,
                damage=damage,
                raid_mode=mode,
            )
            emb = discord.Embed(
                title="🎭 Ton défi (personnel)",
                description=quiz.get("prompt", "").strip() or "Réponds correctement pour infliger des dégâts.",
                color=discord.Color.dark_red(),
            )
            if quiz.get("image_url"):
                emb.set_image(url=quiz["image_url"])
            send_kw = {"embed": emb, "view": pv, "ephemeral": True}
            if attach is not None:
                send_kw["file"] = attach
            await interaction.response.send_message(**send_kw)
        except Exception:
            async with self.state.lock:
                self.state.open_challenge_users.discard(uid)
            raise


class PersonalRaidChallengeView(View):
    """Boutons de choix — message éphémère du joueur (mode raid variable)."""

    def __init__(
        self,
        *,
        cog: "CommunityGames",
        state: RaidBattleState,
        hub: RaidRoundHubView,
        user_id: int,
        quiz: dict[str, Any],
        damage: int,
        raid_mode: str,
    ) -> None:
        super().__init__(timeout=RAID_ROUND_SECONDS)
        self.cog = cog
        self.state = state
        self.hub = hub
        self.user_id = user_id
        self.quiz = quiz
        self.options = list(quiz.get("options") or [])
        self.correct_index = int(quiz.get("correct_index", 0))
        self.correct_name = str(quiz.get("correct_name", "?"))
        self.anime_hint = str(quiz.get("anime_hint", ""))
        self.damage = damage
        self.raid_mode = raid_mode
        self.t0 = monotonic()
        self.resolved = False

        for i, label in enumerate(self.options):
            b = Button(label=str(label)[:79], style=discord.ButtonStyle.primary, row=i // 2)
            b.callback = self._make_cb(i)
            self.add_item(b)

    def _make_cb(self, idx: int):
        async def _cb(interaction: discord.Interaction) -> None:
            await self._handle(interaction, idx)

        return _cb

    def _success_lines(self, dt_ms: int) -> str:
        extra = str(self.quiz.get("success_extra") or "").strip()
        kind = str(self.quiz.get("kind") or "")
        if kind == "higherlower" and not extra:
            t1 = self.quiz.get("hl_title1", "?")
            t2 = self.quiz.get("hl_title2", "?")
            p1 = self.quiz.get("hl_pop1", 0)
            p2 = self.quiz.get("hl_pop2", 0)
            extra = f"**{t1}** ({p1}) vs **{t2}** ({p2})"
        head = f"✅ **{self.correct_name}**"
        if self.anime_hint and self.anime_hint != "—":
            head += f" — _{self.anime_hint}_"
        lines = [head]
        if extra:
            lines.append(extra)
        lines.append(f"**+{self.damage}** dégâts au boss · **{dt_ms}** ms")
        return "\n".join(lines)

    async def _handle(self, interaction: discord.Interaction, idx: int) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Ce n’est pas ton défi.", ephemeral=True)
            return
        if self.resolved:
            try:
                await interaction.response.defer(ephemeral=True)
            except Exception:
                pass
            return

        if idx != self.correct_index:
            async with self.state.lock:
                self.state.wrong_by_user[self.user_id] = self.state.wrong_by_user.get(self.user_id, 0) + 1
            for i, child in enumerate(self.children):
                if isinstance(child, Button) and i == idx:
                    child.disabled = True
                    break
            await interaction.response.edit_message(view=self)
            return

        dt_ms = int((monotonic() - self.t0) * 1000)
        self.resolved = True
        applied = await self.cog._raid_register_hit(
            interaction.user,
            self.state,
            self.damage,
            dt_ms,
            self.hub,
            self.raid_mode,
        )
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True
        if not applied:
            await interaction.response.edit_message(
                content="🏆 Le boss est déjà vaincu — cette réponse n’a pas été comptée.",
                embed=None,
                view=self,
                attachments=[],
            )
            return
        await interaction.response.edit_message(
            content=self._success_lines(dt_ms),
            embed=None,
            view=self,
            attachments=[],
        )

    async def on_timeout(self) -> None:
        ch = self.cog.bot.get_channel(self.state.channel_id)
        async with self.state.lock:
            self.state.open_challenge_users.discard(self.user_id)
            self.state.round_finished_users.add(self.user_id)
        if isinstance(ch, discord.TextChannel):
            await self.cog._raid_maybe_finish_round_early(self.state, self.hub)


class CommunityGames(commands.Cog):
    """Raid boss, chain quiz, guesswho."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.raid_scheduler.start()

    async def cog_unload(self) -> None:
        self.raid_scheduler.cancel()

    # ---------- Raid : logique ----------

    async def _raid_fetch_char_quiz(self) -> Optional[dict[str, Any]]:
        page = random.randint(1, 100)
        query = """
        query ($page: Int) {
          Page(page: $page, perPage: 4) {
            characters(sort: FAVOURITES_DESC) {
              name { full }
              image { large }
              media(type: ANIME) { nodes { title { romaji } } }
            }
          }
        }
        """
        data = core.query_anilist(query, {"page": page})
        if not data or "data" not in data:
            return None
        chars = data["data"]["Page"]["characters"]
        if len(chars) < 4:
            return None
        correct = random.choice(chars)
        correct_name = correct["name"]["full"]
        img = (correct.get("image") or {}).get("large")
        nodes = (correct.get("media") or {}).get("nodes") or []
        anime_hint = (nodes[0]["title"]["romaji"] if nodes else "—")
        options = [c["name"]["full"] for c in chars]
        random.shuffle(options)
        try:
            correct_index = options.index(correct_name)
        except ValueError:
            correct_index = 0
        return {
            "kind": "guesscharacter",
            "options": options,
            "correct_index": correct_index,
            "correct_name": correct_name,
            "anime_hint": anime_hint,
            "image_url": img,
        }

    def _raid_pick_wrong_years(self, correct: int, n: int = 3) -> list[int]:
        out: set[int] = set()
        guard = 0
        while len(out) < n and guard < 80:
            guard += 1
            delta = random.randint(-28, 28)
            y = correct + delta
            if y != correct and 1960 <= y <= datetime.now().year + 1:
                out.add(y)
        while len(out) < n:
            out.add(correct + 7 + len(out))
        return list(out)[:n]

    async def _raid_build_challenge(
        self,
        mode: str,
        round_n: int,
        max_rounds: int,
    ) -> tuple[Optional[dict[str, Any]], Optional[discord.File]]:
        m = mode if mode in RAID_DAMAGE_BY_MODE else RAID_MODE_DEFAULT
        rn, mr = int(round_n), int(max_rounds)

        if m == "guesscharacter":
            q = await self._raid_fetch_char_quiz()
            if not q:
                return None, None
            q["prompt"] = (
                f"Manche **{rn}/{mr}** — clique sur le **bon** personnage.\n"
                f"Indice anime : _{q.get('anime_hint', '—')}_\n"
                "*(Mauvais choix = ce bouton disparaît pour toi seul.)*"
            )
            return q, None

        if m == "guessyear":
            page = random.randint(1, 400)
            query = """
            query ($page: Int) {
              Page(perPage: 1, page: $page) {
                media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                  title { romaji }
                  startDate { year }
                  coverImage { extraLarge }
                }
              }
            }
            """
            data = core.query_anilist(query, {"page": page})
            try:
                anime = data["data"]["Page"]["media"][0]
                title = (anime.get("title") or {}).get("romaji") or "?"
                year = (anime.get("startDate") or {}).get("year")
            except Exception:
                return None, None
            if not year:
                return None, None
            year = int(year)
            wrong = self._raid_pick_wrong_years(year, 3)
            options = [year] + wrong
            random.shuffle(options)
            quiz = {
                "kind": "guessyear",
                "options": [str(x) for x in options],
                "correct_index": options.index(year),
                "correct_name": str(year),
                "anime_hint": title,
                "image_url": (anime.get("coverImage") or {}).get("extraLarge"),
                "prompt": (
                    f"Manche **{rn}/{mr}** — en quelle année **{title}** a-t-il commencé ?\n"
                    "*(Mauvais choix = bouton désactivé.)*"

                ),
            }
            return quiz, None

        if m == "guessepisodes":
            anime = None
            for _ in range(6):
                page = random.randint(1, 400)
                query = """
                query ($page: Int) {
                  Page(perPage: 1, page: $page) {
                    media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                      title { romaji }
                      episodes
                      coverImage { extraLarge }
                    }
                  }
                }
                """
                data = core.query_anilist(query, {"page": page})
                try:
                    cand = data["data"]["Page"]["media"][0]
                    ep = cand.get("episodes")
                    if ep and isinstance(ep, int):
                        anime = cand
                        break
                except Exception:
                    continue
            if not anime:
                return None, None
            title = (anime.get("title") or {}).get("romaji") or "?"
            episodes = int(anime["episodes"])
            candidates: list[int] = [episodes]
            guard = 0
            while len(candidates) < 4 and guard < 80:
                guard += 1
                alt = max(1, episodes + random.randint(-22, 22))
                if alt not in candidates:
                    candidates.append(alt)
            options = candidates[:4]
            random.shuffle(options)
            quiz = {
                "kind": "guessepisodes",
                "options": [str(x) for x in options],
                "correct_index": options.index(episodes),
                "correct_name": str(episodes),
                "anime_hint": title,
                "image_url": (anime.get("coverImage") or {}).get("extraLarge"),
                "prompt": (
                    f"Manche **{rn}/{mr}** — combien d’épisodes pour **{title}** ?\n"
                    "*(Mauvais choix = bouton désactivé.)*"
                ),
            }
            return quiz, None

        if m == "guessgenre":
            anime = None
            for _ in range(6):
                page = random.randint(1, 400)
                query = """
                query ($page: Int) {
                  Page(perPage: 1, page: $page) {
                    media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                      title { romaji }
                      genres
                      coverImage { extraLarge }
                    }
                  }
                }
                """
                data = core.query_anilist(query, {"page": page})
                try:
                    cand = data["data"]["Page"]["media"][0]
                    if cand.get("genres"):
                        anime = cand
                        break
                except Exception:
                    continue
            if not anime:
                return None, None
            title = (anime.get("title") or {}).get("romaji") or "?"
            genres = list(anime.get("genres") or [])
            correct = random.choice(genres)
            pool_extra = [
                "Psychological", "Sports", "Music", "Mecha", "Military",
                "Historical", "Samurai", "Thriller", "Horror", "Mystery",
            ]
            wrong: list[str] = []
            for g in pool_extra:
                if g not in genres and g != correct:
                    wrong.append(g)
                if len(wrong) >= 3:
                    break
            for g in genres:
                if g != correct and len(wrong) < 3:
                    wrong.append(g)
            options = [correct] + wrong[:3]
            filler = [
                "Isekai", "Mystery", "School", "Supernatural", "Kids",
                "Shounen", "Shoujo", "Seinen", "Josei", "Dementia",
            ]
            for g in filler:
                if len(options) >= 4:
                    break
                if g not in options and g not in genres:
                    options.append(g)
            options = options[:4]
            random.shuffle(options)
            quiz = {
                "kind": "guessgenre",
                "options": options,
                "correct_index": options.index(correct),
                "correct_name": correct,
                "anime_hint": title,
                "image_url": (anime.get("coverImage") or {}).get("extraLarge"),
                "prompt": (
                    f"Manche **{rn}/{mr}** — quel genre parmi ces choix correspond à **{title}** ?\n"
                    "*(Un seul est valide ici — format liste AniList.)*"
                ),
            }
            return quiz, None

        if m == "higherlower":
            page = random.randint(1, 20)
            query = """
            query ($page: Int) {
              Page(perPage: 50, page: $page) {
                media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                  title { romaji }
                  popularity
                  coverImage { extraLarge }
                }
              }
            }
            """
            data = core.query_anilist(query, {"page": page})
            try:
                medias = data["data"]["Page"]["media"]
            except Exception:
                return None, None
            if not medias or len(medias) < 2:
                return None, None
            a, b = random.sample(medias, 2)
            t1 = (a.get("title") or {}).get("romaji") or "?"
            t2 = (b.get("title") or {}).get("romaji") or "?"
            p1 = int(a.get("popularity") or 0)
            p2 = int(b.get("popularity") or 0)
            correct_index = 0 if p1 >= p2 else 1
            winner = t1 if correct_index == 0 else t2
            quiz = {
                "kind": "higherlower",
                "options": [f"1️⃣ {t1[:60]}", f"2️⃣ {t2[:60]}"],
                "correct_index": correct_index,
                "correct_name": f"Le plus populaire : {winner}",
                "anime_hint": "Popularité AniList",
                "image_url": None,
                "hl_title1": t1,
                "hl_title2": t2,
                "hl_pop1": p1,
                "hl_pop2": p2,
                "prompt": (
                    f"Manche **{rn}/{mr}** — lequel est le **plus populaire** sur AniList ?\n"
                    f"**1️⃣** {t1}\n**2️⃣** {t2}"
                ),
            }
            return quiz, None

        if m == "animequiz":
            page = random.randint(1, 80)
            query = """
            query ($page: Int) {
              Page(page: $page, perPage: 4) {
                media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                  title { romaji }
                  coverImage { extraLarge }
                }
              }
            }
            """
            data = core.query_anilist(query, {"page": page})
            try:
                medias = data["data"]["Page"]["media"]
            except Exception:
                return None, None
            if not medias or len(medias) < 4:
                return None, None
            correct = random.choice(medias)
            ctitle = (correct.get("title") or {}).get("romaji") or "?"
            options = [(m.get("title") or {}).get("romaji") or "?" for m in medias]
            random.shuffle(options)
            quiz = {
                "kind": "animequiz",
                "options": options,
                "correct_index": options.index(ctitle),
                "correct_name": ctitle,
                "anime_hint": "—",
                "image_url": (correct.get("coverImage") or {}).get("extraLarge"),
                "prompt": (
                    f"Manche **{rn}/{mr}** — quel est cet anime **d’après l’affiche** ?\n"
                    "*(Mauvais choix = bouton désactivé.)*"
                ),
            }
            return quiz, None

        if m == "guesswho":
            page = random.randint(1, 100)
            query = """
            query ($page: Int) {
              Page(page: $page, perPage: 1) {
                characters(sort: FAVOURITES_DESC) {
                  name { full }
                  image { large }
                  media(type: ANIME) { nodes { title { romaji } } }
                }
              }
            }
            """
            data = core.query_anilist(query, {"page": page})
            if not data or "data" not in data:
                return None, None
            chars = data["data"]["Page"]["characters"]
            if not chars:
                return None, None
            correct = chars[0]
            correct_name = correct["name"]["full"]
            url = (correct.get("image") or {}).get("large")
            nodes = (correct.get("media") or {}).get("nodes") or []
            anime_hint = (nodes[0]["title"]["romaji"] if nodes else "—")
            div, blur_r, _gw_to, _xp = GUESSWHO_MODES.get("medium", GUESSWHO_MODES["medium"])
            quiz = {
                "kind": "guesswho_text",
                "correct_name": correct_name,
                "anime_hint": anime_hint,
                "image_url": "attachment://raid_guesswho.png",
                "prompt": (
                    f"Manche **{rn}/{mr}** — **tape le nom du personnage dans ce salon** (comme **`/guesswho`**).\n"
                    f"Indice anime : _{anime_hint}_ · **Une tentative** — ~{int(RAID_ROUND_SECONDS)} s.\n"
                    "_Ta réponse sera **supprimée** du salon dès envoi (si le bot a « Gérer les messages »), pour limiter les spoilers._"
                ),
            }
            if not url:
                quiz["image_url"] = None
                return quiz, None
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        raw = await resp.read()
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                d = max(3, int(div))
                im = im.resize((max(32, im.width // d), max(32, im.height // d)), Image.Resampling.LANCZOS)
                im = im.resize((im.width * d, im.height * d), Image.Resampling.NEAREST)
                im = im.filter(ImageFilter.GaussianBlur(radius=float(blur_r)))
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                buf.seek(0)
                return quiz, discord.File(buf, filename="raid_guesswho.png")
            except Exception:
                LOG.warning("raid guesswho blur failed", exc_info=True)
                quiz["image_url"] = (correct.get("image") or {}).get("large")
                return quiz, None

        q = await self._raid_fetch_char_quiz()
        return (q, None) if q else (None, None)

    def _raid_hub_embed(self, state: RaidBattleState) -> discord.Embed:
        bar = _raid_hp_bar(state.hp, state.max_hp)
        pct = int(100 * state.hp / state.max_hp) if state.max_hp else 0
        total_dmg = sum(state.damage_by_user.values())
        lines = [
            f"❤️ **{state.hp}** / **{state.max_hp}** HP ({pct}%)  `{bar}`",
            f"⚔️ Dégâts cumulés : **{total_dmg}** · Inscrits : **{len(state.participants)}**",
            "",
            f"**Manche {state.round_n}/{state.max_rounds}** — ~{int(RAID_ROUND_SECONDS)} s · clique **Recevoir ma manche** ci-dessous.",
        ]
        if state.log_lines:
            lines.append("")
            lines.append("**Derniers coups**")
            lines.extend(state.log_lines[-8:])
        return discord.Embed(
            title=f"👹 Boss Raid — Manche {state.round_n}/{state.max_rounds}",
            description="\n".join(lines),
            color=discord.Color.dark_red(),
        )

    async def _raid_cancel_round_timer_async(self, state: RaidBattleState) -> None:
        t = state.round_timer_task
        if t is not None and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        state.round_timer_task = None

    async def _raid_round_timer_worker(
        self,
        state: RaidBattleState,
        channel: discord.TextChannel,
        gen: int,
    ) -> None:
        """Fin de manche si le délai est écoulé (non réinitialisé par les edits du message hub)."""
        try:
            await asyncio.sleep(RAID_ROUND_SECONDS)
        except asyncio.CancelledError:
            return
        if state.round_timer_generation != gen:
            return
        if not _active_raids.get(state.guild_id):
            return
        if state.hp <= 0:
            return
        if len(state.round_finished_users) >= len(state.participants):
            return
        await self._raid_after_round_timeout(state, channel)

    async def _raid_refresh_hub(self, state: RaidBattleState) -> None:
        if not state.hub_message:
            return
        try:
            # Ne pas repasser `view=` : sinon discord.py peut réinitialiser le délai interne du View à chaque edit.
            await state.hub_message.edit(embed=self._raid_hub_embed(state))
        except Exception:
            pass

    async def _raid_after_join(self, guild_id: int, channel: discord.TextChannel, join_view: RaidJoinView) -> None:
        joined = set(join_view.joined)
        if not joined:
            await channel.send("❌ **Raid annulé** — aucun participant inscrit.")
            _active_raids.pop(guild_id, None)
            return

        n = len(joined)
        max_hp = _raid_max_hp_for_players(n)
        player_modes = {uid: join_view.mode_by_user.get(uid, RAID_MODE_DEFAULT) for uid in joined}
        try:
            if getattr(join_view, "promo_message", None):
                await join_view.promo_message.delete()
        except Exception:
            pass
        try:
            if getattr(join_view, "message", None):
                await join_view.message.delete()
        except Exception:
            pass
        state = RaidBattleState(
            guild_id=guild_id,
            channel_id=channel.id,
            hp=max_hp,
            max_hp=max_hp,
            round_n=1,
            max_rounds=RAID_MAX_ROUNDS,
            participants=set(joined),
            player_modes=player_modes,
            raid_start_ts=monotonic(),
        )
        await channel.send(
            f"✅ **{n}** participant(s) — le boss a **{max_hp}** HP "
            f"(_{RAID_HP_PER_PLAYER} × {n} selon l’équipe_).\n"
            f"• Jusqu’à **{RAID_MAX_ROUNDS}** manches — timer **~{int(RAID_ROUND_SECONDS)} s** max **par manche** "
            "si quelqu’un n’a pas encore répondu.\n"
            "• Les **dégâts par bonne réponse** dépendent du **mode** choisi à l’inscription (voir ton message éphémère) "
            "— les modes plus difficiles frappent plus fort."
        )
        await self._raid_open_round(channel, state)

    async def _raid_open_round(self, channel: discord.TextChannel, state: RaidBattleState) -> None:
        if state.hp <= 0:
            await self._raid_conclude_victory(channel, state, extra_intro="")
            return
        await self._raid_cancel_round_timer_async(state)
        state.answered_this_round.clear()
        state.round_finished_users.clear()
        state.round_early_scheduled = False
        state.open_challenge_users.clear()
        state.round_start_ts = monotonic()
        hub = RaidRoundHubView(self, state)
        emb = self._raid_hub_embed(state)
        msg = await channel.send(embed=emb, view=hub)
        hub.message = msg
        state.hub_message = msg
        state.hub_view = hub
        state.round_timer_generation += 1
        gen = state.round_timer_generation
        state.round_timer_task = asyncio.create_task(
            self._raid_round_timer_worker(state, channel, gen)
        )

    async def _raid_maybe_finish_round_early(self, state: RaidBattleState, hub: RaidRoundHubView) -> None:
        """Si tous les inscrits ont fini leur défi (bonne réponse, faux, ou temps écoulé), enchaîne la manche."""
        ch = self.bot.get_channel(state.channel_id)
        if not isinstance(ch, discord.TextChannel):
            return
        async with state.lock:
            if state.hp <= 0:
                return
            if len(state.round_finished_users) < len(state.participants):
                return
            if state.round_early_scheduled:
                return
            state.round_early_scheduled = True
        await self._raid_complete_round_early(state, ch, hub)

    async def _raid_register_hit(
        self,
        user: discord.Member | discord.User,
        state: RaidBattleState,
        damage: int,
        dt_ms: int,
        hub: RaidRoundHubView,
        raid_mode: str,
    ) -> bool:
        uid = user.id
        name = user.display_name if hasattr(user, "display_name") else str(user)

        ch = self.bot.get_channel(state.channel_id)
        if not isinstance(ch, discord.TextChannel):
            return False

        async with state.lock:
            if state.hp <= 0:
                return False
            state.hp = max(0, state.hp - damage)
            state.damage_by_user[uid] = state.damage_by_user.get(uid, 0) + damage
            state.hits_by_user[uid] = state.hits_by_user.get(uid, 0) + 1
            prev = state.best_time_ms.get(uid)
            if prev is None or dt_ms < prev:
                state.best_time_ms[uid] = dt_ms
            state.answered_this_round.add(uid)
            state.round_finished_users.add(uid)
            state.open_challenge_users.discard(uid)
            line = f"• **{name}** · **−{damage}** HP · {dt_ms} ms — ❤️ **{state.hp}**"
            state.log_lines = state.log_lines[-14:] + [line]

        await self._raid_refresh_hub(state)

        if state.hp <= 0:
            state.final_blow = (uid, raid_mode if raid_mode in RAID_DAMAGE_BY_MODE else RAID_MODE_DEFAULT)
            await self._raid_cancel_round_timer_async(state)
            hub.ended = True
            hub.stop()
            try:
                if state.hub_message:
                    await state.hub_message.edit(
                        content="🏆 **Boss vaincu !**",
                        embed=self._raid_hub_embed(state),
                        view=None,
                    )
            except Exception:
                pass
            mode_lbl = RAID_MODE_LABEL_FR.get(state.final_blow[1], state.final_blow[1])
            fin_xp = RAID_XP_FINISHER_BY_MODE.get(state.final_blow[1], 0)
            await self._raid_conclude_victory(
                ch,
                state,
                extra_intro=(
                    f"**Coup final** : **{name}** ({mode_lbl}) — **+{fin_xp}** XP bonus."
                ),
            )
            return True

        await self._raid_maybe_finish_round_early(state, hub)
        return True

    async def _raid_run_guesswho_text(
        self,
        interaction: discord.Interaction,
        state: RaidBattleState,
        hub: RaidRoundHubView,
        uid: int,
        quiz: dict[str, Any],
        damage: int,
        raid_mode: str,
    ) -> None:
        """Attend un message dans le salon du raid (même logique que /guesswho : flou + nom tapé)."""
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            async with state.lock:
                state.open_challenge_users.discard(uid)
            return

        correct_name = str(quiz.get("correct_name") or "?")
        anime_hint = str(quiz.get("anime_hint") or "")
        started_round = state.round_n
        t0 = monotonic()

        def _check(m: discord.Message) -> bool:
            return m.author.id == uid and m.channel.id == ch.id and not m.author.bot

        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=RAID_ROUND_SECONDS,
                check=_check,
            )
        except asyncio.TimeoutError:
            async with state.lock:
                if state.round_n != started_round or uid not in state.open_challenge_users:
                    return
                state.open_challenge_users.discard(uid)
                state.round_finished_users.add(uid)
            emb = discord.Embed(
                title="⏰ Temps écoulé",
                description=f"C’était **{correct_name}**.",
                color=discord.Color.orange(),
            )
            try:
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
            except Exception:
                pass
            await self._raid_maybe_finish_round_early(state, hub)
            return

        try:
            await msg.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        async with state.lock:
            if state.round_n != started_round or uid not in state.open_challenge_users:
                return

        g = (msg.content or "").strip()
        qz = self.bot.get_cog("Quiz")
        ok = _raid_guesswho_name_match(g, correct_name, qz)

        if not ok:
            async with state.lock:
                if state.round_n != started_round or uid not in state.open_challenge_users:
                    return
                state.wrong_by_user[uid] = state.wrong_by_user.get(uid, 0) + 1
                state.open_challenge_users.discard(uid)
                state.round_finished_users.add(uid)
            emb = discord.Embed(
                title="❌ Pas la bonne réponse",
                description=f"La réponse était **{correct_name}**.",
                color=discord.Color.dark_red(),
            )
            try:
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
            except Exception:
                pass
            await self._raid_maybe_finish_round_early(state, hub)
            return

        async with state.lock:
            if state.round_n != started_round or uid not in state.open_challenge_users:
                return

        dt_ms = int((monotonic() - t0) * 1000)
        applied = await self._raid_register_hit(
            interaction.user,
            state,
            damage,
            dt_ms,
            hub,
            raid_mode,
        )
        lines = [f"**{correct_name}**", f"**+{damage}** dégâts au boss · **{dt_ms}** ms"]
        if anime_hint and anime_hint != "—":
            lines.insert(1, f"Indice anime : _{anime_hint}_")
        desc = "\n".join(lines)
        try:
            if not applied:
                emb = discord.Embed(
                    title="🏆 Boss déjà vaincu",
                    description="Cette réponse n’a pas été comptée.",
                    color=discord.Color.gold(),
                )
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
            else:
                emb = discord.Embed(
                    title="✅ Bonne réponse !",
                    description=desc,
                    color=discord.Color.green(),
                )
                await interaction.edit_original_response(embed=emb, content=None, attachments=[])
        except Exception:
            pass

    async def _raid_complete_round_early(
        self,
        state: RaidBattleState,
        channel: discord.TextChannel,
        hub: RaidRoundHubView,
    ) -> None:
        """Tous les inscrits ont contribué cette manche : enchaîne sans attendre le timer."""
        if not _active_raids.get(state.guild_id):
            return
        if state.hp <= 0:
            return
        await self._raid_cancel_round_timer_async(state)
        hub.ended = True
        hub.stop()
        try:
            if state.hub_message:
                await state.hub_message.edit(
                    content="✅ **Tout le monde a répondu** — enchaînement…",
                    embed=None,
                    view=None,
                )
        except Exception:
            pass
        await channel.send(
            f"⏩ **Manche {state.round_n}** terminée (tout le monde a participé) — **{state.hp}** HP restants."
        )
        if state.round_n >= state.max_rounds:
            await self._raid_force_finish(channel, state)
            return
        state.round_n += 1
        await self._raid_open_round(channel, state)

    async def _raid_after_round_timeout(self, state: RaidBattleState, channel: discord.TextChannel) -> None:
        if not _active_raids.get(state.guild_id):
            return
        if state.hp <= 0:
            return
        state.round_timer_task = None
        hv = state.hub_view
        if hv is not None and not getattr(hv, "ended", True):
            hv.ended = True
            for c in hv.children:
                if isinstance(c, Button):
                    c.disabled = True
            try:
                if state.hub_message:
                    await state.hub_message.edit(embed=self._raid_hub_embed(state), view=hv)
            except Exception:
                pass
            try:
                hv.stop()
            except Exception:
                pass
        await channel.send(
            f"⏰ **Fin de la manche {state.round_n}** — le boss tient encore (**{state.hp}** HP)."
        )
        LOG.info(
            "raid: timeout manche %s/%s (guild %s)",
            state.round_n,
            state.max_rounds,
            state.guild_id,
        )
        if state.round_n >= state.max_rounds:
            await self._raid_force_finish(channel, state)
            return
        state.round_n += 1
        await self._raid_open_round(channel, state)

    async def _raid_force_finish(self, channel: discord.TextChannel, state: RaidBattleState) -> None:
        await self._raid_cancel_round_timer_async(state)
        extra = []
        if state.hp > 0:
            extra.append(
                f"🔥 **Dernière salve collective !** Le raid se termine : le boss tombe "
                f"(**{state.hp}** HP restants comptés comme vaincus)."
            )
            state.hp = 0
        await self._raid_conclude_victory(channel, state, extra_intro="\n".join(extra))

    async def _raid_conclude_victory(
        self,
        channel: discord.TextChannel,
        state: RaidBattleState,
        *,
        extra_intro: str = "",
    ) -> None:
        await self._raid_cancel_round_timer_async(state)
        guild_id = state.guild_id
        participants = list(state.participants)
        total_dmg = sum(state.damage_by_user.values())

        mvp_uid: Optional[int] = None
        if participants:
            mvp_uid = max(participants, key=lambda u: state.damage_by_user.get(u, 0))

        fastest_uid: Optional[int] = None
        if state.best_time_ms:
            fastest_uid = min(state.best_time_ms, key=lambda u: state.best_time_ms[u])

        fin_uid: Optional[int] = None
        fin_mode: Optional[str] = None
        if state.final_blow:
            fin_uid, fin_mode = state.final_blow[0], state.final_blow[1]

        elapsed = int(monotonic() - state.raid_start_ts) if state.raid_start_ts else 0
        emin, esec = divmod(max(0, elapsed), 60)
        dur_str = f"{emin}m {esec}s" if emin else f"{esec}s"

        summary_parts: list[str] = []
        if extra_intro:
            summary_parts.append(extra_intro.strip())
        summary_parts.append(
            f"**{len(participants)}** joueur(s) · **{state.round_n}** manche(s) · durée **~{dur_str}** · "
            f"dégâts infligés **{total_dmg}** (boss **{state.max_hp}** HP)"
        )
        lines = ["\n".join(summary_parts), "", "**XP par participant**"]

        xp_lines: list[str] = []
        for uid in participants:
            share = (state.damage_by_user.get(uid, 0) / total_dmg) if total_dmg > 0 else 0.0
            xp = RAID_XP_BASE_EACH + int(RAID_XP_DAMAGE_POOL * share)
            if uid == mvp_uid and mvp_uid is not None:
                xp += RAID_XP_MVP_BONUS
            if uid == fastest_uid and fastest_uid is not None:
                xp += RAID_XP_FASTEST_BONUS
            fin_bonus = 0
            if fin_uid is not None and uid == fin_uid and fin_mode:
                fin_bonus = int(RAID_XP_FINISHER_BY_MODE.get(fin_mode, 0))
                xp += fin_bonus
            try:
                await core.add_xp(self.bot, channel, uid, xp, announce=False)
            except Exception:
                pass
            hits = state.hits_by_user.get(uid, 0)
            if hits:
                core.add_mini_score(uid, "bossraid", hits)
            uname = "?"
            m = channel.guild.get_member(uid) if channel.guild else None
            if m:
                uname = m.display_name
            badges = []
            if uid == mvp_uid:
                badges.append("MVP dégâts")
            if uid == fastest_uid:
                badges.append("meilleur temps (1 manche)")
            if fin_uid is not None and uid == fin_uid:
                badges.append(f"coup final (+{fin_bonus} XP)")
            b = f" ({', '.join(badges)})" if badges else ""
            xp_lines.append(f"• **{uname}** — **+{xp}** XP{b} — {state.damage_by_user.get(uid, 0)} dégâts")

        emb = discord.Embed(
            title="🏁 Raid terminé",
            description="\n".join(lines + ["", "\n".join(xp_lines)]),
            color=discord.Color.gold(),
        )
        ft: list[str] = []
        if mvp_uid and channel.guild:
            mv = channel.guild.get_member(mvp_uid)
            if mv:
                ft.append(f"MVP : {mv.display_name}")
        if fastest_uid is not None and fastest_uid in state.best_time_ms:
            fu = channel.guild.get_member(fastest_uid) if channel.guild else None
            nm = fu.display_name if fu else "?"
            ft.append(f"Plus rapide : {nm} ({state.best_time_ms[fastest_uid]} ms)")
        if fin_uid is not None and fin_mode and channel.guild:
            fm = channel.guild.get_member(fin_uid)
            if fm:
                ft.append(
                    f"Coup final : {fm.display_name} (+{RAID_XP_FINISHER_BY_MODE.get(fin_mode, 0)} XP)"
                )
        if ft:
            emb.set_footer(text=" · ".join(ft))
        try:
            await channel.send(embed=emb)
        except Exception:
            pass

        _active_raids.pop(guild_id, None)

    async def _raid_abort(self, channel: discord.TextChannel, guild_id: int, reason: str) -> None:
        await channel.send(reason)
        _active_raids.pop(guild_id, None)

    async def _start_boss_raid(self, guild: discord.Guild, channel: discord.TextChannel, week_key: str) -> None:
        if _active_raids.get(guild.id):
            return
        _active_raids[guild.id] = True
        cfg = _load_raid_cfg()
        gk = str(guild.id)
        if gk in cfg:
            cfg[gk]["raid_started_for_week"] = week_key
            _save_raid_cfg(cfg)

        promo = await channel.send(
            "⚔️ **BOSS RAID (hebdo)** — Inscription ouverte **~{0} s**.\n"
            "• Chaque inscrit a **son propre** défi (boutons en **message privé au salon**).\n"
            "• **Dégâts aléatoires** par bonne réponse : fourchette selon le **mode** choisi à l’inscription.\n"
            "• Jusqu’à **{1}** manches ; PV du boss = **nombre d’inscrits** × {2}.\n"
            "• Tout le monde a **terminé** son défi (réussi, faux, ou temps écoulé) → manche suivante sans attendre la fin du timer.\n"
            "• XP : base + part des dégâts + MVP + meilleur temps sur une manche + coup final.".format(
                int(RAID_JOIN_SECONDS),
                RAID_MAX_ROUNDS,
                RAID_HP_PER_PLAYER,
            )
        )
        join_view = RaidJoinView(self, guild.id, channel.id)
        join_view.promo_message = promo
        msg = await channel.send(
            embed=discord.Embed(
                title="📋 Inscription",
                description="Clique pour participer au combat. **Salon vocal non requis.**",
                color=discord.Color.red(),
            ),
            view=join_view,
        )
        join_view.message = msg

    @tasks.loop(minutes=1.0)
    async def raid_scheduler(self) -> None:
        cfg = _load_raid_cfg()
        now = datetime.now(core.TIMEZONE)
        for gid_str, c in list(cfg.items()):
            if not c.get("enabled"):
                continue
            try:
                gid = int(gid_str)
            except ValueError:
                continue
            ch_id = c.get("channel_id")
            if not ch_id:
                continue
            channel = self.bot.get_channel(int(ch_id))
            if not isinstance(channel, discord.TextChannel):
                continue
            guild = channel.guild
            weekday = int(c.get("weekday", 5))
            hour = int(c.get("hour", 20))
            minute = int(c.get("minute", 0))
            raid_at = _next_raid_moment(now, weekday, hour, minute)
            wkey = _week_key(raid_at)
            alert_at = raid_at - timedelta(hours=1)

            if c.get("alert_sent_for_week") != wkey and alert_at <= now < raid_at:
                try:
                    await channel.send(
                        "@here ⏰ **Boss Raid** dans **1 h** — préparez-vous (quiz / persos AniList) !"
                    )
                except Exception as e:
                    LOG.warning("raid alert: %s", e)
                c["alert_sent_for_week"] = wkey
                _save_raid_cfg(cfg)

            if (
                c.get("raid_started_for_week") != wkey
                and raid_at <= now < raid_at + timedelta(minutes=4)
                and not _active_raids.get(guild.id)
            ):
                try:
                    await self._start_boss_raid(guild, channel, wkey)
                except Exception as e:
                    LOG.exception("raid auto-start: %s", e)

    @raid_scheduler.before_loop
    async def _raid_sched_before(self) -> None:
        await self.bot.wait_until_ready()

    raidconfig = app_commands.Group(
        name="raidconfig",
        description="Configurer le raid boss hebdomadaire (administrateurs uniquement).",
    )

    @raidconfig.command(name="canal", description="Définir le salon des annonces et du combat de raid.")
    @app_commands.describe(channel="Salon texte (défaut : salon actuel)")
    @app_commands.default_permissions(administrator=True)
    async def raid_canal(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("❌ Salon texte requis.", ephemeral=True)
            return
        cfg = _load_raid_cfg()
        cfg[str(interaction.guild.id)] = cfg.get(str(interaction.guild.id), {})
        cfg[str(interaction.guild.id)]["channel_id"] = ch.id
        _save_raid_cfg(cfg)
        await interaction.response.send_message(f"✅ Salon de raid : {ch.mention}", ephemeral=True)

    @raidconfig.command(name="horaire", description="Jour et heure du raid (fuseau du bot, voir BOT_TIMEZONE).")
    @app_commands.describe(
        weekday="Jour de la semaine",
        hour="0–23",
        minute="0–59",
    )
    @app_commands.choices(
        weekday=[
            app_commands.Choice(name="Lundi", value=0),
            app_commands.Choice(name="Mardi", value=1),
            app_commands.Choice(name="Mercredi", value=2),
            app_commands.Choice(name="Jeudi", value=3),
            app_commands.Choice(name="Vendredi", value=4),
            app_commands.Choice(name="Samedi", value=5),
            app_commands.Choice(name="Dimanche", value=6),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def raid_horaire(
        self,
        interaction: discord.Interaction,
        weekday: int,
        hour: app_commands.Range[int, 0, 23],
        minute: app_commands.Range[int, 0, 59],
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        cfg = _load_raid_cfg()
        cfg[str(interaction.guild.id)] = cfg.get(str(interaction.guild.id), {})
        cfg[str(interaction.guild.id)]["weekday"] = int(weekday)
        cfg[str(interaction.guild.id)]["hour"] = int(hour)
        cfg[str(interaction.guild.id)]["minute"] = int(minute)
        _save_raid_cfg(cfg)
        tzname = getattr(core.TIMEZONE, "zone", None) or str(core.TIMEZONE)
        jname = core.JOURS_SEMAINE_FR[int(weekday) % 7]
        await interaction.response.send_message(
            f"✅ Raid planifié : **{jname}** à **{hour:02d}:{minute:02d}** "
            f"(fuseau **{tzname}**, variable d’environnement **`BOT_TIMEZONE`** sur l’hébergeur).",
            ephemeral=True,
        )

    @raidconfig.command(
        name="activer",
        description="Lancer le raid automatiquement chaque semaine (sinon uniquement avec /raidstart).",
    )
    @app_commands.describe(
        actif=(
            "**Oui** : le bot ouvre l’inscription **chaque semaine** à l’horaire + rappel ~1 h avant. "
            "**Non** : pas de lancement auto (admins utilisent **`/raidstart`**)."
        ),
    )
    @app_commands.default_permissions(administrator=True)
    async def raid_activer(self, interaction: discord.Interaction, actif: bool) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        cfg = _load_raid_cfg()
        cfg[str(interaction.guild.id)] = cfg.get(str(interaction.guild.id), {})
        cfg[str(interaction.guild.id)]["enabled"] = actif
        _save_raid_cfg(cfg)
        await interaction.response.send_message(
            f"✅ Lancement **hebdomadaire automatique** : **{'oui' if actif else 'non'}**.",
            ephemeral=True,
        )

    @raidconfig.command(name="statut", description="Afficher la config actuelle du raid.")
    @app_commands.default_permissions(administrator=True)
    async def raid_statut(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        cfg = _load_raid_cfg().get(str(interaction.guild.id), {})
        ch = cfg.get("channel_id")
        ch_txt = f"<#{ch}>" if ch else "—"
        now = datetime.now(core.TIMEZONE)
        wd = int(cfg.get("weekday", 5))
        h = int(cfg.get("hour", 20))
        m = int(cfg.get("minute", 0))
        nxt = _next_raid_moment(now, wd, h, m)
        tzname = getattr(core.TIMEZONE, "zone", None) or str(core.TIMEZONE)
        jname = core.JOURS_SEMAINE_FR[wd % 7]
        auto = bool(cfg.get("enabled", False))
        await interaction.response.send_message(
            f"**Raid boss**\n"
            f"• Salon : {ch_txt}\n"
            f"• Horaire : **{jname}** à **{h:02d}:{m:02d}** (fuseau **{tzname}**)\n"
            f"• Lancement auto chaque semaine : **{'oui' if auto else 'non (utilise /raidstart)'}**\n"
            f"• Prochain créneau (calcul) : <t:{int(nxt.timestamp())}:F>\n"
            f"_Alerte ~1 h avant dans le salon du raid._",
            ephemeral=True,
        )

    @app_commands.command(name="raidstart", description="Lancer un raid boss maintenant (admin).")
    @app_commands.default_permissions(administrator=True)
    async def raid_start(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if _active_raids.get(interaction.guild.id):
            await interaction.followup.send("Un raid est déjà en cours sur ce serveur.", ephemeral=True)
            return
        target = _raid_target_channel(interaction.guild)
        if target is None:
            await interaction.followup.send(
                "❌ Aucun salon de raid configuré. Utilise d’abord **`/raidconfig canal`** (choisis le salon du raid).",
                ephemeral=True,
            )
            return
        wk = _week_key(datetime.now(core.TIMEZONE))
        await self._start_boss_raid(interaction.guild, target, wk)
        await interaction.followup.send(f"✅ Raid lancé dans {target.mention}.", ephemeral=True)

    @app_commands.command(name="raidalerttest", description="Envoie un message type « raid dans 1 h » (test admin).")
    @app_commands.default_permissions(administrator=True)
    async def raid_alert_test(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        target = _raid_target_channel(interaction.guild)
        if target is None:
            await interaction.response.send_message(
                "❌ Aucun salon de raid configuré. Utilise d’abord **`/raidconfig canal`**.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await target.send(
                "@here 🧪 **TEST** — dans 1 h ce serait l’alerte avant le **Boss Raid**.",
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Je ne peux pas envoyer de message dans {target.mention}. Vérifie les permissions du bot.",
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : `{e}`", ephemeral=True)
            return
        await interaction.followup.send(f"✅ Message de test envoyé dans {target.mention}.", ephemeral=True)

    # ---------- Chain quiz ----------

    @commands.hybrid_command(name="chainquiz", description="Enchaîne des quiz : difficulté qui monte à chaque bonne réponse.")
    async def chainquiz(self, ctx: commands.Context) -> None:
        if not await _require_slash(ctx, "chainquiz"):
            return
        uid = ctx.author.id
        if not minigame_lock.try_begin(uid, "chainquiz"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.defer(thinking=True)
            qz = self.bot.get_cog("Quiz")
            if not qz:
                await ctx.send("❌ Module quiz indisponible.")
                return

            streak = 0
            total_xp = 0
            await ctx.send(
                "⛓️ **Chain quiz** — une bonne réponse enchaîne avec une difficulté supérieure. "
                "Erreur ou `jsp` = fin. Tape le titre de l’anime (FR/EN/JP)."
            )

            while True:
                diff = SORT_CHAIN[min(streak, len(SORT_CHAIN) - 1)]
                sort_key = SORT_TO_ANILIST[diff]
                anime = await qz._fetch_random_anilist_media(sort_key)  # type: ignore[attr-defined]
                if not anime:
                    await ctx.send(core.anilist_error_user_message())
                    break
                titles = qz._titles_set(anime)  # type: ignore[attr-defined]
                embed = discord.Embed(
                    title=f"⛓️ Chain · Manche {streak + 1} ({diff})",
                    description=f"**{20 + streak * 5}s** — quel est cet anime ?",
                    color=discord.Color.gold(),
                )
                img = (anime.get("coverImage") or {}).get("extraLarge") or (anime.get("coverImage") or {}).get("large")
                if img:
                    embed.set_image(url=img)
                await ctx.send(embed=embed)
                try:
                    msg = await self.bot.wait_for(
                        "message",
                        timeout=float(20 + streak * 5),
                        check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                    )
                except asyncio.TimeoutError:
                    await ctx.send(f"⏰ Fin de chaîne à **{streak}** bonne(s) réponse(s).")
                    break
                guess = (msg.content or "").strip()
                if guess.lower() in {"jsp", "pass", "skip"}:
                    await ctx.send(f"⏭️ Arrêt — chaîne : **{streak}** · XP gagné : **{total_xp}**.")
                    break
                if qz.title_matcher.find_matches(guess, titles):  # type: ignore[attr-defined]
                    streak += 1
                    xp = 5 + min(streak, 8) * 2
                    total_xp += xp
                    await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp, announce=False)
                    core.add_mini_score(ctx.author.id, "chainquiz", 1)
                    self.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_win")
                    self.bot.dispatch("mission_progress", ctx.author.id, "_custom:quiz_solo_ok")
                    await ctx.send(f"✅ +**{xp}** XP · Chaîne **{streak}** — prochaine manche !")
                else:
                    rom = (anime.get("title") or {}).get("romaji") or "?"
                    await ctx.send(f"❌ C’était **{rom}**. Chaîne terminée : **{streak}** · XP total : **{total_xp}**.")
                    break

        finally:
            minigame_lock.end(uid)

    # ---------- Guess who (flou) ----------

    @commands.hybrid_command(
        name="guesswho",
        description="Devine le personnage sur une image floutée — difficulté = flou + récompense XP.",
    )
    @app_commands.describe(
        difficulte="Facile = un peu plus net (+18 XP). Normal (+28). Difficile = très flou (+42).",
    )
    @app_commands.choices(
        difficulte=[
            app_commands.Choice(name="Facile (+18 XP)", value="easy"),
            app_commands.Choice(name="Normal (+28 XP)", value="medium"),
            app_commands.Choice(name="Difficile (+42 XP)", value="hard"),
        ]
    )
    async def guesswho(self, ctx: commands.Context, difficulte: str = "medium") -> None:
        if not await _require_slash(ctx, "guesswho"):
            return
        uid = ctx.author.id
        if not minigame_lock.try_begin(uid, "guesswho"):
            await minigame_lock.reply_busy(ctx)
            return
        try:
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.defer(thinking=True)

            div, blur_r, timeout_sec, xp_win = GUESSWHO_MODES.get(difficulte, GUESSWHO_MODES["medium"])
            diff_label = {"easy": "Facile", "medium": "Normal", "hard": "Difficile"}.get(difficulte, "Normal")

            page = random.randint(1, 100)
            query = """
            query ($page: Int) {
              Page(page: $page, perPage: 1) {
                characters(sort: FAVOURITES_DESC) {
                  name { full }
                  image { large }
                  media(type: ANIME) { nodes { title { romaji } } }
                }
              }
            }
            """
            data = core.query_anilist(query, {"page": page})
            if not data or "data" not in data:
                await ctx.send(core.anilist_error_user_message())
                return
            chars = data["data"]["Page"]["characters"]
            if not chars:
                await ctx.send("❌ Pas de personnage.")
                return
            char = chars[0]
            name = char["name"]["full"]
            url = (char.get("image") or {}).get("large")
            nodes = (char.get("media") or {}).get("nodes") or []
            hint = nodes[0]["title"]["romaji"] if nodes else "—"

            buf = io.BytesIO()
            if url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            raw = await resp.read()
                    im = Image.open(io.BytesIO(raw)).convert("RGB")
                    d = max(3, int(div))
                    im = im.resize((max(32, im.width // d), max(32, im.height // d)), Image.Resampling.LANCZOS)
                    im = im.resize((im.width * d, im.height * d), Image.Resampling.NEAREST)
                    im = im.filter(ImageFilter.GaussianBlur(radius=float(blur_r)))
                    im.save(buf, format="PNG")
                    buf.seek(0)
                except Exception as e:
                    LOG.warning("guesswho blur: %s", e)
                    buf = None
            else:
                buf = None

            embed = discord.Embed(
                title="🕵️ Qui est-ce ?",
                description=(
                    f"**{diff_label}** — en cas de victoire : **+{xp_win} XP**.\n"
                    f"Tape le **nom du personnage** ({int(timeout_sec)} s). Indice anime : _{hint}_"
                ),
                color=discord.Color.purple(),
            )
            if buf:
                embed.set_image(url="attachment://guesswho.png")
                file = discord.File(buf, filename="guesswho.png")
                await ctx.send(embed=embed, file=file)
            else:
                await ctx.send(embed=embed)

            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=timeout_sec,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                )
            except asyncio.TimeoutError:
                await ctx.send(
                    f"⏰ Temps écoulé — c’était **{name}** "
                    f"_(difficulté **{diff_label}**, récompense prévue **+{xp_win} XP**)_."
                )
                return

            g = (msg.content or "").strip()
            qz = self.bot.get_cog("Quiz")
            ok = False
            if qz:
                ok = bool(qz.title_matcher.find_matches(g, {name}))  # type: ignore[attr-defined]
            if not ok:
                ok = normalize(g) == normalize(name)
            if ok:
                await core.add_xp(self.bot, ctx.channel, ctx.author.id, xp_win, announce=False)
                core.add_mini_score(ctx.author.id, "guesswho", 1)
                await ctx.send(
                    f"✅ Bravo ! C’était **{name}** — tu gagnes **+{xp_win} XP** "
                    f"_(**{diff_label}**)_."
                )
            else:
                await ctx.send(
                    f"❌ Ce n’était pas ça — la réponse était **{name}** "
                    f"_(**{diff_label}** aurait rapporté **+{xp_win} XP**)_."
                )

        finally:
            minigame_lock.end(uid)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityGames(bot))
