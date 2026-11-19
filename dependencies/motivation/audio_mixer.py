import asyncio
import random
import re
import shutil
import tempfile
from pathlib import Path

from dependencies.motivation.music_catalog import Track

FADE_IN_SECONDS = 1.0  # Music fade in at the start of the clip
RISE_SECONDS = 0.5  # Music rising to outro_volume when the voice is over
END_FADE_SECONDS = 0.3  # Very short fade at the end, only to avoid a click


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
        raise RuntimeError(f"Could not read the duration of {path.name}")
    h, m, s = times[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


async def mix_voice_with_music(voice_mp3: bytes, track: Track) -> bytes:
    """Put the voice over a random excerpt of the track and return the clip as MP3 bytes.

    The music fades in, plays alone for `intro_seconds`, goes on quietly under the voice,
    then rises to `outro_volume` when the voice is over, plays `outro_seconds` and stops.
    The excerpt starts at a random point of the track (from the start, looped, if the
    track is shorter than the clip).
    """
    with tempfile.TemporaryDirectory() as tmp:
        voice_path = Path(tmp) / "voice.mp3"
        output_path = Path(tmp) / "clip.mp3"
        voice_path.write_bytes(voice_mp3)

        voice_end = track.intro_seconds + await _duration(voice_path)
        total = voice_end + track.outro_seconds
        track_duration = await _duration(track.path)
        if track_duration > total:
            music_input = ["-ss", f"{random.uniform(0, track_duration - total):.3f}", "-i", str(track.path)]
        else:
            music_input = ["-stream_loop", "-1", "-i", str(track.path)]

        low, high = track.volume, track.outro_volume
        level = (
            f"if(lt(t,{voice_end:.3f}),{low},"
            f"{low}+({high}-{low})*min((t-{voice_end:.3f})/{RISE_SECONDS},1))"
        )
        filters = (
            f"[0:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume='{level}':eval=frame,"
            f"afade=t=in:d={FADE_IN_SECONDS},"
            f"afade=t=out:st={total - END_FADE_SECONDS:.3f}:d={END_FADE_SECONDS}[music];"
            f"[1:a]adelay={int(track.intro_seconds * 1000)}:all=1[voice];"
            "[music][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[out]"
        )
        code, stderr = await _run_ffmpeg(
            "-y",
            *music_input,
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
