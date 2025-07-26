from discord.ext import commands, tasks
import discord
import datetime
from modules.utils import load_json, save_json, get_user_anilist, get_upcoming_episodes, TIMEZONE

@commands.command(name="setalert")
async def set_alert(ctx, time_str: str):
    try:
        datetime.datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await ctx.send("❌ Format invalide. Utilise HH:MM (ex : 18:30).")
        return

    preferences = load_json("alert_preferences.json", {})
    preferences[str(ctx.author.id)] = time_str
    save_json("alert_preferences.json", preferences)
    await ctx.send(f"✅ Alerte définie pour {time_str} chaque jour.")

@commands.command(name="reminder")
async def toggle_reminder(ctx):
    preferences = load_json("reminder_users.json", [])
    user_id = str(ctx.author.id)
    if user_id in preferences:
        preferences.remove(user_id)
        await ctx.send("🔕 Rappel quotidien désactivé.")
    else:
        preferences.append(user_id)
        await ctx.send("🔔 Rappel quotidien activé.")
    save_json("reminder_users.json", preferences)

@commands.command(name="setchannel")
async def set_notification_channel(ctx):
    config = load_json("config.json", {})
    config["notification_channel"] = ctx.channel.id
    save_json("config.json", config)
    await ctx.send(f"✅ Les notifications seront désormais envoyées ici : {ctx.channel.mention}")

@commands.command(name="anitracker")
async def anitracker(ctx, *, title: str = None):
    if not title:
        await ctx.send("❌ Donne un titre d'anime à suivre.")
        return

    title = title.strip()
    trackers = load_json("anitrackers.json", {})
    user_id = str(ctx.author.id)
    if user_id not in trackers:
        trackers[user_id] = []

    trackers[user_id].append(title)
    save_json("anitrackers.json", trackers)
    await ctx.send(f"🔔 Tu seras notifié quand **{title}** sera diffusé.")

# Exemple simple de tâche de fond pour les alertes
@tasks.loop(minutes=1)
async def check_anitrackers():
    now = datetime.datetime.now(tz=TIMEZONE)
    trackers = load_json("anitrackers.json", {})
    for user_id, anime_list in trackers.items():
        username = get_user_anilist(int(user_id))
        if not username:
            continue
        episodes = get_upcoming_episodes(username)
        for ep in episodes:
            if any(title.lower() in ep['title'].lower() for title in anime_list):
                try:
                    user = await bot.fetch_user(int(user_id))
                    await user.send(f"📺 **{ep['title']}** – Épisode {ep['episode']} est prévu bientôt !")
                except:
                    pass

async def setup(bot):
    bot.add_command(set_alert)
    bot.add_command(toggle_reminder)
    bot.add_command(set_notification_channel)
    bot.add_command(anitracker)
    check_anitrackers.start()
