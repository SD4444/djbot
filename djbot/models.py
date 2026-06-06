"""Core data model for tracks in the catalog.

Tracks are identified by a canonical ``id`` derived from artist + title, so the
same song discovered from different sources (Serato, Discogs, TIDAL) merges into
one entry. ``prov`` records which source supplied each precision field, so a
weaker source never overwrites a stronger one (see catalog.merge_tracks).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Relative trust per source, used when merging conflicting precision fields.
SOURCE_PRIORITY = {
    "manual": 4,
    "serato": 3,      # Serato's own analysis
    "audio": 3,       # our own Essentia/librosa analysis (later)
    "getsongbpm": 2,
    "acousticbrainz": 1,
    "discogs": 1,
    "tidal": 1,
    "": 0,
}


def make_id(artist: str, title: str) -> str:
    """Canonical, dedup-friendly id from artist + title."""
    def norm(s: str) -> str:
        s = (s or "").lower().strip()
        s = re.sub(r"\s+", " ", s)
        return s
    return f"{norm(artist)}|{norm(title)}"


@dataclass
class Track:
    artist: str = ""
    title: str = ""
    id: str = ""                       # canonical; auto-derived if empty
    tidal_id: Optional[str] = None     # set when matched to TIDAL (for playback)
    album: str = ""
    bpm: Optional[float] = None
    key_raw: Optional[str] = None      # musical notation, e.g. "Ebm"
    camelot: Optional[str] = None      # derived, e.g. "2A"
    loudness: Optional[float] = None   # Serato AutoGain (dB), rough energy proxy
    energy: Optional[float] = None     # 0..1, from enrichment
    genre: Optional[str] = None        # canonical (see genres.py)
    styles: List[str] = field(default_factory=list)  # raw source tags
    curators: List[str] = field(default_factory=list)  # DJs who mixed/played it (Digweed, ...)
    label: Optional[str] = None
    year: Optional[int] = None
    play_count: int = 0
    art_path: Optional[str] = None
    sources: List[str] = field(default_factory=list)  # which providers touched it
    prov: dict = field(default_factory=dict)           # field -> source name
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = make_id(self.artist, self.title)

    @property
    def label_str(self) -> str:
        return f"{self.artist} — {self.title}".strip(" —")
