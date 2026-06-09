"""TIDAL official Developer API — track availability + tidal_id lookup.

Answers "is this track on TIDAL?" (and gives its tidal_id) before we suggest or
analyse a discovery. OAuth2 client-credentials over the catalog/metadata API.

Creds: config ``tidal_client_id`` / ``tidal_client_secret`` (or env
TIDAL_CLIENT_ID / TIDAL_CLIENT_SECRET). Register an app at developer.tidal.com.
"""

from __future__ import annotations

import base64
import difflib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from . import config

_AUTH = "https://auth.tidal.com/v1/oauth2/token"
_API = "https://openapi.tidal.com/v2"
USER_AGENT = "djbot/0.1 (personal DJ tool)"
_tok = {"token": None, "exp": 0.0}


class TidalError(RuntimeError):
    pass


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _token() -> Optional[str]:
    now = time.time()
    if _tok["token"] and _tok["exp"] - 60 > now:
        return _tok["token"]
    cid = config.get_key("tidal_client_id")
    cs = config.get_key("tidal_client_secret")
    if not cid or not cs:
        return None
    basic = base64.b64encode(f"{cid}:{cs}".encode()).decode()
    req = urllib.request.Request(
        _AUTH,
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        headers={"Authorization": "Basic " + basic,
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        d = json.load(urllib.request.urlopen(req, timeout=20))
    except (urllib.error.URLError, ValueError, OSError):
        return None
    _tok["token"] = d.get("access_token")
    _tok["exp"] = now + float(d.get("expires_in", 3600))
    return _tok["token"]


_find_cache: dict = {}


def find(artist: str, title: str, country: str = "US") -> Optional[dict]:
    """Best TIDAL match for a track, or None if not found / no creds / no match.

    Cached in-process (token is valid ~4h and the catalog is stable). Returns
    ``{"tidal_id", "title"}``.
    """
    key = f"{artist}|{title}".lower().strip()
    if key in _find_cache:
        return _find_cache[key]
    result = _lookup(artist, title, country)
    _find_cache[key] = result
    return result


def _lookup(artist: str, title: str, country: str) -> Optional[dict]:
    tok = _token()
    if not tok:
        return None
    q = urllib.parse.quote(f"{artist} {title}")
    url = f"{_API}/searchResults/{q}?countryCode={country}&include=tracks"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + tok,
        "Accept": "application/vnd.api+json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
    except (urllib.error.URLError, ValueError, OSError):
        return None
    rel = (d.get("data", {}).get("relationships", {})
           .get("tracks", {}).get("data", []))
    if not rel:
        return None
    top_id = rel[0].get("id")
    inc_title = next(
        (i.get("attributes", {}).get("title")
         for i in d.get("included", [])
         if i.get("type") == "tracks" and i.get("id") == top_id),
        None,
    )
    # guard against TIDAL returning a loosely-related track for a track it lacks
    if inc_title and _ratio(inc_title, title) < 0.45:
        return None
    return {"tidal_id": top_id, "title": inc_title or title}
