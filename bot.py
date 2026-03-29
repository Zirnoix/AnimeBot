# bot.py
from __future__ import annotations

import os
import sys
import asyncio
import json
import logging
import types
from datetime import datetime, timezone
from typing import Optional

import discord
from aiohttp import web
from discord.ext import commands, tasks
from discord import app_commands

from modules import core
# ========= LOGGING (unique) =========
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
LOG = logging.getLogger("AnimeBot")

# ========= ENV =========
TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # requis
APPLICATION_ID = os.getenv("APPLICATION_ID")  # optionnel
_owner_raw = os.getenv("OWNER_ID", "").strip()
if not _owner_raw.isdigit():
    LOG.critical(
        "OWNER_ID manquant ou invalide. Définis l’ID Discord numérique du propriétaire "
        "(Paramètres développeur → clic droit sur ton profil → Copier l’identifiant). Voir .env.example."
    )
    raise SystemExit(1)
OWNER_ID = int(_owner_raw)


def _is_bot_owner_user(user_id: int) -> bool:
    """True si l’utilisateur est le propriétaire déclaré (OWNER_ID)."""
    return int(user_id) == OWNER_ID


async def _global_tree_interaction_check(self, interaction: discord.Interaction) -> bool:
    """`self` = CommandTree. Limite les slash en rafale par utilisateur / serveur (owner exempté)."""
    if interaction.type is not discord.InteractionType.application_command:
        return True
    uid = getattr(interaction.user, "id", 0)
    if _is_bot_owner_user(uid):
        return True
    from modules import abuse

    gid = interaction.guild.id if interaction.guild else 0
    ok, retry_after = abuse.allow_slash_burst(uid, gid)
    if ok:
        return True
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"⏳ Trop de commandes en peu de temps — réessaie dans **{max(1, int(retry_after) + 1)}s**.",
                ephemeral=True,
            )
    except Exception:
        pass
    return False


DEV_GUILD_IDS = {
    int(x.strip())
    for x in os.getenv("DEV_GUILD_IDS", "").split(",")
    if x.strip().isdigit()
}

if not TOKEN:
    LOG.critical("DISCORD_BOT_TOKEN manquant. Abandon.")
    raise SystemExit(1)

# ========= INTENTS =========
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.reactions = True
intents.message_content = True  # nécessaire si tes jeux lisent les messages

