# djbot — TODO / where we left off

_Last session: 2026‑06‑09. Phase 4 live + a big cosine/TIDAL/UX push. See
`OVERNIGHT_LOG.md` for the night's commit‑by‑commit log + rollback points._

## ▶️ Pick up here (next session)

### 1. Steer‑through‑sound (the deeper cosine integration)
The fader currently plans a path over your **908 pool** (now with a sonic nudge from
`Weights.sonic`). The big version: plan the path across the **whole 1.9M cosine universe** —
generate candidates from cosine, enrich them (BPM/key) on the fly, then steer. Blocker =
live‑enrich latency (a few seconds/track); needs a UX (progressive fill / pre‑enrich top‑N).
Best built interactively, not overnight.

### 2. Calibrate `recommender.Weights` to Simon's ear
Get 2–3 setlists Simon considers cleanly mixed; fit harmonic/bpm/energy/curation/steer/**sonic**
so scores match his taste. (Descend + cross‑genre drift in `steer()` still skews in‑key.)

### 3. Serato now‑playing auto‑detect (Bar A)
Read `~/Music/_Serato_/History/*.session`, fuzzy‑match the latest track to the catalog, auto‑set
the seed (AUTO ⟷ MANUAL toggle). Must be built **on Simon's machine** with Serato data — can't
test remotely.

### 4. TIDAL search bar (Bar B)
Type a track → live TIDAL catalog search → pick → enrich‑on‑select. Lets the seed come from the
whole TIDAL catalog, not just the local pool. (Official TIDAL API + `/api/enrich` already exist.)

## ✅ Done — Phase 4 + cosine/TIDAL/UX (2026‑06‑09)
- **Live cockpit web app** (`djbot/server.py` stdlib http.server + `djbot/web/index.html`):
  3 suggestion **sources** — My Engine (Next / Next 3 / Steer fader) · Vibe · Vibe+Mix — plus a
  **Set Path queue**, **Previous Travel Logs** (session history), search→now‑playing.
- **cosine.club integration** (`djbot/cosine.py`): audio‑similarity discovery over ~1.9M tracks;
  `/api/vibe` (+ Next‑3 "sonic journey" runway); `djbot vibe` CLI. Search‑first + disk‑cached.
- **Enrich‑on‑add** (`/api/enrich`): tap a NEW discovery → TIDAL availability + librosa BPM/key +
  Discogs genre → upsert to catalog → mixable + grows the pool. (Server must run from `.venv`.)
- **Sonic weight**: cosine similarity blended into Next/Next 3/Steer ranking (`Weights.sonic`).
- **TIDAL** (`djbot/tidal.py`, official Developer API): `find()` cached + confidence‑checked;
  **✓ playable** chips on suggestions + Vibe; **TIDAL ONLY** filter.
- **UI**: vector HUD (Camelot wheel, physics readouts), cyan/violet palette, animated cosmos bg,
  telemetry strip. Config holds `cosine_key` + `tidal_client_id/secret`.
- **Side project (local, not pushed):** synthwave/outrun re‑skin of the full tool at `/console`.

## ✅ Done — earlier (data backbone)
- Phase 1–3: Serato XML → catalog; recommender (Camelot+BPM half/double+energy+lookahead);
  canonical‑id dedup + provenance merge; Discogs (live) + curator signal; `enrich/seed/config`.
- **Phase 3b audio analysis** (`analyze`): iTunes/Deezer 30s previews + librosa BPM/key;
  genre‑aware tempo octave‑fold. Pool = **908 tracks, 6+ genres, ~86% analyzed**. Curator boost.
- GetSongBPM dead (Cloudflare); yt‑dlp dead (PO‑token wall) — iTunes/Deezer is the preview source.

## 🧠 Key decisions locked (don't re‑litigate)
- Free sources only. Recommender = music theory (Camelot/BPM/energy), NOT learned from playlists.
- Pool = a curated universe that GROWS (cosine discovery + enrich + TIDAL availability), not just
  prefilled folders. SQLite (`data/catalog.db`) is the brain.
- Simon spins deep/prog/tech house, trance, goa, dnb/liquid. Influences: Sasha, Digweed, Bäumel.
- Rotate the cosine + TIDAL API keys (pasted in chat) when convenient.
