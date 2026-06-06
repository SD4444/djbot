"""Canonical genre vocabulary, tempo bands, and source-tag normalisation.

Discogs (and other sources) use many spellings for the same scene. We map them
to a small canonical set, each with a typical BPM band, so the recommender can
reason about genre fit and cross-genre transitions for Simon's styles
(deep/progressive/tech house, trance, goa, dnb/liquid).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# Canonical genre -> typical BPM band (low, high).
TEMPO_BANDS = {
    "deep_house": (118, 125),
    "progressive_house": (122, 130),
    "tech_house": (123, 128),
    "house": (120, 128),
    "melodic_house_techno": (120, 126),
    "techno": (125, 140),
    "minimal": (123, 130),
    "trance": (132, 140),
    "progressive_trance": (130, 138),
    "goa_psytrance": (140, 150),
    "drum_and_bass": (170, 176),
    "liquid_dnb": (170, 176),
    "breakbeat": (125, 140),
    "electro": (125, 132),
    "disco": (110, 125),
    "nu_disco": (110, 124),
    "downtempo": (85, 110),
    "dubstep": (138, 145),
    "garage": (128, 136),
}

# Normalised source-tag -> canonical genre. Keys are run through _norm() first.
_STYLE_TO_GENRE = {
    "deep house": "deep_house",
    "progressive house": "progressive_house",
    "prog house": "progressive_house",
    "tech house": "tech_house",
    "house": "house",
    "electro house": "house",
    "future house": "house",
    "melodic house": "melodic_house_techno",
    "melodic techno": "melodic_house_techno",
    "techno": "techno",
    "minimal techno": "techno",
    "minimal": "minimal",
    "trance": "trance",
    "uplifting trance": "trance",
    "progressive trance": "progressive_trance",
    "goa trance": "goa_psytrance",
    "psy trance": "goa_psytrance",
    "psytrance": "goa_psytrance",
    "psychedelic": "goa_psytrance",
    "drum n bass": "drum_and_bass",
    "drum and bass": "drum_and_bass",
    "drumnbass": "drum_and_bass",
    "jungle": "drum_and_bass",
    "liquid funk": "liquid_dnb",
    "liquid dnb": "liquid_dnb",
    "breakbeat": "breakbeat",
    "breaks": "breakbeat",
    "big beat": "breakbeat",
    "electro": "electro",
    "disco": "disco",
    "nu disco": "nu_disco",
    "nu-disco": "nu_disco",
    "downtempo": "downtempo",
    "dubstep": "dubstep",
    "garage": "garage",
    "uk garage": "garage",
}


def _norm(tag: str) -> str:
    t = (tag or "").lower().strip()
    t = t.replace("&", "and").replace("-", " ")
    t = re.sub(r"\s+", " ", t)
    return t


def canonical_genre(styles: List[str] | None) -> Optional[str]:
    """First recognised canonical genre among the given source styles/tags."""
    for s in styles or []:
        g = _STYLE_TO_GENRE.get(_norm(s))
        if g:
            return g
    return None


def tempo_band(genre: Optional[str]) -> Optional[Tuple[int, int]]:
    return TEMPO_BANDS.get(genre or "")


def tempo_fit(genre: Optional[str], bpm: Optional[float]) -> Optional[bool]:
    """True/False if bpm sits in the genre's band; None if we can't tell."""
    band = tempo_band(genre)
    if band is None or bpm is None:
        return None
    return band[0] <= bpm <= band[1]
