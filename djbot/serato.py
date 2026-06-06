"""Read Serato's local analysis cache for TIDAL tracks.

Serato stores one XML per analysed TIDAL track at
``~/Music/_Serato_/Metadata/Tidal/<tidal_id>.xml``. Each file holds the
fields we care about most — BPM and musical key — derived from Serato's own
analysis, alongside loudness (AutoGain) and album art. The filename stem is
the TIDAL track id, which links the entry back to TIDAL.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator, Optional

from .camelot import to_camelot
from .models import Track

DEFAULT_SERATO_DIR = Path.home() / "Music" / "_Serato_"


def tidal_metadata_dir(serato_dir: Path | str = DEFAULT_SERATO_DIR) -> Path:
    return Path(serato_dir) / "Metadata" / "Tidal"


def _text(root: ET.Element, tag: str) -> Optional[str]:
    el = root.find(tag)
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t or None


def _float(root: ET.Element, tag: str) -> Optional[float]:
    raw = _text(root, tag)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_track_xml(path: Path) -> Optional[Track]:
    """Parse one Serato TIDAL metadata XML into a Track. None if unparseable."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None

    key_raw = _text(root, "Key")
    play_count = _float(root, "PlayCount")

    art_path: Optional[str] = None
    art_el = root.find("AlbumArt/Art")
    if art_el is not None:
        fname = art_el.get("filename")
        if fname:
            candidate = path.with_name(fname)
            art_path = str(candidate) if candidate.exists() else None

    bpm = _float(root, "BPM")
    loudness = _float(root, "AutoGain")
    camelot = to_camelot(key_raw)
    # Serato is the authoritative source for the fields it provides.
    prov = {f: "serato" for f, v in (
        ("bpm", bpm), ("key_raw", key_raw), ("camelot", camelot),
        ("loudness", loudness),
    ) if v is not None}

    return Track(
        tidal_id=path.stem,
        artist=_text(root, "Artist") or "",
        title=_text(root, "Name") or "",
        album=_text(root, "Album") or "",
        bpm=bpm,
        key_raw=key_raw,
        camelot=camelot,
        loudness=loudness,
        play_count=int(play_count) if play_count is not None else 0,
        art_path=art_path,
        sources=["serato"],
        prov=prov,
    )


def scan_tidal_library(
    serato_dir: Path | str = DEFAULT_SERATO_DIR,
) -> Iterator[Track]:
    """Yield a Track for every analysed TIDAL XML in the Serato cache."""
    meta_dir = tidal_metadata_dir(serato_dir)
    if not meta_dir.is_dir():
        return
    for xml_path in sorted(meta_dir.glob("*.xml")):
        track = parse_track_xml(xml_path)
        if track is not None:
            yield track
