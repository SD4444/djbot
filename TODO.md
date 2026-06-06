# djbot — TODO / where we left off

_Last session: 2026-06-06. Phases 1, 2, and the Phase 3 enrichment backbone are done._

## ▶️ Pick up here (next session)

### 1. Go live with enrichment (needs Simon — 5 min)
- [ ] Get a free **Discogs personal token**: https://www.discogs.com/settings/developers
- [ ] Get a free **GetSongBPM API key**: https://getsongbpm.com/api
- [ ] Save them:
      ```
      python3 -m djbot config set discogs_token <TOKEN>
      python3 -m djbot config set getsongbpm_key <KEY>
      ```
- [ ] First live run + sanity check coverage:
      ```
      python3 -m djbot seed "John Digweed" "Patrice Bäumel"
      python3 -m djbot enrich
      python3 -m djbot list
      ```

### 2. Validate the two unverified bits (do on first live run)
- [ ] Confirm **GetSongBPM response fields** (`tempo`, `key_of`) match `providers.py:GetSongBPMClient.lookup` — tweak if the live JSON differs.
- [ ] Eyeball **Discogs match quality** on niche tracks — note miss rate (drives Phase 3b).

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
  `enrich`, `seed`, `config` commands. Logic verified offline (not yet run live).
