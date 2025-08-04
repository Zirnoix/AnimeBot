import discord
from discord.ext import commands
import random

from modules import xp_manager, score_manager

class Duel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="duel")
    async def duel(self, ctx, opponent: discord.Member = None):
        if opponent is None:
            await ctx.send("❗ Utilisation : `!duel @opposant`")
            return
        if opponent.bot:
            await ctx.send("🤖 Tu ne peux pas défier un bot.")
            return
        if opponent == ctx.author:
            await ctx.send("🙃 Tu ne peux pas te défier toi-même.")
            return

        author = ctx.author
        result_embed = discord.Embed(title="⚔️ Duel Anime", color=discord.Color.red())
        result_embed.add_field(name="🔁 En cours...", value=f"{author.mention} vs {opponent.mention}")
        duel_msg = await ctx.send(embed=result_embed)

        await ctx.send(f"🎲 Lancement du duel dans 3 secondes...")
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=3))

        winner = random.choice([author, opponent])
        loser = opponent if winner == author else author

        xp_manager.add_xp(str(winner.id), 10)
        score_manager.update_duel_stats(str(winner.id), str(loser.id))

        result_embed = discord.Embed(
            title="🏆 Duel terminé !",
            description=f"**{winner.mention}** remporte la victoire contre {loser.mention} !",
            color=discord.Color.green()
        )
        result_embed.set_footer(text="+10 XP")
        await duel_msg.edit(embed=result_embed)

    @commands.command(name="duelstats")
    async def duel_stats(self, ctx, user: discord.User = None):
        target = user or ctx.author
        stats = score_manager.get_duel_stats(str(target.id))

        embed = discord.Embed(
            title=f"📊 Stats de Duel — {target.display_name}",
            color=discord.Color.orange()
        )
        embed.add_field(name="🏆 Victoires", value=stats.get("wins", 0))
        embed.add_field(name="💀 Défaites", value=stats.get("losses", 0))
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Duel(bot))
