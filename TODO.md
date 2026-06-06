# djbot — TODO / where we left off

_Last session: 2026-06-06. Discogs is LIVE; GetSongBPM is dead (Cloudflare); per-track
attribution + curator signal shipped. Catalog at 147 tracks (97 with a curator)._

## ▶️ Pick up here (next session)

### 1. Run audio analysis across the whole pool + clean up
Phase 3b works (`djbot analyze`). Deps live in `.venv/` (librosa + ffmpeg). Run:
`PATH=/opt/homebrew/bin:$PATH .venv/bin/python -m djbot analyze`  (downloads previews, local/free).
- [ ] Run `analyze` over all 147 tracks (only 5 done so far).
- [ ] **Purge the 16 Serato test tracks** (ABBA/Madonna/etc. — random disco/pop, not Simon's
      taste). They pollute `next`/`runway`. Delete by id or re-scan with a real Serato lib.
- [ ] Spot-check a few BPM/key estimates against what you know — note accuracy.

### 2. Use the curator signal in scoring
- [ ] Add a curation boost to `recommender.Weights` — a candidate a DJ Simon admires has
      played/mixed (`Track.curators`) should score higher. 97 tracks already carry this.

## 🔜 Next phases
- [ ] **Phase 3b — own audio analysis** (Essentia/librosa on 30s previews): free,
      niche-proof BPM/key + audio embeddings. The real quality backbone. Solves
      Discogs/GetSongBPM misses on obscure tracks. (Needs a preview-audio source.)
- [ ] **MixesDB ingestion** — real DJ-set adjacency (what pros actually play
      back-to-back) as a discovery signal; the one free/legal source for it.
- [ ] **TIDAL match** — link catalog tracks to TIDAL ids for playback
      (`tidalapi`, needs Simon's browser login — token only, never password).
- [ ] **Phase 4 — live "play next" panel**: local web app (laptop + phone),
      driven by Serato now-playing detection (History session files / Live Playlist).
- [ ] **Phase 5 — prep mode**: generate energy-arc / genre playlists, push to TIDAL.
- [ ] **Tune the recommender to Simon's ear**: he'll provide 2-3 setlists he
      considers cleanly mixed; fit `recommender.Weights` so scores match his taste.

## 🧠 Key decisions locked (don't re-litigate)
- Free sources only (no Beatport/paid). Discogs + GetSongBPM + Serato + own audio analysis.
- Recommender logic = music theory (Camelot/BPM/energy), NOT learned from past playlists.
- Pool = a curated universe that grows from Simon's scene, drawing on all of TIDAL via
  discovery — NOT limited to his prefilled folders. (TIDAL's own recommender is weak for niche.)
- Storage = SQLite (`data/catalog.db`), the structured brain. Markdown = human-readable exports only.
- Simon spins: deep/prog/tech house, trance, goa, dnb/liquid. Influences: Sasha, Digweed, Bäumel.

## ✅ Done
- Phase 1: Serato TIDAL XML → catalog (`scan`, `list`).
- Phase 2: recommender (`next`, `runway`) — Camelot + BPM (half/double) + energy + lookahead.
- Phase 3 backbone: canonical-id dedup + provenance merge; Discogs + GetSongBPM providers;
  `enrich`, `seed`, `config` commands.
- Discogs LIVE: token saved; fixed `artist_release_ids` to over-fetch+filter (was yielding 1).
- Per-track attribution + **curator signal**: `release()` returns per-track artists + `mixed`;
  `seed_from_artist` credits the real producer and records the mixing DJ in new
  `Track.curators` (catalog column + auto-migrate + merge union). Free MixesDB-style signal.
- GetSongBPM: confirmed dead (Cloudflare "Just a moment" JS challenge on the whole API host).
- **Phase 3b audio analysis** (`djbot analyze`): own BPM/key backbone. yt-dlp/YouTube ruled
  out (PO-token wall); pivoted to free no-auth iTunes + Deezer 30s previews + librosa
  (BPM via beat_track, key via Krumhansl–Kessler chroma). `prov=audio`. Verified on 5 tracks.
