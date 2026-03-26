# cogs/onboarding.py
from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

SUPPORT_DISCORD = "@zirnoix"
SUPPORT_ID = "180389173985804288"

INTRO_TITLE = "👋 Merci d’avoir ajouté AnimeBot !"
INTRO_LEAD = (
    "Voici **l’ordre conseillé** pour que le serveur profite des annonces d’épisodes et des commandes « liste du serveur », "
    "puis un **rapide topo** pour tes membres."
)

INTRO_ADMIN = (
    "**1) Remplir la liste du serveur — `/airings`**\n"
    "Sous-commande **`all`** (parcourir les sorties) ou ajout/retrait un par un. "
    "C’est la **liste utilisée** par **`/next`** et **`/planning`** en mode **serveur**. "
    "**Tant qu’elle est vide**, pas de prochains épisodes côté serveur et **aucune carte** « épisode sorti ».\n\n"
    "**2) Choisir le salon des annonces — `/setchannel`**\n"
    "À lancer **dans le salon** où tu veux les **cartes** quand un épisode de la liste sort "
    "(même liste que `/airings`).\n\n"
    "**3) Raid boss (optionnel) — `/raidconfig`**\n"
    "Salon du raid, **jour/heure**, lancement automatique ou non. "
    "Pour un essai : **`/raidstart`** (admins)."
)

INTRO_MINIGAMES = (
    "**À faire découvrir sur le serveur**\n"
    "• **/next** · **/planning** — mode **serveur** = liste `/airings` ; mode **global** = toutes les sorties.\n"
    "• **/animequiz** · **/duel** · **/guessop** · **/minijeux** — **/animetop** pour les classements mini-jeux.\n"
    "• **Raid boss** (mini-jeu communautaire) une fois **`/raidconfig`** en place."
)

EXTRA_TIPS = (
    "Tape **`/guide`** pour recevoir le **tutoriel complet en MP** : "
    "**XP & niveaux**, badges, lien AniList, rappels, détail du raid, etc."
)

CONTACT = (
    f"Un souci ? Contacte **{SUPPORT_DISCORD}** (ID `{SUPPORT_ID}`) — je réponds vite."
)

