# djbot — TODO / where we left off

_Last session: 2026-06-08. Purged Serato test junk, analyzed the whole pool, fixed BPM
octave errors, shipped the curator boost. Catalog now 131 tracks (131 with a curator;
98 with BPM+key after the cleanup)._

## ▶️ Pick up here (next session)

### 1. Build Phase 4 — the cockpit web panel (IN PROGRESS)
Data foundation is DONE: 908 tracks, 6 genres, 781 analyzed (86%), curator signal, and the
`steer()` fader engine. Build order (decided): backend server → cockpit HTML → Serato auto.
- [ ] Backend: stdlib `http.server` exposing JSON API (next / runway / steer) + static page,
      on localhost (laptop + phone on same wifi). Now-playing = MANUAL first.
- [ ] Cockpit HTML/CSS: spacecraft-cockpit look — dark space backdrop, neon blue/cyan glow +
      violet/purple accents, panels as glowing instrument readouts, fader = throttle. v1 =
      steady star drift (looking out the window into deep space); warp-on-climb = fast-follow.
      3 modes: next / next-3 / steering fader. See [[djbot-ui-vision]] memory.
- [ ] Serato now-playing auto-detect (follow-up).

### 2. Tune the steering + calibrate weights to Simon's ear
- [ ] `steer()` climb/hold work; descend + cross-genre drift need tuning (harmonic weight is
      dominant so paths stay in-key). Get 2–3 setlists Simon considers cleanly mixed; fit
      `recommender.Weights` (harmonic/bpm/energy/**curation**/**steer**) to his taste.
- [ ] Clean the ~5% BPM edge cases (e.g. one DnB at 86 = wrong preview match) during calibration.

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
  (BPM via beat_track, key via Krumhansl–Kessler chroma). `prov=audio`.
- **2026-06-08 session:** purged 16 Serato test tracks; ran `analyze`; fixed librosa
  octave/metric errors — `_normalize_tempo` (now genre-aware: dnb~174/goa~145/trance~138/
  house~125); shipped **curator boost** (`Weights.curation`=0.10). Wrote CLAUDE.md.
- **Diversified the pool:** seeded 17 artists (prog-trance / liquid dnb / goa) → **908 tracks,
  6+ genres**, 781 analyzed (86%), per-genre BPM averages correct.
- **Steering fader engine:** `recommender.steer()` + `score_steered`/`_progress_score` — smooth
  multi-track hold/climb/cool path; climb drifts genres (house→goa) on the full pool.
- **Phase 4 v1 cockpit:** `djbot/server.py` (stdlib http.server + JSON API) + `djbot/web/index.html`
  (spacecraft flight-deck UI, starfield, neon-blue/violet, 3 modes). `python3 -m djbot.server`
  → localhost:8765. Project skill `.claude/skills/run-cockpit` added.
- Backups: `data/catalog.db.{bak,preBPMfix}`. Detector-upgrade options noted in memory.
