# cogs/emoji_status.py
import os
import json
import discord
from discord import app_commands
from discord.ext import commands

from modules import i18n
from modules.app_cmd_locale import ui_str

ASSETS_GUILD_ID = int(os.getenv("ASSETS_GUILD_ID", "0"))
OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS", "").replace(" ", "").split(",") if x.isdigit()}


class EmojiStatus(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _authorized(self, interaction: discord.Interaction) -> bool:
        try:
            if await self.bot.is_owner(interaction.user):
                return True
        except Exception:
            pass
        if interaction.user.id in OWNER_IDS:
            return True
        perms = getattr(interaction.user, "guild_permissions", None)
        if perms and perms.administrator:
            return True
        return False

    @app_commands.command(name="emojistatus", description=ui_str("emoji_status.cmd_desc"))
    async def emojistatus(self, interaction: discord.Interaction):
        lg = i18n.guild_lang(interaction.guild)
        if not await self._authorized(interaction):
            return await interaction.response.send_message(i18n.t("emoji_status.denied", lg), ephemeral=True)

        mapping = {}
        try:
            with open("data/config_emojis.json", "r", encoding="utf-8") as f:
                mapping = json.load(f)
        except Exception:
            pass

        guild = self.bot.get_guild(ASSETS_GUILD_ID)
        if not guild:
            return await interaction.response.send_message(i18n.t("emoji_status.no_guild", lg), ephemeral=True)

        lines = []
        for name, e_id in mapping.items():
            e = self.bot.get_emoji(int(e_id))
            lines.append(f"{name} → {e} ({e_id})" if e else f"{name} → ❓ ({e_id})")

        await interaction.response.send_message("\n".join(lines) or i18n.t("emoji_status.empty", lg), ephemeral=True)

    @app_commands.command(name="whoami", description=ui_str("emoji_status.whoami_desc"))
    async def whoami(self, interaction: discord.Interaction):
        allowed = await self._authorized(interaction)
        perms = getattr(interaction.user, "guild_permissions", None)
        admin = getattr(perms, "administrator", None) if perms else None
        await interaction.response.send_message(
            f"User: {interaction.user} ({interaction.user.id})\n"
            f"Authorized: {allowed}\n"
            f"Admin: {admin}\n"
            f"OWNER_IDS: {sorted(list(OWNER_IDS))}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EmojiStatus(bot))
