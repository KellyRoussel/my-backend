import asyncio
import re
import shutil
import tempfile
from pathlib import Path

from dependencies.motivation.music_catalog import Track

FADE_SECONDS = 1.5


def _ffmpeg_exe() -> str:
    # Render's Python runtime has no system ffmpeg: fall back to the binary shipped by imageio-ffmpeg
    system = shutil.which("ffmpeg")
    if system:
        return system
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


async def _run_ffmpeg(*args: str) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        _ffmpeg_exe(), "-hide_banner", *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    return process.returncode, stderr.decode(errors="replace")


async def _duration(path: Path) -> float:
    # Decode the whole file: the duration in the MP3 header is only an estimate
    _, stderr = await _run_ffmpeg("-i", str(path), "-f", "null", "-")
    times = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not times:
        raise RuntimeError("Could not read the voice duration")
    h, m, s = times[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


async def mix_voice_with_music(voice_mp3: bytes, track: Track) -> bytes:
    """Put the voice over the track and return the clip as MP3 bytes.

    The music plays alone for `intro_seconds`, goes on under the voice and stops
    `outro_seconds` after it, with a fade in and out. It loops if it is too short.
    """
    with tempfile.TemporaryDirectory() as tmp:
        voice_path = Path(tmp) / "voice.mp3"
        output_path = Path(tmp) / "clip.mp3"
        voice_path.write_bytes(voice_mp3)

        total = track.intro_seconds + await _duration(voice_path) + track.outro_seconds
        delay_ms = int(track.intro_seconds * 1000)
        fade_out_start = max(total - FADE_SECONDS, 0)

        filters = (
            f"[0:a]atrim=0:{total:.3f},volume={track.volume},"
            f"afade=t=in:d={FADE_SECONDS},afade=t=out:st={fade_out_start:.3f}:d={FADE_SECONDS}[music];"
            f"[1:a]adelay={delay_ms}:all=1[voice];"
            "[music][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[out]"
        )
        code, stderr = await _run_ffmpeg(
            "-y",
            "-stream_loop", "-1", "-i", str(track.path),
            "-i", str(voice_path),
            "-filter_complex", filters,
            "-map", "[out]",
            "-ac", "2", "-ar", "44100",
            "-c:a", "libmp3lame", "-b:a", "192k",
            str(output_path),
        )
        if code != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr[-500:]}")
        return output_path.read_bytes()
