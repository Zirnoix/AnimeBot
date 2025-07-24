from discord.ext import commands
import discord
from datetime import datetime
from babel.dates import format_datetime
from modules.utils import get_upcoming_episodes, get_user_anilist, genre_emoji, TIMEZONE
import pytz

@commands.command(name="monplanning")
async def mon_planning(ctx):
    username = get_user_anilist(ctx.author.id)
    if not username:
        await ctx.send("❌ Tu n’as pas encore lié ton compte AniList. Utilise `!linkanilist <pseudo>`.")
        return

    episodes = get_upcoming_episodes(username)
    if not episodes:
        await ctx.send(f"📭 Aucun épisode à venir trouvé pour **{username}**.")
        return

    embed = discord.Embed(
        title=f"📅 Planning personnel – {username}",
        description="Voici les prochains épisodes à venir dans ta liste.",
        color=discord.Color.teal()
    )

    for ep in sorted(episodes, key=lambda e: e["airingAt"])[:10]:
        dt = datetime.fromtimestamp(ep["airingAt"], tz=TIMEZONE)
        emoji = genre_emoji(ep["genres"])
        date_fr = format_datetime(dt, "EEEE d MMMM", locale='fr_FR').capitalize()
        heure = dt.strftime('%H:%M')
        value = f"🕒 {date_fr} à {heure}"

        embed.add_field(
            name=f"{emoji} {ep['title']} – Épisode {ep['episode']}",
            value=value,
            inline=False
        )

    embed.set_thumbnail(url=episodes[0]["image"])
    await ctx.send(embed=embed)


@commands.command(name="next")
async def next_episode(ctx):
    episodes = get_upcoming_episodes("default_user")  # Peut être remplacé par un nom ou système
    if not episodes:
        await ctx.send("❌ Aucun épisode à venir trouvé.")
        return

    next_ep = min(episodes, key=lambda e: e["airingAt"])
    dt = datetime.fromtimestamp(next_ep["airingAt"], tz=TIMEZONE)
    date_fr = format_datetime(dt, "EEEE d MMMM", locale='fr_FR').capitalize()
    heure = dt.strftime('%H:%M')
    msg = f"🎬 Prochain épisode : **{next_ep['title']}** – Épisode {next_ep['episode']}\n🕒 {date_fr} à {heure}"
    await ctx.send(msg)

def setup(bot):
    bot.add_command(mon_planning)
    bot.add_command(next_episode)