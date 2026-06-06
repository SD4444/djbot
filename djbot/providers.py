"""HTTP clients for free enrichment sources (stdlib only).

  - DiscogsClient:    genre/sub-genre (styles), label, year, and artist discography
  - GetSongBPMClient: BPM and musical key

Both are best-effort and defensive: network/parse errors return None rather than
raising, so enrichment degrades gracefully. Response shapes are documented inline
and may need a small tweak after the first live call (noted where uncertain).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

USER_AGENT = "djbot/0.1 (+https://github.com/local/djbot)"


class RateLimiter:
    """Spaces calls out to stay within a per-minute budget."""

    def __init__(self, per_minute: int):
        self.min_interval = 60.0 / max(per_minute, 1)
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


def _get_json(url: str, headers: dict, timeout: float = 15.0) -> Optional[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        return None


class DiscogsClient:
    BASE = "https://api.discogs.com"

    def __init__(self, token: str, per_minute: int = 55):
        self.token = token
        self.rl = RateLimiter(per_minute)

    def _headers(self) -> dict:
        return {"Authorization": f"Discogs token={self.token}"}

    def _get(self, path: str, params: dict) -> Optional[dict]:
        self.rl.wait()
        url = f"{self.BASE}{path}?{urllib.parse.urlencode(params)}"
        return _get_json(url, self._headers())

    def search_release(self, artist: str, title: str) -> Optional[dict]:
        """Best release match -> {styles, genres, label, year}."""
        data = self._get("/database/search", {
            "artist": artist, "track": title, "type": "release", "per_page": 5,
        })
        if not data:
            return None
        for r in data.get("results", []):
            if r.get("style") or r.get("genre"):
                labels = r.get("label") or []
                return {
                    "styles": r.get("style", []),
                    "genres": r.get("genre", []),
                    "label": labels[0] if labels else None,
                    "year": _to_int(r.get("year")),
                }
        return None

    def artist_id(self, name: str) -> Optional[int]:
        data = self._get("/database/search", {
            "q": name, "type": "artist", "per_page": 1,
        })
        results = (data or {}).get("results", [])
        return results[0].get("id") if results else None

    def artist_release_ids(self, name: str, max_releases: int = 10) -> List[int]:
        """Main-role release ids for an artist (bounded)."""
        aid = self.artist_id(name)
        if aid is None:
            return []
        data = self._get(f"/artists/{aid}/releases", {
            "sort": "year", "sort_order": "desc", "per_page": max_releases,
        })
        ids = []
        for r in (data or {}).get("releases", []):
            if r.get("role") == "Main" and r.get("type") == "release":
                ids.append(r["id"])
        return ids[:max_releases]

    def release(self, release_id: int) -> Optional[dict]:
        """A release -> {styles, genres, label, year, tracks:[title,...]}."""
        data = self._get(f"/releases/{release_id}", {})
        if not data:
            return None
        labels = data.get("labels") or []
        tracks = [t.get("title") for t in data.get("tracklist", [])
                  if t.get("title") and t.get("type_") == "track"]
        return {
            "styles": data.get("styles", []),
            "genres": data.get("genres", []),
            "label": labels[0].get("name") if labels else None,
            "year": _to_int(data.get("year")),
            "artist": (data.get("artists") or [{}])[0].get("name", ""),
            "tracks": tracks,
        }


class GetSongBPMClient:
    BASE = "https://api.getsongbpm.com"

    def __init__(self, api_key: str, per_minute: int = 120):
        self.api_key = api_key
        self.rl = RateLimiter(per_minute)

    def lookup(self, artist: str, title: str) -> Optional[dict]:
        """Search by song+artist -> {bpm, key_raw}. None if not found."""
        self.rl.wait()
        lookup = f"song:{title} artist:{artist}"
        url = (f"{self.BASE}/search/?api_key={urllib.parse.quote(self.api_key)}"
               f"&type=song&lookup={urllib.parse.quote(lookup)}")
        data = _get_json(url, {})
        if not data:
            return None
        search = data.get("search")
        if not isinstance(search, list) or not search:
            return None
        hit = search[0]
        bpm = _to_float(hit.get("tempo"))
        # GetSongBPM exposes key as e.g. "key_of": "Dm" (field name may vary).
        key_raw = hit.get("key_of") or (hit.get("key") if isinstance(hit.get("key"), str) else None)
        if bpm is None and not key_raw:
            return None
        return {"bpm": bpm, "key_raw": key_raw}


def _to_int(v) -> Optional[int]:
    try:
        return int(str(v)[:4])
    except (TypeError, ValueError):
        return None


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
