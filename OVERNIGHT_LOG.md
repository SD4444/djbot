# Overnight worklog — 2026‑06‑09 (evening → night)

Autonomous session while you slept. Everything below is **committed + pushed to
`origin/main`**. Each feature is its own commit so you can roll back to whatever
point you like: `git reset --hard <hash>` (then `git push --force` if you want it
remote too). Newest first.

## Commits this session (rollback points)

| hash | what it added | roll back *to* this to keep it / *past* it to drop it |
|------|---------------|--------------------------------------------------------|
| `5f550c0` | **TIDAL flag on Vibe discoveries + "TIDAL ALL/ONLY" filter** (topbar toggle hides non‑playable) | keep TIDAL filter |
| `f34e030` | **Sonic weight** — cosine.club similarity blended into Next/Next 3/Steer ranking (adds "~ sounds alike N%" reason; `Weights.sonic=0.20`) | keep sonic ranking |
| `e70a538` | **TIDAL "✓ playable" flag** on engine suggestions + cached `/api/tidal` endpoint | keep TIDAL flags |
| `43e34b6` | **The big one** — cosine.club discovery (Vibe / Vibe+Mix + Next‑3 sonic runway), enrich‑on‑add (TIDAL avail + librosa BPM/key + Discogs genre), TIDAL client, Travel Logs, Set Path queue, full UI overhaul (vector HUD, cyan/violet palette, cosmos bg) | the state right before tonight's polish |
| `f948e71` | (prior) docs to Phase 4 | pre‑cosine baseline |

➡️ **If you like things as they are now, do nothing** — `main` is at the top commit.
➡️ **If something tonight feels off**, `git reset --hard 43e34b6` rewinds to just the
big Phase‑4 push (drops sonic weight + TIDAL flags/filter but keeps cosine/enrich/logs/queue).

## What's live
- **Flight deck (the real app):** `http://localhost:8765/` — run `PATH=/opt/homebrew/bin:$PATH .venv/bin/python -m djbot.server` (venv needed for enrich‑on‑add).
- **Synthwave/outrun console (side project, local‑only, gitignored):** `http://localhost:8765/console`.

## Done tonight
- Sonic weight wired through the whole recommender (Next / Next 3 / Steer) — best‑effort + cached, never breaks suggestions if cosine is down.
- TIDAL "✓ playable / no TIDAL" chips on **both** engine suggestions and Vibe discoveries (lazy, cached, title‑confidence‑checked so it doesn't false‑positive).
- "TIDAL ONLY" filter to hide tracks you can't play.

## NOT done — needs you / deliberate work (left alone on purpose)
- **Steer‑through‑sound (universe‑scale):** the fader plans a path across the whole 1.9M cosine universe (not just your 908 pool). Needs the live‑enrich latency design — too risky to build untested overnight. *Partially* there already: the sonic weight nudges the steered path toward sonically‑similar pool tracks.
- **Serato now‑playing auto‑detect:** can only be built+tested on your machine with Serato running (binary `.session` history format). Skipped to avoid shipping untested code.
- **Calibrate `recommender.Weights` to your ear:** needs 2–3 setlists you consider cleanly mixed.
- **Rotate the cosine + TIDAL keys** (they were pasted in chat).
