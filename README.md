# djbot

A DJ assistant that suggests harmonically and rhythmically compatible next
tracks while you spin TIDAL through Serato DJ Pro. It reasons about Camelot key,
BPM (including half/double-time), energy, and genre to line up the next 1–3
tracks and to keep transitions clean — including across genres.

## Setup (Simon's rig)
- **Source:** TIDAL (streaming) via Serato DJ Pro on a MacBook / Air
- **Controller:** Pioneer DDJ-FLX4 (2-channel, no screen → suggestions show on
  laptop/phone)

## How it gets analysis data
TIDAL tracks are DRM streams — no local files to analyse — so BPM/key/energy
comes from two places:

1. **Serato's local cache (ground truth):** Serato writes one XML per analysed
   TIDAL track at `~/Music/_Serato_/Metadata/Tidal/<tidal_id>.xml`, containing
   BPM, musical key, loudness (AutoGain), and album art. Accurate and free, but
   only exists *after* a track has been loaded in Serato.
2. **TIDAL API + enrichment (forward-looking):** `tidalapi` enumerates your full
   playlists/favorites; BPM/key/energy for tracks you haven't loaded yet are
   filled from a metadata service (Tunebat / GetSongBPM / SongData). This is what
   lets the assistant suggest tracks *ahead of time* without pre-loading them.

Both sources upsert into one SQLite catalog keyed by `tidal_id`; Serato data
wins where present.

## Phase 1 (done): catalog from Serato cache
Stdlib-only, read-only against your Serato folder.

```bash
python3 -m djbot scan          # read Serato TIDAL cache -> data/catalog.db
python3 -m djbot list          # print catalog with Camelot keys
python3 -m djbot list --sort bpm
```

## Phase 2 (done): the recommender
```bash
python3 -m djbot next "track name"          # rank compatible next tracks
python3 -m djbot runway "track name" --depth 3   # plan a flowing 1-3 track runway
```
Scores by Camelot harmony + BPM proximity (incl. half/double-time) + energy
direction. Popularity-blind, so it treats niche and famous tracks equally.

## Phase 3 (in progress): grow the universe via free enrichment
Free API keys (one-time): get a [Discogs personal token](https://www.discogs.com/settings/developers)
and a [GetSongBPM key](https://getsongbpm.com/api), then:
```bash
python3 -m djbot config set discogs_token <TOKEN>
python3 -m djbot config set getsongbpm_key <KEY>
python3 -m djbot seed "John Digweed" "Patrice Bäumel"   # pull scene catalogs (Discogs)
python3 -m djbot enrich                                  # fill genre/label/BPM/key
```
- **Discogs** → genre/sub-genre (styles), label, year (gold standard for electronic)
- **GetSongBPM** → BPM + key for tracks Serato hasn't analysed
- Merge respects source priority: Serato/our-analysis > GetSongBPM > Discogs, so
  good data is never overwritten. Genre/label always from Discogs.

## Roadmap
- **Phase 3b** — our own audio analysis (Essentia/librosa) on preview clips:
  free, niche-proof BPM/key/embeddings; the quality backbone.
- **Phase 4** — live "play next" panel (local web app, laptop + phone) driven by
  Serato now-playing detection.
- **Phase 5** — prep mode: generate energy-arc / genre playlists, push back to TIDAL.
- **TIDAL match** — link catalog tracks to TIDAL ids for playback (needs login).

## Layout
- `djbot/camelot.py` — key ↔ Camelot conversion + compatibility scoring
- `djbot/serato.py` — Serato TIDAL XML parser
- `djbot/models.py` — `Track` data model
- `djbot/catalog.py` — SQLite-backed catalog
- `djbot/cli.py` — command-line interface
