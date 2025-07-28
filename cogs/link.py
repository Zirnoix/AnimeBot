# cogs/link.py

import discord
from discord.ext import commands
from modules.user_settings import link_anilist_account, unlink_anilist_account, get_anilist_username

class Link(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="linkanilist")
    async def link_anilist(self, ctx, username: str):
        link_anilist_account(ctx.author.id, username)
        await ctx.send(f"🔗 Ton compte Anilist **{username}** a bien été lié.")

    @commands.command(name="unlinkanilist")
    async def unlink_anilist(self, ctx):
        if not get_anilist_username(ctx.author.id):
            await ctx.send("❌ Aucun compte Anilist n’est actuellement lié.")
            return

        unlink_anilist_account(ctx.author.id)
        await ctx.send("🔓 Ton compte Anilist a bien été délié.")

    @commands.command(name="anilist")
    async def anilist_profile(self, ctx):
        username = get_anilist_username(ctx.author.id)
        if not username:
            await ctx.send("❌ Tu dois d’abord lier ton compte Anilist avec `!linkanilist <pseudo>`.")
            return

        embed = discord.Embed(title="🧾 Ton profil Anilist", color=0x1e90ff)
        embed.add_field(name="Nom d’utilisateur", value=username, inline=False)
        embed.add_field(name="Lien", value=f"https://anilist.co/user/{username}/", inline=False)
        embed.set_footer(text="AnimeBot - Anilist Integration")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Link(bot))
