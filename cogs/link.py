from discord.ext import commands
from modules.anilist import fetch_anilist_user_id
import json
import os

LINKS_FILE = "data/user_links.json"

class LinkAniList(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        os.makedirs("data", exist_ok=True)
        if not os.path.exists(LINKS_FILE):
            with open(LINKS_FILE, "w") as f:
                json.dump({}, f)

    def save_link(self, discord_id, anilist_id):
        with open(LINKS_FILE, "r") as f:
            data = json.load(f)
        data[str(discord_id)] = anilist_id
        with open(LINKS_FILE, "w") as f:
            json.dump(data, f, indent=4)

    @commands.command(name="linkanilist")
async def link_anilist(self, ctx, *, username: str):
    print(f"[DEBUG] Commande reçue ! Utilisateur : {username}")
    await ctx.send("🔍 Je cherche ton profil AniList, attends une seconde...")

    user_id = await fetch_anilist_user_id(username)
    print(f"[DEBUG] Résultat fetch_anilist_user_id: {user_id}")

    if user_id:
        self.save_link(ctx.author.id, user_id)
        await ctx.send(f"✅ Ton compte AniList a été lié à `{username}` (ID: {user_id})")
    else:
        await ctx.send("❌ Aucun utilisateur AniList trouvé avec ce nom.")

    @commands.command(name="unlinkanilist")
    async def unlink_anilist(self, ctx):
        """Délie ton compte AniList de ton compte Discord."""
        with open(LINKS_FILE, "r") as f:
            data = json.load(f)
        if str(ctx.author.id) in data:
            del data[str(ctx.author.id)]
            with open(LINKS_FILE, "w") as f:
                json.dump(data, f, indent=4)
            await ctx.send("✅ Ton compte AniList a été délié avec succès.")
        else:
            await ctx.send("❌ Aucun compte AniList n’est lié à ton profil Discord.")

async def setup(bot):
    await bot.add_cog(LinkAniList(bot))
