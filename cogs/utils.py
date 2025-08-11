"""
Utility commands for configuration and bot status.

This cog provides utility commands such as uptime check, alert configuration,
reminder settings, and notification channel setup.
"""

from __future__ import annotations

import time
import platform
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
from modules.image import generate_next_card
from modules import core


class Utils(commands.Cog):
    """Utility commands for bot configuration and status."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.start_time = time.time()

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Affiche la latence du bot."""
        latency = round(self.bot.latency * 1000)  # en ms
        await ctx.send(f"🏓 Pong ! Latence : **{latency} ms**")

    @commands.command(name="uptime")
    async def uptime(self, ctx: commands.Context):
        """Affiche depuis combien de temps le bot est en ligne."""
        delta = time.time() - self.start_time
        days = int(delta // 86400)
        hours = int((delta % 86400) // 3600)
        minutes = int((delta % 3600) // 60)
        seconds = int(delta % 60)
        await ctx.send(f"⏳ Uptime : **{days}j {hours}h {minutes}m {seconds}s**")

    @commands.command(name="botinfo")
    async def botinfo(self, ctx: commands.Context):
        """Affiche des infos sur le bot."""
        embed = discord.Embed(
            title="🤖 Infos sur le bot",
            description="Un bot Discord dédié à l’univers des animés, avec AniList, quiz et plus encore !",
            color=discord.Color.blue()
        )
        embed.add_field(name="Créateur", value="**Julien**", inline=True)
        embed.add_field(name="Langage", value="Python", inline=True)
        embed.add_field(name="Librairie", value=f"discord.py {discord.__version__}", inline=True)
        embed.add_field(name="Système", value=platform.system(), inline=True)
        embed.add_field(name="Version Python", value=platform.python_version(), inline=True)
        embed.set_footer(text=f"Demandé par {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="source")
    async def source(self, ctx: commands.Context):
        """Affiche le lien vers le code source du bot."""
        await ctx.send("📦 Code source du bot : https://github.com/Zirnoix/AnimeBot")

    @commands.command(name="setalert")
    async def setalert(self, ctx: commands.Context, time_str: str) -> None:
        """Définit l'heure de l'alerte quotidienne (HH:MM). Ex: !setalert 08:30"""
        try:
            hour, minute = map(int, time_str.split(":"))
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError("Heure invalide")

            prefs = core.load_preferences()
            uid = str(ctx.author.id)
            prefs.setdefault(uid, {})
            prefs[uid]["alert_time"] = f"{hour:02d}:{minute:02d}"
            core.save_preferences(prefs)

            await ctx.send(f"✅ Alerte quotidienne définie à **{hour:02d}:{minute:02d}**.")
        except ValueError:
            await ctx.send("❌ Format invalide. Utilise `!setalert HH:MM` (ex: `!setalert 08:30`).")
        except Exception:
            await ctx.send("❌ Une erreur s'est produite lors de la configuration.")

    @commands.command(name="testalert")
    @commands.is_owner()
    async def testalert(self, ctx):
        ch = ctx.channel
        try:
            item = core.get_my_next_airing_one()
            if not item:
                return await ctx.send("Aucun prochain épisode (ANILIST_USERNAME ?)")
            item["when"] = core.format_airing_datetime_fr(item.get("airingAt"), "Europe/Paris")
            img_path = generate_next_card(item, out_path="/tmp/test_alert.png", scale=1.2, padding=40)
            await ch.send("🧪 Test alerte (carte) :", file=discord.File(img_path, filename="test_alert.png"))
        except Exception as e:
            await ctx.send(f"Erreur test: `{type(e).__name__}: {e}`")

    
    @commands.command(name="showchannel")
    @commands.is_owner()
    async def showchannel(self, ctx: commands.Context) -> None:
        """Affiche le salon configuré pour les alertes (!setchannel)."""
        try:
            cfg = core.get_config() or {}
            cid = int(cfg.get("channel_id", 0)) if cfg.get("channel_id") else 0
            if not cid:
                await ctx.send("ℹ️ Aucun salon n'est configuré. Utilise `!setchannel` ici pour l'enregistrer.")
                return

            ch = self.bot.get_channel(cid)
            # Fallback si pas en cache
            if ch is None:
                try:
                    ch = await self.bot.fetch_channel(cid)
                except Exception:
                    ch = None

            if isinstance(ch, discord.TextChannel):
                # petit check permission d'envoi
                perms = ch.permissions_for(ch.guild.me) if ch.guild and ch.guild.me else None
                can_send = perms.send_messages if perms else False
                await ctx.send(
                    f"✅ Salon configuré : {ch.mention} (`{cid}`)\n"
                    f"Permissions d'envoi ici : **{'OK' if can_send else 'NON'}**"
                )
            else:
                await ctx.send(
                    f"⚠️ Un ID de salon est configuré (`{cid}`) mais introuvable/invalide.\n"
                    "Fais `!setchannel` dans le bon salon pour le réenregistrer."
                )
        except Exception:
            await ctx.send("❌ Impossible de lire la config. Réessaie ou refais `!setchannel`.")


    @commands.command(name="reminder")
    async def reminder(self, ctx: commands.Context, mode: Optional[str] = None) -> None:
        """Active ou désactive les rappels d'épisodes. Ex: !reminder on / off"""
        uid = str(ctx.author.id)
        settings = core.load_user_settings()
        settings.setdefault(uid, {})

        try:
            if mode:
                mode = mode.lower()
                if mode in {"off", "disable", "désactiver"}:
                    settings[uid]["reminder"] = False
                    await ctx.send("🔕 Rappels désactivés pour toi.")
                elif mode in {"on", "enable", "activer"}:
                    settings[uid]["reminder"] = True
                    await ctx.send("🔔 Rappels activés pour toi.")
                else:
                    await ctx.send("❌ Option invalide. Utilise `on` ou `off`.")
                core.save_user_settings(settings)
            else:
                current = settings.get(uid, {}).get("reminder", True)
                emoji = "🔔" if current else "🔕"
                await ctx.send(f"{emoji} Les rappels sont actuellement **{'activés' if current else 'désactivés'}** pour toi.")
        except Exception:
            await ctx.send("❌ Une erreur s'est produite.")

    @commands.command(name="setchannel")
    @commands.is_owner()
    async def setchannel(self, ctx: commands.Context) -> None:
        """Définit le salon de notifications (réservé au propriétaire)."""
        try:
            config = core.get_config()
            config["channel_id"] = ctx.channel.id
            core.save_config(config)
            await ctx.send("✅ Ce salon a été défini pour les notifications.")
        except Exception:
            await ctx.send("❌ Une erreur s'est produite lors de la configuration.")


class BotAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="setavatar")
    @commands.is_owner()
    async def set_avatar(self, ctx: commands.Context):
        """Change l'avatar du bot avec l'image attachée au message."""
        if not ctx.message.attachments:
            return await ctx.send("❌ Envoie l'image **dans le même message** que la commande.")
        try:
            avatar_bytes = await ctx.message.attachments[0].read()
            await self.bot.user.edit(avatar=avatar_bytes)
            await ctx.send("✅ Avatar du bot mis à jour avec succès !")
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")


async def setup(bot: commands.Bot):
    # Un seul setup qui ajoute les deux cogs
    await bot.add_cog(Utils(bot))
    await bot.add_cog(BotAdmin(bot))
