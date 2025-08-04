import discord
from discord.ext import commands
import random
import asyncio

from modules import anilist, xp_manager, score_manager, image, history_data

class AnimeQuiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="animequiz")
    async def anime_quiz(self, ctx):
        user_id = str(ctx.author.id)

        # Empêcher les doublons récents
        history = history_data.get_recent_history(user_id)
        anime = anilist.get_random_anime(exclude_ids=history)

        if not anime:
            await ctx.send("❌ Impossible de récupérer un anime.")
            return

        # Stocker dans l’historique
        history_data.add_to_history(user_id, anime['id'])

        # Nettoyage de la description
        description = anime['description'].replace('\n', ' ').replace('<br>', '').split('.')[0] + "..."

        # Choix de réponses
        options = anilist.get_alternative_titles(anime['title']['romaji'])
        options.append(anime['title']['romaji'])
        random.shuffle(options)

        correct_index = options.index(anime['title']['romaji'])

        embed = discord.Embed(
            title="🧠 Anime Quiz",
            description=f"Quel anime correspond à cette description ?\n\n*{description}*",
            color=discord.Color.orange()
        )
        for i, title in enumerate(options):
            embed.add_field(name=f"{i+1}️⃣", value=title, inline=False)

        quiz_msg = await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

        try:
            guess = await self.bot.wait_for("message", check=check, timeout=20.0)
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était : **{anime['title']['romaji']}**")
            return

        choice = int(guess.content) - 1
        if choice == correct_index:
            await ctx.send("✅ Bonne réponse ! +10 points et +5 XP.")
            score_manager.update_quiz_score(user_id, 10)
            xp_manager.add_xp(user_id, 5)
        else:
            await ctx.send(f"❌ Mauvaise réponse ! C'était : **{anime['title']['romaji']}**")

    @commands.command(name="animequizmulti")
    async def anime_quiz_multi(self, ctx):
        await ctx.send("🛠 La version multijoueur arrive bientôt !")

    @commands.command(name="quiztop")
    async def quiztop(self, ctx):
        leaderboard = score_manager.get_quiz_leaderboard()

        if not leaderboard:
            await ctx.send("🏆 Aucun score enregistré pour l’instant.")
            return

        desc = ""
        for i, (uid, score) in enumerate(leaderboard, 1):
            user = await self.bot.fetch_user(int(uid))
            title = xp_manager.get_rank_title(xp_manager.get_xp(uid))
            desc += f"`#{i}` {user.display_name} — **{score} pts** ({title})\n"

        embed = discord.Embed(
            title="🏆 Classement Quiz",
            description=desc,
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @commands.command(name="myrank")
    async def myrank(self, ctx):
        user = ctx.author
        user_id = str(user.id)

        xp = xp_manager.get_xp(user_id)
        title = xp_manager.get_rank_title(xp)

        path = f"data/{user_id}_rank.png"
        image.save_user_card(user.display_name, xp, title, path)

        file = discord.File(path, filename="rank.png")
        embed = discord.Embed(
            title=f"📈 Rang de {user.display_name}",
            color=discord.Color.blue()
        )
        embed.set_image(url="attachment://rank.png")
        await ctx.send(file=file, embed=embed)

async def setup(bot):
    await bot.add_cog(AnimeQuiz(bot))
