"""
Weekly and anime challenge commands.

This cog provides a simple weekly challenge system and an AniList
challenge where the bot suggests an anime to watch and allows the user
to rate it once completed.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from modules import core


class Challenge(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="weekly")
    async def weekly(self, ctx: commands.Context, sub: str | None = None) -> None:
        """Gère les défis hebdomadaires.

        Utilise ``!weekly`` pour recevoir un nouveau défi aléatoire. Utilise
        ``!weekly complete`` pour valider ton défi actuel.
        """
        user_id = str(ctx.author.id)
        data = core.load_weekly()
        if sub == "complete":
            last = data.get(user_id, {}).get("last_completed")
            if last:
                last_time = datetime.fromisoformat(last)
                if datetime.now() - last_time < timedelta(days=7):
                    next_time = last_time + timedelta(days=7)
                    wait_days = (next_time - datetime.now()).days + 1
                    await ctx.send(f"⏳ Tu as déjà validé ton défi cette semaine.\nTu pourras le refaire dans **{wait_days} jour(s)**.")
                    return
            if user_id not in data or not data[user_id].get("active"):
                await ctx.send("❌ Tu n’as pas de défi en cours.")
                return
            challenge = data[user_id]["active"]
            history = data[user_id].get("history", [])
            history.append({"description": challenge["description"], "completed": True})
            data[user_id]["history"] = history
            data[user_id]["active"] = None
            data[user_id]["last_completed"] = datetime.now().isoformat()
            core.save_weekly(data)
            core.add_xp(ctx.author.id, 25)
            await ctx.send(f"✅ Défi terminé : **{challenge['description']}** ! Bien joué 🎉")
            return
        # Generate a new challenge
        challenges = [
            "Regarder 3 animes du genre Action",
            "Finir un anime de +20 épisodes",
            "Donner une note de 10 à un anime",
            "Regarder un anime en cours de diffusion",
            "Terminer une saison complète en une semaine",
            "Découvrir un anime noté < 70 sur AniList",
            "Regarder un anime de ton genre préféré",
            "Essayer un anime d’un genre que tu n’aimes pas",
            "Faire un duel avec un ami avec `!duel`",
            "Compléter un challenge `!anichallenge`",
        ]
        chosen = random.choice(challenges)
        data[user_id] = {
            "active": {"description": chosen},
            "history": data.get(user_id, {}).get("history", [])
        }
        core.save_weekly(data)
        await ctx.send(f"📅 Ton défi de la semaine :\n**{chosen}**\nQuand tu as terminé, tape `!weekly complete`.")

    @commands.command(name="anichallenge")
    async def anichallenge(self, ctx: commands.Context) -> None:
        """Propose un anime aléatoire à regarder."""
        data = core.load_challenges()
        user_id = str(ctx.author.id)
        if user_id in data and data[user_id].get("active"):
            await ctx.send(f"📌 Tu as déjà un défi en cours : **{data[user_id]['active']['title']}**.\nUtilise `!challenge complete <note/10>` quand tu l’as terminé.")
            return
        # Try up to 10 times to find a random anime
        for _ in range(10):
            page = random.randint(1, 500)
            query = f'''
            query {{
              Page(perPage: 1, page: {page}) {{
                media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {{
                  id
                  title {{ romaji }}
                  siteUrl
                }}
              }}
            }}
            '''
            res = core.query_anilist(query)
            try:
                anime = res["data"]["Page"]["media"][0]
                title = anime["title"]["romaji"]
                site = anime["siteUrl"]
                data[user_id] = {
                    "active": {"id": anime["id"], "title": title},
                    "history": data.get(user_id, {}).get("history", [])
                }
                core.save_challenges(data)
                await ctx.send(f"🎯 Nouveau défi pour **{ctx.author.display_name}** :\n**{title}**\n🔗 {site}\n\nUne fois vu, fais `!challenge complete <note>`")
                return
            except Exception:
                continue
        await ctx.send("❌ Impossible de récupérer un anime pour le challenge.")

    @commands.command(name="challenge")
    async def challenge_complete(self, ctx: commands.Context, subcommand: str | None = None, note: int | None = None) -> None:
        """Valide ton AniList challenge en donnant une note sur 10."""
        if subcommand != "complete" or note is None:
            await ctx.send("❌ Utilise : `!challenge complete <note sur 10>`")
            return
        data = core.load_challenges()
        uid = str(ctx.author.id)
        if uid not in data or not data[uid].get("active"):
            await ctx.send("❌ Tu n’as aucun défi en cours.")
            return
        active = data[uid]["active"]
        history = data[uid].get("history", [])
        history.append({"title": active["title"], "completed": True, "score": note})
        data[uid]["history"] = history
        data[uid]["active"] = None
        core.save_challenges(data)
        core.add_xp(ctx.author.id, 15)
        await ctx.send(f"✅ Bien joué **{ctx.author.display_name}** ! Tu as terminé **{active['title']}** avec la note **{note}/10** 🎉")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Challenge(bot))
