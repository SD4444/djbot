---
name: run-cockpit
description: Launch the djbot Phase 4 cockpit web panel (the live "play next" UI) so the user can open it in a browser. Use when asked to run, start, launch, open, or screenshot the djbot app / cockpit / flight deck / web panel / live panel, or to confirm a UI change works in the real app.
---

# Run the djbot cockpit

The cockpit is a stdlib-only local web server (`djbot/server.py`) that serves the
flight-deck UI (`djbot/web/index.html`) and a JSON API wrapping the recommender +
catalog. It reads `data/catalog.db`.

## Launch it
Run from the project root, in the background (it runs until stopped).
**Launch from the venv** so the live **enrich-on-add** (Vibe+Mix discoveries → librosa
BPM/key) works — system python serves fine but enrich will report "analysis offline":

```bash
PATH=/opt/homebrew/bin:$PATH .venv/bin/python -m djbot.server   # serves http://localhost:8765
# (plain `python3 -m djbot.server` also works, minus enrich-on-add)
# options: --port 9000   --db path/to/catalog.db
```

Then tell the user to open **http://localhost:8765** (works on this Mac, or a
phone on the same wifi). Default port is 8765.

## Verify it's up
After launching, confirm the API responds before telling the user it's ready:

```bash
curl -s http://localhost:8765/api/state            # -> {"total":…,"mixable":…,"genres":{…}}
curl -s "http://localhost:8765/api/search?q=cattaneo"   # -> matching tracks (for now-playing)
```

To smoke-test the steering fader end to end, grab an id from search and call steer
(intensity -1..1); at +1 from a ~125 house seed the path should climb in BPM and
drift toward faster genres (trance/goa):

```bash
curl -s "http://localhost:8765/api/steer?id=<urlencoded-id>&intensity=1"
```

## Notes
- If port 8765 is taken, use `--port`.
- The pool is loaded into memory at startup, so after re-running `analyze`/`seed`
  you must restart the server to pick up catalog changes.
- This is a local dev server (`http.server`) — fine for Simon's laptop+phone on a
  trusted LAN; not hardened for public exposure.
