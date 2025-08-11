import discord
from discord.ext import commands

class Help(commands.Cog):
    """Commande !help personnalisée avec embed."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def custom_help(self, ctx):
        """Affiche l'aide du bot avec catégories et emojis."""
        embed = discord.Embed(
            title="📚 Commandes disponibles",
            description="Voici la liste des commandes que tu peux utiliser :",
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="🎮 Quiz & Mini-jeux",
            value=(
                "`!animequiz` - Trouve l'anime à partir du résumé\n"
                "`!animequizmulti` - Version multi-joueurs\n"
                "`!quiztop` - Classement des meilleurs joueurs\n"
                "`!higherlower`, `!guessyear`, `!guessop`\n"
                "`!guessepisodes`, `!guessgenre`\n"
            ),
            inline=False
        )

        embed.add_field(
            name="📅 Épisodes & Planning",
            value=(
                "`!prochains` - Voir les prochains épisodes\n"
                "`!next` / `!monnext` - Prochain épisode (global / perso)\n"
                "`!planning` / `!monplanning` - Planning hebdomadaire"
            ),
            inline=False
        )

        embed.add_field(
            name="🧷 Track (suivi en MP)",
            value=(
                "`!track list` – Affiche ta liste d'animes suivis\n"
                "`!track add <titre>` – Ajoute un anime à ta liste\n"
                "`!track remove <titre>` – Retire un anime de ta liste\n"
                "`!track clear` – Vide ta liste\n\n"
                "🔔 Tu recevras un **MP** 15 min avant la sortie du prochain épisode "
                "des animes suivis. Les confirmations (add/remove/list) partent aussi en MP."
            ),
            inline=False
        )


        embed.add_field(
            name="🧑 Profil & Statistiques",
            value=(
                "`!myrank` - Voir ton rang actuel\n"
                "`!mystats` - Statistiques AniList\n"
                "`!mycard` - Carte de profil AnimeBot"
            ),
            inline=False
        )

        embed.add_field(
            name="🔗 Liens & AniList",
            value=(
                "`!linkanilist <pseudo>` - Lier ton compte AniList\n"
                "`!unlink` - Délier ton compte\n"
                "`!duelstats @membre` - Comparer les stats AniList"
            ),
            inline=False
        )

        embed.add_field(
            name="⚙️ Divers",
            value=(
                "`!ping`, `!uptime`, `!botinfo`, `!source`, etc."
            ),
            inline=False
        )

        embed.set_footer(text="AnimeBot • Codé par Zirnoixd'coco.")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))
