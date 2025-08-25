
"""
Point d'entrée principal du AnimeBot restructuré.

Ce script initialise le bot Discord, charge tous les cogs situés dans le
package ``cogs``, et planifie les tâches d'arrière-plan pour :
- Les notifications d'épisodes
- Les résumés quotidiens
- Les réinitialisations mensuelles
- La mise à jour du cache
"""

import asyncio
import os
import sys
import pytz
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
import discord
from discord.ext import commands, tasks
from discord import app_commands
from modules import core

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration des intents Discord
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class AnimeBot(commands.Bot):
    """Classe principale du bot gérant les fonctionnalités anime.

    Attributes:
        uptime_start: Timestamp du démarrage du bot
        title_cache_refresh_rate: Taux de rafraîchissement du cache en secondes
        last_episodes: Cache des derniers épisodes notifiés
    """

    def __init__(self):
        """Initialise le bot avec la configuration de base."""
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            case_insensitive=True
        )
        self.uptime_start = datetime.now(timezone.utc)
        self.title_cache_refresh_rate = 3600  # Rafraîchir le cache toutes les heures
        self.last_episodes: Dict[str, List[int]] = {}  # Pour éviter les notifications en double
        self.anilist_online = True  # État actuel de l’API AniList

    async def setup_hook(self) -> None:
        """Configure le bot au démarrage."""
        await self.load_extensions()
        self.start_tasks()
        # --- [AJOUT] Slash command /ping minimaliste ---
        @app_commands.command(name="ping", description="Répond avec Pong et la latence.")
        async def ping_slash(interaction: discord.Interaction):
            latency_ms = round(self.latency * 1000)
            await interaction.response.send_message(f"Pong ! {latency_ms} ms")

        try:
            # On ajoute la commande et on synchronise l'arbre global
            self.tree.add_command(ping_slash)
            await self.tree.sync()
            logger.info("Slash command /ping enregistrée et synchronisée.")
        except Exception as e:
            logger.error(f"Échec d'enregistrement de /ping : {e}")
        # --- [FIN AJOUT] ---


    async def on_ready(self):
        """Appelé quand le bot est prêt et connecté."""
        logger.info(f"Bot connecté en tant que {self.user.name} (ID: {self.user.id})")
        logger.info(f"Version Discord.py : {discord.__version__}")
        logger.info("------")

    async def load_extensions(self) -> None:
        """Charge tous les cogs depuis le dossier cogs."""
        try:
            cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py") and not filename.startswith("_"):
                    extension = f"cogs.{filename[:-3]}"
                    try:
                        await self.load_extension(extension)
                        logger.info(f"Extension chargée : {filename}")
                    except Exception as e:
                        logger.error(f"Échec du chargement de l'extension {filename}: {str(e)}")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des extensions : {str(e)}")

    def start_tasks(self) -> None:
        """Démarre toutes les tâches périodiques."""
        # self.update_title_cache.start()
        # self.send_daily_summaries.start()
        # self.check_new_episodes.start()
        self.monthly_reset.start()
        self.check_anilist_status.start()

        # 🔁 Force un premier check immédiat d'AniList au lancement
        self.loop.create_task(self.check_anilist_status())


    @tasks.loop(seconds=3600)
    async def update_title_cache(self) -> None:
        """Met à jour périodiquement le cache des titres."""
        await asyncio.sleep(10)
        try:
            await core.update_title_cache()
            logger.info("Cache des titres mis à jour avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du cache: {str(e)}")

    @tasks.loop(minutes=1)
    async def send_daily_summaries(self) -> None:
        """Envoie les résumés quotidiens aux utilisateurs."""
        await asyncio.sleep(10)
        try:
            now = datetime.now(core.TIMEZONE)
            current_time = now.strftime("%H:%M")
            current_day = now.strftime("%A")

            for user_id, prefs in core.load_preferences().items():
                await self._process_user_summary(user_id, prefs, current_time, current_day)
        except Exception as e:
            logger.error(f"Erreur dans send_daily_summaries: {str(e)}")

    @tasks.loop(minutes=5)
    async def check_anilist_status(self) -> None:
        from modules.core import query_anilist

        test_query = """
        query {
          Media(id: 1, type: ANIME) {
            id
          }
        }
        """

        response = query_anilist(test_query)

        if response:
            if not self.anilist_online:
                self.anilist_online = True
                logger.info("✅ AniList est de nouveau en ligne.")
                channel = self._get_notification_channel_sync()
                if channel:
                    self.loop.create_task(channel.send("✅ AniList est de nouveau en ligne. Le bot fonctionne à nouveau normalement."))
        else:
            if self.anilist_online:
                self.anilist_online = False
                logger.warning("⚠️ AniList est hors ligne.")
                channel = self._get_notification_channel_sync()
                if channel:
                    self.loop.create_task(channel.send("⚠️ AniList est actuellement indisponible. Certaines commandes peuvent ne pas fonctionner."))

    @tasks.loop(minutes=10)
    async def check_new_episodes(self) -> None:
        """Vérifie et notifie les nouveaux épisodes."""
        await self.wait_until_ready()
        try:
            channel = await self._get_notification_channel()
            if channel:
                await self._process_new_episodes(channel)
        except Exception as e:
            logger.error(f"Erreur dans check_new_episodes: {str(e)}")

    @tasks.loop(hours=24)
    async def monthly_reset(self) -> None:
        """Gère la réinitialisation mensuelle des scores."""
        try:
            now = datetime.now(tz=core.TIMEZONE)
            if now.day == 1:
                await self._process_monthly_reset()
        except Exception as e:
            logger.error(f"Erreur dans monthly_reset: {str(e)}")

    async def _process_user_summary(self, user_id: str, prefs: dict, current_time: str, current_day: str) -> None:
        """Traite le résumé quotidien pour un utilisateur."""
        try:
            user_settings = core.load_user_settings().get(user_id, {})
            if not user_settings.get("daily_summary", True):
                return

            alert_time = prefs.get("alert_time", "08:00")
            if current_time != alert_time:
                return

            episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)
            episodes_today = [
                ep for ep in episodes
                if datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE).strftime("%A") == current_day
            ]

            if episodes_today:
                await self._send_summary_message(user_id, episodes_today, current_day)
        except Exception as e:
            logger.error(f"Erreur lors du traitement du résumé pour {user_id}: {str(e)}")

    async def _process_new_episodes(self, channel: discord.TextChannel) -> None:
        """Traite et notifie les nouveaux épisodes."""
        try:
            episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)
            if not episodes:
                return

            now = datetime.now(core.TIMEZONE)
            # Filtre les épisodes sortant dans les 10 prochaines minutes
            upcoming = [
                ep for ep in episodes
                if abs(datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE) - now) <= timedelta(minutes=10)
                and not self._is_already_notified(ep)
            ]

            for episode in upcoming:
                await self._send_episode_notification(channel, episode)
                self._mark_as_notified(episode)
        except Exception as e:
            logger.error(f"Erreur lors du traitement des nouveaux épisodes : {str(e)}")

    def _is_already_notified(self, episode: dict) -> bool:
        """Vérifie si un épisode a déjà été notifié."""
        anime_id = str(episode.get("mediaId", ""))
        episode_num = episode.get("episode", 0)
        return anime_id in self.last_episodes and episode_num in self.last_episodes[anime_id]

    def _mark_as_notified(self, episode: dict) -> None:
        """Marque un épisode comme notifié."""
        anime_id = str(episode.get("mediaId", ""))
        episode_num = episode.get("episode", 0)
        if anime_id not in self.last_episodes:
            self.last_episodes[anime_id] = []
        self.last_episodes[anime_id].append(episode_num)
        # Limiter la taille du cache
        self.last_episodes[anime_id] = self.last_episodes[anime_id][-10:]

    async def _send_episode_notification(self, channel: discord.TextChannel, episode: dict) -> None:
        """Envoie une notification pour un nouvel épisode."""
        embed = discord.Embed(
            title="🆕 Nouvel épisode disponible !",
            description=f"**{episode['title']}** — Épisode {episode['episode']}",
            color=discord.Color.green()
        )
        if "image" in episode:
            embed.set_thumbnail(url=episode["image"])
        await channel.send(embed=embed)

    async def _process_monthly_reset(self) -> None:
        """Traite la réinitialisation mensuelle des scores."""
        scores = core.load_scores()
        if not scores:
            return

        top_uid = max(scores.items(), key=lambda x: x[1])[0]
        winner_data = {
            "uid": top_uid,
            "timestamp": datetime.now().isoformat()
        }
        core.save_json(core.WINNER_FILE, winner_data)
        core.save_scores({})

        await self._announce_monthly_winner(top_uid)

    async def _announce_monthly_winner(self, user_id: str) -> None:
        """Annonce le gagnant mensuel."""
        try:
            channel = await self._get_notification_channel()
            if not channel:
                return

            user = await self.fetch_user(int(user_id))
            if not user:
                return

            embed = discord.Embed(
                title="🏆 Gagnant du mois !",
                description=f"Félicitations à **{user.display_name}** qui remporte le classement du mois !",
                color=discord.Color.gold()
            )
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Erreur lors de l'annonce du gagnant : {str(e)}")

    def _get_notification_channel_sync(self) -> Optional[discord.TextChannel]:
        config = core.get_config()
        channel_id = config.get("channel_id")
        if not channel_id:
            return None
        return self.get_channel(int(channel_id))

    async def _send_summary_message(self, user_id: str, episodes: list, current_day: str) -> None:
        """Envoie un résumé quotidien à l'utilisateur."""
        try:
            user = await self.fetch_user(int(user_id))
            embed = self._create_summary_embed(episodes, current_day)
            await user.send(embed=embed)
        except discord.NotFound:
            logger.warning(f"Utilisateur {user_id} non trouvé")
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer un message à {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du résumé à {user_id}: {str(e)}")

    def _create_summary_embed(self, episodes: list, current_day: str) -> discord.Embed:
        """Crée l'embed pour le résumé quotidien."""
        embed = discord.Embed(
            title="📺 Résumé du jour",
            description=f"Voici les épisodes à regarder ce **{core.JOURS_FR.get(current_day, current_day)}** !",
            color=discord.Color.green()
        )

        for ep in sorted(episodes, key=lambda e: e['airingAt']):
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            emoji = core.genre_emoji(ep.get("genres", []))
            embed.add_field(
                name=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
                value=f"🕒 {dt.strftime('%H:%M')}",
                inline=False
            )
        return embed

@commands.is_owner()
@commands.command(name="sync")
async def sync_cmd(ctx: commands.Context):
    synced = await ctx.bot.tree.sync()  # global
    await ctx.send(f"{len(synced)} slash commands synchronisées.")

@commands.is_owner()
@commands.command(name="sync_guild")
async def sync_guild(ctx: commands.Context, guild_id: int = None):
    """Sync slash sur 1 serveur (instantané). Utilise l'ID du serveur courant si non fourni."""
    try:
        guild = discord.Object(id=guild_id or ctx.guild.id)
        synced = await ctx.bot.tree.sync(guild=guild)
        await ctx.send(f"✅ Sync GUILD {guild.id} : {len(synced)} commande(s).")
    except Exception as e:
        await ctx.send(f"❌ Sync guild échec : {e}")

@commands.is_owner()
@commands.command(name="list_slash")
async def list_slash(ctx: commands.Context):
    """Liste ce que le bot a actuellement dans bot.tree (côté code) avant publication."""
    try:
        cmds = ctx.bot.tree.get_commands()  # côté bot (pas ce qui est déjà publié)
        lines = [f"- {c.name} ({c.__class__.__name__})" for c in cmds]
        chunk = "\n".join(lines) or "(aucune)"
        # évite les messages trop longs
        for i in range(0, len(chunk), 1800):
            await ctx.send(f"```{chunk[i:i+1800]}```")
    except Exception as e:
        await ctx.send(f"❌ list_slash échec : {e}")

@commands.is_owner()
@commands.command(name="sync_global")
async def sync_global(ctx: commands.Context):
    """Force la sync globale (peut prendre du temps à apparaître côté Discord)."""
    try:
        synced = await ctx.bot.tree.sync()
        await ctx.send(f"🌍 Sync GLOBAL : {len(synced)} commande(s).")
    except Exception as e:
        await ctx.send(f"❌ Sync global échec : {e}")



# Création de l'instance du bot
bot = AnimeBot()
bot.add_command(sync_cmd)  # <<< on enregistre la commande définie au module
bot.add_command(sync_guild)
bot.add_command(list_slash)
bot.add_command(sync_global)

if __name__ == "__main__":
    # Vérification de la présence du token
    if not hasattr(core, 'DISCORD_BOT_TOKEN') or not core.DISCORD_BOT_TOKEN:
        logger.error("Token Discord non trouvé dans la configuration")
        sys.exit(1)

    # Démarrage du bot
    try:
        logger.info("Démarrage du bot...")
        asyncio.run(bot.start(core.DISCORD_BOT_TOKEN))
    except KeyboardInterrupt:
        logger.info("Arrêt du bot par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur fatale: {str(e)}")
    finally:
        logger.info("Nettoyage et fermeture...")
        asyncio.run(bot.close())
