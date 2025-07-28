import discord
from discord.ext import commands

class HelpMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.current_page = 0
        self.embeds = self.generate_embeds()

    def generate_embeds(self):
        embeds = []

        # Page 1 - Général
        embed1 = discord.Embed(title="📚 Commandes - Général", description="Commandes d'information générale", color=0x3498db)
        embed1.add_field(name="🔹 Général", value="`!help` - Affiche ce menu\n`!ping` - Test de latence\n`!uptime` - Uptime du bot\n`!botinfo` - Infos sur le bot\n`!source` - Lien du code source\n`!todayinhistory` - Anecdote du jour dans l’histoire des animés", inline=False)
        embeds.append(embed1)

        # Page 2 - Anilist
        embed2 = discord.Embed(title="👤 Commandes - Anilist", description="Gestion de ton compte Anilist", color=0x1abc9c)
        embed2.add_field(name="👤 Anilist", value="`!linkanilist <pseudo>` - Lier ton compte Anilist\n`!unlinkanilist` - Dé-lier ton compte\n`!anilist` - Voir ton profil Anilist\n`!stats` - Statistiques de ton compte Anilist", inline=False)
        embeds.append(embed2)

        # Page 3 - Planning & Épisodes
        embed3 = discord.Embed(title="⏭️ Commandes - Planning & Épisodes", description="Infos sur les épisodes et planning hebdo", color=0xe67e22)
        embed3.add_field(name="⏭️ Épisodes & Planning", value="`!next` - Prochain épisode à venir\n`!monnext` - Prochain épisode (ton compte)\n`!planning` - Planning de la semaine\n`!setchannel` - Définir le salon d’alerte", inline=False)
        embeds.append(embed3)

        # Page 4 - Quiz & Classement
        embed4 = discord.Embed(title="🧠 Commandes - Quiz & Classements", description="Jeux et compétitions de quiz", color=0x9b59b6)
        embed4.add_field(name="🧠 Quiz & Classements", value="`!animequiz` - Deviner un anime via une image (+1 point)\n`!animequizmulti <N>` - Série de quiz (5 à 20)\n`!quiztop` - Classement mensuel\n`!myrank` - Ton score et ton rang", inline=False)
        embeds.append(embed4)

        return embeds

    @discord.ui.button(label='⬅️', style=discord.ButtonStyle.primary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label='➡️', style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        view = HelpMenu()
        await ctx.send(embed=view.embeds[0], view=view)

async def setup(bot):
    await bot.add_cog(Help(bot))
