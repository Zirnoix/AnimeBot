""# restructured_bot/cogs/minigames.py

import random
import discord
from discord.ext import commands
from restructured_bot.modules import core

class MiniGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_user_data(self, user_id):
        level = core.get_user_level(user_id)
        xp = core.get_user_xp(user_id)
        return level, xp

    def update_user_data(self, user_id, xp_gain):
        core.add_user_xp(user_id, xp_gain)
        core.increment_minigame_score(user_id, "guess")

    @commands.command(name="higherlower")
    async def higher_lower(self, ctx):
        anime1 = core.get_random_anime()
        anime2 = core.get_random_anime()

        while anime1["id"] == anime2["id"]:
            anime2 = core.get_random_anime()

        score1 = anime1.get("averageScore") or 0
        score2 = anime2.get("averageScore") or 0

        embed = discord.Embed(
            title="📊 Quel anime a le meilleur score AniList ?",
            description=f"**1. {anime1['title']['romaji']}**\nvs\n**2. {anime2['title']['romaji']}**",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Réponds avec 1 ou 2")
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2"]

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30.0)
        except Exception:
            await ctx.send("⏰ Temps écoulé ou réponse invalide.")
            return

        selected = anime1 if msg.content == "1" else anime2
        correct = score1 > score2 if msg.content == "1" else score2 > score1

        if correct:
            self.update_user_data(ctx.author.id, 10)
            await ctx.send(f"✅ Bonne réponse ! +10 XP\n{selected['title']['romaji']} a {selected['averageScore']} de score.")
        else:
            await ctx.send(f"❌ Mauvaise réponse. {selected['title']['romaji']} a {selected['averageScore']} de score.")

    @commands.command(name="higherman")
    async def higher_man(self, ctx):
        animes = [core.get_random_anime() for _ in range(4)]
        scores = [(a, a.get("averageScore", 0)) for a in animes]
        winner = max(scores, key=lambda x: x[1])[0]

        desc = "\n".join([f"{i+1}. {a['title']['romaji']}" for i, a in enumerate(animes)])
        embed = discord.Embed(
            title="🏆 Quel est l'anime le mieux noté ?",
            description=desc,
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30.0)
            choice = int(msg.content)
        except Exception:
            await ctx.send("⏰ Temps écoulé ou réponse invalide.")
            return

        if 1 <= choice <= 4 and animes[choice-1]["id"] == winner["id"]:
            self.update_user_data(ctx.author.id, 20)
            await ctx.send(f"✅ Bonne réponse ! +20 XP\nC'était {winner['title']['romaji']} avec {winner['averageScore']} de score.")
        else:
            await ctx.send(f"❌ Mauvaise réponse. C'était {winner['title']['romaji']}.")

    @commands.command(name="guessyear")
    async def guess_year(self, ctx):
        anime = core.get_random_anime()
        correct_year = anime.get("startDate", {}).get("year")

        if not correct_year:
            await ctx.send("❌ Impossible de récupérer l'année de cet anime.")
            return

        options = [correct_year]
        while len(options) < 4:
            y = random.randint(1980, 2023)
            if y not in options:
                options.append(y)

        random.shuffle(options)

        desc = "\n".join([f"{i+1}. {y}" for i, y in enumerate(options)])
        embed = discord.Embed(title="📅 Devine l'année de sortie !", description=f"**{anime['title']['romaji']}**\n\n{desc}", color=discord.Color.blurple())
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30.0)
            choice = int(msg.content)
        except Exception:
            await ctx.send("⏰ Temps écoulé ou entrée invalide.")
            return

        if 1 <= choice <= 4 and options[choice-1] == correct_year:
            self.update_user_data(ctx.author.id, 15)
            await ctx.send("✅ Bonne réponse ! +15 XP")
        else:
            await ctx.send(f"❌ Mauvaise réponse. L'année correcte était {correct_year}.")

    @commands.command(name="guessepisode")
    async def guess_episode(self, ctx):
        anime = core.get_random_anime()
        ep_count = anime.get("episodes")

        if not ep_count or ep_count > 200:
            await ctx.send("❌ Anime inadapté pour ce mini-jeu.")
            return

        options = [ep_count]
        while len(options) < 4:
            e = random.randint(1, max(12, ep_count + 20))
            if e not in options:
                options.append(e)

        random.shuffle(options)

        desc = "\n".join([f"{i+1}. {e} épisodes" for i, e in enumerate(options)])
        embed = discord.Embed(title="🎬 Devine le nombre d'épisodes !", description=f"**{anime['title']['romaji']}**\n\n{desc}", color=discord.Color.blurple())
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30.0)
            choice = int(msg.content)
        except Exception:
            await ctx.send("⏰ Temps écoulé ou entrée invalide.")
            return

        if 1 <= choice <= 4 and options[choice-1] == ep_count:
            self.update_user_data(ctx.author.id, 15)
            await ctx.send("✅ Bonne réponse ! +15 XP")
        else:
            await ctx.send(f"❌ Mauvaise réponse. Il y avait {ep_count} épisodes.")

    @commands.command(name="guessgenre")
    async def guess_genre(self, ctx):
        anime = core.get_random_anime()
        genres = anime.get("genres", [])

        if not genres:
            await ctx.send("❌ Genres introuvables pour cet anime.")
            return

        correct_genre = genres[0]
        all_genres = core.get_all_genres()
        options = [correct_genre]
        while len(options) < 4:
            g = random.choice(all_genres)
            if g not in options:
                options.append(g)

        random.shuffle(options)

        desc = "\n".join([f"{i+1}. {g}" for i, g in enumerate(options)])
        embed = discord.Embed(title="🏷️ Devine le genre principal !", description=f"**{anime['title']['romaji']}**\n\n{desc}", color=discord.Color.blurple())
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30.0)
            choice = int(msg.content)
        except Exception:
            await ctx.send("⏰ Temps écoulé ou entrée invalide.")
            return

        if 1 <= choice <= 4 and options[choice-1] == correct_genre:
            self.update_user_data(ctx.author.id, 15)
            await ctx.send("✅ Bonne réponse ! +15 XP")
        else:
            await ctx.send(f"❌ Mauvaise réponse. Le bon genre était {correct_genre}.")

async def setup(bot):
    await bot.add_cog(MiniGames(bot))
