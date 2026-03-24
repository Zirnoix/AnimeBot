# cogs/onboarding.py
from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

SUPPORT_DISCORD = "@zirnoix"
SUPPORT_ID = "180389173985804288"

INTRO_TITLE = "👋 Merci d’avoir ajouté AnimeBot !"
INTRO_DESC = (
    "Voici l’essentiel pour démarrer en **moins de 60 secondes**.\n\n"
    "1) **Salon des annonces**\n"
    "→ `/setchannel` dans le salon voulu\n\n"
    "2) **Liste du serveur** (ce que suivent `/next` et `/planning` en mode serveur)\n"
    "→ `/airings all` — ajoute les titres à suivre\n\n"
    "Les **alertes image** (à la sortie de l’épisode) utilisent le compte du bot + comptes liés, pas cette liste."
)

INTRO_MINIGAMES = (
    "**🎮 Mini-jeux populaires (essayez-les !)**\n"
    "• **/animequiz** — Quiz solo rapide (images/indices)\n"
    "• **/duel** — Affronte un ami en 1v1\n"
    "• **/guessop** — Devine l’**opening** à l’oreille (vocal)\n"
    "• **/minijeux** — Deux menus (**Devinettes** / **Autres**) : un clic = une partie\n"
    "• **`/higherlower`** — Plus ou moins populaire (hors menu)"
)

EXTRA_TIPS = (
    "Besoin d’aller plus loin ? Tape **`/guide`** (ici en MP) pour le tutoriel complet "
    "(liens AniList, stats, missions, rappels, etc.)."
)

CONTACT = (
    f"Un souci ? Contacte **{SUPPORT_DISCORD}** (ID `{SUPPORT_ID}`) — je réponds vite."
)

def make_intro_embed(guild: discord.Guild | None) -> discord.Embed:
    em = discord.Embed(
        title=INTRO_TITLE,
        description=INTRO_DESC,
        color=discord.Color.blurple(),
    )
    if guild:
        em.set_footer(text=f"Serveur: {guild.name}")
    em.add_field(name="🎮 Mini-jeux à découvrir", value=INTRO_MINIGAMES, inline=False)
    em.add_field(name="ℹ️ Astuce", value=EXTRA_TIPS, inline=False)
    em.add_field(name="🆘 Support", value=CONTACT, inline=False)
    return em

