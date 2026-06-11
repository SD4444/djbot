"""Grow the pool with sonically-coherent psy/goa/dnb/trance tracks.

For each seed track we ensure it's enriched (so it's a valid harvest origin),
then harvest its cosine neighbourhood (BPM/key/TIDAL read on the top-N), which
upserts sonically-adjacent, mixable tracks into the catalog. Reuses the exact
server machinery (server._Panel.harvest) so the result matches the live UI.

Run from the venv (librosa needed):
    PATH=/opt/homebrew/bin:$PATH .venv/bin/python -m scripts.seed_genres
Idempotent: already-mixable tracks are skipped, so re-runs are cheap.
"""
from __future__ import annotations

import sys
import time

from djbot import cosine, server
from djbot.catalog import Catalog
from djbot.models import Track, make_id

# Strong scene entry points keyed by the canonical genre cosine harvests into.
# Each seed's neighbourhood inherits the genre when Discogs can't label it.
SEEDS = {
    "goa_psytrance": [
        ("Astrix", "Deep Jungle Walk"), ("Vini Vici", "The Tribe"),
        ("Hallucinogen", "LSD"), ("Shpongle", "Divine Moments of Truth"),
        ("Ural 13 Diktators", "Le Voyage"),
    ],
    "drum_and_bass": [
        ("Calibre", "Mr Right On"), ("Noisia", "Stigma"),
        ("LTJ Bukem", "Horizons"), ("Alix Perez", "Forsaken"),
    ],
    "trance": [
        ("Ferry Corsten", "Punk"), ("System F", "Cry"),
        ("Solarstone", "Seven Cities"), ("Gouryella", "Gouryella"),
    ],
}

N_PER_SEED = 6


def seed() -> int:
    panel = server._Panel("data/catalog.db")
    start_total = len(panel.mixable)
    print(f"start: {len(panel.pool)} tracks ({start_total} mixable)\n", flush=True)

    for genre, seeds in SEEDS.items():
        print(f"=== {genre} ===", flush=True)
        for artist, title in seeds:
            t0 = time.time()
            # ensure the seed itself is in the pool so it can anchor a harvest
            panel.ensure_enriched(artist, title, fallback_genre=genre)
            s = panel.by_id.get(make_id(artist, title))
            if s is None:
                print(f"  ✗ seed unresolved: {artist} — {title}", flush=True)
                continue
            try:
                res = panel.harvest(s, n=N_PER_SEED, fallback_genre=genre)
            except Exception as e:
                print(f"  ! harvest failed {artist} — {title}: {e}", flush=True)
                continue
            print(f"  {artist} — {title}: read {res['harvested']}, "
                  f"+{res['gained']} mixable  ({time.time()-t0:.0f}s)", flush=True)

    end_total = len(panel.mixable)
    print(f"\ndone: {len(panel.pool)} tracks "
          f"({end_total} mixable, +{end_total - start_total} new)", flush=True)
    return 0


def backfill() -> int:
    """Label already-seeded genre-less tracks by re-walking each seed's
    neighbourhood (cosine is cached, so this needs no audio analysis)."""
    with Catalog("data/catalog.db") as cat:
        pool = {t.id: t for t in cat.all_tracks()}
        updates: list[Track] = []
        for genre, seeds in SEEDS.items():
            for artist, title in seeds:
                for c in cosine.neighbourhood(artist, title):
                    tr = pool.get(make_id(c["artist"], c["title"]))
                    if tr and tr.bpm and tr.camelot and not tr.genre:
                        updates.append(Track(id=tr.id, artist=tr.artist,
                                             title=tr.title, genre=genre))
                        tr.genre = genre  # avoid re-queuing across seeds
        cat.upsert(updates)
    print(f"backfilled genre on {len(updates)} tracks", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(backfill() if "--backfill" in sys.argv else seed())
