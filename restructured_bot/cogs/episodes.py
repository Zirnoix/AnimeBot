import calendar
from datetime import datetime
import discord
from discord.ext import commands

from restructured_bot.modules import core

class Episodes(commands.Cog):
    """Cog pour les commandes liées aux épisodes et au planning."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="prochains")
    async def prochains(self, ctx: commands.Context, *args: str) -> None:
        """Affiche les prochains épisodes à venir (peut filtrer par genre et nombre)."""
        filter_genre: str | None = None
        limit: int = 10
        for arg in args:
            if arg.isdigit():
                limit = min(100, int(arg))
            elif arg.lower() in {"all", "tout"}:
                limit = 100
            else:
                filter_genre = arg.capitalize()
        episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)
        if not episodes:
            await ctx.send("Aucun épisode à venir.")
            return
        if filter_genre:
            episodes = [ep for ep in episodes if filter_genre in ep.get("genres", [])]
            if not episodes:
                await ctx.send(f"Aucun épisode trouvé pour le genre **{filter_genre}**.")
                return
        episodes = sorted(episodes, key=lambda e: e["airingAt"])[:limit]
        embed = discord.Embed(
            title="📅 Prochains épisodes",
            description=f"Épisodes à venir{f' pour le genre **{filter_genre}**' if filter_genre else ''} :",
            color=discord.Color.blurple(),
        )
        for ep in episodes:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            date_fr = core.format_date_fr(dt, "d MMMM")
            jour = core.JOURS_FR.get(dt.strftime("%A"), dt.strftime("%A"))
            heure = dt.strftime("%H:%M")
            value = f"🗓️ {jour} {date_fr} à {heure}"
            emoji = core.genre_emoji(ep.get("genres", []))
            embed.add_field(
                name=f"{emoji} {ep['title']} — Épisode {ep['episode']}",
                value=value,
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command(name="next")
    async def next_episode(self, ctx: commands.Context) -> None:
        """Affiche le prochain épisode à venir dans la liste AniList de l'utilisateur ou d'un ami mentionné."""
        user_id = str(ctx.author.id)
        try:
            airing = core.get_next_airing(ctx.author.id)
            if not airing:
                await ctx.send("❌ Aucun épisode à venir trouvé ou compte AniList non lié.")
                return
            # Préparer les données pour l'image
            ep_media = airing["media"]
            dt = datetime.fromtimestamp(airing["airingAt"], tz=core.TIMEZONE)
            buf = core.generate_next_image(
                ep={
                    "title": ep_media["title"].get("romaji", "Titre inconnu"),
                    "episode": airing["episode"],
                    "image": ep_media["coverImage"].get("extraLarge"),
                    "genres": ep_media.get("genres", []),
                },
                dt=dt,
                tagline="Prochain épisode"
            )
            if not buf:
                await ctx.send("❌ Impossible de générer l’image du prochain épisode.")
                return
            file = discord.File(buf, filename="next.jpg")
            embed = discord.Embed(title="📺 Prochain épisode", color=discord.Color.dark_purple())
            embed.set_image(url="attachment://next.jpg")
            await ctx.send(embed=embed, file=file)
        except Exception as e:
            await ctx.send(f"❌ Une erreur est survenue : `{type(e).__name__}` — {e}")

    @commands.command(name="monnext")
    async def my_next(self, ctx: commands.Context) -> None:
        """Affiche le prochain épisode à venir pour l'utilisateur (compte AniList lié requis)."""
        username = core.get_user_anilist(ctx.author.id)
        if not username:
            await ctx.send("❌ Tu n’as pas encore lié ton compte AniList. Utilise `!linkanilist <pseudo>`.") 
            return
        episodes = core.get_upcoming_episodes(username)
        if not episodes:
            await ctx.send("📭 Aucun épisode à venir dans ta liste AniList.")
            return
        next_ep = min(episodes, key=lambda e: e["airingAt"])
        dt = datetime.fromtimestamp(next_ep["airingAt"], tz=core.TIMEZONE)
        try:
            buf = core.generate_next_image(next_ep, dt, tagline="Ton prochain épisode")
            file = discord.File(buf, filename="mynext.jpg")
            embed = discord.Embed(title="🎬 Ton prochain épisode", color=discord.Color.purple())
            embed.set_image(url="attachment://mynext.jpg")
            await ctx.send(embed=embed, file=file)
        except Exception:
            # Secours : embed texte si l’image ne peut être générée
            embed = discord.Embed(
                title="🎬 Ton prochain épisode à venir",
                description=f"{next_ep['title']} — Épisode {next_ep['episode']}",
                color=discord.Color.purple(),
            )
            embed.add_field(
                name="Date",
                value=dt.strftime("%d/%m/%Y à %H:%M"),
                inline=False
            )
            await ctx.send(embed=embed)

    @commands.command(name="planning")
    async def planning(self, ctx: commands.Context) -> None:
        """Affiche le planning hebdomadaire global des épisodes à venir."""
        episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)
        if not episodes:
            await ctx.send("Aucun planning disponible.")
            return
        # Grouper les épisodes par jour (en français)
        planning: dict[str, list[str]] = {day: [] for day in core.JOURS_FR.values()}
        for ep in episodes:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            jour = core.JOURS_FR.get(dt.strftime("%A"), dt.strftime("%A"))
            time_str = dt.strftime("%H:%M")
            planning[jour].append(f"• {ep['title']} — Ép. {ep['episode']} ({time_str})")
        # Envoyer un embed par jour contenant les épisodes
        for day, items in planning.items():
            if not items:
                continue
            embed = discord.Embed(
                title=f"📅 Planning du {day}",
                description="\n".join(items[:10]),
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)

    @commands.command(name="monplanning")
    async def mon_planning(self, ctx: commands.Context) -> None:
        """Affiche les prochains épisodes à venir dans la liste AniList de l'utilisateur lié."""
        username = core.get_user_anilist(ctx.author.id)
        if not username:
            await ctx.send("❌ Tu n’as pas encore lié ton compte AniList. Utilise `!linkanilist <pseudo>`.")
            return
        episodes = core.get_upcoming_episodes(username)
        if not episodes:
            await ctx.send(f"📭 Aucun épisode à venir trouvé pour **{username}**.")
            return
        embed = discord.Embed(
            title=f"📅 Planning personnel – {username}",
            description="Voici les prochains épisodes à venir dans ta liste.",
            color=discord.Color.teal(),
        )
        for ep in sorted(episodes, key=lambda e: e["airingAt"])[:10]:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            emoji = core.genre_emoji(ep.get("genres", []))
            date_fr = core.format_date_fr(dt, "EEEE d MMMM")
            heure = dt.strftime('%H:%M')
            embed.add_field(
                name=f"{emoji} {ep['title']} – Épisode {ep['episode']}",
                value=f"🕒 {date_fr} à {heure}",
                inline=False
            )
        # Utiliser la couverture du premier anime en vignette
        if episodes:
            embed.set_thumbnail(url=episodes[0].get("image"))
        await ctx.send(embed=embed)

    @commands.command(name="planningvisuel")
    async def planningvisuel(self, ctx: commands.Context) -> None:
        """Génère une image récapitulative du planning hebdomadaire des épisodes."""
        import io
        from PIL import Image, ImageDraw, ImageFont

        episodes = core.get_upcoming_episodes(core.ANILIST_USERNAME)
        if not episodes:
            await ctx.send("❌ Impossible de récupérer les épisodes à venir.")
            return
        # Préparation des données par jour (anglais -> français via JOURS_FR)
        days_en = list(calendar.day_name)  # ["Monday", ... "Sunday"]
        planning = {core.JOURS_FR.get(day, day): [] for day in days_en}
        for ep in episodes:
            dt = datetime.fromtimestamp(ep["airingAt"], tz=core.TIMEZONE)
            day_fr = core.JOURS_FR.get(dt.strftime("%A"), dt.strftime("%A"))
            planning[day_fr].append({
                "title": ep["title"],
                "episode": ep["episode"],
                "time": dt.strftime("%H:%M")
            })
        # Création de l'image (800x600)
        width, height = 800, 600
        card = Image.new("RGB", (width, height), (30, 30, 40))
        draw = ImageDraw.Draw(card)
        # Polices
        font_title = core.load_font(28, bold=True)
        font_day = core.load_font(22, bold=True)
        font_text = core.load_font(18)
        # Titre
        draw.text((20, 20), "Planning des épisodes – Semaine", font=font_title, fill="white")
        # Placement du texte
        x, y = 40, 70
        for day, items in planning.items():
            draw.text((x, y), f"> {day}", font=font_day, fill="#ffdd77")
            y += 30
            for ep in items[:4]:  # max 4 épisodes par jour pour lisibilité
                draw.text((x + 10, y), f"• {ep['title']} – Ep {ep['episode']} ({ep['time']})", font=font_text, fill="white")
                y += 24
            y += 30
        # Enregistrement temporaire et envoi
        buf = io.BytesIO()
        card.save(buf, format="PNG")
        buf.seek(0)
        file = discord.File(buf, filename="planning.png")
        await ctx.send(file=file)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Episodes(bot))