class Onboarding(commands.Cog):
    """Envoie un MP concis au propriétaire du serveur + /guide (DM)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- DM à l’owner quand le bot rejoint une guilde (1 message unique) ----
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        try:
            owner = guild.owner
            if not owner:
                return
            try:
                await owner.send(embed=make_intro_embed(guild))
            except discord.Forbidden:
                # Si l’owner bloque ses MP : on poste un message minimaliste dans un salon autorisé
                ch = guild.system_channel or next(
                    (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),  # type: ignore
                    None
                )
                if ch:
                    await ch.send(
                        f"👋 **{owner.mention}** merci d’avoir ajouté **AnimeBot**.\n"
                        "Je t’ai mis le guide en MP, mais tes MP semblent fermés.\n"
                        "Ouvre tes MP ou tape `/guide` pour recevoir le tutoriel (en MP)."
                    )
        except Exception:
            # ne pas casser le flux de démarrage si un DM échoue
            pass

    # ---- /guide : détaillé, pensé pour **MP**. Utilisable depuis un serveur -> redirige en MP. ----
    @app_commands.command(name="guide", description="(MP) Tutoriel complet : configuration, AniList, missions, rappels, mini-jeux.")
    async def guide(self, interaction: discord.Interaction):
        try:
            # Si lancé depuis un serveur, prévenir en ephemeral puis envoyer en MP
            if interaction.guild:
                if not interaction.response.is_done():
                    await interaction.response.send_message("📬 Je t’envoie le guide en **MP**.", ephemeral=True)
                else:
                    await interaction.followup.send("📬 Je t’envoie le guide en **MP**.", ephemeral=True)
            else:
                # En MP, les réponses « éphémères » ne sont pas supportées comme en salon.
                await interaction.response.defer(ephemeral=False)

            user = interaction.user

            e1 = discord.Embed(
                title="⚙️ Mise en route — pas à pas",
                color=discord.Color.blurple(),
                description=(
                    "**1) Salon des annonces**\n"
                    "→ `/setchannel` dans ce salon\n\n"
                    "**2) Liste du serveur** (`/next` / `/planning` mode serveur)\n"
                    "→ `/airings all` pour choisir les titres.\n\n"
                    "_Les alertes image (sortie d’épisode) viennent du compte du bot + comptes liés, pas de cette liste._"
                ),
            )

            eMini = discord.Embed(
                title="🎮 Mini-jeux — mettez l’ambiance !",
                color=discord.Color.purple(),
                description=(
                    "• **/animequiz** — Quiz solo (rapide, fun)\n"
                    "• **/duel** — 1v1 quiz entre amis\n"
                    "• **/guessop** — Devine l’**opening** 🎧 (vocal)\n"
                    "• **/minijeux** — Menu : un clic = une partie\n"
                    "• Plus: **`/minijeux`** (Guess + autres), **`/higherlower`**\n\n"
                    "Astuce: lancez ces jeux dans un salon dédié pour éviter de flood."
                ),
            )

            e2 = discord.Embed(
                title="🔗 Compte AniList (recommandé)",
                color=discord.Color.green(),
                description=(
                    "**Lier votre compte** : `/linkanilist <pseudo>`\n"
                    "• Vos stats : `/mystats`\n"
                    "• Prochain épisode perso : `/monnext`\n"
                    "• Planning perso : `/monplanning`\n\n"
                    "💡 Si un utilisateur **non lié** utilise une commande perso, le bot lui suggèrera de lier son compte."
                ),
            )

            e3 = discord.Embed(
                title="🛎️ Rappels & récap quotidiens",
                color=discord.Color.gold(),
                description=(
                    "• `/reminder on|off` et `/setalert HH:MM` — récap **personnel** en MP (AniList lié ou global).\n\n"
                    "➡️ **`/next` / `/planning` (serveur)** = **liste du serveur** (`/airings`).\n"
                    "➡️ **`/monnext` / `/monplanning`** = **votre** AniList lié."
                ),
            )

            e4 = discord.Embed(
                title="🎯 Missions & divers",
                color=discord.Color.teal(),
                description=(
                    "• Mission du jour : `/mission`\n"
                    "• Check quotidien : `/checkin` (XP + streak)\n\n"
                    "• Stats d’un membre : `/stats @membre`\n"
                    "• Infos bot : `/botinfo` — Ping : `/ping`"
                ),
            )

            e5 = discord.Embed(
                title="🆘 Support",
                color=discord.Color.dark_teal(),
                description=(
                    f"Besoin d’aide ? **{SUPPORT_DISCORD}** — ID `{SUPPORT_ID}`\n"
                    "Tu peux répondre directement à ce MP."
                ),
            )

            # Un seul message DM avec plusieurs embeds = une seule notif
            await user.send(embeds=[e1, eMini, e2, e3, e4, e5])

            if not interaction.guild:
                await interaction.followup.send("✅ Guide envoyé ci-dessus.", ephemeral=False)

        except discord.Forbidden:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ Impossible d’envoyer un MP (paramètres privés).",
                    ephemeral=bool(interaction.guild),
                )
            else:
                await interaction.response.send_message(
                    "❌ Impossible d’envoyer un MP (paramètres privés).",
                    ephemeral=bool(interaction.guild),
                )
        except Exception as e:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Erreur: {type(e).__name__}", ephemeral=bool(interaction.guild))
            else:
                await interaction.response.send_message(f"❌ Erreur: {type(e).__name__}", ephemeral=bool(interaction.guild))

async def setup(bot: commands.Bot):
    await bot.add_cog(Onboarding(bot))
