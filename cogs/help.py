
import discord
from discord.ext import commands
from discord.ui import View, Button

class HelpView(View):
    def __init__(self, embeds):
        super().__init__(timeout=None)
        self.embeds = embeds
        self.index = 0
        self.message = None

        self.previous = Button(label="◀", style=discord.ButtonStyle.secondary)
        self.next = Button(label="▶", style=discord.ButtonStyle.secondary)

        self.previous.callback = self.go_previous
        self.next.callback = self.go_next

        self.add_item(self.previous)
        self.add_item(self.next)

    async def go_previous(self, interaction):
        self.index = (self.index - 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    async def go_next(self, interaction):
        self.index = (self.index + 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        embeds = []

        embed1 = discord.Embed(title="🎮 Quiz & Classement", description="\n".join([
            "`!animequiz` - Trouve le nom de l’anime à partir de l’image",
            "`!quiztop` - Classement des meilleurs joueurs",
            "`!myrank` - Ton niveau et titre personnalisé"
        ]), color=discord.Color.blue())

        embed2 = discord.Embed(title="🗓️ Planning & Épisodes", description="\n".join([
            "`!next` - Prochains épisodes à sortir",
            "`!monnext` - Ton prochain épisode personnel",
            "`!monplanning` - Ton planning personnel",
            "`!seasonal` - Animés de la saison actuelle"
        ]), color=discord.Color.blue())

        embed3 = discord.Embed(title="🏆 Défis & Statistiques", description="\n".join([
            "`!anichallenge` - Défi à compléter",
            "`!weekly` - Défi de la semaine",
            "`!complete` - Marque ton défi comme terminé",
            "`!mystats` - Tes stats de quiz",
            "`!duelstats` - Tes victoires/défaites en duel"
        ]), color=discord.Color.blue())

        embed4 = discord.Embed(title="📡 Suivi & Utilitaires", description="\n".join([
            "`!linkanilist` - Lie ton compte Anilist",
            "`!anitracker` - Voir les animés suivis",
            "`!track`/`!untrack` - Gérer les suivis",
            "`!uptime` - Temps depuis le démarrage du bot",
            "`!todayinhistory` - Événement historique du jour"
        ]), color=discord.Color.blue())

        embeds.extend([embed1, embed2, embed3, embed4])

        view = HelpView(embeds)
        await ctx.send(embed=embeds[0], view=view)

async def setup(bot):
    await bot.add_cog(Help(bot))
