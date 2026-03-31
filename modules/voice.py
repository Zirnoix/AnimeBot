# modules/voice.py
from __future__ import annotations
import asyncio
import os
import discord

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

def make_source(
    path: str,
    duration_sec: float = 20.0,
    seek_start: float = 0.0,
    fade_sec: float = 1.0,
    normalize: bool = False,
) -> discord.FFmpegPCMAudio:
    """
    Sortie PCM s16le stéréo 48kHz (Discord-friendly), coupe exacte et fades.
    On force le flux audio 0 (anti-silence), et on normalise en option.
    IMPORTANT : -ss / -t après -i pour la précision.
    """
    fade = max(0.0, float(fade_sec))
    dur = max(0.1, float(duration_sec))
    st_out = max(0.0, dur - fade)

    loud = 'loudnorm=I=-16:TP=-1.5:LRA=11,' if normalize else ''
    af = f"{loud}afade=t=in:st=0:d={fade:.3f},afade=t=out:st={st_out:.3f}:d={fade:.3f}"

    before = "-nostdin -loglevel warning"

    # -map 0:a:0 => prend le 1er flux audio, évite les vidéos muettes
    # -f s16le -ar 48000 -ac 2 => sortie PCM brute pour Discord
    options = (
        f"-vn -sn -dn -map 0:a:0 "
        f"-ss {seek_start:.3f} -t {dur:.3f} "
        f"-af {af} "
        f"-f s16le -ar 48000 -ac 2"
    )

    return discord.FFmpegPCMAudio(
        source=path,
        executable=FFMPEG_BIN,
        before_options=before,
        options=options,
    )

async def ensure_connected(channel: discord.VoiceChannel) -> discord.VoiceClient:
    """Rejoins/déplace si besoin et renvoie le VoiceClient (self-deaf). Retries sur erreurs transitoires."""
    backoff = 0.55
    for attempt in range(3):
        try:
            vc: discord.VoiceClient | None = channel.guild.voice_client
            if vc and vc.channel != channel:
                try:
                    await vc.move_to(channel)
                except Exception:
                    try:
                        await vc.disconnect(force=True)
                    except Exception:
                        pass
                    vc = None
            if vc is None:
                vc = await channel.connect(self_deaf=True)
            return vc
        except Exception:
            if attempt < 2:
                await asyncio.sleep(backoff)
                backoff *= 2.1
                continue
            raise

async def play_clip_in_channel(
    channel: discord.VoiceChannel,
    filepath: str,
    duration_sec: float = 20.0,
    disconnect_after: bool = False,
    fade_sec: float = 1.0,
    normalize: bool = False,
) -> None:
    """
    Joue un extrait et attend la fin via un Event (pas de polling approximatif).
    """
    vc = await ensure_connected(channel)

    if vc.is_playing():
        vc.stop()

    source = make_source(filepath, duration_sec=duration_sec, fade_sec=fade_sec, normalize=normalize)

    done = asyncio.Event()
    def _after_play(err: Exception | None):
        try:
            done.set()
        except Exception:
            pass

    vc.play(source, after=_after_play)

    # petite attente de démarrage (facultatif)
    for _ in range(30):  # ~3s
        await asyncio.sleep(0.1)
        if vc.is_playing():
            break

    try:
        await asyncio.wait_for(done.wait(), timeout=float(duration_sec) + 2.0)
    except asyncio.TimeoutError:
        try: vc.stop()
        except Exception: pass

    if disconnect_after:
        try: await vc.disconnect()
        except Exception: pass
