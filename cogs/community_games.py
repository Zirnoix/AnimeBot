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
from discord.ui import Button, View
from PIL import Image, ImageFilter

from modules import core
from modules import minigame_lock
from modules.core import normalize

LOG = logging.getLogger(__name__)

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
RAID_JOIN_SECONDS = 90.0
RAID_ROUND_SECONDS = 95.0
RAID_MAX_ROUNDS = 12
RAID_BOSS_HP = 22_000
RAID_DAMAGE_MIN = 550
RAID_DAMAGE_MAX = 980
# XP hebdo : base + bonus dégâts + MVP + plus rapide
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
    damage_by_user: dict[int, int] = field(default_factory=dict)
    hits_by_user: dict[int, int] = field(default_factory=dict)
    wrong_by_user: dict[int, int] = field(default_factory=dict)
    best_time_ms: dict[int, int] = field(default_factory=dict)
    answered_this_round: set[int] = field(default_factory=set)
    open_challenge_users: set[int] = field(default_factory=set)
    log_lines: list[str] = field(default_factory=list)
    hub_message: Optional[discord.Message] = None
    hub_view: Any = None
    round_start_ts: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


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


class RaidJoinView(View):
    """Inscription avant le combat (salon public)."""

    def __init__(self, cog: "CommunityGames", guild_id: int, channel_id: int) -> None:
        super().__init__(timeout=RAID_JOIN_SECONDS)
        self.cog = cog
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.joined: set[int] = set()

    @discord.ui.button(label="✅ S'inscrire au raid", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: Button) -> None:
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("❌ Mauvais serveur.", ephemeral=True)
            return
        self.joined.add(interaction.user.id)
        n = len(self.joined)
        await interaction.response.send_message(
            f"Tu es enregistré(e) pour ce raid. **{n}** participants pour l’instant.",
            ephemeral=True,
        )

    async def on_timeout(self) -> None:
        ch = self.cog.bot.get_channel(self.channel_id)
        if isinstance(ch, discord.TextChannel):
            await self.cog._raid_after_join(self.guild_id, ch, self.joined)


class RaidRoundHubView(View):
    """Message public : bouton pour recevoir un défi perso (éphemeral)."""

    def __init__(self, cog: "CommunityGames", state: RaidBattleState) -> None:
        super().__init__(timeout=RAID_ROUND_SECONDS)
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
        if uid in self.state.answered_this_round:
            await interaction.response.send_message(
                "Tu as déjà contribué à cette manche (dégâts infligés).",
                ephemeral=True,
            )
            return
        if uid in self.state.open_challenge_users:
            await interaction.response.send_message(
                "Tu as déjà un défi en cours — regarde tes messages **éphémères** au-dessus.",
                ephemeral=True,
            )
            return

        quiz = await self.cog._raid_fetch_char_quiz()
        if not quiz:
            await interaction.response.send_message("❌ Impossible de charger un personnage. Réessaie.", ephemeral=True)
            return

        damage = random.randint(RAID_DAMAGE_MIN, RAID_DAMAGE_MAX)
        async with self.state.lock:
            self.state.open_challenge_users.add(uid)

        pv = PersonalRaidChallengeView(
            cog=self.cog,
            state=self.state,
            hub=self,
            user_id=uid,
            quiz=quiz,
            damage=damage,
        )
        emb = discord.Embed(
            title="🎭 Ton défi (personnel)",
            description=(
                f"Manche **{self.state.round_n}/{self.state.max_rounds}** — clique sur le **bon** personnage.\n"
                f"Indice anime : _{quiz['anime_hint']}_\n"
                f"*(Mauvais choix = ce bouton disparaît pour toi seul.)*"
            ),
            color=discord.Color.dark_red(),
        )
        if quiz.get("image_url"):
            emb.set_image(url=quiz["image_url"])
        await interaction.response.send_message(embed=emb, view=pv, ephemeral=True)

    async def on_timeout(self) -> None:
        self.ended = True
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
        if self.state.hp <= 0:
            return
        ch = self.cog.bot.get_channel(self.state.channel_id)
        if isinstance(ch, discord.TextChannel):
            await self.cog._raid_after_round_timeout(self.state, ch)


