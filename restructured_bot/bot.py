import asyncio
from datetime import datetime
import os
import pytz

import discord
from discord.ext import commands, tasks

import restructured_bot.modules.core as core

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

bot.uptime_start = datetime.now(pytz.utc)

###############################################################################
# Events
###############################################################################

@bot.event
async def on_ready():
    now = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
    print(f"[BOOT 🟢] {bot.user.name} prêt — ID: {bot.user.id} à {now}")
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, core.update_title_cache)
    if not send_daily_summaries.is_running():
        send_daily_summaries.start()
    if not check_new_episodes.is_running():
        check_new_episodes.start()
    if not monthly_reset.is_running():
        monthly_reset.start()

@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    await ctx.send(f"❌ Une erreur est survenue : `{type(error).__name__}` — {str(error)}")

###############################################################################
# Tasks
###############################################################################

@tasks.loop(minutes=1)
async def send_daily_summaries():
    now = datetime.now(core.TIMEZONE)
    current_time = now.strftime("%H:%M")
    current_day = now.strftime("%A")
    preferences = core.load_preferences()
    for user_id, prefs in preferences.items():
        user_settings = core.load_user_settings().get(user_id, {})
        if not user_settings.get("daily_summary", True):
            continue
        alert_time = prefs.get("alert_time", "08:00")
        if current_time != alert_time:
            continue
        episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)
        episodes_today = [ep for ep in episodes if datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE).strftime("%A") == current_day]
        if not episodes_today:
            continue
        try:
            user = await bot.fetch_user(int(user_id))
            embed = discord.Embed(
                title="📺 Résumé du jour",
                description=f"Voici les épisodes à regarder ce **{core.JOURS_FR.get(current_day, current_day)}** !",
                color=discord.Color.green(),
            )
            for ep in sorted(episodes_today, key=lambda e: e['airingAt']):
                dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
                emoji = core.genre_emoji(ep.get("genres", []))
                embed.add_field(
                    name=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
                    value=f"🕒 {dt.strftime('%H:%M')}",
                    inline=False,
                )
            await user.send(embed=embed)
        except Exception as e:
            print(f"[Erreur DM résumé pour {user_id}] {e}")

@tasks.loop(minutes=5)
async def check_new_episodes():
    await bot.wait_until_ready()
    config = core.get_config()
    channel_id = config.get("channel_id")
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)
    now_ts = int(datetime.now(tz=pytz.utc).timestamp())
    notified = set(core.load_json(core.NOTIFIED_FILE, []))
    for ep in episodes:
        uid = f"{ep['id']}-{ep['episode']}"
        if uid in notified:
            continue
        if now_ts >= ep["airingAt"] - 900:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            embed = core.build_embed(ep, dt)
            await channel.send("🔔 Rappel d'épisode imminent :", embed=embed)
            notified.add(uid)
            core.save_json(core.NOTIFIED_FILE, list(notified))
            tracker_data = core.load_tracker()
            user_settings = core.load_user_settings()
            for user_id, titles in tracker_data.items():
                if not user_settings.get(str(user_id), {}).get("reminder", True):
                    continue
                if core.normalize(ep["title"]) in [core.normalize(t) for t in titles]:
                    try:
                        user = await bot.fetch_user(int(user_id))
                        await user.send(
                            f"🔔 Nouvel épisode dispo : **{ep['title']} – Épisode {ep['episode']}**",
                            embed=embed,
                        )
                    except Exception:
                        pass

@tasks.loop(hours=24)
async def monthly_reset():
    now = datetime.now(tz=core.TIMEZONE)
    if now.day != 1:
        return
    scores = core.load_scores()
    if scores:
        top_uid = max(scores.items(), key=lambda x: x[1])[0]
        winner_data = {"uid": top_uid, "timestamp": now.isoformat()}
        core.save_json(core.WINNER_FILE, winner_data)
        core.save_scores({})
        config = core.get_config()
        channel_id = config.get("channel_id")
        if channel_id:
            channel = bot.get_channel(channel_id)
            if channel:
                try:
                    user = await bot.fetch_user(int(top_uid))
                    await channel.send(
                        f"🔁 **Début du mois !** Le classement `!quiztop` a été remis à zéro !\n"
                        f"🏆 Bravo à **{user.display_name}** pour sa victoire le mois dernier ! Bonne chance à tous 🍀"
                    )
                except Exception:
                    pass

###############################################################################
# Extensions
###############################################################################

async def load_extensions():
    for filename in os.listdir(os.path.join(os.path.dirname(__file__), 'cogs')):
        if filename.endswith('.py') and not filename.startswith('_'):
            module = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(module)
                print(f"[DEBUG] ✅ {module} chargé")
            except Exception as e:
                print(f"[DEBUG] ❌ Erreur de chargement pour {module}: {e}")

async def main():
    await load_extensions()
    await bot.start(core.DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
