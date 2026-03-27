# bot.py
from __future__ import annotations

import os
import sys
import asyncio
import logging
import tempfile
import types
from datetime import datetime, timezone
from typing import Optional

import discord
from aiohttp import web
from discord.ext import commands, tasks
from discord import app_commands

from modules import core
from modules.image import generate_next_card

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

        # Groupe /admin
        self.admin_group = app_commands.Group(
            name="admin",
            description="Owner : debug slash, sync globale, cogs, test alerte, salon notifications.",
        )
        self._register_admin_commands()
        self.tree.interaction_check = types.MethodType(_global_tree_interaction_check, self.tree)

    # ---------- Setup ----------
    async def setup_hook(self) -> None:
        await self._load_extensions()
        try:
            self.tree.add_command(self.admin_group)
        except Exception:
            pass
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
                    # Uniquement /reminder (sans prefs) → ne pas ajouter le 1er récap par défaut.
                    if user_id in prefs_all:
                        daily = True
                    elif user_settings.get("reminder_on"):
                        daily = False
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
                lines.append(f"• {title_md} — Épisode {ep.get('episode', '?')}")
            em = discord.Embed(
                title=f"🗓️ Sorties du {day_fr}",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            )
            em.set_footer(
                text="Récap « Sorties du jour » — `/dailysummary` + `/setalert` (heure) + `/linkanilist`. Autre récap : `/reminder` (off par défaut). /help"
            )
            await user.send(embed=em)
        except Exception as e:
            LOG.error("_send_summary_message: %s", e)

    # ---------- Admin ----------
    def _register_admin_commands(self) -> None:
        async def _owner_only(itx: discord.Interaction) -> bool:
            u = getattr(itx, "user", None)
            if u is None:
                return False
            try:
                return int(u.id) == OWNER_ID
            except (TypeError, ValueError):
                return False

        @self.admin_group.command(name="debug_tree", description="(Owner) Affiche le tree local.")
        @app_commands.check(_owner_only)
        async def admin_debug_tree(itx: discord.Interaction):
            cmds = itx.client.tree.get_commands()
            lines: list[str] = []
            for c in cmds:
                if isinstance(c, app_commands.Command):
                    lines.append(f"/{c.name}")
                elif isinstance(c, app_commands.Group):
                    if c.commands:
                        for sc in c.commands:
                            lines.append(f"/{c.name} {sc.name}")
                    else:
                        lines.append(f"/{c.name} (group vide)")
            chunk = "\n".join(lines) or "(aucune)"
            await itx.response.send_message(f"```\n{chunk[:1900]}\n```", ephemeral=True)

        @self.admin_group.command(name="debug_pub", description="(Owner) GLOBAL vs GUILD publiés.")
        @app_commands.check(_owner_only)
        async def admin_debug_pub(itx: discord.Interaction):
            await itx.response.defer(ephemeral=True)
            try:
                global_cmds = await itx.client.tree.fetch_commands()
                guild_cmds = await itx.client.tree.fetch_commands(guild=itx.guild) if itx.guild else []
                g_names = ["/" + c.name for c in global_cmds]
                gu_names: list[str] = []
                for c in guild_cmds:
                    if isinstance(c, app_commands.Command):
                        gu_names.append("/" + c.name)
                    else:
                        for sc in c.commands:
                            gu_names.append(f"/{c.name} {sc.name}")
                txt = (
                    f"GLOBAL ({len(g_names)}):\n" + "\n".join(sorted(g_names))[:900] +
                    "\n\nGUILD ({len(gu_names)}):\n" + "\n".join(sorted(gu_names))[:900]
                )
                await itx.followup.send(f"```\n{txt}\n```", ephemeral=True)
            except Exception as e:
                await itx.followup.send(f"❌ debug_pub: {e}", ephemeral=True)

        @self.admin_group.command(name="publish_global", description="(Owner) Publie toutes les commandes en GLOBAL (à utiliser rarement).")
        @app_commands.check(_owner_only)
        async def admin_publish_global(itx: discord.Interaction):
            await itx.response.defer(ephemeral=True)
            try:
                cmds = await itx.client.tree.sync()
                await itx.followup.send(f"✅ Global sync OK — {len(cmds)} commande(s) publiées.", ephemeral=True)
            except Exception as e:
                await itx.followup.send(f"❌ Global sync a échoué: {e}", ephemeral=True)

        @self.admin_group.command(name="cogs", description="(Owner) Liste les cogs chargés.")
        @app_commands.check(_owner_only)
        async def admin_cogs(itx: discord.Interaction):
            names = sorted(self._loaded_cogs or [])
            txt = "Aucun." if not names else "\n".join(names)
            await itx.response.send_message(f"```\n{txt}\n```", ephemeral=True)

        @self.admin_group.command(
            name="test_alert",
            description="(Owner) Envoie une carte d’alerte test dans ce salon (comme les alertes auto).",
        )
        @app_commands.check(_owner_only)
        async def admin_test_alert(itx: discord.Interaction):
            if not isinstance(itx.channel, discord.TextChannel):
                await itx.response.send_message("❌ Utilise cette commande dans un salon texte.", ephemeral=True)
                return
            await itx.response.defer(ephemeral=True)
            try:
                item = core.get_my_next_airing_one()
                if not item:
                    await itx.followup.send(
                        "Aucun prochain épisode à afficher (vérifie `ANILIST_USERNAME` / API AniList).",
                        ephemeral=True,
                    )
                    return
                item["when"] = core.format_airing_datetime_fr(item.get("airingAt"), "Europe/Paris")
                img_path = generate_next_card(
                    item,
                    out_path=os.path.join(tempfile.gettempdir(), "test_alert.png"),
                    scale=1.2,
                    padding=40,
                )
                await itx.channel.send(
                    "🧪 Test alerte (carte) :",
                    file=discord.File(img_path, filename="test_alert.png"),
                )
                await itx.followup.send("✅ Carte envoyée dans ce salon.", ephemeral=True)
            except Exception as e:
                await itx.followup.send(f"❌ Erreur : `{type(e).__name__}: {e}`", ephemeral=True)

        @self.admin_group.command(
            name="show_channel",
            description="(Owner) Salons configurés sur ce serveur (alertes, level-up, raid, legacy local).",
        )
        @app_commands.check(_owner_only)
        async def admin_show_channel(itx: discord.Interaction):
            if not itx.guild:
                await itx.response.send_message(
                    "❌ Utilise cette commande **sur un serveur** (pas en message privé).",
                    ephemeral=True,
                )
                return
            await itx.response.defer(ephemeral=True)
            try:
                summary = core.format_guild_channels_config_summary(itx.client, itx.guild.id)
                await itx.followup.send(
                    "**Salons de notification (ce serveur)**\n" + summary,
                    ephemeral=True,
                )
            except Exception:
                await itx.followup.send(
                    "❌ Impossible de lire la config.",
                    ephemeral=True,
                )

        @self.admin_group.command(
            name="recap_mensuel",
            description="(Owner) Stats internes : mois en cours / précédent, usages slash, pics serveurs & membres.",
        )
        @app_commands.check(_owner_only)
        async def admin_recap_mensuel(itx: discord.Interaction):
            await itx.response.defer(ephemeral=True)
            try:
                core.owner_telemetry_refresh_peaks(itx.client)
            except Exception:
                pass
            data = core.owner_telemetry_summary()
            cur_m = data.get("current_month", "?")
            cur = data.get("current") or {}
            cmds_cur = cur.get("commands") or {}
            top_cur = sorted(cmds_cur.items(), key=lambda x: (-x[1], x[0]))[:15]
            lines = [
                f"**Mois courant** `{cur_m}`",
                f"· Pic **serveurs** : **{cur.get('peak_guilds', 0)}**",
                f"· Pic **membres** (somme des guilds, max vu) : **{cur.get('peak_members', 0)}**",
            ]
            if top_cur:
                lines.append("· **Top commandes slash** (comptage local, depuis la dernière rotation de mois) :")
                for k, v in top_cur:
                    lines.append(f"  – `{k}` — **{v}**")
            else:
                lines.append(
                    "· Aucun usage slash enregistré pour ce mois (le compteur démarre après mise à jour ; "
                    "les membres rejoignent une guilde où le bot voit du trafic)."
                )
            prev_m = data.get("previous_month")
            prev = data.get("previous") or {}
            if prev_m and prev:
                pc = prev.get("commands") or {}
                ptop = sorted(pc.items(), key=lambda x: (-x[1], x[0]))[:10]
                lines.append("")
                lines.append(
                    f"**Mois précédent** `{prev_m}` — pic serveurs **{prev.get('peak_guilds', 0)}**, "
                    f"membres **{prev.get('peak_members', 0)}**"
                )
                if ptop:
                    lines.append("· Top : " + " · ".join(f"`{a}`×{b}" for a, b in ptop))
            await itx.followup.send("\n".join(lines)[:1950], ephemeral=True)


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


# ========= Healthcheck HTTP (Railway / hébergeurs qui exposent PORT) =========
_health_runner: web.AppRunner | None = None


async def _start_health_server_if_configured() -> None:
    """Répond 200 sur / et /health si PORT ou HEALTHCHECK_PORT est défini (ex. Railway)."""
    global _health_runner
    port_s = (os.getenv("PORT") or os.getenv("HEALTHCHECK_PORT") or "").strip()
    if not port_s:
        return
    try:
        port = int(port_s)
    except ValueError:
        LOG.warning("PORT/HEALTHCHECK_PORT invalide (%r) — healthcheck HTTP désactivé.", port_s)
        return

    async def _ok(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", _ok)
    app.router.add_get("/health", _ok)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    _health_runner = runner
    LOG.info("Healthcheck HTTP sur 0.0.0.0:%s (/ et /health)", port)


# ========= RUN =========
async def _amain() -> None:
    await _start_health_server_if_configured()
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
