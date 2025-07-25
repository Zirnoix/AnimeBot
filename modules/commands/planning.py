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
async def next_episode(self, ctx):
    username = get_user_anilist(ctx.author.id) or OWNER_USERNAME
    episodes = get_upcoming_episodes(username)

    if not episodes:
        return await ctx.send("📭 Aucun épisode à venir trouvé.")

    next_ep = episodes[0]
    time = next_ep["airing_at"].strftime("%A %d %B %Y à %Hh%M")

    embed = discord.Embed(
        title="📺 Prochain épisode à venir",
        description=f"**{next_ep['title']}** – Épisode {next_ep['episode']}",
        color=discord.Color.green()
    )
    embed.add_field(name="📅 Date de diffusion", value=time)
    embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

    await ctx.send(embed=embed)

async def setup(bot):
    bot.add_command(mon_planning)
    bot.add_command(next_episode)
