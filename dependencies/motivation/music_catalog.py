"""Background tracks the clips can use.

The audio files stay on the machine running the backend, in assets/motivation/music/:
they are git-ignored (copyrighted music for personal use, never pushed). Any audio file
dropped there is a track, its id being the file name without extension. Add an entry
to SETTINGS only to give it a nicer title or other levels than the defaults.
"""
from dataclasses import dataclass
from pathlib import Path

MUSIC_DIR = Path(__file__).resolve().parents[2] / "assets" / "motivation" / "music"
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".flac"}


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    filename: str
    volume: float = 0.25  # Music level under the voice (1.0 = original level)
    intro_seconds: float = 2.0  # Music alone before the voice starts
    outro_seconds: float = 3.0  # Music alone after the voice ends

    @property
    def path(self) -> Path:
        return MUSIC_DIR / self.filename


# Optional settings per track, keyed by file name without extension, e.g.
# "eye-of-the-tiger": {"title": "Eye of the Tiger", "volume": 0.2, "intro_seconds": 4},
SETTINGS: dict[str, dict] = {}


def list_tracks() -> list[Track]:
    """Tracks present in MUSIC_DIR, read at each call so a new file needs no restart."""
    if not MUSIC_DIR.is_dir():
        return []
    tracks = []
    for path in sorted(MUSIC_DIR.iterdir()):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            options = {"title": path.stem.replace("-", " ").replace("_", " ").capitalize()}
            options.update(SETTINGS.get(path.stem, {}))
            tracks.append(Track(id=path.stem, filename=path.name, **options))
    return tracks


def get_track(track_id: str) -> Track | None:
    return next((track for track in list_tracks() if track.id == track_id), None)
