import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button

class HelpMenu(View):
    def __init__(self, embeds):
        super().__init__(timeout=None)
        self.embeds = embeds
        self.current_page = 0
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        self.add_item(Button(label="⬅️", style=discord.ButtonStyle.primary, custom_id="prev"))
        self.add_item(Button(label="➡️", style=discord.ButtonStyle.primary, custom_id="next"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.primary, custom_id="prev")
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.primary, custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        pages = []

        # ℹ️ Commandes Générales
        embed1 = discord.Embed(title="📘 Aide - Général", description="Commandes d'information et basiques.", color=0x7289da)
        embed1.add_field(name="!help", value="Affiche ce menu d'aide.", inline=False)
        embed1.add_field(name="!ping", value="Test de latence du bot.", inline=False)
        embed1.add_field(name="!uptime", value="Temps de fonctionnement du bot.", inline=False)
        embed1.add_field(name="!botinfo", value="Informations sur le bot.", inline=False)
        embed1.add_field(name="!source", value="Lien vers le code source du bot.", inline=False)
        embed1.add_field(name="!todayinhistory", value="Anecdote animée du jour dans l'histoire.", inline=False)
        embed1.set_footer(text="AnimeBot - Aide")

        # 👤 Commandes Anilist & Utilisateur
        embed2 = discord.Embed(title="👤 Aide - Utilisateur & Anilist", description="Liens et stats de ton compte Anilist.", color=0x3498db)
        embed2.add_field(name="!linkanilist <pseudo>", value="Lie ton compte Anilist.", inline=False)
        embed2.add_field(name="!unlinkanilist", value="Dé-lie ton compte Anilist.", inline=False)
        embed2.add_field(name="!anilist", value="Affiche ton profil Anilist lié.", inline=False)
        embed2.add_field(name="!stats", value="Statistiques détaillées de ton compte Anilist.", inline=False)
        embed2.set_footer(text="AnimeBot - Aide")

        # 📺 Commandes Animés & Notifications
        embed3 = discord.Embed(title="📺 Aide - Suivi & Planning", description="Système de suivi des épisodes et planning.", color=0x9b59b6)
        embed3.add_field(name="!next", value="Prochain épisode à venir (basé sur le compte du bot).", inline=False)
        embed3.add_field(name="!monnext", value="Prochain épisode avec ton compte lié.", inline=False)
        embed3.add_field(name="!planning", value="Planning hebdomadaire des sorties d’animes.", inline=False)
        embed3.add_field(name="!setchannel", value="Définit le salon pour les alertes de sortie d’épisodes.", inline=False)
        embed3.set_footer(text="AnimeBot - Aide")

        # 🎮 Commandes Quiz & Classements
        embed4 = discord.Embed(title="🎮 Aide - Quiz & Classements", description="Jeux, scores et classements mensuels.", color=0xe67e22)
        embed4.add_field(name="!animequiz", value="Devine l’anime via une image. +1 point par bonne réponse.", inline=False)
        embed4.add_field(name="!animequizmulti <N>", value="Fait N quiz d’affilée (entre 5 et 20). Gagne si +50% bonnes réponses.", inline=False)
        embed4.add_field(name="!quiztop", value="Top 10 des meilleurs joueurs du mois.", inline=False)
        embed4.add_field(name="!myrank", value="Ton score et ton classement actuel.", inline=False)
        embed4.set_footer(text="AnimeBot - Aide")

        pages.extend([embed1, embed2, embed3, embed4])

        view = HelpMenu(pages)
        view.update_buttons()
        msg = await ctx.send(embed=pages[0], view=view)
        view.message = msg

async def setup(bot):
    await bot.add_cog(Help(bot))
