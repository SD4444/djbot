"""cosine.club client — audio-similarity discovery provider.

Wraps the free cosine.club API (https://cosine.club/api/v1): resolve a track to a
cosine id via ``/search``, then pull sonically-similar tracks via
``/tracks/{id}/similar``. Embeddings are Essentia's discogs-effnet model over a
~1.9M underground/electronic catalog (Discogs + Bandcamp + nina).

Search-first by design: ``/search`` hits pre-computed embeddings (cheap, fast). We
deliberately avoid ``/tracks/lookup`` here — it *downloads and analyses* the audio
through the owner's paid YouTube proxies (slow, can fail), so it's a future fallback,
not the default. Responses are cached on disk to respect the 120 req/min limit and to
be a good API citizen.

Auth: config key ``cosine_key`` (or env ``COSINE_API_KEY``). Free at
https://cosine.club/account/api
"""

from __future__ import annotations

import difflib
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from . import config
from .catalog import DEFAULT_DB_PATH

BASE = "https://cosine.club/api/v1"
USER_AGENT = "djbot/0.1 (personal DJ harmonic-mix tool)"
_CACHE_PATH = Path(DEFAULT_DB_PATH).parent / "cosine_cache.json"


class CosineError(RuntimeError):
    """Raised for auth/rate-limit problems the caller should surface."""


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


_cache = _load_cache()


def _save_cache() -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(_cache))
    except OSError:
        pass


def _get(path: str, params: dict) -> Optional[dict]:
    key = config.get_key("cosine_key")
    if not key:
        raise CosineError("no cosine_key configured — get one at cosine.club/account/api")
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise CosineError("cosine rate limit hit (120/min) — try again shortly")
        if e.code == 401:
            raise CosineError("cosine key rejected (401) — check or rotate the key")
        return None
    except (urllib.error.URLError, ValueError, OSError):
        return None


def _items(data: Optional[dict], *keys: str) -> list:
    """Pull the track list out of a {success, data, meta} envelope."""
    if not data:
        return []
    d = data.get("data", data)
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in keys:
            v = d.get(k)
            if isinstance(v, list):
                return v
    return []


def _norm(t: dict) -> dict:
    return {
        "cosine_id": str(t.get("id", "")),
        "artist": t.get("artist") or "",
        "title": t.get("track") or t.get("name") or "",
        "score": t.get("score"),
        "url": t.get("external_link") or t.get("video_uri"),
    }


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def search(query: str, limit: int = 5) -> list[dict]:
    ck = f"search:{query.lower()}:{limit}"
    if ck in _cache:
        return _cache[ck]
    out = [_norm(t) for t in _items(_get("/search", {"q": query, "limit": limit}),
                                    "tracks", "results")]
    _cache[ck] = out
    _save_cache()
    return out


def similar(cosine_id: str, limit: int = 20) -> list[dict]:
    ck = f"similar:{cosine_id}:{limit}"
    if ck in _cache:
        return _cache[ck]
    data = _get(f"/tracks/{urllib.parse.quote(str(cosine_id))}/similar", {"limit": limit})
    out = [_norm(t) for t in _items(data, "similar_tracks")]
    _cache[ck] = out
    _save_cache()
    return out


def resolve(artist: str, title: str, min_ratio: float = 0.6) -> Optional[dict]:
    """Best cosine match for a track via fuzzy artist+title over /search."""
    q = f"{artist} {title}".strip()
    best, best_r = None, min_ratio
    for c in search(q, limit=5):
        r = _ratio(f"{c['artist']} {c['title']}", q)
        if r >= best_r:
            best, best_r = c, r
    return best


def similar_for(artist: str, title: str, limit: int = 20) -> list[dict]:
    """Resolve a track then return its sonically-similar candidates (or [])."""
    m = resolve(artist, title)
    return similar(m["cosine_id"], limit=limit) if m else []
