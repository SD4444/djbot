"""Turn provider lookups into mergeable Track deltas.

Each enrichment produces a partial Track carrying only the new fields (plus the
canonical id/artist/title so it merges onto the right entry). The catalog's
`merge_tracks` then applies source-priority rules, so Serato's BPM is never
clobbered by GetSongBPM, etc.
"""

from __future__ import annotations

from typing import List, Optional

from . import audio
from .camelot import to_camelot
from .genres import canonical_genre
from .models import Track
from .providers import DiscogsClient, GetSongBPMClient


def enrich_track(
    track: Track,
    discogs: Optional[DiscogsClient] = None,
    getsongbpm: Optional[GetSongBPMClient] = None,
) -> List[Track]:
    """Return partial Track deltas to upsert for `track`. Possibly empty."""
    deltas: List[Track] = []

    if discogs is not None and not track.genre:
        r = discogs.search_release(track.artist, track.title)
        if r:
            styles = r["styles"] or r["genres"]
            deltas.append(Track(
                id=track.id, artist=track.artist, title=track.title,
                genre=canonical_genre(styles),
                styles=styles,
                label=r.get("label"),
                year=r.get("year"),
                sources=["discogs"],
            ))

    if getsongbpm is not None and (track.bpm is None or track.camelot is None):
        r = getsongbpm.lookup(track.artist, track.title)
        if r:
            key_raw = r.get("key_raw")
            camelot = to_camelot(key_raw)
            prov = {}
            if r.get("bpm") is not None:
                prov["bpm"] = "getsongbpm"
            if key_raw:
                prov["key_raw"] = "getsongbpm"
            if camelot:
                prov["camelot"] = "getsongbpm"
            deltas.append(Track(
                id=track.id, artist=track.artist, title=track.title,
                bpm=r.get("bpm"), key_raw=key_raw, camelot=camelot,
                sources=["getsongbpm"], prov=prov,
            ))

    return deltas


def analyze_track(track: Track) -> Optional[Track]:
    """Estimate BPM/key for `track` from its own audio (Phase 3b backbone).

    Returns a partial Track delta tagged with `audio` provenance (priority ties
    Serato, beats Discogs/GetSongBPM), or None if no audio could be analysed.
    """
    res = audio.analyze_track_audio(track.artist, track.title, track.genre)
    if not res:
        return None
    bpm = res.get("bpm")
    key_raw = res.get("key_raw")
    camelot = to_camelot(key_raw)
    prov = {}
    if bpm is not None:
        prov["bpm"] = "audio"
    if key_raw:
        prov["key_raw"] = "audio"
    if camelot:
        prov["camelot"] = "audio"
    if not prov:
        return None
    return Track(
        id=track.id, artist=track.artist, title=track.title,
        bpm=bpm, key_raw=key_raw, camelot=camelot,
        sources=["audio"], prov=prov,
    )


def seed_from_artist(
    discogs: DiscogsClient, artist_name: str, max_releases: int = 10,
) -> List[Track]:
    """Pull an artist's recent releases from Discogs into candidate tracks.

    These have no tidal_id yet (matched to TIDAL later for playback); they carry
    genre/styles/label/year so the universe grows with scene-accurate metadata.
    """
    out: List[Track] = []
    seen = set()
    for rid in discogs.artist_release_ids(artist_name, max_releases):
        rel = discogs.release(rid)
        if not rel:
            continue
        styles = rel["styles"] or rel["genres"]
        genre = canonical_genre(styles)
        rel_artist = rel.get("artist") or artist_name
        mixed = rel.get("mixed")
        for tr in rel["tracks"]:
            # The real producer is the per-track artist; only fall back to the
            # release artist when a track carries no credit of its own.
            producer = " & ".join(a for a in tr["artists"] if a) or rel_artist
            # On a DJ-mix comp, the release artist is the curator, not the maker.
            curators = ([rel_artist] if mixed and _norm(producer) != _norm(rel_artist)
                        else [])
            t = Track(
                artist=producer, title=tr["title"],
                genre=genre, styles=styles, curators=curators,
                label=rel.get("label"), year=rel.get("year"),
                sources=["discogs"],
            )
            if t.id not in seen:
                seen.add(t.id)
                out.append(t)
    return out


def _norm(s: str) -> str:
    return (s or "").strip().lower()
