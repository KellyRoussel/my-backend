"""Background tracks the clips can use.

The files live in assets/motivation/music/ (committed, not publicly served).
To add a track: drop the file there and add a line below.
"""
from dataclasses import dataclass
from pathlib import Path

MUSIC_DIR = Path(__file__).resolve().parents[2] / "assets" / "motivation" / "music"


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


# TODO(Kelly): list the real tracks
TRACKS: list[Track] = [
    # Track(id="epic", title="Épique", filename="epic.mp3"),
]

_BY_ID = {track.id: track for track in TRACKS}


def get_track(track_id: str) -> Track | None:
    return _BY_ID.get(track_id)