def make_intro_embed(guild: discord.Guild | None) -> discord.Embed:
    em = discord.Embed(
        title=INTRO_TITLE,
        description=INTRO_LEAD,
        color=discord.Color.blurple(),
    )
    if guild:
        em.set_footer(text=f"Serveur: {guild.name}")
    em.add_field(name="⚙️ Configuration (à faire en premier)", value=INTRO_ADMIN, inline=False)
    em.add_field(name="🎮 Pour les joueurs", value=INTRO_MINIGAMES, inline=False)
    em.add_field(name="📘 Tutoriel complet", value=EXTRA_TIPS, inline=False)
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
                        "Je t’ai envoyé un **récap config** en MP, mais tes MP sont fermés.\n"
                        "**En bref :** remplis **`/airings`** (liste du serveur), puis **`/setchannel`** "
                        "dans le salon d’annonces — optionnel : **`/raidconfig`** pour le raid boss.\n"
                        "Ouvre tes MP ou tape **`/guide`** pour le tutoriel détaillé (XP, badges, AniList…)."
                    )
        except Exception:
            # ne pas casser le flux de démarrage si un DM échoue
            pass

    # ---- /guide : détaillé, pensé pour **MP**. Utilisable depuis un serveur -> redirige en MP. ----
    @app_commands.command(
        name="guide",
        description="(MP) Tutoriel : config serveur (/airings, /setchannel, raid), XP, mini-jeux, AniList, rappels.",
    )
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

            e_server = discord.Embed(
                title="⚙️ Serveur — ce que configurent les admins",
                color=discord.Color.blurple(),
                description=(
                    "**1) Liste des animés suivis — `/airings`**\n"
                    "Utilise **`all`** (parcourir les sorties AniList) ou ajoute/retire des titres. "
                    "C’est la **whitelist** pour **`/next`** et **`/planning`** en mode **serveur**.\n"
                    "**Sans titre dans cette liste**, ces commandes restent vides côté serveur et **aucune annonce** "
                    "« épisode sorti » ne sera postée.\n\n"
                    "**2) Salon des annonces — `/setchannel`**\n"
                    "À lancer **dans le salon** où tu veux les **cartes** quand un épisode sort "
                    "(uniquement pour les animés de la liste `/airings`).\n\n"
                    "**3) Raid boss (optionnel) — `/raidconfig`**\n"
                    "Salon du combat, **jour et heure** (fuseau du bot), lancement auto oui/non. "
                    "Pour tester sans attendre : **`/raidstart`** (admins). "
                    "Les joueurs s’inscrivent puis reçoivent un **défi perso** par manche."
                ),
            )

            e_xp = discord.Embed(
                title="📈 XP, niveaux et badges",
                color=discord.Color.orange(),
                description=(
                    "• L’**XP** augmente ton **niveau global** et change ton **titre** (voir **`/mycard`**, **`/myrank`**).\n"
                    "• Tu en gagnes en jouant (**`/animequiz`**, devinettes, **`/duel`**, **raid boss**, etc.), "
                    "avec **`/checkin`** (quotidien + streak) et **`/mission`** (objectif du jour).\n"
                    "• **`/mybadges`** — progression par activité · **`/animetop`** / **`/quiztop`** — classements.\n"
                    "• **`/mystats`** — stats AniList détaillées une fois le compte lié."
                ),
            )

            e_mini = discord.Embed(
                title="🎮 Mini-jeux & communauté",
                color=discord.Color.purple(),
                description=(
                    "• **/animequiz** · **/duel** · **/guessop** · **/minijeux** (menus devinettes / autres)\n"
                    "• **/higherlower** · **/guesswho** · **/chainquiz**\n"
                    "• **Raid boss** — événement serveur si **`/raidconfig`** est réglé (inscription + manches).\n\n"
                    "_Astuce : un salon dédié aux mini-jeux évite de noyer le général._"
                ),
            )

            e_anilist = discord.Embed(
                title="🔗 Compte AniList",
                color=discord.Color.green(),
                description=(
                    "**Lier :** `/linkanilist <pseudo>` puis coller le **code** dans la bio AniList et **`/verifyanilist`**.\n"
                    "**Perso :** `/mystats` · `/monnext` · `/monplanning`\n\n"
                    "Les commandes **serveur** (`/next`, `/planning` mode serveur, annonces) utilisent **`/airings`**, "
                    "pas ton compte. Les commandes **perso** demandent un lien."
                ),
            )

            e_reminders = discord.Embed(
                title="🛎️ Rappels (MP)",
                color=discord.Color.gold(),
                description=(
                    "• `/reminder on|off` et `/setalert HH:MM` — récap **personnel** en MP.\n"
                    "• Indépendant des annonces du serveur (`/setchannel`).\n\n"
                    "**`/next` / `/planning`** — mode **serveur** = liste **`/airings`** · mode **global** = sorties générales.\n"
                    "**`/monnext` / `/monplanning`** — **ton** planning AniList (compte lié)."
                ),
            )

            e_misc = discord.Embed(
                title="🎯 Infos utiles",
                color=discord.Color.teal(),
                description=(
                    "• **`/stats @membre`** — carte AniList d’un membre (si lié)\n"
                    "• **`/botinfo`** · **`/ping`** — version du bot, latence\n"
                    "• **`/help`** — liste des commandes ; **`/help <nom>`** — détail"
                ),
            )

            e_support = discord.Embed(
                title="🆘 Support",
                color=discord.Color.dark_teal(),
                description=(
                    f"Besoin d’aide ? **{SUPPORT_DISCORD}** — ID `{SUPPORT_ID}`\n"
                    "Tu peux répondre directement à ce MP."
                ),
            )

            await user.send(embeds=[e_server, e_xp, e_mini, e_anilist, e_reminders, e_misc, e_support])

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