class PersonalRaidChallengeView(View):
    """4 boutons — uniquement sur le message éphémère du joueur."""

    def __init__(
        self,
        *,
        cog: "CommunityGames",
        state: RaidBattleState,
        hub: RaidRoundHubView,
        user_id: int,
        quiz: dict[str, Any],
        damage: int,
    ) -> None:
        super().__init__(timeout=RAID_ROUND_SECONDS)
        self.cog = cog
        self.state = state
        self.hub = hub
        self.user_id = user_id
        self.options = quiz["options"]
        self.correct_index = quiz["correct_index"]
        self.correct_name = quiz["correct_name"]
        self.anime_hint = quiz["anime_hint"]
        self.damage = damage
        self.t0 = monotonic()
        self.resolved = False

        for i, label in enumerate(self.options):
            b = Button(label=label[:79], style=discord.ButtonStyle.primary, row=i // 2)
            b.callback = self._make_cb(i)
            self.add_item(b)

    def _make_cb(self, idx: int):
        async def _cb(interaction: discord.Interaction) -> None:
            await self._handle(interaction, idx)

        return _cb

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

        # Bonne réponse
        dt_ms = int((monotonic() - self.t0) * 1000)
        self.resolved = True
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True
        await interaction.response.edit_message(
            content=f"✅ **{self.correct_name}** — {self.anime_hint}\n"
            f"**+{self.damage}** dégâts au boss · **{dt_ms}** ms",
            embed=None,
            view=self,
        )
        await self.cog._raid_register_hit(
            interaction.user,
            self.state,
            self.damage,
            dt_ms,
            self.hub,
        )

    async def on_timeout(self) -> None:
        async with self.state.lock:
            self.state.open_challenge_users.discard(self.user_id)


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
            "options": options,
            "correct_index": correct_index,
            "correct_name": correct_name,
            "anime_hint": anime_hint,
            "image_url": img,
        }

    def _raid_hub_embed(self, state: RaidBattleState) -> discord.Embed:
        bar = _raid_hp_bar(state.hp, state.max_hp)
        pct = int(100 * state.hp / state.max_hp) if state.max_hp else 0
        total_dmg = sum(state.damage_by_user.values())
        lines = [
            f"❤️ **{state.hp}** / **{state.max_hp}** HP ({pct}%)  `{bar}`",
            f"⚔️ Dégâts cumulés (raid) : **{total_dmg}** · Inscrits : **{len(state.participants)}**",
            "",
            "**Chaque joueur inscrit** : une **question différente** (message éphémère) — pas de spam sur les mêmes boutons.",
            f"**Manche {state.round_n}/{state.max_rounds}** — ~{int(RAID_ROUND_SECONDS)} s par manche.",
        ]
        if state.log_lines:
            lines.append("")
            lines.append("**Journal (derniers coups)**")
            lines.extend(state.log_lines[-8:])
        return discord.Embed(
            title=f"👹 Boss Raid — Manche {state.round_n}/{state.max_rounds}",
            description="\n".join(lines),
            color=discord.Color.dark_red(),
        )

    async def _raid_refresh_hub(self, state: RaidBattleState) -> None:
        if not state.hub_message:
            return
        try:
            await state.hub_message.edit(embed=self._raid_hub_embed(state), view=state.hub_view)
        except Exception:
            pass

    async def _raid_after_join(self, guild_id: int, channel: discord.TextChannel, joined: set[int]) -> None:
        if not joined:
            await channel.send("❌ **Raid annulé** — aucun participant inscrit.")
            _active_raids.pop(guild_id, None)
            return

        state = RaidBattleState(
            guild_id=guild_id,
            channel_id=channel.id,
            hp=RAID_BOSS_HP,
            max_hp=RAID_BOSS_HP,
            round_n=1,
            max_rounds=RAID_MAX_ROUNDS,
            participants=set(joined),
        )
        await channel.send(
            f"✅ **{len(joined)}** participant(s). Le combat commence !\n"
            f"• **{RAID_BOSS_HP}** HP · jusqu’à **{RAID_MAX_ROUNDS}** manches (~{int(RAID_ROUND_SECONDS)} s chacune)\n"
            "• Chaque **bonne réponse** (défi perso) inflige **~{0}–{1}** dégâts.".format(
                RAID_DAMAGE_MIN, RAID_DAMAGE_MAX
            )
        )
        await self._raid_open_round(channel, state)

    async def _raid_open_round(self, channel: discord.TextChannel, state: RaidBattleState) -> None:
        if state.hp <= 0:
            await self._raid_conclude_victory(channel, state, extra_intro="")
            return
        state.answered_this_round.clear()
        state.open_challenge_users.clear()
        state.round_start_ts = monotonic()
        hub = RaidRoundHubView(self, state)
        emb = self._raid_hub_embed(state)
        msg = await channel.send(embed=emb, view=hub)
        hub.message = msg
        state.hub_message = msg
        state.hub_view = hub

    async def _raid_register_hit(
        self,
        user: discord.Member | discord.User,
        state: RaidBattleState,
        damage: int,
        dt_ms: int,
        hub: RaidRoundHubView,
    ) -> None:
        uid = user.id
        name = user.display_name if hasattr(user, "display_name") else str(user)

        ch = self.bot.get_channel(state.channel_id)
        if not isinstance(ch, discord.TextChannel):
            return

        async with state.lock:
            state.hp = max(0, state.hp - damage)
            state.damage_by_user[uid] = state.damage_by_user.get(uid, 0) + damage
            state.hits_by_user[uid] = state.hits_by_user.get(uid, 0) + 1
            prev = state.best_time_ms.get(uid)
            if prev is None or dt_ms < prev:
                state.best_time_ms[uid] = dt_ms
            state.answered_this_round.add(uid)
            state.open_challenge_users.discard(uid)
            line = f"• **{name}** · **−{damage}** HP · {dt_ms} ms — ❤️ **{state.hp}**"
            state.log_lines = state.log_lines[-14:] + [line]

        await self._raid_refresh_hub(state)

        if state.hp <= 0:
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
            await self._raid_conclude_victory(ch, state, extra_intro=f"Coup final : **{name}**.")
            return

    async def _raid_after_round_timeout(self, state: RaidBattleState, channel: discord.TextChannel) -> None:
        if not _active_raids.get(state.guild_id):
            return
        if state.hp <= 0:
            return
        await channel.send(
            f"⏰ **Fin de la manche {state.round_n}** — le boss tient encore (**{state.hp}** HP)."
        )
        if state.round_n >= state.max_rounds:
            await self._raid_force_finish(channel, state)
            return
        state.round_n += 1
        await self._raid_open_round(channel, state)

    async def _raid_force_finish(self, channel: discord.TextChannel, state: RaidBattleState) -> None:
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
        guild_id = state.guild_id
        participants = list(state.participants)
        total_dmg = sum(state.damage_by_user.values())

        mvp_uid: Optional[int] = None
        if participants:
            mvp_uid = max(participants, key=lambda u: state.damage_by_user.get(u, 0))

        fastest_uid: Optional[int] = None
        if state.best_time_ms:
            fastest_uid = min(state.best_time_ms, key=lambda u: state.best_time_ms[u])

        lines = []
        if extra_intro:
            lines.append(extra_intro)
        lines.append("**Récap XP (événement hebdo)** — merci à tous !")

        xp_lines: list[str] = []
        for uid in participants:
            share = (state.damage_by_user.get(uid, 0) / total_dmg) if total_dmg > 0 else 0.0
            xp = RAID_XP_BASE_EACH + int(RAID_XP_DAMAGE_POOL * share)
            if uid == mvp_uid and mvp_uid is not None:
                xp += RAID_XP_MVP_BONUS
            if uid == fastest_uid and fastest_uid is not None:
                xp += RAID_XP_FASTEST_BONUS
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
                badges.append("réflexe")
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
                ft.append(f"MVP dégâts : {mv.display_name}")
        if fastest_uid is not None and fastest_uid in state.best_time_ms:
            ft.append(f"Meilleur temps : {state.best_time_ms[fastest_uid]} ms")
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

        await channel.send(
            "⚔️ **BOSS RAID (hebdo)** — Inscription ouverte **~{0} s**.\n"
            "• Chaque inscrit aura **son propre** quiz (message **éphémère**) : pas de mêmes boutons pour tout le monde.\n"
            "• Le salon affiche **HP + journal** des coups. **{1}** manches max, **{2}** HP — à la fin du temps, "
            "le boss **tombe** même s’il reste des PV.\n"
            "• XP **généreuse** (base + part des dégâts + bonus MVP / plus rapide).".format(
                int(RAID_JOIN_SECONDS),
                RAID_BOSS_HP,
                RAID_MAX_ROUNDS,
            )
        )
        join_view = RaidJoinView(self, guild.id, channel.id)
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

    @raidconfig.command(name="horaire", description="Jour et heure du raid (fuseau du bot : BOT_TIMEZONE).")
    @app_commands.describe(
        weekday="0 = lundi … 6 = dimanche",
        hour="0–23",
        minute="0–59",
    )
    @app_commands.default_permissions(administrator=True)
    async def raid_horaire(
        self,
        interaction: discord.Interaction,
        weekday: app_commands.Range[int, 0, 6],
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
        await interaction.response.send_message(
            f"✅ Raid planifié : **jour {weekday}** à **{hour:02d}:{minute:02d}** (voir `BOT_TIMEZONE`).",
            ephemeral=True,
        )

    @raidconfig.command(name="activer", description="Activer ou désactiver le raid automatique.")
    @app_commands.default_permissions(administrator=True)
    async def raid_activer(self, interaction: discord.Interaction, actif: bool) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Serveur uniquement.", ephemeral=True)
            return
        cfg = _load_raid_cfg()
        cfg[str(interaction.guild.id)] = cfg.get(str(interaction.guild.id), {})
        cfg[str(interaction.guild.id)]["enabled"] = actif
        _save_raid_cfg(cfg)
        await interaction.response.send_message(f"✅ Raid auto : **{'activé' if actif else 'désactivé'}**.", ephemeral=True)

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
        await interaction.response.send_message(
            f"**Raid boss**\n"
            f"• Salon : {ch_txt}\n"
            f"• Horaire : jour **{wd}** à **{h:02d}:{m:02d}**\n"
            f"• Actif : **{cfg.get('enabled', False)}**\n"
            f"• Prochain créneau (calcul) : <t:{int(nxt.timestamp())}:F>\n"
            f"_Alerte ~1 h avant dans le salon._",
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
