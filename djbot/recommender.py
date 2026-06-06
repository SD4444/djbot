"""The recommendation engine: score and rank compatible next tracks.

The logic is grounded in DJ theory, NOT learned from anyone's past playlists:
  - harmonic compatibility on the Camelot wheel
  - BPM proximity, including half-time / double-time matches
  - energy direction (do we want to lift, hold, or cool down)

Weights are tunable (see `Weights`) so the engine can later be calibrated
against example setlists the user considers cleanly mixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .camelot import compatibility, harmonic_score
from .models import Track

# Human-readable labels for Camelot relationships.
_REL_TEXT = {
    "same": "same key",
    "adjacent": "adjacent key (±1)",
    "relative": "relative major/minor",
    "energy": "energy jump (±2)",
    "distant": "key clash",
    "unknown": "key unknown",
}


@dataclass
class Weights:
    harmonic: float = 0.55
    bpm: float = 0.40
    energy: float = 0.05
    bpm_tolerance: float = 0.06   # fraction; ~6% is a comfortable beatmatch
    # Penalty applied to half/double-time matches (still useful, but a bigger
    # move than a straight tempo match).
    octave_penalty: float = 0.1


@dataclass
class Suggestion:
    track: Track
    score: float
    reasons: List[str] = field(default_factory=list)


def bpm_match(
    current_bpm: Optional[float],
    cand_bpm: Optional[float],
    tolerance: float,
    octave_penalty: float,
) -> tuple[float, Optional[str]]:
    """Best BPM-compatibility score over straight/half/double time.

    Returns (score 0..1, human note). Score falls off linearly to 0 at
    `tolerance` away. Half/double matches get a small penalty.
    """
    if not current_bpm or not cand_bpm:
        return 0.0, None

    best_score = 0.0
    best_note: Optional[str] = None
    for mult, tag in ((1.0, ""), (2.0, "double-time"), (0.5, "half-time")):
        target = cand_bpm * mult
        diff = abs(target - current_bpm) / current_bpm
        if diff >= tolerance:
            continue
        score = 1.0 - diff / tolerance
        if mult != 1.0:
            score -= octave_penalty
        if score > best_score:
            best_score = score
            if mult == 1.0:
                best_note = f"{current_bpm:.0f}↔{cand_bpm:.0f} BPM"
            else:
                best_note = f"{current_bpm:.0f}→{cand_bpm:.0f} BPM ({tag})"
    return max(best_score, 0.0), best_note


def _energy_value(t: Track) -> Optional[float]:
    """Best available energy proxy: explicit energy, else loudness (AutoGain).

    AutoGain is negative dB; less negative = louder = roughly more energetic,
    so we negate it to get an ascending scale.
    """
    if t.energy is not None:
        return t.energy
    if t.loudness is not None:
        return -t.loudness
    return None


def energy_match(
    current: Track, cand: Track, direction: str
) -> tuple[float, Optional[str]]:
    """Score how well the candidate fits the desired energy direction."""
    cv, nv = _energy_value(current), _energy_value(cand)
    if cv is None or nv is None:
        return 0.5, None  # neutral when we can't tell
    delta = nv - cv
    if direction == "up":
        return (1.0 if delta > 0 else 0.3), ("energy up" if delta > 0 else None)
    if direction == "down":
        return (1.0 if delta < 0 else 0.3), ("energy down" if delta < 0 else None)
    if direction == "hold":
        return (1.0 - min(abs(delta) / 4.0, 1.0)), "energy steady"
    return 0.5, None  # "any"


def score_transition(
    current: Track,
    cand: Track,
    weights: Weights = Weights(),
    direction: str = "any",
) -> Suggestion:
    reasons: List[str] = []

    h = harmonic_score(current.camelot, cand.camelot)
    rel = compatibility(current.camelot, cand.camelot)
    if cand.camelot:
        reasons.append(f"{cand.camelot} · {_REL_TEXT[rel]}")

    b, bnote = bpm_match(
        current.bpm, cand.bpm, weights.bpm_tolerance, weights.octave_penalty
    )
    if bnote:
        reasons.append(bnote)

    e, enote = energy_match(current, cand, direction)
    if enote:
        reasons.append(enote)

    total = weights.harmonic * h + weights.bpm * b + weights.energy * e
    return Suggestion(track=cand, score=round(total, 4), reasons=reasons)


def recommend_next(
    current: Track,
    pool: Sequence[Track],
    *,
    weights: Weights = Weights(),
    direction: str = "any",
    limit: int = 10,
    min_score: float = 0.0,
) -> List[Suggestion]:
    """Rank tracks in `pool` as candidates to follow `current`."""
    out: List[Suggestion] = []
    for cand in pool:
        if cand.id == current.id:
            continue
        s = score_transition(current, cand, weights, direction)
        if s.score >= min_score:
            out.append(s)
    out.sort(key=lambda s: s.score, reverse=True)
    return out[:limit]


def build_runway(
    start: Track,
    pool: Sequence[Track],
    *,
    depth: int = 3,
    weights: Weights = Weights(),
    direction: str = "any",
    beam_width: int = 4,
) -> List[Suggestion]:
    """Plan a sequence of `depth` tracks after `start` that flows end to end.

    Beam search: keep the `beam_width` best partial paths by cumulative score,
    extend each by its best next steps, never repeating a track.
    """
    # Each beam entry: (cum_score, [Suggestion...], used_ids, last_track)
    beams: List[tuple[float, List[Suggestion], set, Track]] = [
        (0.0, [], {start.id}, start)
    ]

    for _ in range(depth):
        nxt: List[tuple[float, List[Suggestion], set, Track]] = []
        for cum, path, used, last in beams:
            candidates = [t for t in pool if t.id not in used]
            steps = recommend_next(
                last, candidates, weights=weights,
                direction=direction, limit=beam_width,
            )
            for s in steps:
                nxt.append((
                    cum + s.score,
                    path + [s],
                    used | {s.track.id},
                    s.track,
                ))
        if not nxt:
            break
        nxt.sort(key=lambda x: x[0], reverse=True)
        beams = nxt[:beam_width]

    if not beams or not beams[0][1]:
        return []
    return beams[0][1]
