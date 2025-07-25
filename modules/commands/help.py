from discord.ext import commands
import discord

class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", help="Affiche la liste des commandes disponibles.")
    async def help_command(self, ctx):
        pages = [
            discord.Embed(
                title="📚 Aide - Page 1/3",
                description="Voici quelques commandes utiles pour t’amuser avec le bot.",
                color=discord.Color.blurple()
            )
            .add_field(name="🎮 !animequiz", value="Lance un quiz avec des animés de ta liste AniList.", inline=False)
            .add_field(name="➡️ !next", value="Passe à la question suivante pendant un quiz.", inline=False)
            .add_field(name="🏆 !quiztop", value="Affiche le classement mensuel des meilleurs joueurs.", inline=False),

            discord.Embed(
                title="📚 Aide - Page 2/3",
                description="Commandes pour les défis, les stats et le suivi.",
                color=discord.Color.blurple()
            )
            .add_field(name="🧠 !anichallenge", value="Reçois un anime aléatoire à regarder.", inline=False)
            .add_field(name="✅ !challenge complete <note>", value="Valide ton challenge avec une note sur 10.", inline=False)
            .add_field(name="📅 !planning", value="Affiche les sorties d’épisodes à venir.", inline=False)
            .add_field(name="🔔 !anitracker <anime>", value="Reçois une notification quand un épisode sort.", inline=False),

            discord.Embed(
                title="📚 Aide - Page 3/3",
                description="Utilitaires et autres outils.",
                color=discord.Color.blurple()
            )
            .add_field(name="📈 !genrestats", value="Génère un graphique de tes genres préférés.", inline=False)
            .add_field(name="💾 !linkanilist <pseudo>", value="Lie ton compte AniList au bot.", inline=False)
            .add_field(name="🧑‍💻 !profil", value="Affiche ton profil lié AniList.", inline=False)
        ]

        view = HelpPaginationView(ctx, pages)
        await ctx.send(embed=pages[0], view=view)


class HelpPaginationView(discord.ui.View):
    def __init__(self, ctx, pages):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.pages = pages
        self.index = 0

    async def update(self, interaction):
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("❌ Tu ne peux pas utiliser ces boutons.", ephemeral=True)
        self.index = (self.index - 1) % len(self.pages)
        await self.update(interaction)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("❌ Tu ne peux pas utiliser ces boutons.", ephemeral=True)
        self.index = (self.index + 1) % len(self.pages)
        await self.update(interaction)


async def setup(bot):
    await bot.add_cog(HelpCommand(bot))
