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
        &universe=1                 -> steer THROUGH SOUND: candidates from the whole
                                       cosine universe (the seed's sonic neighbourhood),
                                       not just the local pool; returns `pending` tracks
                                       awaiting a read + universe meta
    /api/harvest?id=…&n=6           -> pre-enrich (BPM/key/TIDAL) the top-N not-yet-mixable
                                       tracks in the seed's sonic neighbourhood so the next
                                       universe-steer can plan through them (progressive fill)
"""

from __future__ import annotations

import argparse
import datetime
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .catalog import DEFAULT_DB_PATH, Catalog
from .models import Track, make_id
from . import recommender as rec
from . import cosine
from . import tidal
from . import audio
from . import enrichment
from . import providers
from . import config

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
        self.db_path = db_path
        with Catalog(db_path) as cat:
            self.pool = cat.all_tracks()
        self.by_id = {t.id: t for t in self.pool}
        # Pool usable for mixing = tracks we can actually beatmatch/key-match.
        self.mixable = [t for t in self.pool if t.bpm and t.camelot]
        # Serialises catalog writes + pool swaps across enrich/harvest threads.
        self._enrich_lock = threading.Lock()

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

    # ---- travel logs (mixed-set history) ----
    def _sessions_path(self) -> Path:
        return Path(self.db_path).parent / "sessions.json"

    def _load_sessions(self) -> dict:
        try:
            return json.loads(self._sessions_path().read_text())
        except (OSError, json.JSONDecodeError):
            return {"current": None, "sessions": []}

    def _save_sessions(self, data: dict) -> None:
        try:
            p = self._sessions_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data))
        except OSError:
            pass

    def log_track(self, t: dict) -> dict:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        data = self._load_sessions()
        sess = next((s for s in data["sessions"] if s["id"] == data.get("current")), None)
        if sess is None:
            sess = {"id": "S" + str(int(time.time())), "started": now, "tracks": []}
            data["sessions"].append(sess)
            data["current"] = sess["id"]
        # don't double-log the same track back-to-back
        if not (sess["tracks"] and sess["tracks"][-1].get("id") == t.get("id")):
            sess["tracks"].append({**t, "at": now})
            sess["updated"] = now
            self._save_sessions(data)
        return {"ok": True, "session": sess["id"], "count": len(sess["tracks"])}

    def session_new(self) -> dict:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        data = self._load_sessions()
        sess = {"id": "S" + str(int(time.time())), "started": now, "tracks": []}
        data["sessions"].append(sess)
        data["current"] = sess["id"]
        self._save_sessions(data)
        return {"ok": True, "session": sess["id"]}

    def sessions_list(self) -> list[dict]:
        data = self._load_sessions()
        out = []
        for s in reversed(data["sessions"]):
            tr = s.get("tracks", [])
            if not tr:
                continue
            out.append({"id": s["id"], "started": s.get("started"), "count": len(tr),
                        "first": f'{tr[0]["artist"]} — {tr[0]["title"]}',
                        "last": f'{tr[-1]["artist"]} — {tr[-1]["title"]}',
                        "current": s["id"] == data.get("current")})
        return out

    def session_get(self, sid: str) -> dict:
        data = self._load_sessions()
        return next((s for s in data["sessions"] if s["id"] == sid), {"error": "not found"})

    def _mixable_track(self, track_id: str) -> Track | None:
        """The pool track for `track_id` if it's mixable (has bpm+key), else None."""
        t = self.by_id.get(track_id)
        return t if (t and t.bpm and t.camelot) else None

    # ---- enrich-on-add (read a discovery's DNA, grow the pool) ----
    def ensure_enriched(self, artist: str, title: str) -> dict:
        """Read a discovery's DNA (TIDAL availability + Discogs genre + librosa
        BPM/key), upsert it into the catalog, and refresh the in-memory pool.

        Returns the merged track as JSON plus enrichment flags. Serialised by
        `_enrich_lock` so concurrent harvest workers don't race on the SQLite
        write or the in-memory pool swap.
        """
        if not artist or not title:
            return {"error": "artist & title required"}
        existing = self._mixable_track(make_id(artist, title))
        if existing is not None:
            out = _track_json(existing)
            out.update({"enriched": True, "analysed": True,
                        "tidal_available": bool(existing.tidal_id)})
            return out

        base = Track(artist=artist, title=title)
        deltas: list[Track] = [base]

        # genre (best-effort Discogs) — also helps audio's tempo-fold
        dtok = config.get_key("discogs_token")
        if dtok:
            try:
                deltas += enrichment.enrich_track(base, discogs=providers.DiscogsClient(dtok))
            except Exception:
                pass
        genre = next((d.genre for d in deltas if d.genre), None)
        if genre:
            base.genre = genre

        # BPM/key (librosa over a free preview) — needs the venv. This is the
        # slow part; we run it OUTSIDE the lock so harvests can analyse in
        # parallel, then serialise only the catalog write + pool swap below.
        analysed = False
        ok, _why = audio.available()
        if ok:
            try:
                ad = enrichment.analyze_track(base)
                if ad:
                    deltas.append(ad)
                    analysed = True
            except Exception:
                pass

        # TIDAL availability + id
        tinfo = None
        try:
            tinfo = tidal.find(artist, title)
        except Exception:
            tinfo = None
        if tinfo and tinfo.get("tidal_id"):
            deltas.append(Track(id=base.id, artist=artist, title=title,
                                tidal_id=str(tinfo["tidal_id"])))

        with self._enrich_lock:
            with Catalog(self.db_path) as cat:
                cat.upsert(deltas)
                merged = cat.get(base.id)
            # refresh the live pool so it's immediately mixable/searchable
            self.pool = [t for t in self.pool if t.id != merged.id] + [merged]
            self.by_id[merged.id] = merged
            self.mixable = [t for t in self.pool if t.bpm and t.camelot]

        out = _track_json(merged)
        out.update({
            "enriched": bool(merged.camelot and merged.bpm),
            "analysed": analysed,
            "audio_available": ok,
            "tidal_available": bool(tinfo),
        })
        return out

    # ---- steer-through-sound: plan a path across the cosine universe ----
    def _neighbourhood(self, seed: Track, *, hops=2, breadth=18, cap=80) -> list[dict]:
        try:
            return cosine.neighbourhood(seed.artist, seed.title,
                                        hops=hops, breadth=breadth, cap=cap)
        except cosine.CosineError:
            raise
        except Exception:
            return []

    def steer_universe(self, seed: Track, intensity: float, *, depth: int = 5,
                       weights: rec.Weights = rec.Weights()) -> dict:
        """Steer a path whose candidates come from the whole cosine universe.

        The seed's sonic neighbourhood (harvested across hops) supplies the
        candidate pool *and* the sonic scores. Only tracks already enriched
        (bpm+key, hence mixable) can be planned through now; the rest are
        returned as `pending` for an explicit `/api/harvest` pre-enrich pass.
        We top up thin candidate sets from the local mixable pool (sonic-
        neighbours first) so the fader always returns a full-depth path.
        """
        # One pass over the neighbourhood: collect sonic scores, the tracks
        # already mixable (candidates), and the rest (pending an enrich pass).
        nb = self._neighbourhood(seed)
        sonic: dict[str, float] = {}
        nb_mixable: list[Track] = []
        pending: list[dict] = []
        for c in nb:
            cid = make_id(c["artist"], c["title"])
            sc = c.get("score")
            if isinstance(sc, (int, float)):
                sonic[cid] = round(float(sc), 4)
            m = self._mixable_track(cid)
            if m is not None:
                nb_mixable.append(m)
            else:
                pending.append({"artist": c["artist"], "title": c["title"],
                                "score": c.get("score"), "url": c.get("url")})

        # Candidate pool: universe-enriched first, then top up from the local
        # mixable pool (sonic neighbours ahead of the rest) so steer has room.
        seen = {seed.id} | {t.id for t in nb_mixable}
        topup = sorted(
            (t for t in self.mixable if t.id not in seen),
            key=lambda t: sonic.get(t.id, 0.0), reverse=True,
        )
        candidates = nb_mixable + topup

        path = rec.steer(seed, candidates, intensity, depth=depth,
                         weights=weights, sonic_scores=sonic)
        return {
            "now": _track_json(seed),
            "intensity": intensity,
            "universe": True,
            "path": [_sugg_json(s) for s in path],
            "pending": pending[:12],
            "meta": {"neighbourhood": len(nb), "universe_mixable": len(nb_mixable),
                     "pending": len(pending)},
        }

    def harvest(self, seed: Track, n: int = 6, budget: float = 90.0) -> dict:
        """Pre-enrich the top-N not-yet-mixable tracks in the seed's sonic
        neighbourhood so the next universe-steer can plan through them.

        Bounded by `n` and a wall-clock `budget`; enrichment is the slow part
        (librosa over a preview), so this is the explicit "progressive fill"
        step the UI fires behind a spinner. Returns per-track outcomes.
        """
        nb = self._neighbourhood(seed)
        todo = [c for c in nb
                if self._mixable_track(make_id(c["artist"], c["title"])) is None][:n]
        results, gained, started = [], 0, time.time()
        for c in todo:
            if time.time() - started > budget:
                break
            r = self.ensure_enriched(c["artist"], c["title"])
            ok = bool(r.get("enriched"))
            gained += ok
            results.append({"artist": c["artist"], "title": c["title"],
                            "enriched": ok, "bpm": r.get("bpm"),
                            "camelot": r.get("camelot"),
                            "tidal": bool(r.get("tidal_available"))})
        return {"now": _track_json(seed), "harvested": len(results),
                "gained": gained, "results": results}


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

    def _sonic_scores(self, seed: Track) -> dict:
        """{catalog_id: cosine_similarity} for the seed's sonic neighbours.

        Lets the recommender reward pool tracks that also *sound* like the seed
        (cosine.club). Best-effort + cached (cosine caches on disk), so a cosine
        outage just drops the sonic term rather than breaking suggestions.
        """
        try:
            cands = cosine.similar_for(seed.artist, seed.title, limit=60)
        except Exception:
            return {}
        out: dict = {}
        for c in cands:
            sc = c.get("score")
            if isinstance(sc, (int, float)):
                out[make_id(c["artist"], c["title"])] = round(float(sc), 4)
        return out

    def _enrich(self, artist: str, title: str) -> dict:
        return self.panel.ensure_enriched(artist, title)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        path = u.path

        if path in ("/", "/index.html"):
            f = _WEB_DIR / "index.html"
            return self._send(f.read_bytes(), ctype="text/html; charset=utf-8")

        if path in ("/console", "/console.html"):
            f = _WEB_DIR / "console.html"
            return self._send(f.read_bytes(), ctype="text/html; charset=utf-8")

        if path.startswith("/assets/"):
            f = (_WEB_DIR / path.lstrip("/")).resolve()
            assets = (_WEB_DIR / "assets").resolve()
            if assets in f.parents and f.is_file():
                ext = f.suffix.lower()
                ct = {".png": "image/png", ".jpg": "image/jpeg",
                      ".jpeg": "image/jpeg", ".webp": "image/webp",
                      ".svg": "image/svg+xml"}.get(ext, "application/octet-stream")
                return self._send(f.read_bytes(), ctype=ct)
            return self._send({"error": "not found"}, status=404)

        if path == "/api/state":
            return self._send(self.panel.state())

        if path == "/api/search":
            return self._send(self.panel.search((qs.get("q") or [""])[0]))

        if path == "/api/enrich":
            return self._send(self._enrich((qs.get("artist") or [""])[0],
                                           (qs.get("title") or [""])[0]))

        if path == "/api/log":
            a = (qs.get("artist") or [""])[0]
            if not a:
                return self._send({"error": "artist required"}, status=400)
            ti = (qs.get("title") or [""])[0]
            return self._send(self.panel.log_track({
                "id": make_id(a, ti), "artist": a, "title": ti,
                "camelot": (qs.get("camelot") or [None])[0],
                "bpm": (qs.get("bpm") or [None])[0],
                "genre": (qs.get("genre") or [None])[0]}))

        if path == "/api/tidal":
            a = (qs.get("artist") or [""])[0]
            t = (qs.get("title") or [""])[0]
            if not a:
                return self._send({"error": "artist required"}, status=400)
            try:
                info = tidal.find(a, t)
            except Exception:
                info = None
            return self._send({"available": bool(info),
                               "tidal_id": (info or {}).get("tidal_id")})

        if path == "/api/sessions":
            return self._send(self.panel.sessions_list())
        if path == "/api/session":
            return self._send(self.panel.session_get((qs.get("sid") or [""])[0]))
        if path == "/api/session/new":
            return self._send(self.panel.session_new())

        seed = self._seed(qs)
        if path.startswith("/api/") and seed is None:
            return self._send({"error": "track not found"}, status=404)

        if path == "/api/next":
            direction = (qs.get("dir") or ["any"])[0]
            sug = rec.recommend_next(
                seed, self.panel.mixable, direction=direction, limit=10,
                sonic_scores=self._sonic_scores(seed),
            )
            return self._send({"now": _track_json(seed),
                               "suggestions": [_sugg_json(s) for s in sug]})

        if path == "/api/runway":
            depth = int((qs.get("depth") or ["3"])[0])
            path_ = rec.build_runway(seed, self.panel.mixable, depth=depth,
                                     sonic_scores=self._sonic_scores(seed))
            return self._send({"now": _track_json(seed),
                               "path": [_sugg_json(s) for s in path_]})

        if path == "/api/steer":
            intensity = float((qs.get("intensity") or ["0"])[0])
            depth = int((qs.get("depth") or ["5"])[0])
            universe = (qs.get("universe") or ["0"])[0] not in ("0", "", "false")
            if universe:
                try:
                    return self._send(self.panel.steer_universe(
                        seed, intensity, depth=depth))
                except cosine.CosineError as e:
                    return self._send({"now": _track_json(seed), "error": str(e),
                                       "path": []})
            path_ = rec.steer(seed, self.panel.mixable, intensity, depth=depth,
                              sonic_scores=self._sonic_scores(seed))
            return self._send({"now": _track_json(seed),
                               "intensity": intensity,
                               "path": [_sugg_json(s) for s in path_]})

        if path == "/api/harvest":
            n = int((qs.get("n") or ["6"])[0])
            try:
                return self._send(self.panel.harvest(seed, n=n))
            except cosine.CosineError as e:
                return self._send({"now": _track_json(seed), "error": str(e),
                                   "harvested": 0, "gained": 0, "results": []})

        if path == "/api/vibe":
            # cosine.club audio-similarity over the whole ~1.9M universe.
            limit = int((qs.get("limit") or ["18"])[0])
            depth = int((qs.get("depth") or ["1"])[0])
            no_match = "no cosine match (track not in the underground DB)"

            def to_item(c):
                it = {"artist": c["artist"], "title": c["title"],
                      "score": c["score"], "url": c.get("url"), "in_pool": False}
                hit = self.panel.by_id.get(make_id(c["artist"], c["title"]))
                if hit is not None:
                    it.update({"id": hit.id, "in_pool": True, "camelot": hit.camelot,
                               "bpm": round(hit.bpm, 1) if hit.bpm else None,
                               "genre": hit.genre})
                return it

            try:
                if depth > 1:
                    # chain similar->similar for a "sonic journey" runway
                    items, used = [], {make_id(seed.artist, seed.title)}
                    cur = (seed.artist, seed.title)
                    for _ in range(depth):
                        chain = cosine.similar_for(cur[0], cur[1], limit=12)
                        nxt = next((c for c in chain
                                    if make_id(c["artist"], c["title"]) not in used), None)
                        if nxt is None:
                            break
                        used.add(make_id(nxt["artist"], nxt["title"]))
                        items.append(to_item(nxt))
                        cur = (nxt["artist"], nxt["title"])
                    return self._send({"now": _track_json(seed), "runway": True,
                                       "items": items,
                                       **({} if items else {"error": no_match})})
                cands = cosine.similar_for(seed.artist, seed.title, limit=limit)
                if not cands:
                    return self._send({"now": _track_json(seed), "items": [], "error": no_match})
                return self._send({"now": _track_json(seed),
                                   "items": [to_item(c) for c in cands]})
            except cosine.CosineError as e:
                return self._send({"now": _track_json(seed), "error": str(e), "items": []})

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