# ========= BOT =========
class AnimeBot(commands.Bot):
    """Bot principal (full slash + auto-sync par guilde, sans global auto)."""

    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            application_id=int(APPLICATION_ID) if (APPLICATION_ID and APPLICATION_ID.isdigit()) else None,
            help_command=None,
            case_insensitive=True,
            owner_id=OWNER_ID,
        )
        self.uptime_start = datetime.now(timezone.utc)
        self.anilist_online = True
        self._anilist_ok_streak = 0
        self._anilist_fail_streak = 0

        self._synced_once = False
        self._template_commands: list[app_commands.Command | app_commands.Group] = []
        self._loaded_cogs: list[str] = []

        # IMPORTANT : pas de purge/sync globale auto pour éviter les 429
        self.PURGE_GLOBAL_ON_BOOT = False
        self.AUTO_GLOBAL_SYNC = False

        self.tree.interaction_check = types.MethodType(_global_tree_interaction_check, self.tree)

    # ---------- Setup ----------
    async def setup_hook(self) -> None:
        await self._load_extensions()
        await self._sync_slash_commands()
        self._start_tasks()

    async def on_ready(self) -> None:
        LOG.info(
            "Connecté comme %s (ID: %s) — discord.py %s — %d serveurs",
            self.user, getattr(self.user, "id", "?"), discord.__version__, len(self.guilds)
        )
        if self._synced_once:
            return

        # Snapshot des commandes locales comme template
        self._template_commands = list(self.tree.get_commands())
        if not self._template_commands:
            LOG.warning("[slash] Aucun app command trouvé dans le tree local.")

        # Publie sur chaque guilde (mirror local -> guild)
        await self._mirror_template_to_all_guilds()

        # NE PAS purger ni republier en GLOBAL automatiquement (évite 429)
        # if self.PURGE_GLOBAL_ON_BOOT: ...

        self._synced_once = True
        # Ping AniList une fois
        asyncio.create_task(self._check_anilist_status_once())
        try:
            core.owner_telemetry_refresh_peaks(self)
        except Exception:
            pass

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is discord.InteractionType.application_command:
            try:
                cmd = interaction.command
                qn = cmd.qualified_name if cmd and getattr(cmd, "qualified_name", None) else None
                if not qn and interaction.data:
                    qn = str(interaction.data.get("name") or "?")
                core.record_owner_slash_command(qn or "?")
                core.owner_telemetry_refresh_peaks(self)
            except Exception:
                pass

    async def on_guild_join(self, guild: discord.Guild) -> None:
        LOG.info("Nouveau serveur: %s (%s) — membres: %s", guild.name, guild.id, guild.member_count)
        try:
            await self._mirror_template_to_guild(guild)
            LOG.info("[slash] Sync auto sur join OK: %s (%s)", guild.name, guild.id)
        except Exception as e:
            LOG.warning("[slash] Auto-sync join échouée pour %s: %s", guild.id, e)

    # ---------- Chargement des cogs ----------
    async def _load_extensions(self) -> None:
        import pathlib
        self._loaded_cogs.clear()
        cogs_dir = pathlib.Path(__file__).parent / "cogs"
        if not cogs_dir.exists():
            LOG.warning("Dossier 'cogs' introuvable. Aucune extension à charger.")
            return
        for path in cogs_dir.glob("*.py"):
            if path.name.startswith("_"):
                continue
            ext = f"cogs.{path.stem}"
            try:
                await self.load_extension(ext)
                self._loaded_cogs.append(ext)
                LOG.info("Chargé: %s", ext)
            except commands.errors.ExtensionAlreadyLoaded:
                LOG.debug("Déjà chargé: %s", ext)
                if ext not in self._loaded_cogs:
                    self._loaded_cogs.append(ext)
            except Exception as e:
                LOG.error("Échec chargement %s: %s", ext, e)

        if self._loaded_cogs:
            LOG.info("Cogs chargés (%d): %s", len(self._loaded_cogs), ", ".join(sorted(self._loaded_cogs)))
        else:
            LOG.warning("Aucun cog chargé.")

    # ---------- Sync / Purge ----------
    async def _mirror_template_to_guild(self, guild: discord.Guild) -> None:
        # Ajoute/override le snapshot sur la guilde
        for cmd in self._template_commands:
            try:
                self.tree.add_command(cmd, guild=guild, override=True)
            except Exception:
                try:
                    self.tree.add_command(cmd.copy(), guild=guild, override=True)
                except Exception:
                    pass
        published = await self.tree.sync(guild=guild)
        LOG.info("[slash] GUILD %s: %d commande(s) sync.", guild.id, len(published))

    async def _mirror_template_to_all_guilds(self) -> None:
        n = 0
        for g in list(self.guilds):
            await self._mirror_template_to_guild(g)
            n += 1
            # espace un peu pour ne pas spammer l'API
            await asyncio.sleep(2.0)
        LOG.info("[slash] Publication du template sur %d guilde(s).", n)

    async def _sync_slash_commands(self) -> None:
        """Sync contrôlée pour éviter les 429."""
        # 1) Sync par-guilde pour les guilds de DEV uniquement (rapide)
        if DEV_GUILD_IDS:
            for gid in DEV_GUILD_IDS:
                try:
                    guild_obj = discord.Object(id=gid)
                    cmds = await self.tree.sync(guild=guild_obj)
                    LOG.info("[slash] GUILD %s: %d commande(s) sync.", gid, len(cmds))
                except discord.HTTPException as e:
                    LOG.error("[slash] Échec sync guild %s: %s", gid, e)
                await asyncio.sleep(2.5)

        # 2) Sync GLOBAL seulement si explicitement activée
        if self.AUTO_GLOBAL_SYNC:
            try:
                cmds = await self.tree.sync()
                LOG.info("[slash] GLOBAL: %d commande(s) publiées.", len(cmds))
            except discord.HTTPException as e:
                LOG.error("[slash] Échec sync GLOBAL: %s", e)

    # ---------- Tasks ----------
    def _start_tasks(self) -> None:
        for loop in (self.check_anilist_status, self.update_title_cache, self.send_daily_summaries, self.refresh_anilist_cache):
            try:
                loop.start()
            except Exception:
                pass

    def _iter_alert_text_channels(self) -> list[discord.TextChannel]:
        """Salons `/setchannel` par serveur ; repli sur `channel_id` legacy si aucune entrée par guilde."""
        out: list[discord.TextChannel] = []
        cfg = core.get_config() or {}
        m = cfg.get("guild_alert_channels") or {}
        for cid in m.values():
            try:
                ch = self.get_channel(int(cid))
                if isinstance(ch, discord.TextChannel):
                    out.append(ch)
            except Exception:
                pass
        if not m:
            leg = cfg.get("channel_id")
            if leg:
                try:
                    ch = self.get_channel(int(leg))
                    if isinstance(ch, discord.TextChannel):
                        out.append(ch)
                except Exception:
                    pass
        return out

    async def _broadcast_to_alert_channels(self, content: str) -> None:
        for ch in self._iter_alert_text_channels():
            try:
                await ch.send(content)
            except Exception:
                pass

    @tasks.loop(minutes=5)
    async def check_anilist_status(self) -> None:
        try:
            test_query = "query { Media(id: 1, type: ANIME) { id } }"
            ok = bool(await asyncio.to_thread(core.query_anilist, test_query))
            if ok:
                self._anilist_fail_streak = 0
                if not self.anilist_online:
                    self._anilist_ok_streak += 1
                    if self._anilist_ok_streak >= 2:
                        self.anilist_online = True
                        self._anilist_ok_streak = 0
                        LOG.info("✅ AniList de retour.")
                        asyncio.create_task(
                            self._broadcast_to_alert_channels("✅ AniList est de nouveau en ligne.")
                        )
                else:
                    self._anilist_ok_streak = 0
            else:
                self._anilist_ok_streak = 0
                if self.anilist_online:
                    self._anilist_fail_streak += 1
                    if self._anilist_fail_streak >= 2:
                        self.anilist_online = False
                        self._anilist_fail_streak = 0
                        LOG.warning("⚠️ AniList semble hors ligne.")
                        asyncio.create_task(
                            self._broadcast_to_alert_channels(
                                "⚠️ AniList indisponible — certaines commandes peuvent échouer."
                            )
                        )
                else:
                    self._anilist_fail_streak = 0
        except Exception as e:
            LOG.warning("check_anilist_status: %s", e)

    @check_anilist_status.before_loop
    async def _check_anilist_status_before(self) -> None:
        # Évite le 1er ping en même temps que le ping boot (on_ready) ; limite les 429 AniList
        await asyncio.sleep(45)

    async def _check_anilist_status_once(self) -> None:
        try:
            test_query = "query { Media(id: 1, type: ANIME) { id } }"
            self.anilist_online = bool(await asyncio.to_thread(core.query_anilist, test_query))
            LOG.info("AniList status au boot: %s", "OK" if self.anilist_online else "DOWN")
        except Exception as e:
            LOG.warning("_check_anilist_status_once: %s", e)

    @tasks.loop(hours=1)
    async def update_title_cache(self) -> None:
        await asyncio.sleep(10)
        try:
            await core.update_title_cache()
            LOG.info("Cache titres mis à jour.")
        except Exception as e:
            LOG.error("update_title_cache: %s", e)

    @tasks.loop(hours=2)
    async def refresh_anilist_cache(self) -> None:
        try:
            for name in core.get_linked_anilist_usernames_bulk():
                try:
                    core.get_or_refresh_anilist_stats(name, ttl_hours=6)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
        except Exception as e:
            LOG.error("refresh_anilist_cache: %s", e)

    @tasks.loop(minutes=1)
    async def send_daily_summaries(self) -> None:
        await asyncio.sleep(10)
        try:
            now = datetime.now(core.TIMEZONE)
            current_time = now.strftime("%H:%M")
            current_day = now.strftime("%A")
            prefs_all = core.load_preferences() or {}
            settings_all = core.load_user_settings() or {}
            all_uids = set(settings_all.keys()) | set(prefs_all.keys())
            for user_id in all_uids:
                user_settings = settings_all.get(user_id, {})
                daily = user_settings.get("daily_summary")
                if daily is None:
                    # Legacy preferences.json → garder le récap « Sorties du jour ».
                    if user_id in prefs_all:
                        daily = True
                    else:
                        daily = True
                if not daily:
                    continue
                pref_prefs = prefs_all.get(user_id, {})
                alert_time = (
                    user_settings.get("alert_time")
                    or pref_prefs.get("alert_time")
                    or core.get_config().get("default_alert_time", "08:00")
                )
                if alert_time != current_time:
                    continue

                episodes = core.get_upcoming_episodes_for_discord(int(user_id)) or []
                episodes_today = [
                    ep for ep in episodes
                    if datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE).strftime("%A") == current_day
                ]
                if episodes_today:
                    await self._send_summary_message(user_id, episodes_today, current_day)
        except Exception as e:
            LOG.error("send_daily_summaries: %s", e)

    async def _send_summary_message(self, user_id: str, episodes: list[dict], day_name: str) -> None:
        try:
            user = await self.fetch_user(int(user_id))
            if not user:
                return
            day_fr = {
                "Monday": "lundi",
                "Tuesday": "mardi",
                "Wednesday": "mercredi",
                "Thursday": "jeudi",
                "Friday": "vendredi",
                "Saturday": "samedi",
                "Sunday": "dimanche",
            }.get(day_name, day_name)
            lines = []
            for ep in episodes[:10]:
                title_md = core.format_anilist_episode_title_markdown(ep)
                ep_lbl = core.format_episode_line_part(ep.get("episode"), ep)
                lines.append(f"• {title_md} — Épisode {ep_lbl}")
            trivia = await asyncio.to_thread(core.get_daily_anime_trivia_line)
            al_name = core.get_linked_username(int(user_id))
            if al_name:
                safe_anilist = discord.utils.escape_markdown(al_name)
                intro = (
                    f"📌 Récap basé sur **ta liste AniList** ({safe_anilist}) — "
                    "ce qui correspond à ce que tu suis en **En cours** / **En relecture**.\n\n"
                )
            else:
                intro = (
                    "📌 Récap basé sur **ta liste AniList** — utilise `/linkanilist` pour lier ton compte "
                    "et personnaliser cette liste.\n\n"
                )
            body = "\n".join(lines)
            desc = f"{intro}{body}\n\n💡 **Le saviez-vous ?** {trivia}"
            em = discord.Embed(
                title=f"🗓️ Sorties du {day_fr}",
                description=desc,
                color=discord.Color.blurple(),
            )
            em.set_footer(
                text="Récap « Sorties du jour » — `/recap` + `/setalert` (heure) + `/linkanilist`. /help"
            )
            await user.send(embed=em)
        except Exception as e:
            LOG.error("_send_summary_message: %s", e)

