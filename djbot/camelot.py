"""Musical key <-> Camelot wheel conversion and compatibility.

The Camelot wheel encodes every key as a number (1-12) plus a letter:
  - 'A' = minor keys, 'B' = major keys.
Two tracks blend cleanly when they share a code, sit next to each other on the
same letter (+/-1 number, wrapping 12<->1), or swap letter on the same number
(relative major/minor). See https://mixedinkey.com/harmonic-mixing-guide/
"""

from __future__ import annotations

# Serato writes keys in musical notation: a note (A-G), optional accidental
# (# or b), and a trailing lowercase "m" for minor. Examples: "Dm", "Ebm",
# "F#m", "Ab", "B". We map every enharmonic spelling to its Camelot code.

_MINOR = {
    "G#": "1A", "Ab": "1A",
    "D#": "2A", "Eb": "2A",
    "A#": "3A", "Bb": "3A",
    "F": "4A",
    "C": "5A",
    "G": "6A",
    "D": "7A",
    "A": "8A",
    "E": "9A",
    "B": "10A",
    "F#": "11A", "Gb": "11A",
    "C#": "12A", "Db": "12A",
}

_MAJOR = {
    "B": "1B",
    "F#": "2B", "Gb": "2B",
    "C#": "3B", "Db": "3B",
    "G#": "4B", "Ab": "4B",
    "D#": "5B", "Eb": "5B",
    "A#": "6B", "Bb": "6B",
    "F": "7B",
    "C": "8B",
    "G": "9B",
    "D": "10B",
    "A": "11B",
    "E": "12B",
}


def to_camelot(key: str | None) -> str | None:
    """Convert a Serato/musical key string (e.g. "Ebm", "F#", "B") to Camelot.

    Returns None if the key is empty or unrecognised. Input that already looks
    like a Camelot code (e.g. "7A") is passed through.
    """
    if not key:
        return None
    k = key.strip()
    if not k:
        return None

    # Already Camelot? e.g. "7A", "12B"
    if k[:-1].isdigit() and k[-1:].upper() in ("A", "B"):
        return k[:-1] + k[-1].upper()

    is_minor = k.endswith("m")
    note = k[:-1] if is_minor else k

    # Normalise: capitalise the letter, keep the accidental as-is (# or b).
    if not note:
        return None
    note = note[0].upper() + note[1:]
    table = _MINOR if is_minor else _MAJOR
    return table.get(note)


def _parse_code(code: str) -> tuple[int, str] | None:
    """Split a Camelot code like "7A" into (7, "A"). None if malformed."""
    if not code or len(code) < 2:
        return None
    num, letter = code[:-1], code[-1].upper()
    if not num.isdigit() or letter not in ("A", "B"):
        return None
    n = int(num)
    if not 1 <= n <= 12:
        return None
    return n, letter


def _ring_distance(a: int, b: int) -> int:
    """Shortest distance on the 12-hour Camelot ring."""
    d = abs(a - b) % 12
    return min(d, 12 - d)


def compatibility(a: str | None, b: str | None) -> str:
    """Describe the harmonic relationship between two Camelot codes.

    Returns one of: "same", "adjacent", "relative", "energy" (a +/-2 jump
    commonly used to lift energy), "distant", or "unknown".
    """
    pa, pb = _parse_code(a or ""), _parse_code(b or "")
    if pa is None or pb is None:
        return "unknown"
    (na, la), (nb, lb) = pa, pb

    if na == nb and la == lb:
        return "same"
    if na == nb and la != lb:
        return "relative"  # relative major/minor swap
    if la == lb:
        dist = _ring_distance(na, nb)
        if dist == 1:
            return "adjacent"
        if dist == 2:
            return "energy"
    return "distant"


# Higher score = smoother blend. Used later by the recommender.
_SCORE = {"same": 1.0, "adjacent": 0.85, "relative": 0.8, "energy": 0.6,
          "distant": 0.0, "unknown": 0.0}


def harmonic_score(a: str | None, b: str | None) -> float:
    """0..1 harmonic-compatibility score between two Camelot codes."""
    return _SCORE[compatibility(a, b)]
