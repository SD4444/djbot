"""Own audio analysis — the niche-proof BPM/key backbone (Phase 3b).

For any track we can't get from Serato, we fetch a free 30s preview clip and
estimate BPM + musical key locally with librosa. Previews come from public,
no-auth APIs (Apple iTunes Search, then Deezer as fallback) — stable, legal, and
free, unlike scraping YouTube (PO-token walls) or GetSongBPM (Cloudflare-walled).

Only librosa is a heavy/optional dep (lazy-imported); preview lookup + download
use the stdlib. `available()` reports whether analysis can run. Decoding the
preview (AAC/m4a) needs ffmpeg on PATH.
"""

from __future__ import annotations

import difflib
import json
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

_UA = "djbot/0.1 (+https://github.com/SD4444/djbot)"
_TIMEOUT = 25

# Krumhansl–Kessler key profiles: perceived stability of each scale degree.
# We correlate a track's average chroma against all 24 rotations to pick a key.
_KK_MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_KK_MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
# Pitch-class index -> note name (sharps; all map cleanly in camelot.to_camelot).
_NOTES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def available() -> tuple[bool, str]:
    """(True, "") if librosa imports; else (False, reason)."""
    try:
        __import__("librosa")
    except ImportError:
        return False, "missing: librosa"
    return True, ""


def _http_json(url: str) -> Optional[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.load(r)
    except Exception:
        return None


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_preview_url(artist: str, title: str) -> Optional[str]:
    """Best free 30s-preview URL for artist/title: iTunes first, then Deezer.

    Each candidate is scored by fuzzy similarity to "artist title" so we don't
    grab a wrong remix/cover; below a floor we treat it as no match.
    """
    want = f"{artist} {title}"

    def best(cands) -> tuple[float, Optional[str]]:
        scored = [(_similarity(want, lbl), url) for lbl, url in cands if url]
        return max(scored, default=(0.0, None))

    # iTunes Search API
    iq = urllib.parse.urlencode({"term": want, "entity": "song", "limit": 5})
    data = _http_json(f"https://itunes.apple.com/search?{iq}")
    cands = [(f"{r.get('artistName','')} {r.get('trackName','')}", r.get("previewUrl"))
             for r in (data or {}).get("results", [])]
    score, url = best(cands)
    if url and score >= 0.5:
        return url

    # Deezer fallback
    dq = urllib.parse.urlencode({"q": want, "limit": 5})
    data = _http_json(f"https://api.deezer.com/search?{dq}")
    cands = [(f"{(r.get('artist') or {}).get('name','')} {r.get('title','')}",
              r.get("preview")) for r in (data or {}).get("data", [])]
    d_score, d_url = best(cands)
    if d_url and d_score >= 0.5:
        return d_url
    # Last resort: return the better of whatever we found, even if weak.
    return url or d_url


def _download(url: str, dest: Path) -> Optional[Path]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            dest.write_bytes(r.read())
    except Exception:
        return None
    return dest if dest.stat().st_size > 1024 else None


def analyze_file(path: Path) -> Optional[dict]:
    """Estimate {bpm, key_raw} from an audio file. None if it can't be read."""
    import librosa  # lazy
    import numpy as np

    try:
        y, sr = librosa.load(str(path), sr=22050, mono=True)
    except Exception:
        return None
    if y is None or len(y) < sr:  # < 1s of audio is unusable
        return None

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])
    key_raw = _estimate_key(y, sr)
    if bpm <= 0 and not key_raw:
        return None
    return {"bpm": round(bpm, 1) if bpm > 0 else None, "key_raw": key_raw}


def _estimate_key(y, sr) -> Optional[str]:
    """Krumhansl–Kessler key estimate from chroma -> "Am"/"C"-style string."""
    import librosa
    import numpy as np

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    profile = chroma.mean(axis=1)
    if not np.any(profile):
        return None

    maj, minr = np.array(_KK_MAJOR), np.array(_KK_MINOR)
    best_score, best = -2.0, None
    for tonic in range(12):
        rotated = np.roll(profile, -tonic)
        for prof, mode in ((maj, ""), (minr, "m")):
            score = float(np.corrcoef(rotated, prof)[0, 1])
            if score > best_score:
                best_score, best = score, (tonic, mode)
    if best is None:
        return None
    tonic, mode = best
    return _NOTES[tonic] + mode


def analyze_track_audio(artist: str, title: str) -> Optional[dict]:
    """End-to-end: find a preview for artist/title, download, analyse. None on fail."""
    url = find_preview_url(artist, title)
    if not url:
        return None
    with tempfile.TemporaryDirectory(prefix="djbot-audio-") as tmp:
        clip = _download(url, Path(tmp) / "preview.m4a")
        if clip is None:
            return None
        return analyze_file(clip)
