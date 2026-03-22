# cogs/emoji_autosync.py
from __future__ import annotations
import os, json, asyncio, hashlib, discord
from pathlib import Path
from typing import Dict, List, Tuple
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

EMOJI_PREFIX = "ab_"
ASSETS_GUILD_ID = int(os.getenv("ASSETS_GUILD_ID", "0"))
STATE_DIR = Path(os.getenv("EMOJI_STATE_DIR", "data"))
OUT_FILE  = STATE_DIR / "config_emojis.json"

# Plusieurs racines locales possibles, scannées en récursif
_local_dirs_env = os.getenv("EMOJI_LOCAL_DIRS") or os.getenv("EMOJI_LOCAL_DIR", "assets/emojis")
LOCAL_DIRS = [Path(p.strip()) for p in _local_dirs_env.split(":") if p.strip()]

MANIFEST_URL = (os.getenv("EMOJI_MANIFEST_URL") or "").strip()
PRUNE = (os.getenv("EMOJI_PRUNE", "0").strip().lower() in {"1","true","yes"})
HASH_FILE = Path("data/emoji_hashes.json")
OUT_FILE  = Path("data/config_emojis.json")

def _sha1(b: bytes) -> str: return hashlib.sha1(b).hexdigest()

def _save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _is_img(p: Path) -> bool:
    return p.suffix.lower() in {".png",".jpg",".jpeg",".webp",".gif"}

async def _collect_source() -> Tuple[Dict[str, bytes], List[str]]:
    """
    Retourne (source, logs) où source = {emoji_name: bytes}
    - via MANIFEST_URL si fourni, sinon via scan récursif de LOCAL_DIRS
    """
    logs: List[str] = []
    out: Dict[str, bytes] = {}

    if MANIFEST_URL:
        logs.append(f"Manifest URL: {MANIFEST_URL}")
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(MANIFEST_URL, timeout=30) as r:
                    r.raise_for_status()
                    manifest = await r.json()
            except Exception as e:
                logs.append(f"❌ Échec lecture manifest: {e}")
                return {}, logs

            for name, url in manifest.items():
                key = f"{EMOJI_PREFIX}{str(name).lower()}"
                try:
                    async with s.get(str(url), timeout=30) as img:
                        img.raise_for_status()
                        out[key] = await img.read()
                except Exception as e:
                    logs.append(f"❌ Téléchargement {name} depuis {url}: {e}")
        logs.append(f"Manifest: {len(out)} fichier(s) chargé(s).")
        return out, logs

    # Mode LOCAL
    roots = [str(p.resolve()) for p in LOCAL_DIRS]
    logs.append(f"Local dirs (récursif): {', '.join(roots) if roots else '(aucun)'}")
    for root in LOCAL_DIRS:
        if not root.exists():
            logs.append(f"⚠️ Dossier inexistant: {root}")
            continue
        for p in root.rglob("*"):
            if p.is_file() and _is_img(p):
                key = f"{EMOJI_PREFIX}{p.stem.lower()}"
                try:
                    data = p.read_bytes()
                except Exception as e:
                    logs.append(f"❌ Lecture {p}: {e}")
                    continue
                out[key] = data
    logs.append(f"Local: {len(out)} fichier(s) trouvé(s).")
    return out, logs

