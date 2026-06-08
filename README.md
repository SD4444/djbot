# djbot

A DJ assistant that suggests harmonically and rhythmically compatible next
tracks while you spin TIDAL through Serato DJ Pro. It reasons about Camelot key,
BPM (including half/double-time), energy, genre, and DJ-curation to line up the
next 1–3 tracks and to keep transitions clean — including across genres — and it
can **steer a set** smoothly up or down in energy/tempo over several tracks.

## Setup (Simon's rig)
- **Source:** TIDAL (streaming) via Serato DJ Pro on a MacBook / Air
- **Controller:** Pioneer DDJ-FLX4 (2-channel, no screen → suggestions show on
  laptop/phone via a local web app)

## How it gets analysis data
TIDAL tracks are DRM streams — no local files to analyse — so BPM/key comes from
three places, upserted into one SQLite catalog (`data/catalog.db`) keyed by a
canonical `artist|title` id with per-field provenance merge:

1. **Serato's local cache (ground truth):** one XML per analysed TIDAL track at
   `~/Music/_Serato_/Metadata/Tidal/<id>.xml` (BPM, key, loudness, art). Accurate
   but only exists *after* a track has been loaded in Serato.
2. **Discogs API (live):** genre/styles/label/year + discography breadth + the
   **curator signal** (which DJ mixed/played a track — a free MixesDB-style
   adjacency/quality signal). No BPM/key.
3. **Our own audio analysis:** free no-auth 30s preview clips (iTunes Search API →
   Deezer fallback) analysed locally with **librosa** — BPM via beat tracking,
   key via Krumhansl–Kessler chroma → Camelot. A genre-aware fold corrects
   librosa's metric/octave misdetections (DnB ~174, goa ~145, trance ~138,
   house ~125).

## Commands
Core CLI is stdlib-only:
```bash
python3 -m djbot scan                 # read Serato TIDAL cache -> catalog
python3 -m djbot list [--sort bpm]    # print catalog with Camelot keys
python3 -m djbot next  "track"        # rank compatible next tracks
python3 -m djbot runway "track" --depth 3   # plan a flowing 1-3 track runway
python3 -m djbot seed  "Artist" …     # grow the universe from Discogs catalogs
python3 -m djbot enrich               # fill genre/label from Discogs
python3 -m djbot config set discogs_token <TOKEN>
```

Audio analysis needs the venv + ffmpeg on PATH (librosa is the only heavy dep):
```bash
PATH=/opt/homebrew/bin:$PATH .venv/bin/python -m djbot analyze   # fill BPM/key
```

The live cockpit panel (Phase 4) is stdlib-only:
```bash
python3 -m djbot.server                # http://localhost:8765 (laptop + phone)
```

## The recommender
Scores transitions by Camelot harmony + BPM proximity (incl. half/double-time) +
energy direction + a **curation boost** (a track a trusted DJ has played ranks
higher). Popularity-blind: niche and famous tracks are treated equally. The logic
is grounded in DJ theory, **not** learned from anyone's past playlists — your
library is only the candidate pool.

`steer(current, pool, intensity)` plans a smooth multi-track path: intensity in
[-1, 1] holds the vibe (~0), climbs tempo/energy (+), or cools it down (−). Genre
drift is emergent — as the path's BPM climbs, faster genres (trance → goa → dnb)
naturally start out-scoring house candidates.

## The cockpit (Phase 4, v1)
A spacecraft flight-deck web UI: animated starfield (looking out into deep space),
neon-blue/violet panels, instrument-style gauges, and three modes —
**Next track**, **Next three**, and a **Steer throttle** (the fader). Now-playing
is set manually by search; click a suggestion to advance the set. Serato
auto-detect and a warp-on-climb starfield effect are planned follow-ups.

## Status / roadmap
- **Phases 1–3b: done** — Serato scan, recommender, Discogs seeding + provenance
  merge, curator signal, own librosa BPM/key analysis.
- **Phase 4: v1 standing up** — cockpit panel + steering. Next: tune steering /
  weights to Simon's ear, Serato now-playing auto-detect, warp effect.
- **Phase 5 (later):** prep mode — energy-arc / genre playlists pushed to TIDAL.
- **TIDAL match (later):** link catalog tracks to TIDAL ids for playback.

See `TODO.md` for the live punch list and `CLAUDE.md` for durable context.

## Layout
- `djbot/camelot.py` — key ↔ Camelot + compatibility scoring
- `djbot/serato.py` — Serato TIDAL XML parser
- `djbot/models.py` — `Track` model + source priority
- `djbot/catalog.py` — SQLite catalog + provenance merge
- `djbot/providers.py` · `enrichment.py` — Discogs lookups, seeding, deltas
- `djbot/audio.py` — preview fetch + librosa analysis + genre-aware tempo fold
- `djbot/genres.py` — genre canonicalisation
- `djbot/recommender.py` — scoring, runway, and the steering fader
- `djbot/server.py` · `djbot/web/` — Phase 4 cockpit (JSON API + flight-deck UI)
- `djbot/cli.py` — command-line interface
