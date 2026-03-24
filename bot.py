# bot.py
from __future__ import annotations

import os
import sys
import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from typing import Optional

import discord
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
OWNER_ID = int(os.getenv("OWNER_ID", "180389173985804288"))  # défaut
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
        for loop in (self.check_anilist_status, self.monthly_reset, self.update_title_cache, self.send_daily_summaries, self.refresh_anilist_cache):
            try:
                loop.start()
            except Exception:
                pass

    @check_anilist_status.before_loop
    async def _check_anilist_status_before(self) -> None:
        # Décalle le 1er ping par rapport au ping boot (on_ready) pour limiter les 429 AniList
        await asyncio.sleep(45)

    @tasks.loop(minutes=5)
    async def check_anilist_status(self) -> None:
        try:
            test_query = "query { Media(id: 1, type: ANIME) { id } }"
            ok = bool(await asyncio.to_thread(core.query_anilist, test_query))
            chan = self._get_notification_channel_sync()
            if ok:
                self._anilist_fail_streak = 0
                if not self.anilist_online:
                    self._anilist_ok_streak += 1
                    if self._anilist_ok_streak >= 2:
                        self.anilist_online = True
                        self._anilist_ok_streak = 0
                        LOG.info("✅ AniList de retour.")
                        if chan:
                            asyncio.create_task(chan.send("✅ AniList est de nouveau en ligne."))
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
                        if chan:
                            asyncio.create_task(chan.send("⚠️ AniList indisponible — certaines commandes peuvent échouer."))
                else:
                    self._anilist_fail_streak = 0
        except Exception as e:
            LOG.warning("check_anilist_status: %s", e)

    async def _check_anilist_status_once(self) -> None:
        try:
            test_query = "query { Media(id: 1, type: ANIME) { id } }"
            self.anilist_online = bool(await asyncio.to_thread(core.query_anilist, test_query))
            LOG.info("AniList status au boot: %s", "OK" if self.anilist_online else "DOWN")
        except Exception as e:
            LOG.warning("_check_anilist_status_once: %s", e)

    @tasks.loop(hours=24)
    async def monthly_reset(self) -> None:
        try:
            now = datetime.now(tz=core.TIMEZONE)
            if now.day == 1:
                scores = core.load_scores()
                if scores:
                    top_uid = max(scores.items(), key=lambda x: x[1])[0]
                    core.save_scores({})
                    await self._announce_monthly_winner(top_uid)
        except Exception as e:
            LOG.error("monthly_reset: %s", e)

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
            prefs_all = core.load_preferences()
            settings_all = core.load_user_settings()
            for user_id, prefs in (prefs_all or {}).items():
                user_settings = (settings_all or {}).get(user_id, {})
                if not user_settings.get("daily_summary", True):
                    continue
                if prefs.get("alert_time", "08:00") != current_time:
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
                t = core.format_anilist_title_obj(ep.get("title"))
                lines.append(f"• **{t}** — Épisode {ep.get('episode', '?')}")
            em = discord.Embed(
                title=f"🗓️ Sorties du {day_fr}",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            )
            em.set_footer(
                text="Récap auto (préférences) — le récap /reminder est séparé ; voir /help."
            )
            await user.send(embed=em)
        except Exception as e:
            LOG.error("_send_summary_message: %s", e)

    async def _announce_monthly_winner(self, user_id: str) -> None:
        try:
            channel = await self._get_notification_channel()
            if not channel:
                return
            user = await self.fetch_user(int(user_id))
            if not user:
                return
            em = discord.Embed(
                title="🏆 Gagnant du mois !",
                description=f"Félicitations à **{user.display_name}** !",
                color=discord.Color.gold(),
            )
            await channel.send(embed=em)
        except Exception as e:
            LOG.error("_announce_monthly_winner: %s", e)

    # ---------- Channels ----------
    def _get_notification_channel_sync(self) -> Optional[discord.TextChannel]:
        config = core.get_config()
        cid = config.get("channel_id")
        return self.get_channel(int(cid)) if cid else None

    async def _get_notification_channel(self) -> Optional[discord.TextChannel]:
        return self._get_notification_channel_sync()

    # ---------- Admin ----------
    def _register_admin_commands(self) -> None:
        async def _owner_only(itx: discord.Interaction) -> bool:
            return int(getattr(itx.user, "id", 0)) == OWNER_ID

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
            description="(Owner) Affiche le salon enregistré pour les alertes (via /setchannel).",
        )
        @app_commands.check(_owner_only)
        async def admin_show_channel(itx: discord.Interaction):
            await itx.response.defer(ephemeral=True)
            try:
                cfg = core.get_config() or {}
                cid = int(cfg.get("channel_id", 0)) if cfg.get("channel_id") else 0
                if not cid:
                    await itx.followup.send(
                        "ℹ️ Aucun salon configuré. Utilise **`/setchannel`** dans le salon voulu.",
                        ephemeral=True,
                    )
                    return
                ch = self.get_channel(cid)
                if ch is None:
                    try:
                        ch = await self.fetch_channel(cid)
                    except Exception:
                        ch = None
                if isinstance(ch, discord.TextChannel):
                    perms = ch.permissions_for(ch.guild.me) if ch.guild and ch.guild.me else None
                    can_send = perms.send_messages if perms else False
                    await itx.followup.send(
                        f"✅ Salon configuré : {ch.mention} (`{cid}`)\n"
                        f"Permissions d’envoi : **{'OK' if can_send else 'NON'}**",
                        ephemeral=True,
                    )
                else:
                    await itx.followup.send(
                        f"⚠️ ID `{cid}` enregistré mais salon introuvable ou invalide.\n"
                        "Refais **`/setchannel`** dans le bon salon.",
                        ephemeral=True,
                    )
            except Exception:
                await itx.followup.send(
                    "❌ Impossible de lire la config. Réessaie ou refais **`/setchannel`**.",
                    ephemeral=True,
                )


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
    LOG.error("Erreur slash: %s", error, exc_info=error)
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Oups, erreur inattendue.", ephemeral=True)
    except Exception:
        pass

# ========= RUN =========
def main() -> None:
    try:
        LOG.info("Démarrage du bot…")
        bot.run(TOKEN, log_handler=None)  # basicConfig gère console + fichier
    except KeyboardInterrupt:
        LOG.info("Arrêt demandé (Ctrl+C).")
    except Exception as e:
        LOG.error("Erreur fatale: %s", e)

if __name__ == "__main__":
    main()
