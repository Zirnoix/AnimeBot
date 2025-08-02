import discord
from discord.ext import commands

class Help(commands.Cog):
    """Cog fournissant la commande d'aide du bot."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context) -> None:
        """Affiche les différentes catégories de commandes du bot."""
        pages = [
            {
                "title": "📅 Épisodes & Planning + 🔔 Notifications",
                "fields": [
                    ("`!next` / `!monnext`", "Prochain épisode dans ta liste ou celle d'un membre."),
                    ("`!planning` / `!monplanning`", "Planning complet de la semaine."),
                    ("`!prochains <genre>`", "Épisodes à venir filtrés par genre."),
                    ("`!planningvisuel`", "Affiche une version visuelle du planning."),
                    ("`!reminder`", "Active ou désactive les rappels quotidiens."),
                    ("`!setalert HH:MM`", "Définit l’heure de ton résumé automatique."),
                    ("`!anitracker <titre>`", "Suis un anime et reçois une alerte DM."),
                    ("`!anitracker list` / `remove <titre>`", "Voir ou retirer tes suivis.")
                ]
            },
            {
                "title": "🎮 Quiz & Niveaux + 🏆 Challenges",
                "fields": [
                    ("`!animequiz`", "Devine un anime en solo."),
                    ("`!animequizmulti <N>`", "Enchaîne N questions à difficulté aléatoire."),
                    ("`!duel @ami`", "Affronte un ami en duel de 3 questions."),
                    ("`!animebattle`", "Mode quiz duel basé sur des descriptions."),
                    ("`!quiztop`", "Classement des meilleurs au quiz."),
                    ("`!myrank`", "Affiche ton niveau, XP et ton titre."),
                    ("`!anichallenge`", "Reçois un anime à regarder et note-le."),
                    ("`!challenge complete <note>`", "Valide ton défi en cours avec une note."),
                    ("`!weekly`", "Obtiens un nouveau défi hebdomadaire."),
                    ("`!weekly complete`", "Valide ton défi hebdomadaire.")
                ]
            },
            {
                "title": "📊 Stats & Profils + 🎯 Comparaison",
                "fields": [
                    ("`!linkanilist <pseudo>`", "Lier ton compte AniList au bot."),
                    ("`!unlink`", "Retirer le lien avec ton compte AniList."),
                    ("`!mystats` / `!stats @utilisateur`", "Carte de profil (toi ou un membre du serveur)."),
                    ("`!mychart` / `!monchart`", "Répartition de tes genres préférés."),
                    ("`!duelstats @ami`", "Compare tes stats AniList avec un ami."),
                    ("`!classementgenre <genre>`", "Top membres passionnés par ce genre.")
                ]
            },
            {
                "title": "🛠️ Utilitaires & Recherche",
                "fields": [
                    ("`!uptime`", "Depuis combien de temps le bot est actif."),
                    ("`!setchannel`", "Définit ce salon comme canal des notifications."),
                    ("`!search <titre>`", "Recherche un anime par titre."),
                    ("`!seasonal`", "Top 10 des animés de la saison en cours."),
                    ("`!topanime`", "Top des animés les mieux notés.")
                ]
            }
        ]
        for page in pages:
            embed = discord.Embed(title=page["title"], color=discord.Color.blurple())
            for name, value in page["fields"]:
                embed.add_field(name=name, value=value, inline=False)
            await ctx.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
