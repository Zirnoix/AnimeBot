"""
Anime tracker commands.

This cog allows users to subscribe to specific anime titles and receive
notifications when new episodes air. Users can add or remove titles
from their personal watchlist and list their current subscriptions.
The bot checks the tracker in a background task (see ``bot.py``)
and will send a direct message whenever a tracked anime releases a
new episode.
"""

from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from ..modules import core


class Tracker(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="anitracker")
    async def anitracker(self, ctx: commands.Context, action: Optional[str] = None, *, anime: Optional[str] = None) -> None:
        """Gère la liste des animes suivis pour les rappels d'épisode.

        Utilise ``!anitracker`` pour voir la liste actuelle de tes animes suivis.
        Utilise ``!anitracker add <titre>`` pour ajouter un anime à ta liste.
        Utilise ``!anitracker remove <titre>`` pour retirer un anime de ta liste.
        """
        uid = str(ctx.author.id)
        tracker = core.load_tracker()
        # Ensure user has a list
        tracker.setdefault(uid, [])
        current_list = tracker[uid]
        # If no action provided, show current list
        if action is None:
            if not current_list:
                await ctx.send("📭 Tu ne suis actuellement aucun anime. Utilise `!anitracker add <titre>` pour en ajouter.")
            else:
                # Display list with numbering
                desc = "\n".join(f"{idx+1}. {title}" for idx, title in enumerate(current_list))
                embed = discord.Embed(
                    title=f"📌 Animes suivis par {ctx.author.display_name}",
                    description=desc,
                    color=discord.Color.gold(),
                )
                await ctx.send(embed=embed)
            return
        # Normalise action
        act = action.lower()
        if act in {"add", "ajouter", "suivre"}:
            if not anime:
                await ctx.send("❌ Merci de préciser le titre de l'anime à ajouter.")
                return
            # Prevent duplicates by normalising
            normalized = core.normalize(anime)
            for existing in current_list:
                if core.normalize(existing) == normalized:
                    await ctx.send(f"⚠️ Tu suis déjà **{existing}**.")
                    return
            current_list.append(anime)
            tracker[uid] = current_list
            core.save_tracker(tracker)
            await ctx.send(f"✅ **{anime}** a été ajouté à ta liste de suivi.")
            return
        if act in {"remove", "delete", "supprimer", "unsuivre"}:
            if not anime:
                await ctx.send("❌ Merci de préciser le titre de l'anime à retirer.")
                return
            normalized = core.normalize(anime)
            for existing in current_list:
                if core.normalize(existing) == normalized:
                    current_list.remove(existing)
                    tracker[uid] = current_list
                    core.save_tracker(tracker)
                    await ctx.send(f"✅ **{existing}** a été retiré de ta liste de suivi.")
                    return
            await ctx.send(f"❌ L'anime **{anime}** n'est pas dans ta liste.")
            return
        # Unknown action
        await ctx.send("❌ Action inconnue. Utilise `add` pour ajouter ou `remove` pour retirer.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tracker(bot))
