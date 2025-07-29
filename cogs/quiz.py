import sys
sys.stdout.write("[DEBUG] cogs.quiz chargé\n")
sys.stdout.flush()
import discord
from discord.ext import commands
from modules.score_manager import load_scores, update_score
from modules.rank_card import generate_rank_card
from modules.quiz import get_days_until_reset, fetch_quiz_question, get_title
import asyncio
import random
import aiohttp

def normalize(text):
    return ''.join(e for e in text.lower() if e.isalnum())

class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def testquiz(self, ctx):
        await ctx.send("✅ Cog quiz chargé correctement.")

    @commands.command(name="animequiz")
    async def anime_quiz(self, ctx):
        try:
            async with ctx.typing():

                anime = await get_random_anime()

                if not anime:
                    await ctx.send("❌ Impossible de récupérer un anime.")
                    return

                title = anime["title"]["romaji"]
                image_url = anime.get("coverImage", {}).get("extraLarge") or anime.get("coverImage", {}).get("large")

                embed = discord.Embed(
                    title="🎲 Devine l’anime !",
                    description="Tu as 15 secondes pour trouver le nom !",
                    color=discord.Color.blurple()
                )
                embed.set_image(url=image_url)
                await ctx.send(embed=embed)

                def check(m):
                    return m.channel == ctx.channel and m.author == ctx.author

                msg = await self.bot.wait_for("message", timeout=15.0, check=check)

                if normalize(msg.content) in [
                    normalize(title),
                    normalize(anime["title"].get("english") or ""),
                    normalize(anime["title"].get("native") or "")
                ]:
                    
                    await ctx.send("✅ Bonne réponse !")
                    update_score(ctx.author.id, 1)
                    await ctx.send("💾 Score mis à jour !")
                else:
                    await ctx.send(f"❌ Mauvaise réponse. C’était : **{title}**")

        except asyncio.TimeoutError:
            await ctx.send(f"⏱️ Temps écoulé ! La bonne réponse était : **{title}**")

        except Exception as e:
            await ctx.send(f"❌ Erreur pendant le quiz : {e}")


    @commands.command(name="quiztop")
    async def quiztop(self, ctx):
        scores = load_scores()
        if not scores:
            await ctx.send("🏆 Aucun score enregistré pour l’instant.")
            return

        leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
        desc = ""

        for i, (uid, score) in enumerate(leaderboard, 1):
            try:
                user = await self.bot.fetch_user(int(uid))
            except Exception as e:
                await ctx.send(f"❌ Erreur fetch_user({uid}) : {e}")
                continue

            try:
                title = get_title(score)
            except Exception as e:
                title = "⛔️"
                await ctx.send(f"❌ Erreur titre pour {user.name} : {e}")

            desc += f"**{i}.** {user.name} — {score} points ({title})\n"

        if not desc:
            await ctx.send("❌ Aucun utilisateur valide pour le classement.")
            return

        days_left = get_days_until_reset()
        embed = discord.Embed(title="🏆 Classement Quiz", description=desc, color=0xf1c40f)
        embed.set_footer(text=f"🏁 Réinitialisation dans {days_left} jour(s).")
        await ctx.send(embed=embed)

    @commands.command(name="myrank")
    async def myrank(self, ctx):
        scores = load_scores()
        points = scores.get(str(ctx.author.id), 0)
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

async def setup(bot):
    await bot.add_cog(Quiz(bot))
