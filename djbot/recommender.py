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
    # Quality/adjacency prior: reward candidates a DJ we trust has actually
    # played or mixed (Track.curators). Modest, so harmony/BPM still decide the
    # mix; this only nudges between otherwise-comparable picks.
    curation: float = 0.10
    # Sonic-similarity prior: reward candidates in the seed track's cosine.club
    # audio-embedding neighbourhood (passed in as sonic_scores). Only fires when
    # a pool track is among the seed's sonic neighbours; nudges "harmonically
    # fine AND sounds alike" picks upward.
    sonic: float = 0.20
    bpm_tolerance: float = 0.06   # fraction; ~6% is a comfortable beatmatch
    # Penalty applied to half/double-time matches (still useful, but a bigger
    # move than a straight tempo match).
    octave_penalty: float = 0.1
    # --- Fader / directional steering (Phase 4) ---
    # When the user drags the fader, each next track should still be mixable
    # (harmonic + bpm) AND nudge the set's tempo/energy in the chosen direction.
    # `steer` weights that directional progress; `step_bpm` is the BPM move we
    # aim for per track at full fader; `progress_window` is how far off-target a
    # candidate can be before the progress reward decays to zero.
    steer: float = 0.30
    step_bpm: float = 5.0
    progress_window: float = 8.0


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


def curation_score(cand: Track) -> tuple[float, Optional[str]]:
    """Reward a candidate that DJs we trust have played/mixed.

    The catalog's curators are seeded from DJs the user rates (Digweed, Bäumel,
    …), so any curator at all is a positive signal — a free MixesDB-style
    adjacency/quality prior. More distinct curators = a stronger signal, ramped
    gently and capped at 1.0.
    """
    curators = [c for c in (cand.curators or []) if c]
    if not curators:
        return 0.0, None
    score = min(0.7 + 0.15 * (len(curators) - 1), 1.0)
    return score, "played by " + ", ".join(curators)


def score_transition(
    current: Track,
    cand: Track,
    weights: Weights = Weights(),
    direction: str = "any",
    sonic_scores: Optional[dict] = None,
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

    c, cnote = curation_score(cand)
    if cnote:
        reasons.append(cnote)

    sn = (sonic_scores or {}).get(cand.id, 0.0)
    if sn > 0:
        reasons.append(f"~ sounds alike {round(sn * 100)}%")

    total = (
        weights.harmonic * h
        + weights.bpm * b
        + weights.energy * e
        + weights.curation * c
        + weights.sonic * sn
    )
    return Suggestion(track=cand, score=round(total, 4), reasons=reasons)


def recommend_next(
    current: Track,
    pool: Sequence[Track],
    *,
    weights: Weights = Weights(),
    direction: str = "any",
    limit: int = 10,
    min_score: float = 0.0,
    sonic_scores: Optional[dict] = None,
) -> List[Suggestion]:
    """Rank tracks in `pool` as candidates to follow `current`."""
    out: List[Suggestion] = []
    for cand in pool:
        if cand.id == current.id:
            continue
        s = score_transition(current, cand, weights, direction, sonic_scores)
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
    sonic_scores: Optional[dict] = None,
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
                direction=direction, limit=beam_width, sonic_scores=sonic_scores,
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


def _progress_score(
    current_bpm: Optional[float],
    cand_bpm: Optional[float],
    intensity: float,
    step_bpm: float,
    window: float,
) -> tuple[float, Optional[str]]:
    """Reward a candidate for moving tempo in the fader's direction.

    `intensity` is the fader: -1 (descend) .. 0 (hold) .. +1 (climb). The target
    is `current_bpm + intensity*step_bpm`; the score peaks at the target and
    decays linearly to 0 at `window` BPM away. With intensity 0 this rewards
    holding tempo, so the fader's centre behaves like "same vibe".
    """
    if not current_bpm or not cand_bpm:
        return 0.0, None
    delta = cand_bpm - current_bpm
    if abs(intensity) <= 0.05:
        # Fader centred: reward holding the tempo (proximity to current).
        return max(0.0, 1.0 - abs(delta) / window), None
    # Fader pushed: reward movement IN the chosen direction, peaking when the
    # step reaches ~intensity*step_bpm. Staying put (delta 0) scores 0, so the
    # mixability term no longer pins the set in place; wrong-way moves score 0.
    ideal = abs(intensity) * step_bpm
    moved = delta if intensity > 0 else -delta   # signed toward the goal
    if moved <= 0:
        return 0.0, None
    score = min(moved / ideal, 1.0) if ideal else 0.0
    arrow = "↑" if intensity > 0 else "↓"
    return score, f"tempo {arrow} {current_bpm:.0f}→{cand_bpm:.0f}"


def score_steered(
    current: Track,
    cand: Track,
    intensity: float,
    weights: Weights = Weights(),
    sonic_scores: Optional[dict] = None,
) -> Suggestion:
    """Score a transition for the fader: stay mixable, but move in `intensity`.

    Blends harmonic compatibility + BPM mixability (so it's still playable) with
    a directional-progress term (so the set drifts the chosen way) + curation.
    Genre drift is emergent: as the path's BPM climbs, higher-tempo genres
    (trance→goa→dnb) naturally start out-scoring house candidates.
    """
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

    p, pnote = _progress_score(
        current.bpm, cand.bpm, intensity, weights.step_bpm, weights.progress_window
    )
    if pnote:
        reasons.append(pnote)

    c, cnote = curation_score(cand)
    if cnote:
        reasons.append(cnote)

    sn = (sonic_scores or {}).get(cand.id, 0.0)
    if sn > 0:
        reasons.append(f"~ sounds alike {round(sn * 100)}%")

    total = (
        weights.harmonic * h
        + weights.bpm * b
        + weights.steer * p
        + weights.curation * c
        + weights.sonic * sn
    )
    return Suggestion(track=cand, score=round(total, 4), reasons=reasons)


def steer(
    start: Track,
    pool: Sequence[Track],
    intensity: float,
    *,
    depth: int = 4,
    weights: Weights = Weights(),
    beam_width: int = 4,
    sonic_scores: Optional[dict] = None,
) -> List[Suggestion]:
    """Plan a smooth `depth`-track path that steers the set per the fader.

    `intensity` in [-1, 1]: positive climbs tempo/energy (and drifts toward
    faster genres), negative cools it down, ~0 holds the vibe. Beam search over
    `score_steered`, never repeating a track — same machinery as `build_runway`
    but each step is scored for directional progress as well as mixability.
    """
    intensity = max(-1.0, min(1.0, intensity))
    beams: List[tuple[float, List[Suggestion], set, Track]] = [
        (0.0, [], {start.id}, start)
    ]
    for _ in range(depth):
        nxt: List[tuple[float, List[Suggestion], set, Track]] = []
        for cum, path, used, last in beams:
            scored = [
                score_steered(last, t, intensity, weights, sonic_scores)
                for t in pool if t.id not in used
            ]
            scored.sort(key=lambda s: s.score, reverse=True)
            for s in scored[:beam_width]:
                nxt.append((
                    cum + s.score, path + [s], used | {s.track.id}, s.track,
                ))
        if not nxt:
            break
        nxt.sort(key=lambda x: x[0], reverse=True)
        beams = nxt[:beam_width]

    if not beams or not beams[0][1]:
        return []
    return beams[0][1]
