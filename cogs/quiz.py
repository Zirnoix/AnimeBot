import discord
from discord.ext import commands
from modules.score_manager import load_scores, save_scores, add_quiz_point, get_top_scores, reset_monthly_scores, get_user_rank
from modules.rank_card import generate_rank_card
from modules.quiz import get_days_until_reset, fetch_quiz_question, get_title, update_score, get_random_anime
import asyncio
import random
import aiohttp

ANILIST_API_URL = "https://graphql.anilist.co"

class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="animequiz")
    async def anime_quiz(self, ctx):
        await ctx.send("🔍 Début de la commande anime_quiz()")
        await ctx.send("📩 Commande reçue ! Je commence le quiz...")
        await ctx.send("📡 Je vais chercher un anime...")
        await ctx.trigger_typing()

        anime = await get_random_anime()  # 👈 Assure-toi que cette fonction est bien importée

        if not anime:
            await ctx.send("❌ Impossible de récupérer un anime. Réessaie.")
                return

        title = anime["title"]["romaji"]
        print(f"[DEBUG] Titre sélectionné : {title}")

        image_url = anime.get("coverImage", {}).get("extraLarge") or anime.get("coverImage", {}).get("large")
        print(f"[DEBUG] Image URL : {image_url}")

        embed = discord.Embed(
            title="🎲 Devine l’anime !",
            description="Tu as 15 secondes pour trouver le nom !",
            color=discord.Color.blurple()
        )
        embed.set_image(url=image_url)

        await ctx.send(embed=embed)
        print("[DEBUG] Embed envoyé")

        def check(m):
            return m.channel == ctx.channel and m.author == ctx.author

        try:
            msg = await self.bot.wait_for("message", timeout=15.0, check=check)
            print(f"[DEBUG] Message reçu : {msg.content}")
        except asyncio.TimeoutError:
            await ctx.send(f"⏱️ Temps écoulé ! La bonne réponse était : **{title}**")
            print("[DEBUG] Timeout utilisateur")
            return

        if normalize(msg.content) in [
            normalize(title),
            normalize(anime["title"].get("english", "")),
            normalize(anime["title"].get("native", ""))
        ]:
            await ctx.send("✅ Bonne réponse !")
        else:
            await ctx.send(f"❌ Mauvaise réponse. C’était : **{title}**")

    @commands.command(name="animequizmulti")
    async def anime_quiz_multi(self, ctx, nombre: int):
        if not (5 <= nombre <= 20):
            await ctx.send("❌ Tu dois choisir un nombre entre 5 et 20.")
            return

        score = 0
        for _ in range(nombre):
            question = fetch_quiz_question()
            if not question:
                await ctx.send("❌ Impossible de récupérer une question de quiz.")
                return

            embed = discord.Embed(title="🎮 Anime Quiz", description="Quel est cet anime ?", color=0x3498db)
            embed.set_image(url=question['image'])
            options = question['options']
            correct_index = question['answer']

            view = discord.ui.View()
            for i, opt in enumerate(options):
                view.add_item(discord.ui.Button(label=opt, style=discord.ButtonStyle.primary, custom_id=str(i)))

            message = await ctx.send(embed=embed, view=view)

            def check(inter):
                return inter.user == ctx.author and inter.message.id == message.id

            try:
                interaction = await self.bot.wait_for("interaction", timeout=20.0, check=check)
            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Temps écoulé ! La bonne réponse était : **{options[correct_index]}**")
                continue

            if int(interaction.data["custom_id"]) == correct_index:
                await interaction.response.send_message("✅ Bonne réponse !")
                score += 1
            else:
                await interaction.response.send_message(f"❌ Mauvaise réponse. C'était **{options[correct_index]}**")

            await asyncio.sleep(1)

        if score > nombre // 2:
            update_score(ctx.author.id, score)
            await ctx.send(f"🏁 Quiz terminé ! Tu as obtenu {score}/{nombre} bonnes réponses. +{score} points !")
        else:
            await ctx.send(f"🏁 Quiz terminé ! Tu as obtenu {score}/{nombre} bonnes réponses. Aucun point gagné.")

    @commands.command(name="quiztop")
    async def quiztop(self, ctx):
        scores = load_scores()
        if not scores:
            await ctx.send("🏆 Aucun score enregistré pour l’instant.")
            return

        leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]

        desc = ""
        for i, (uid, score) in enumerate(leaderboard, 1):
            user = await self.bot.fetch_user(uid)
            desc += f"**{i}.** {user.name} — {score} points ({get_title(score)})\n"

        days_left = get_days_until_reset()
        embed = discord.Embed(title="🏆 Classement Quiz", description=desc, color=0xf1c40f)
        embed.set_footer(text=f"🏁 Réinitialisation dans {days_left} jour(s).")
        await ctx.send(embed=embed)

    @commands.command(name="myrank")
    async def myrank(self, ctx):
        scores = load_scores()
        user_id = ctx.author.id
        points = scores.get(user_id, 0)
        img = generate_rank_card(ctx.author, points)
        file = discord.File(fp=img, filename="rank.png")
        await ctx.send(file=file)

async def get_random_anime():
    query = '''
    query ($page: Int) {
        Page(perPage: 1, page: $page) {
            media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
                title {
                    romaji
                    english
                    native
                }
                coverImage {
                    large
                    extraLarge
                }
            }
        }
    }
    '''
    page = random.randint(1, 500)

    async with aiohttp.ClientSession() as session:
        async with session.post("https://graphql.anilist.co", json={"query": query, "variables": {"page": page}}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            try:
                return data["data"]["Page"]["media"][0]
            except (KeyError, IndexError):
                return None
                
def normalize(text):
    return ''.join(e for e in text.lower() if e.isalnum())

async def setup(bot):
    print("[DEBUG] Quiz cog setup() appelé")
    await bot.add_cog(Quiz(bot))
