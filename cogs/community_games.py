"""
Mini-jeux communautaires : raid boss (planning hebdo + alerte admin), chain quiz,
« qui est-ce » (image floutée), bingo multijoueur.

Commandes en slash (hybrid désactivé pour le préfixe sur les groupes admin — utiliser /).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
from datetime import datetime, time, timedelta
from typing import Any, Optional, Set, Tuple

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
from PIL import Image, ImageFilter

from modules import core
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

# Lignes bingo 3×3 (indices 0–8)
_BINGO_LINES: Tuple[Tuple[int, ...], ...] = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)

_active_raids: dict[int, bool] = {}  # guild_id -> running
_bingo_lock: dict[int, bool] = {}  # channel_id -> running


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


# ---------- Boss raid : combat ----------


class BossRaidRoundView(View):
    def __init__(
        self,
        *,
        cog: CommunityGames,
        channel: discord.TextChannel,
        correct_index: int,
        options: list[str],
        correct_name: str,
        anime_hint: str,
        damage: int,
        round_n: int,
        max_rounds: int,
        hp_left: list[int],  # mutable [hp]
        guild_id: int,
    ):
        super().__init__(timeout=45.0)
        self.cog = cog
        self.channel = channel
        self.correct_index = correct_index
        self.options = options
        self.correct_name = correct_name
        self.anime_hint = anime_hint
        self.damage = damage
        self.round_n = round_n
        self.max_rounds = max_rounds
        self.hp_left = hp_left
        self.guild_id = guild_id
        self.resolved = False
        self.message: discord.Message | None = None

        for i, label in enumerate(options):
            b = Button(label=label[:79], style=discord.ButtonStyle.primary, row=i // 2)
            b.callback = self._make_cb(i)
            self.add_item(b)

    def _make_cb(self, idx: int):
        async def _cb(interaction: discord.Interaction) -> None:
            await self._handle(interaction, idx)

        return _cb

    async def _handle(self, interaction: discord.Interaction, idx: int) -> None:
        if self.resolved:
            try:
                await interaction.response.defer()
            except Exception:
                pass
            return
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("❌ Partie sur un autre serveur.", ephemeral=True)
            return

        self.resolved = True
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True

        uid = interaction.user.id
        if idx == self.correct_index:
            self.hp_left[0] = max(0, self.hp_left[0] - self.damage)
            core.add_mini_score(uid, "bossraid", 1)
            try:
                await core.add_xp(self.cog.bot, self.channel, uid, 8, announce=False)
            except Exception:
                pass
            msg = (
                f"✅ **{interaction.user.display_name}** inflige **{self.damage}** dégâts ! "
                f"*(**{self.correct_name}** — {self.anime_hint})*\n"
                f"❤️ Boss : **{self.hp_left[0]}** HP · Manche **{self.round_n}/{self.max_rounds}**"
            )
        else:
            msg = (
                f"❌ **{interaction.user.display_name}** rate ! C’était **{self.correct_name}** "
                f"({self.anime_hint}).\n"
                f"❤️ Boss : **{self.hp_left[0]}** HP"
            )

        await interaction.response.edit_message(content=msg, embed=None, view=self)

        await asyncio.sleep(2.0)
        if self.hp_left[0] <= 0:
            await self.channel.send(
                f"🏆 **Raid terminé !** Le boss est vaincu ! GG à tous — **{interaction.user.display_name}** "
                f"a porté le coup final de la manche."
            )
            _active_raids.pop(self.guild_id, None)
            return
        if self.round_n >= self.max_rounds:
            await self.channel.send(
                f"⏱️ **Fin du raid** — le boss a encore **{self.hp_left[0]}** HP. Réessayez la semaine prochaine !"
            )
            _active_raids.pop(self.guild_id, None)
            return
        await self.cog._raid_next_round(self.channel, self.guild_id, self.hp_left[0], self.round_n + 1)

    async def on_timeout(self) -> None:
        if self.resolved:
            return
        self.resolved = True
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    content=f"⏰ Temps écoulé — c’était **{self.correct_name}**. Le boss garde ses HP (**{self.hp_left[0]}**).",
                    embed=None,
                    view=self,
                )
            except Exception:
                pass
        await asyncio.sleep(2.0)
        if self.hp_left[0] > 0 and self.round_n < self.max_rounds:
            await self.cog._raid_next_round(self.channel, self.guild_id, self.hp_left[0], self.round_n + 1)
        else:
            _active_raids.pop(self.guild_id, None)


class BingoView(View):
    """Bouton Bingo — vérifie qu’une ligne complète est tirée."""

    def __init__(self, session: BingoSession):
        super().__init__(timeout=300.0)
        self.session = session
        btn = Button(label="Bingo !", style=discord.ButtonStyle.success, emoji="🎉")
        btn.callback = self._on_bingo
        self.add_item(btn)

    async def _on_bingo(self, interaction: discord.Interaction) -> None:
        await self.session.try_claim(interaction)


class BingoSession:
    def __init__(self, cog: CommunityGames, channel: discord.TextChannel, titles: list[str], order: list[int]):
        self.cog = cog
        self.channel = channel
        self.titles = titles
        self.order = order
        self.revealed: Set[int] = set()
        self.message: discord.Message | None = None
        self.view: BingoView | None = None
        self.winner_id: int | None = None
        self._task: asyncio.Task | None = None

    def grid_text(self) -> str:
        lines = []
        for r in range(3):
            row = []
            for c in range(3):
                i = r * 3 + c
                mark = "✅" if i in self.revealed else "⬜"
                t = self.titles[i][:22] + ("…" if len(self.titles[i]) > 22 else "")
                row.append(f"{mark} `{i+1}` {t}")
            lines.append(" · ".join(row))
        return "\n".join(lines)

    async def try_claim(self, interaction: discord.Interaction) -> None:
        if self.winner_id is not None:
            await interaction.response.send_message("La partie est déjà terminée.", ephemeral=True)
            return
        if len(self.revealed) < 3:
            await interaction.response.send_message("Il faut au moins **3** titres tirés pour un bingo.", ephemeral=True)
            return
        for line in _BINGO_LINES:
            if all(i in self.revealed for i in line):
                self.winner_id = interaction.user.id
                core.add_mini_score(interaction.user.id, "bingo", 1)
                try:
                    await core.add_xp(self.cog.bot, self.channel, interaction.user.id, 15, announce=False)
                except Exception:
                    pass
                cells = " · ".join(str(i + 1) for i in line)
                await interaction.response.send_message(
                    f"🎉 **{interaction.user.display_name}** crie **Bingo !** — cases **{cells}** complètes ! GG !",
                    ephemeral=False,
                )
                if self._task and not self._task.done():
                    self._task.cancel()
                _bingo_lock.pop(self.channel.id, None)
                if self.message:
                    try:
                        await self.message.edit(view=None)
                    except Exception:
                        pass
                return
        await interaction.response.send_message(
            "❌ Aucune ligne / colonne / diagonale complète avec les titres déjà tirés.", ephemeral=True
        )

    async def run_reveals(self) -> None:
        try:
            for step, idx in enumerate(self.order):
                await asyncio.sleep(5.0 if step > 0 else 1.0)
                self.revealed.add(idx)
                if self.winner_id is not None:
                    return
                if not self.message:
                    continue
                emb = discord.Embed(
                    title="🎱 Bingo anime",
                    description=self.grid_text(),
                    color=discord.Color.green(),
                )
                emb.add_field(
                    name="Dernier tirage",
                    value=f"**{self.titles[idx]}**",
                    inline=False,
                )
                emb.set_footer(text="Quand une ligne est entièrement verte dans ta tête, clique Bingo ! (réel : ✅ sur les cases).")
                try:
                    await self.message.edit(embed=emb, view=self.view)
                except Exception:
                    break
            await asyncio.sleep(2.0)
            if self.winner_id is None and self.message:
                await self.channel.send("⏱️ Fin des tirages — personne n’a validé à temps.")
        except asyncio.CancelledError:
            pass
        finally:
            _bingo_lock.pop(self.channel.id, None)


class CommunityGames(commands.Cog):
    """Raid boss, chain quiz, guesswho, bingo."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.raid_scheduler.start()

    async def cog_unload(self) -> None:
        self.raid_scheduler.cancel()

    # ---------- Raid : logique ----------

    async def _raid_next_round(
        self,
        channel: discord.TextChannel,
        guild_id: int,
        hp: int,
        round_n: int,
        max_rounds: int = 8,
    ) -> None:
        page = random.randint(1, 80)
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
            await channel.send(core.anilist_error_user_message())
            _active_raids.pop(guild_id, None)
            return
        chars = data["data"]["Page"]["characters"]
        if len(chars) < 4:
            await channel.send("❌ Pas assez de données personnages.")
            _active_raids.pop(guild_id, None)
            return
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

        hp_box = [hp]
        damage = random.randint(700, 1100)

        emb = discord.Embed(
            title=f"👹 Boss Raid — Manche {round_n}/{max_rounds}",
            description=(
                f"❤️ **{hp}** HP · Premier à cliquer sur le **bon** personnage inflige des dégâts au boss.\n"
                f"*(Anime lié : {anime_hint})*"
            ),
            color=discord.Color.dark_red(),
        )
        if img:
            emb.set_image(url=img)

        view = BossRaidRoundView(
            cog=self,
            channel=channel,
            correct_index=correct_index,
            options=options,
            correct_name=correct_name,
            anime_hint=anime_hint,
            damage=damage,
            round_n=round_n,
            max_rounds=max_rounds,
            hp_left=hp_box,
            guild_id=guild_id,
        )
        msg = await channel.send(embed=emb, view=view)
        view.message = msg

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
            "⚔️ **BOSS RAID** — La bataille commence ! Cliquez vite sur le bon personnage à chaque manche.\n"
            "_Toute l’équipe participe : le premier bon clic compte._"
        )
        await self._raid_next_round(channel, guild.id, hp=10000, round_n=1)

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
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ Salon texte serveur requis.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if _active_raids.get(interaction.guild.id):
            await interaction.followup.send("Un raid est déjà en cours sur ce serveur.", ephemeral=True)
            return
        wk = _week_key(datetime.now(core.TIMEZONE))
        await self._start_boss_raid(interaction.guild, interaction.channel, wk)
        await interaction.followup.send("✅ Raid lancé dans ce salon.", ephemeral=True)

    @app_commands.command(name="raidalerttest", description="Envoie un message type « raid dans 1 h » (test admin).")
    @app_commands.default_permissions(administrator=True)
    async def raid_alert_test(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ Salon texte requis.", ephemeral=True)
            return
        await interaction.response.send_message(
            "@here 🧪 **TEST** — dans 1 h ce serait l’alerte avant le **Boss Raid**.",
            allowed_mentions=discord.AllowedMentions.all(),
        )

    # ---------- Chain quiz ----------

    @commands.hybrid_command(name="chainquiz", description="Enchaîne des quiz : difficulté qui monte à chaque bonne réponse.")
    async def chainquiz(self, ctx: commands.Context) -> None:
        if not await _require_slash(ctx, "chainquiz"):
            return
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

    # ---------- Guess who (flou) ----------

    @commands.hybrid_command(
        name="guesswho",
        description="Devine le personnage à partir d’une image très floutée (réponse dans le salon).",
    )
    async def guesswho(self, ctx: commands.Context) -> None:
        if not await _require_slash(ctx, "guesswho"):
            return
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

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
                im = im.resize((max(32, im.width // 8), max(32, im.height // 8)), Image.Resampling.LANCZOS)
                im = im.resize((im.width * 8, im.height * 8), Image.Resampling.NEAREST)
                im = im.filter(ImageFilter.GaussianBlur(radius=6))
                im.save(buf, format="PNG")
                buf.seek(0)
            except Exception as e:
                LOG.warning("guesswho blur: %s", e)
                buf = None
        else:
            buf = None

        embed = discord.Embed(
            title="🕵️ Qui est-ce ?",
            description=f"Image **très** dégradée — devine le **personnage** ({45}s). Indice anime : _{hint}_",
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
                timeout=45.0,
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
            )
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Temps écoulé — c’était **{name}**.")
            return

        g = (msg.content or "").strip()
        qz = self.bot.get_cog("Quiz")
        ok = False
        if qz:
            ok = bool(qz.title_matcher.find_matches(g, {name}))  # type: ignore[attr-defined]
        if not ok:
            ok = normalize(g) == normalize(name)
        if ok:
            await core.add_xp(self.bot, ctx.channel, ctx.author.id, 12, announce=False)
            core.add_mini_score(ctx.author.id, "guesswho", 1)
            await ctx.send(f"✅ Bravo ! C’était **{name}**.")
        else:
            await ctx.send(f"❌ Non — la réponse était **{name}**.")

    # ---------- Bingo ----------

    @commands.hybrid_command(
        name="bingo",
        description="Bingo 3×3 : des titres d’anime sont tirés — sois le premier à valider une ligne complète.",
    )
    async def bingo(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        if not await _require_slash(ctx, "bingo"):
            return
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        if _bingo_lock.get(ctx.channel.id):
            await ctx.send("❌ Une partie de bingo est déjà en cours dans ce salon.")
            return

        qz = self.bot.get_cog("Quiz")
        if not qz:
            await ctx.send("❌ Indisponible.")
            return

        titles: list[str] = []
        seen: set[str] = set()
        for _ in range(24):
            anime = await qz._fetch_random_anilist_media("POPULARITY_DESC")  # type: ignore[attr-defined]
            if not anime:
                continue
            t = (anime.get("title") or {}).get("romaji") or (anime.get("title") or {}).get("english") or "?"
            if t in seen:
                continue
            seen.add(t)
            titles.append(t)
            if len(titles) >= 9:
                break
        if len(titles) < 9:
            await ctx.send("❌ Pas assez de titres AniList.")
            return

        random.shuffle(titles)
        order = list(range(9))
        random.shuffle(order)

        session = BingoSession(self, ctx.channel, titles, order)
        emb = discord.Embed(
            title="🎱 Bingo anime",
            description=session.grid_text(),
            color=discord.Color.green(),
        )
        emb.add_field(
            name="Règles",
            value="Les **9** titres vont être tirés un par un (~5 s). Quand **3 cases** de ta ligne/colonne/diagonale sont sorties, clique **Bingo !**",
            inline=False,
        )
        view = BingoView(session)
        session.view = view
        msg = await ctx.send(embed=emb, view=view)
        session.message = msg
        _bingo_lock[ctx.channel.id] = True
        session._task = asyncio.create_task(session.run_reveals())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityGames(bot))
