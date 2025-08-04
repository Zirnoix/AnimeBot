# cogs/help.py

import discord
from discord.ext import commands

class CustomHelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def custom_help(self, ctx):
        embed = discord.Embed(
            title="📚 Commandes disponibles",
            description="Voici la liste des commandes organisées par catégorie :",
            color=0xf1c40f
        )

        embed.add_field(
            name="🎮 Quiz et Mini-jeux",
            value=(
                "`!animequiz` - Quiz solo sur les animés\n"
                "`!animequizmulti` - Quiz multi-joueurs\n"
                "`!guessyear` - Devine l’année de diffusion\n"
                "`!guessgenre` - Devine le genre de l’anime\n"
                "`!guessepisode` - Trouve le numéro d’épisode\n"
                "`!guesscharacter` - Devine le personnage\n"
                "`!guessop` - Trouve l’opening audio"
            ),
            inline=False
        )

        embed.add_field(
            name="📊 Stats et Profils",
            value=(
                "`!mycard` - Affiche ta carte de joueur\n"
                "`!mystats` - Affiche tes stats globales\n"
                "`!myrank` - Affiche ton rang XP"
            ),
            inline=False
        )

        embed.add_field(
            name="🎥 AniList",
            value=(
                "`!linkanilist` - Lier ton compte AniList\n"
                "`!unlinkanilist` - Supprimer le lien\n"
                "`!anilist` - Voir ton profil\n"
                "`!stats` - Statistiques de visionnage"
            ),
            inline=False
        )

        embed.add_field(
            name="📆 Planning et Notifications",
            value=(
                "`!planning` - Planning du jour\n"
                "`!next` - Prochain épisode à venir\n"
                "`!setchannel` - Activer les notifs auto\n"
                "`!disablechannel` - Désactiver les notifs"
            ),
            inline=False
        )

        embed.add_field(
            name="⚙️ Divers",
            value=(
                "`!ping` - Latence du bot\n"
                "`!uptime` - Depuis combien de temps il tourne\n"
                "`!botinfo` - Infos système\n"
                "`!source` - Lien du code du bot"
            ),
            inline=False
        )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CustomHelp(bot))
