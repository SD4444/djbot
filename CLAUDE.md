# CLAUDE.md — djbot

DJ assistant that suggests harmonically/rhythmically compatible next tracks while
Simon spins TIDAL through Serato. Reasons about Camelot key, BPM (incl.
half/double-time), energy, and genre to line up the next 1–3 tracks with clean
(incl. cross-genre) transitions. README.md is user-facing; this file is the
durable context + ground rules for working in the repo.

## The rig
TIDAL (streaming) → Serato DJ Pro → Pioneer DDJ-FLX4 (2-channel, no screen) on a
MacBook/Air. Suggestions must show on laptop/phone. Both a pre-set prep mode and a
live in-the-moment panel are wanted; the live panel is a local web app.

## Data strategy (the core constraint)
TIDAL tracks are DRM streams — no local files to analyse. Everything upserts into
one SQLite catalog (`data/catalog.db`) keyed by a canonical `artist|title` id,
with per-field provenance merge (`catalog.merge_tracks`, priority in
`models.SOURCE_PRIORITY`) so weaker sources never clobber stronger ones.

Sources, by role:
1. **Serato local cache** — ground truth (BPM, key, AutoGain loudness, art) at
   `~/Music/_Serato_/Metadata/Tidal/<id>.xml`. Only exists *after* a track is
   loaded in Serato.
2. **Discogs API (LIVE)** — genre/styles/label/year + discography breadth +
   per-track artists + `videos`. Has ZERO BPM/key/energy. Token in
   `~/.config/djbot/config.json`.
3. **Our own audio analysis (`audio.py`)** — niche-proof BPM/key backbone.
   Pulls free no-auth 30s preview MP3s from **iTunes Search API** (primary) +
   **Deezer** (fallback), fuzzy-matched to artist+title, then librosa estimates
   BPM (`beat.beat_track`) + key (Krumhansl–Kessler chroma → camelot). Tagged
   `prov=audio` (priority ties Serato, beats Discogs).

**Curator signal:** Discogs exposes per-track producers AND tags DJ-mix comps
"Mixed". So `Track.curators` records the DJ who mixed/played a track (e.g. John
Digweed) — a free MixesDB-style adjacency/quality signal, kept separate from the
real-producer `artist` field. ~131/147 tracks carry one.

## Commands
Plain CLI (stdlib only): `python3 -m djbot {scan|list|next|runway|enrich|seed|config}`

Audio analysis needs the venv + ffmpeg on PATH (librosa is the only heavy dep;
system python is 3.9 and too old):
```
PATH=/opt/homebrew/bin:$PATH .venv/bin/python -m djbot analyze [--all] [--limit N]
```

## Decisions locked — do NOT re-litigate
- **Free sources only.** No Beatport/paid services.
- **GetSongBPM is dead** — its whole API host sits behind a Cloudflare JS
  challenge; 403s every way. Provider code stays but is unusable. Don't retry it.
- **yt-dlp/YouTube is dead** for previews — PO-token wall. iTunes/Deezer is the
  preview source. (Discogs `videos` are the same walled YouTube links.)
- **Recommender = music theory** (Camelot/BPM/energy), NOT learned from Simon's
  past setlists. His library is only the candidate POOL; he distrusts using his
  setlists as the definition of "good." He'll supply a few clean setlists ONLY to
  calibrate scoring weights, as a tuning layer.
- **Pool = all of TIDAL via discovery** (a curated universe that grows from his
  scene), not just his prefilled crates. TIDAL's own recommender is weak for niche.
- **Storage = SQLite** is the structured brain. Markdown = human-readable exports only.
- Simon spins deep/prog/tech house, trance, goa, dnb/liquid. Influences: Sasha,
  Digweed, Patrice Bäumel. (The 16 disco/pop Serato tracks are random TEST content,
  NOT his taste — ignore them, and they should be purged.)

## Status & next steps
See TODO.md for the live punch list. As of last session: 147 tracks, ~131 with a
curator, ~21 with audio-analysed BPM. Immediate next: finish `analyze` across the
pool, purge the 16 Serato test tracks, then wire `Track.curators` into
`recommender.Weights` as a scoring boost.

## Module layout
`camelot.py` key↔Camelot + compat scoring · `serato.py` Serato XML parser ·
`models.py` Track model + SOURCE_PRIORITY · `catalog.py` SQLite catalog + merge ·
`providers.py` Discogs/GetSongBPM · `enrichment.py` enrich/seed · `audio.py`
preview fetch + librosa analysis + genre-aware `_normalize_tempo` fold · `genres.py` ·
`recommender.py` next/runway + `steer()` fader · `server.py` + `web/index.html` Phase 4
cockpit (stdlib http.server JSON API + flight-deck UI) · `config.py` · `cli.py` /
`__main__.py` entry points.

## Running the cockpit (Phase 4)
`python3 -m djbot.server` → http://localhost:8765 (stdlib-only; reachable from a phone
on the same wifi). Now-playing is manual (search). Steering fader = `recommender.steer`.
Audio analysis is the only thing needing the venv: `PATH=/opt/homebrew/bin:$PATH
.venv/bin/python -m djbot analyze`.

## BPM detector note
librosa is octave-error-prone; `_normalize_tempo` is a genre-aware band-aid (works, genre
averages correct). A detector upgrade (tempo-cnn / madmom / Essentia) is queued as a future
bake-off — see the `djbot-bpm-detectors` memory. Don't pivot detectors casually.
