"""
Panneau unique /owner pour le propriétaire du bot (OWNER_ID).
"""
from __future__ import annotations

import os

import discord
from discord import app_commands
from discord.ext import commands

from modules import owner_actions

LOG = __import__("logging").getLogger(__name__)


def _is_owner_id(user_id: int) -> bool:
    raw = os.getenv("OWNER_ID", "").strip()
    return raw.isdigit() and int(raw) == int(user_id)


class OwnerActionSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot) -> None:
        opts: list[discord.SelectOption] = []
        for val, label, desc in owner_actions.ACTIONS:
            opts.append(
                discord.SelectOption(
                    label=label[:100],
                    description=(desc[:100] if desc else None),
                    value=val,
                )
            )
        super().__init__(
            placeholder="Choisir une action…",
            min_values=1,
            max_values=1,
            options=opts[:25],
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        if not _is_owner_id(interaction.user.id):
            await interaction.response.send_message("❌ Réservé au propriétaire du bot.", ephemeral=True)
            return
        key = self.values[0]
        runner = owner_actions.RUNNERS.get(key)
        if not runner:
            await interaction.response.send_message("❌ Action inconnue.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await runner(self.bot, interaction)
        except Exception as e:
            LOG.exception("owner action %s: %s", key, e)
            try:
                await interaction.followup.send(f"❌ Erreur : `{type(e).__name__}: {e}`", ephemeral=True)
            except Exception:
                pass


class OwnerHubView(discord.ui.View):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=600)
        self.add_item(OwnerActionSelect(bot))


class OwnerHub(commands.Cog):
    """Regroupe les outils propriétaire sous /owner."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="setavatar", hidden=True)
    @commands.is_owner()
    async def set_avatar_prefix(self, ctx: commands.Context) -> None:
        """Préfixe uniquement : !setavatar + image jointe (pas de slash)."""
        if not ctx.message.attachments:
            await ctx.send("❌ Envoie l’image **dans le même message** que **`!setavatar`**.")
            return
        try:
            avatar_bytes = await ctx.message.attachments[0].read()
            await self.bot.user.edit(avatar=avatar_bytes)
            await ctx.send("✅ Avatar du bot mis à jour.")
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")

    @app_commands.command(
        name="owner",
        description="Panneau propriétaire : debug, stats, tests (OWNER_ID uniquement).",
    )
    async def owner_panel(self, interaction: discord.Interaction) -> None:
        if not _is_owner_id(interaction.user.id):
            await interaction.response.send_message(
                "❌ Réservé au **propriétaire** du bot (`OWNER_ID` sur l’hébergeur).",
                ephemeral=True,
            )
            return
        lines = [f"**{label}** — {desc}" for _, label, desc in owner_actions.ACTIONS]
        embed = discord.Embed(
            title="🔧 Panneau propriétaire",
            description=(
                "Choisis une action dans le menu ci-dessous. Tout est **éphémère** (visible par toi seul).\n\n"
                + "\n".join(lines)[:4000]
            ),
            color=discord.Color.dark_teal(),
        )
        embed.set_footer(text="Outils owner regroupés ici — Guess OP, stats, aide MP, etc.")
        await interaction.response.send_message(embed=embed, view=OwnerHubView(self.bot), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OwnerHub(bot))
