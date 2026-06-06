"""Persistent track catalog backed by SQLite — the engine's source of truth.

One local file holds the whole growing universe. Every source (Serato, Discogs,
GetSongBPM, later our audio analysis) upserts into the same table keyed by the
canonical ``id``; `merge_tracks` decides field-by-field what wins so the catalog
only ever gets richer, never degraded by a weaker source.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional

from .models import SOURCE_PRIORITY, Track

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.db"

# Precision fields are merged by source priority; the rest by "last non-empty".
_PRECISION = ("bpm", "key_raw", "camelot", "energy", "loudness")
_AUTHORITATIVE = ("genre", "styles", "label", "year", "art_path", "tidal_id", "album")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id         TEXT PRIMARY KEY,
    tidal_id   TEXT,
    artist     TEXT,
    title      TEXT,
    album      TEXT,
    bpm        REAL,
    key_raw    TEXT,
    camelot    TEXT,
    loudness   REAL,
    energy     REAL,
    genre      TEXT,
    styles     TEXT,
    label      TEXT,
    year       INTEGER,
    play_count INTEGER,
    art_path   TEXT,
    sources    TEXT,
    prov       TEXT,
    extra      TEXT
);
CREATE INDEX IF NOT EXISTS idx_tracks_camelot ON tracks(camelot);
CREATE INDEX IF NOT EXISTS idx_tracks_bpm ON tracks(bpm);
CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);
"""

_COLUMNS = [
    "id", "tidal_id", "artist", "title", "album", "bpm", "key_raw", "camelot",
    "loudness", "energy", "genre", "styles", "label", "year", "play_count",
    "art_path", "sources", "prov", "extra",
]


def merge_tracks(base: Track, inc: Track) -> Track:
    """Merge ``inc`` into ``base`` in place, respecting source priority.

    Precision fields (bpm/key/...) are overwritten only when the incoming source
    is at least as trusted as the one that set the current value. Authoritative
    fields (genre/label/...) take the latest non-empty value. Nothing good is
    ever wiped by an empty incoming value.
    """
    for f in _PRECISION:
        iv = getattr(inc, f)
        if iv in (None, ""):
            continue
        i_src = inc.prov.get(f) or (inc.sources[0] if inc.sources else "")
        e_src = base.prov.get(f, "")
        if getattr(base, f) is None or \
                SOURCE_PRIORITY.get(i_src, 0) >= SOURCE_PRIORITY.get(e_src, 0):
            setattr(base, f, iv)
            base.prov[f] = i_src

    for f in _AUTHORITATIVE:
        iv = getattr(inc, f)
        if iv:  # non-empty string/list/number
            setattr(base, f, iv)

    if not base.artist:
        base.artist = inc.artist
    if not base.title:
        base.title = inc.title
    base.play_count = max(base.play_count, inc.play_count)
    base.sources = sorted(set(base.sources) | set(inc.sources))
    base.extra.update(inc.extra)
    return base


def _track_to_row(t: Track) -> tuple:
    return (
        t.id, t.tidal_id, t.artist, t.title, t.album, t.bpm, t.key_raw,
        t.camelot, t.loudness, t.energy, t.genre, json.dumps(t.styles),
        t.label, t.year, t.play_count, t.art_path, json.dumps(t.sources),
        json.dumps(t.prov), json.dumps(t.extra) if t.extra else None,
    )


def _row_to_track(row: sqlite3.Row) -> Track:
    def jload(v, default):
        return json.loads(v) if v else default
    return Track(
        id=row["id"],
        tidal_id=row["tidal_id"],
        artist=row["artist"] or "",
        title=row["title"] or "",
        album=row["album"] or "",
        bpm=row["bpm"],
        key_raw=row["key_raw"],
        camelot=row["camelot"],
        loudness=row["loudness"],
        energy=row["energy"],
        genre=row["genre"],
        styles=jload(row["styles"], []),
        label=row["label"],
        year=row["year"],
        play_count=row["play_count"] or 0,
        art_path=row["art_path"],
        sources=jload(row["sources"], []),
        prov=jload(row["prov"], {}),
        extra=jload(row["extra"], {}),
    )


class Catalog:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Catalog":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def upsert(self, tracks: Iterable[Track]) -> int:
        """Insert or merge each track, returning the number processed."""
        placeholders = ", ".join("?" for _ in _COLUMNS)
        sql = f"INSERT OR REPLACE INTO tracks ({', '.join(_COLUMNS)}) VALUES ({placeholders})"
        n = 0
        with self.conn:
            for t in tracks:
                existing = self.get(t.id)
                merged = merge_tracks(existing, t) if existing else t
                self.conn.execute(sql, _track_to_row(merged))
                n += 1
        return n

    def all_tracks(self, order_by: str = "camelot") -> List[Track]:
        allowed = {"camelot", "bpm", "artist", "title", "play_count", "genre"}
        col = order_by if order_by in allowed else "camelot"
        cur = self.conn.execute(
            f"SELECT * FROM tracks ORDER BY {col} IS NULL, {col}"
        )
        return [_row_to_track(r) for r in cur.fetchall()]

    def get(self, track_id: str) -> Optional[Track]:
        cur = self.conn.execute(
            "SELECT * FROM tracks WHERE id = ?", (track_id,)
        )
        row = cur.fetchone()
        return _row_to_track(row) if row else None

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]

    def search(self, query: str, limit: int = 25) -> List[Track]:
        like = f"%{query}%"
        cur = self.conn.execute(
            "SELECT * FROM tracks WHERE artist LIKE ? OR title LIKE ? "
            "ORDER BY play_count DESC LIMIT ?",
            (like, like, limit),
        )
        return [_row_to_track(r) for r in cur.fetchall()]

    def find_one(self, query: str) -> Optional[Track]:
        exact = self.get(query)
        if exact:
            return exact
        matches = self.search(query, limit=1)
        return matches[0] if matches else None

    def needing_enrichment(self, fields=("genre", "bpm", "camelot")) -> List[Track]:
        """Tracks missing any of the given fields."""
        conds = " OR ".join(f"{f} IS NULL OR {f} = ''" for f in fields)
        cur = self.conn.execute(f"SELECT * FROM tracks WHERE {conds}")
        return [_row_to_track(r) for r in cur.fetchall()]