async def _run_sync(bot: commands.Bot) -> Tuple[str, Dict[str, int]]:
    lines: List[str] = []
    if not ASSETS_GUILD_ID:
        return "❌ ASSETS_GUILD_ID non défini.", {}

    guild = bot.get_guild(ASSETS_GUILD_ID)
    if not guild:
        return "❌ Guild d'assets introuvable (bot non invité ? mauvais ID ?).", {}

    me = guild.me
    if not me or not me.guild_permissions.manage_emojis:
        lines.append("❌ Le bot N'A PAS la permission **Manage Emojis and Stickers** sur le serveur Assets.")
        return "\n".join(lines), {}

    source, src_logs = await _collect_source()
    lines.extend(src_logs)

    if not source:
        lines.append("ℹ️ Aucun fichier source détecté (manifest vide ou dossier vide).")
        return "\n".join(lines), {}

    try:
        old_hash = json.loads(HASH_FILE.read_text(encoding="utf-8"))
    except Exception:
        old_hash = {}

    existing = {e.name: e for e in guild.emojis}
    created, updated, kept = [], [], []

    for name, data in source.items():
        # Soft check taille (Discord ~256 Ko). Si trop gros → conseille de réduire à 128px.
        if len(data) > 256_000:
            lines.append(f"⚠️ {name}: fichier >256KB. Réduis à 128x128/PNG optimisé.")
        h = _sha1(data)
        emo = existing.get(name)
        if emo and old_hash.get(name) == h:
            kept.append(f"{name} ({emo.id})")
            continue
        if emo:
            try: await emo.delete(reason="EmojiAutoSync replace")
            except Exception as e: lines.append(f"⚠️ Delete {name}: {e}")
            await asyncio.sleep(0.2)
        try:
            new_emoji = await guild.create_custom_emoji(name=name, image=data, reason="EmojiAutoSync upload")
            existing[name] = new_emoji
            old_hash[name] = h
            created.append(f"{name} ({new_emoji.id})")
            await asyncio.sleep(0.3)
        except discord.HTTPException as e:
            lines.append(f"❌ Upload {name}: {e}")

    if PRUNE:
        names_in_source = set(source.keys())
        removed = []
        for emo in list(guild.emojis):
            if emo.name.startswith(EMOJI_PREFIX) and emo.name not in names_in_source:
                try:
                    await emo.delete(reason="EmojiAutoSync prune")
                    removed.append(f"{emo.name} ({emo.id})")
                    await asyncio.sleep(0.3)
                except Exception as e:
                    lines.append(f"⚠️ Prune {emo.name}: {e}")
        if removed:
            lines.append(f"🧹 Supprimés: {', '.join(removed)}")

    mapping = {e.name: e.id for e in guild.emojis if e.name.startswith(EMOJI_PREFIX)}
    try:
        _save_json(OUT_FILE, mapping)
        _save_json(HASH_FILE, old_hash)
    except Exception as e:
        lines.append(f"⚠️ Écriture mapping/hash: {e}")

    if created:
        lines.append(f"✅ Créés/Remplacés ({len(created)}): " + ", ".join(created))
    if kept:
        lines.append(f"👌 Inchangés ({len(kept)}): " + ", ".join(kept))
    lines.append(f"📝 Mapping écrit dans `{OUT_FILE.as_posix()}` (clés = noms d'emoji).")
    return "\n".join(lines), mapping

class EmojiAutoSync(commands.Cog):
    """Auto-sync au démarrage + commandes /emojidiag et /syncemojis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._done = False

    async def _authorized(self, interaction: discord.Interaction) -> bool:
        OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS","").replace(" ","").split(",") if x.isdigit()}
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

    @app_commands.command(name="emojimap", description="Télécharge le mapping des emojis.")
    async def emojimap(self, interaction: discord.Interaction):
        if not await self._authorized(interaction):
            return await interaction.response.send_message("⛔ Accès refusé.", ephemeral=True)

        if not OUT_FILE.exists():
            return await interaction.response.send_message("❌ Fichier introuvable (pas encore généré).", ephemeral=True)

        try:
            await interaction.response.send_message(
                content="📝 Voici `config_emojis.json`",
                file=discord.File(OUT_FILE.as_posix(), filename="config_emojis.json"),
                ephemeral=True
            )
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            try:
                await interaction.user.send(file=discord.File(OUT_FILE.as_posix(), filename="config_emojis.json"))
                await interaction.followup.send("📬 Mapping envoyé en DM.", ephemeral=True)
            except Exception as ex:
                await interaction.followup.send(f"❌ Échec de l’envoi : {ex}", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._done:
            return
        self._done = True
        if not ASSETS_GUILD_ID:
            print("❌ ASSETS_GUILD_ID non défini.")
            return
        msg, _ = await _run_sync(self.bot)
        print(msg)

    @app_commands.command(name="emojidiag", description="Diagnostic: chemins, fichiers détectés, permissions.")
    async def emojidiag(self, interaction: discord.Interaction):
        if not await self._authorized(interaction):
            return await interaction.response.send_message("⛔ Accès refusé.", ephemeral=True)

        lines: List[str] = []
        lines.append(f"ASSETS_GUILD_ID: {ASSETS_GUILD_ID}")
        g = self.bot.get_guild(ASSETS_GUILD_ID)
        lines.append(f"Guild trouvé: {bool(g)}")
        if g and g.me:
            lines.append(f"Manage Emojis: {g.me.guild_permissions.manage_emojis}")
        lines.append(f"MANIFEST_URL: {MANIFEST_URL or '(vide)'}")
        lines.append("LOCAL_DIRS: " + (", ".join(str(p.resolve()) for p in LOCAL_DIRS) if LOCAL_DIRS else "(aucun)"))

        source, src_logs = await _collect_source()
        lines.extend(src_logs)
        sample = ", ".join(list(source.keys())[:10]) if source else "(aucun)"
        lines.append(f"Exemples clés détectées: {sample}")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="syncemojis", description="Force la synchronisation des emojis (owner/admin).")
    async def syncemojis(self, interaction: discord.Interaction):
        if not await self._authorized(interaction):
            return await interaction.response.send_message("⛔ Accès refusé.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        msg, mapping = await _run_sync(self.bot)
        await interaction.followup.send(msg, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(EmojiAutoSync(bot))