# ========= INSTANCE =========
bot = AnimeBot()

# ========= HYBRID : slash + préfixe (!) =========
@bot.check
async def _block_prefix_invocation(ctx: commands.Context) -> bool:
    # Slash : interaction présente. Préfixe : message utilisateur sans interaction.
    # (Anciennement `return bool(ctx.interaction)` bloquait toutes les commandes `!`.)
    if ctx.interaction is not None:
        return True
    return getattr(ctx, "message", None) is not None

# ========= Gestion des erreurs App Commands =========
async def _slash_error_respond(interaction: discord.Interaction, msg: str) -> None:
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
    except Exception:
        pass


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    _reg_err = getattr(app_commands, "CommandRegistrationError", None)
    if _reg_err is not None and isinstance(error, _reg_err):
        LOG.warning("CommandRegistrationError: %s", error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("⚠️ Une commande existe déjà (doublon).", ephemeral=True)
        except Exception:
            pass
        return

    if isinstance(error, app_commands.CommandInvokeError):
        orig = error.original
        if isinstance(orig, commands.CommandOnCooldown):
            ra = getattr(orig, "retry_after", None)
            sec = int(ra) + 1 if ra is not None else 5
            await _slash_error_respond(interaction, f"⏳ Cooldown : réessaie dans **{sec}s**.")
            return
        LOG.error("Erreur slash (invoke): %s", orig, exc_info=orig)
        await _slash_error_respond(interaction, "❌ Une erreur s’est produite en exécutant la commande.")
        return

    if isinstance(error, app_commands.CheckFailure):
        await _slash_error_respond(
            interaction,
            "❌ Tu n’as pas la permission d’utiliser cette commande.",
        )
        return

    _transform_err = getattr(app_commands, "TransformerError", None)
    if _transform_err is not None and isinstance(error, _transform_err):
        await _slash_error_respond(interaction, "❌ Paramètre invalide — vérifie les valeurs saisies.")
        return

    LOG.error("Erreur slash: %s", error, exc_info=error)
    await _slash_error_respond(interaction, "❌ Oups, erreur inattendue.")


# ========= Erreurs commandes préfixe (!) =========
@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    """Réponses claires pour `!commande` — slash / hybrid (interaction) restent gérés par `@bot.tree.error`."""
    if isinstance(error, commands.CommandNotFound):
        return
    if getattr(ctx, "interaction", None) is not None:
        return

    if isinstance(error, commands.CommandInvokeError) and error.original is not None:
        error = error.original

    if isinstance(error, commands.CommandOnCooldown):
        ra = getattr(error, "retry_after", None)
        sec = int(ra) + 1 if ra is not None else 5
        try:
            await ctx.send(f"⏳ Cooldown : réessaie dans **{sec}s**.")
        except Exception:
            pass
        return

    if isinstance(error, commands.MissingPermissions):
        try:
            await ctx.send("❌ Permissions insuffisantes sur ce serveur pour cette commande.")
        except Exception:
            pass
        return

    if isinstance(error, commands.BotMissingPermissions):
        try:
            await ctx.send("❌ Il manque des permissions au bot sur ce salon (rôle du bot / ordre des rôles).")
        except Exception:
            pass
        return

    if isinstance(error, commands.CheckFailure):
        try:
            await ctx.send("❌ Tu ne peux pas utiliser cette commande ici.")
        except Exception:
            pass
        return

    if isinstance(error, commands.BadArgument):
        try:
            await ctx.send(f"❌ Argument invalide : {error}")
        except Exception:
            pass
        return

    if isinstance(error, commands.UserInputError):
        try:
            await ctx.send(f"❌ Saisie invalide : {error}")
        except Exception:
            pass
        return

    LOG.error("Erreur commande préfixe: %s", error, exc_info=error)
    try:
        await ctx.send("❌ Erreur en exécutant la commande.")
    except Exception:
        pass


# ========= Healthcheck HTTP + webhook Top.gg (PORT / HEALTHCHECK_PORT) =========
_health_runner: web.AppRunner | None = None


async def _process_topgg_upvote(bot: AnimeBot, user_id: int, is_weekend: bool) -> None:
    """Enregistre le vote, XP, mini-score ; MP de remerciement si possible."""
    from modules import topgg_vote

    try:
        mult_w = float(os.getenv("TOPGG_WEEKEND_XP_MULT", "1.5"))
    except ValueError:
        mult_w = 1.5

    reward = topgg_vote.record_successful_vote(user_id)
    xp = reward.total_after_weekend(is_weekend, mult_w)
    sub = reward.subtotal_xp

    try:
        core.add_mini_score(user_id, "topgg_vote", 1)
    except Exception:
        pass
    try:
        await core.add_xp(bot, None, user_id, xp, announce=False)
    except Exception as e:
        LOG.warning("top.gg add_xp failed uid=%s: %s", user_id, e)

    try:
        u = await bot.fetch_user(user_id)
        url = topgg_vote.vote_page_url(bot.user.id)
        cd_sec = topgg_vote.cooldown_seconds()
        cd_h = max(1, cd_sec // 3600)
        weekend_line = ""
        if is_weekend and xp != sub:
            weekend_line = f"\n_Bonus week-end : {sub} XP → **{xp}** XP._"

        detail = (
            f"**Détail XP :** {reward.base_xp} base + {reward.streak_bonus} série "
            f"+ {reward.loyalty_bonus} fidélité = **{sub}** XP"
        )
        stats = (
            f"**Série :** {reward.streak} jour(s) · **Record :** {reward.best_streak} · "
            f"**Votes totaux :** {reward.total_votes}"
        )

        em = discord.Embed(
            title="🗳️ Tu viens de voter pour AnimeBot",
            description=(
                f"Ton vote sur **Top.gg** est bien enregistré — merci !\n\n"
                f"**Récompense :** +**{xp}** XP sur ta carte (ex. `/mycard`).\n"
                f"{detail}\n"
                f"{stats}\n"
                f"**Prochain vote possible** dans environ **{cd_h} h**.\n\n"
                f"🔗 [Lien pour revoter quand le cooldown est passé]({url})"
                f"{weekend_line}"
            ),
            color=discord.Color.green(),
            url=url,
        )
        em.set_footer(text="Message privé — visible uniquement par toi.")

        dm = await u.create_dm()
        await dm.send(embed=em)
        LOG.info("top.gg thank-you DM envoyé uid=%s", user_id)
    except discord.Forbidden:
        LOG.info(
            "top.gg thank-you DM refusé uid=%s — MP fermés, bot bloqué, ou pas de serveur commun avec le bot "
            "(rejoins un serveur où AnimeBot est présent et autorise les MP des membres du serveur).",
            user_id,
        )
    except discord.HTTPException as e:
        if getattr(e, "code", None) == 50007:
            LOG.info(
                "top.gg thank-you DM impossible uid=%s (50007 : utilisateur injoignable en MP).",
                user_id,
            )
        else:
            LOG.warning("top.gg thank-you DM HTTPException uid=%s: %s", user_id, e)
    except Exception as e:
        LOG.warning("top.gg thank-you DM échec uid=%s: %s", user_id, e, exc_info=True)

    try:
        topgg_vote.set_pending_vote_recap(
            user_id,
            {
                "xp": int(xp),
                "subtotal": int(sub),
                "base_xp": int(reward.base_xp),
                "streak_bonus": int(reward.streak_bonus),
                "loyalty_bonus": int(reward.loyalty_bonus),
                "streak": int(reward.streak),
                "best_streak": int(reward.best_streak),
                "total_votes": int(reward.total_votes),
                "weekend": bool(is_weekend),
            },
        )
    except Exception as e:
        LOG.warning("top.gg set_pending_vote_recap uid=%s: %s", user_id, e)

    LOG.info(
        "top.gg vote traité uid=%s xp=%s streak=%s votes=%s",
        user_id,
        xp,
        reward.streak,
        reward.total_votes,
    )


async def _topgg_post_handler(request: web.Request) -> web.Response:
    """Webhook Top.gg : TOPGG_WEBHOOK_SECRET via `Authorization` ou `X-TopGG-Signature` (HMAC ou secret brut)."""
    from modules import topgg_vote

    secret = topgg_vote.webhook_secret()
    if not secret:
        return web.Response(status=503, text="not configured")

    raw = await request.read()
    auth = (
        request.headers.get("Authorization")
        or request.headers.get("authorization")
        or request.headers.get("X-TopGG-Authorization")
        or ""
    )
    sig = request.headers.get("X-TopGG-Signature") or request.headers.get("X-Topgg-Signature") or ""

    if not topgg_vote.webhook_request_authorized(secret, raw, auth, sig):
        la = len(topgg_vote.normalize_webhook_token(auth))
        ls = len((sig or "").strip())
        lb = len(topgg_vote.normalize_webhook_token(secret))
        hnames = sorted(request.headers.keys())
        extra = ""
        if la == 0 and lb > 0:
            extra = (
                " Authorization vide (souvent supprimé par le proxy) — "
                "on accepte aussi X-TopGG-Signature (secret ou HMAC du corps). "
            )
        LOG.warning(
            "top.gg webhook: refusé (auth_len=%s sig_len=%s env_len=%s)%s — "
            "TOPGG_WEBHOOK_SECRET = valeur Top.gg ; noms d’en-têtes: %s",
            la,
            ls,
            lb,
            extra,
            hnames,
        )
        return web.Response(status=401, text="unauthorized")

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return web.Response(status=400, text="bad json")

    bot = request.app.get("bot")
    if not isinstance(bot, AnimeBot):
        return web.Response(status=503, text="bot not ready")

    typ = data.get("type")
    if typ == "test":
        return web.Response(text="ok")

    if not bot.is_ready():
        try:
            await asyncio.wait_for(bot.wait_until_ready(), timeout=4.5)
        except asyncio.TimeoutError:
            LOG.warning("top.gg webhook: bot pas prêt (timeout)")
            return web.Response(status=503, text="bot not ready")

    bot_user = bot.user
    if bot_user is None:
        return web.Response(status=503, text="bot not ready")

    try:
        if str(data.get("bot")) != str(bot_user.id):
            LOG.warning("top.gg webhook: bot id mismatch got=%s expected=%s", data.get("bot"), bot_user.id)
            return web.Response(status=400, text="bad bot id")
    except Exception:
        return web.Response(status=400, text="bad bot id")

    if typ != "upvote":
        return web.Response(text="ignored")

    try:
        user_id = int(data["user"])
    except (KeyError, TypeError, ValueError):
        return web.Response(status=400, text="bad user")

    is_weekend = bool(data.get("isWeekend"))

    try:
        await _process_topgg_upvote(bot, user_id, is_weekend)
    except Exception:
        LOG.exception("top.gg vote processing")
        return web.Response(status=500, text="internal error")

    LOG.info("top.gg upvote OK user_id=%s weekend=%s", user_id, is_weekend)
    return web.Response(text="ok")


async def _start_health_server_if_configured(bot_instance: AnimeBot) -> None:
    """Répond 200 sur / et /health ; POST /topgg pour Top.gg si TOPGG_WEBHOOK_SECRET est défini."""
    global _health_runner
    from modules import topgg_vote

    port_s = (os.getenv("PORT") or os.getenv("HEALTHCHECK_PORT") or "").strip()
    if not port_s:
        if topgg_vote.webhook_secret():
            LOG.warning(
                "TOPGG_WEBHOOK_SECRET défini mais PORT absent — aucun serveur HTTP, webhook Top.gg impossible "
                "(pas d’URL /topgg, donc pas d’XP automatique). "
                "Render Web Service : vérifie que le service est bien **Web** (pas Worker) ; "
                "sinon ajoute la variable PORT (Render l’injecte en général). "
                "En local : mets PORT=8080 (ou autre) dans .env."
            )
        return
    try:
        port = int(port_s)
    except ValueError:
        LOG.warning("PORT/HEALTHCHECK_PORT invalide (%r) — serveur HTTP désactivé.", port_s)
        return

    async def _ok(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app = web.Application()
    app["bot"] = bot_instance
    app.router.add_get("/", _ok)
    app.router.add_get("/health", _ok)
    app.router.add_post("/topgg", _topgg_post_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    _health_runner = runner
    hook = " + POST /topgg (Top.gg)" if topgg_vote.webhook_secret() else ""
    LOG.info("HTTP sur 0.0.0.0:%s (/, /health%s)", port, hook)


# ========= RUN =========
async def _amain() -> None:
    await _start_health_server_if_configured(bot)
    async with bot:
        await bot.start(TOKEN)


def main() -> None:
    try:
        LOG.info("Démarrage du bot…")
        asyncio.run(_amain())
    except KeyboardInterrupt:
        LOG.info("Arrêt demandé (Ctrl+C).")
    except Exception as e:
        LOG.error("Erreur fatale: %s", e)


if __name__ == "__main__":
    main()
