"""Phase 4 backend: a tiny local web server for the live cockpit panel.

Stdlib-only (`http.server`) on purpose — it just wraps the existing recommender
and catalog behind a small JSON API and serves the static cockpit page. Runs on
localhost so the laptop and a phone on the same wifi can both reach it.

    python3 -m djbot.server            # serve ./data/catalog.db on :8765
    python3 -m djbot.server --port 9000 --db path/to/catalog.db

API (all GET, JSON out):
    /api/state                      -> catalog summary (counts, genres)
    /api/search?q=…                 -> tracks matching a query (now-playing picker)
    /api/next?id=…&dir=any          -> ranked next tracks (mode 1)
    /api/runway?id=…&depth=3        -> a flowing N-track runway (mode 2)
    /api/steer?id=…&intensity=0.5   -> a steered path; intensity -1..1 (mode 3, the fader)
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .catalog import DEFAULT_DB_PATH, Catalog
from .models import Track
from . import recommender as rec

_WEB_DIR = Path(__file__).parent / "web"


def _track_json(t: Track) -> dict:
    return {
        "id": t.id,
        "artist": t.artist,
        "title": t.title,
        "bpm": round(t.bpm, 1) if t.bpm else None,
        "camelot": t.camelot,
        "key_raw": t.key_raw,
        "genre": t.genre,
        "energy": t.energy,
        "curators": t.curators or [],
        "tidal_id": t.tidal_id,
    }


def _sugg_json(s: rec.Suggestion) -> dict:
    return {**_track_json(s.track), "score": s.score, "reasons": s.reasons}


class _Panel:
    """Holds the in-memory pool so each request is a fast read."""

    def __init__(self, db_path: str):
        with Catalog(db_path) as cat:
            self.pool = cat.all_tracks()
        self.by_id = {t.id: t for t in self.pool}
        # Pool usable for mixing = tracks we can actually beatmatch/key-match.
        self.mixable = [t for t in self.pool if t.bpm and t.camelot]

    def find(self, query: str) -> Track | None:
        if query in self.by_id:
            return self.by_id[query]
        q = query.lower()
        hits = [t for t in self.pool if q in f"{t.artist} {t.title}".lower()]
        return hits[0] if hits else None

    def state(self) -> dict:
        genres: dict[str, int] = {}
        for t in self.pool:
            genres[t.genre or "—"] = genres.get(t.genre or "—", 0) + 1
        return {
            "total": len(self.pool),
            "mixable": len(self.mixable),
            "genres": dict(sorted(genres.items(), key=lambda kv: -kv[1])),
        }

    def search(self, query: str, limit: int = 20) -> list[dict]:
        q = query.lower().strip()
        if not q:
            return []
        hits = [t for t in self.pool if q in f"{t.artist} {t.title}".lower()]
        hits.sort(key=lambda t: (t.bpm is None, t.artist.lower()))
        return [_track_json(t) for t in hits[:limit]]


class _Handler(BaseHTTPRequestHandler):
    panel: _Panel = None  # set on the server instance below

    def log_message(self, *a):  # quiet by default
        pass

    def _send(self, obj, status=200, ctype="application/json"):
        body = (obj if isinstance(obj, bytes)
                else json.dumps(obj).encode("utf-8"))
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _seed(self, qs) -> Track | None:
        sid = (qs.get("id") or [""])[0]
        return self.panel.find(sid) if sid else None

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        path = u.path

        if path in ("/", "/index.html"):
            f = _WEB_DIR / "index.html"
            return self._send(f.read_bytes(), ctype="text/html; charset=utf-8")

        if path == "/api/state":
            return self._send(self.panel.state())

        if path == "/api/search":
            return self._send(self.panel.search((qs.get("q") or [""])[0]))

        seed = self._seed(qs)
        if path.startswith("/api/") and seed is None:
            return self._send({"error": "track not found"}, status=404)

        if path == "/api/next":
            direction = (qs.get("dir") or ["any"])[0]
            sug = rec.recommend_next(
                seed, self.panel.mixable, direction=direction, limit=10
            )
            return self._send({"now": _track_json(seed),
                               "suggestions": [_sugg_json(s) for s in sug]})

        if path == "/api/runway":
            depth = int((qs.get("depth") or ["3"])[0])
            path_ = rec.build_runway(seed, self.panel.mixable, depth=depth)
            return self._send({"now": _track_json(seed),
                               "path": [_sugg_json(s) for s in path_]})

        if path == "/api/steer":
            intensity = float((qs.get("intensity") or ["0"])[0])
            depth = int((qs.get("depth") or ["5"])[0])
            path_ = rec.steer(seed, self.panel.mixable, intensity, depth=depth)
            return self._send({"now": _track_json(seed),
                               "intensity": intensity,
                               "path": [_sugg_json(s) for s in path_]})

        return self._send({"error": "not found"}, status=404)


def serve(db_path: str = DEFAULT_DB_PATH, port: int = 8765) -> None:
    _Handler.panel = _Panel(db_path)
    st = _Handler.panel.state()
    httpd = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    print(f"djbot cockpit on http://localhost:{port}")
    print(f"  pool: {st['total']} tracks ({st['mixable']} mixable). "
          f"Open it on this Mac or a phone on the same wifi.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
        httpd.shutdown()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="djbot.server")
    ap.add_argument("--db", default=DEFAULT_DB_PATH)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    serve(args.db, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
