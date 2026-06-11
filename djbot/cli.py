"""Command-line entry point for djbot.

Phase 1 commands:
  scan   read the Serato TIDAL cache into the catalog
  list   print the catalog (sorted, with Camelot keys)
"""

from __future__ import annotations

import argparse
from typing import List

from . import audio
from . import config as cfg
from .catalog import Catalog
from .enrichment import analyze_track, enrich_track, seed_from_artist
from .models import Track
from .providers import DiscogsClient, GetSongBPMClient
from .recommender import Weights, build_runway, recommend_next
from .serato import DEFAULT_SERATO_DIR, scan_tidal_library


def _fmt_bpm(bpm) -> str:
    return f"{bpm:5.1f}" if bpm is not None else "  -  "


def _print_table(tracks: List[Track]) -> None:
    if not tracks:
        print("(catalog is empty — run `djbot scan` first)")
        return
    print(f"{'CAMELOT':<8}{'BPM':<7}{'GENRE':<20}ARTIST — TITLE")
    print("-" * 84)
    for t in tracks:
        print(
            f"{t.camelot or '-':<8}{_fmt_bpm(t.bpm):<7}"
            f"{(t.genre or '-'):<20}{t.label_str}"
        )
    print("-" * 84)
    print(f"{len(tracks)} track(s)")


def cmd_scan(args: argparse.Namespace) -> int:
    tracks = list(scan_tidal_library(args.serato_dir))
    with Catalog(args.db) as cat:
        n = cat.upsert(tracks)
    missing_key = sum(1 for t in tracks if not t.camelot)
    missing_bpm = sum(1 for t in tracks if t.bpm is None)
    print(f"Scanned {n} TIDAL track(s) from {args.serato_dir}")
    if missing_key:
        print(f"  ! {missing_key} without a recognised key")
    if missing_bpm:
        print(f"  ! {missing_bpm} without a BPM")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with Catalog(args.db) as cat:
        _print_table(cat.all_tracks(order_by=args.sort))
    return 0


def _track_line(t: Track) -> str:
    bpm = _fmt_bpm(t.bpm).strip()
    return f"[{t.camelot or '?':<3} {bpm:>5} BPM] {t.label_str}"


def _resolve_seed(cat: Catalog, query: str) -> Track | None:
    seed = cat.find_one(query)
    if seed is None:
        print(f"No track matches {query!r}. Try `djbot list`.")
    return seed


def cmd_next(args: argparse.Namespace) -> int:
    weights = Weights(bpm_tolerance=args.bpm_tolerance)
    with Catalog(args.db) as cat:
        seed = _resolve_seed(cat, args.seed)
        if seed is None:
            return 1
        pool = cat.all_tracks()
        suggestions = recommend_next(
            seed, pool, weights=weights,
            direction=args.direction, limit=args.limit,
        )
    print(f"NOW:  {_track_line(seed)}")
    print(f"NEXT (energy: {args.direction}):")
    if not suggestions:
        print("  (no compatible tracks found)")
        return 0
    for i, s in enumerate(suggestions, 1):
        print(f"  {i:>2}. {s.score:.2f}  {_track_line(s.track)}")
        print(f"        ↳ {' · '.join(s.reasons)}")
    return 0


def cmd_runway(args: argparse.Namespace) -> int:
    weights = Weights(bpm_tolerance=args.bpm_tolerance)
    with Catalog(args.db) as cat:
        seed = _resolve_seed(cat, args.seed)
        if seed is None:
            return 1
        pool = cat.all_tracks()
        path = build_runway(
            seed, pool, depth=args.depth,
            weights=weights, direction=args.direction,
        )
    print(f"  ▶ {_track_line(seed)}")
    if not path:
        print("    (couldn't build a runway — try more tracks or a wider tolerance)")
        return 0
    for step in path:
        print(f"  ↓ {' · '.join(step.reasons)}")
        print(f"  ▶ {_track_line(step.track)}")
    return 0


def _make_clients(need_discogs: bool, need_bpm: bool):
    """Build provider clients from config; warn (don't crash) on missing keys."""
    discogs = bpm = None
    dtok, gkey = cfg.get_key("discogs_token"), cfg.get_key("getsongbpm_key")
    if need_discogs:
        if dtok:
            discogs = DiscogsClient(dtok)
        else:
            print("  ! no Discogs token — genre/label enrichment skipped.")
            print("    get one free at https://www.discogs.com/settings/developers")
            print("    then: djbot config set discogs_token <TOKEN>")
    if need_bpm:
        if gkey:
            bpm = GetSongBPMClient(gkey)
        else:
            print("  ! no GetSongBPM key — BPM/key enrichment skipped.")
            print("    get one free at https://getsongbpm.com/api")
            print("    then: djbot config set getsongbpm_key <KEY>")
    return discogs, bpm


def cmd_enrich(args: argparse.Namespace) -> int:
    discogs, bpm = _make_clients(need_discogs=True, need_bpm=True)
    if discogs is None and bpm is None:
        return 1
    with Catalog(args.db) as cat:
        targets = cat.all_tracks() if args.all else cat.needing_enrichment()
        if args.limit:
            targets = targets[:args.limit]
        print(f"Enriching {len(targets)} track(s)…")
        enriched = 0
        for t in targets:
            deltas = enrich_track(t, discogs=discogs, getsongbpm=bpm)
            if deltas:
                cat.upsert(deltas)
                enriched += 1
                print(f"  ✓ {t.label_str}")
    print(f"Done. Updated {enriched} track(s).")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    ok, why = audio.available()
    if not ok:
        print(f"  ! audio analysis unavailable ({why}).")
        print("    install with: pip install librosa  (also needs ffmpeg on PATH)")
        return 1
    with Catalog(args.db) as cat:
        targets = (cat.all_tracks() if args.all
                   else cat.needing_enrichment(fields=("bpm", "camelot")))
        if args.limit:
            targets = targets[:args.limit]
        print(f"Analysing audio for {len(targets)} track(s)… (downloads previews)")
        done = 0
        for t in targets:
            delta = analyze_track(t)
            if delta:
                cat.upsert([delta])
                done += 1
                print(f"  ✓ {delta.camelot or '?':<3} {_fmt_bpm(delta.bpm).strip():>5} "
                      f"BPM  {t.label_str}")
            else:
                print(f"  · no audio match: {t.label_str}")
    print(f"Done. Analysed {done} track(s).")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    discogs, _ = _make_clients(need_discogs=True, need_bpm=False)
    if discogs is None:
        return 1
    total = 0
    with Catalog(args.db) as cat:
        for artist in args.artist:
            tracks = seed_from_artist(discogs, artist, max_releases=args.max_releases)
            n = cat.upsert(tracks)
            total += n
            print(f"  + {n:>4} candidate track(s) from {artist}")
    print(f"Seeded {total} track(s). Run `djbot enrich` to add BPM/key.")
    return 0


def cmd_vibe(args: argparse.Namespace) -> int:
    import difflib
    from . import cosine
    from .catalog import Catalog
    from .models import make_id

    with Catalog(args.db) as cat:
        seed = cat.find_one(" ".join(args.query))
        if seed is None:
            print("no catalog track matches that query.")
            return 1
        try:
            match = cosine.resolve(seed.artist, seed.title)
        except cosine.CosineError as e:
            print(f"cosine error: {e}")
            return 1
        if match is None:
            print(f"'{seed}' not found on cosine.club (underground DB — may be absent).")
            return 0
        cands = cosine.similar(match["cosine_id"], limit=args.limit)
        print(f"~ same vibe as: {seed}")
        print(f"  (cosine match: {match['artist']} — {match['title']})\n")
        pool = cat.all_tracks()
        in_pool = 0
        for c in cands:
            hit = cat.get(make_id(c["artist"], c["title"]))
            if hit is None:  # fall back to fuzzy match against the pool
                best, br = None, 0.72
                tgt = f"{c['artist']} {c['title']}".lower()
                for t in pool:
                    rr = difflib.SequenceMatcher(
                        None, f"{t.artist} {t.title}".lower(), tgt).ratio()
                    if rr >= br:
                        best, br = t, rr
                hit = best
            score = c.get("score")
            sc = f"{score:.3f}" if isinstance(score, (int, float)) else "  ·  "
            if hit:
                in_pool += 1
                tag = f"IN POOL · {hit.camelot or '?'} · {round(hit.bpm) if hit.bpm else '—'} BPM · {hit.genre or '—'}"
            else:
                tag = "NEW · not yet analysed (would enrich on add)"
            print(f"  {sc}  {c['artist']} — {c['title']}")
            print(f"           {tag}")
        print(f"\n{len(cands)} similar · {in_pool} already in your pool · "
              f"{len(cands) - in_pool} new to discover.")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    if args.action == "set":
        cfg.set_key(args.name, args.value)
        print(f"Saved {args.name} to {cfg.CONFIG_PATH}")
    else:  # show
        current = cfg.load_config()
        if not current:
            print("No config set. Add keys with: djbot config set <name> <value>")
        for k, v in current.items():
            print(f"  {k} = {v[:4]}…" if v else f"  {k} = (empty)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="djbot", description=__doc__)
    p.add_argument("--db", default=None,
                   help="path to catalog SQLite db (default: ./data/catalog.db)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="read Serato TIDAL cache into the catalog")
    s.add_argument("--serato-dir", default=str(DEFAULT_SERATO_DIR),
                   dest="serato_dir", help="path to the _Serato_ folder")
    s.set_defaults(func=cmd_scan)

    l = sub.add_parser("list", help="print the catalog")
    l.add_argument("--sort", default="camelot",
                   choices=["camelot", "bpm", "artist", "title", "play_count"])
    l.set_defaults(func=cmd_list)

    def add_reco_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("seed", help="track id or artist/title substring")
        sp.add_argument("--direction", default="any",
                        choices=["any", "up", "hold", "down"],
                        help="desired energy direction")
        sp.add_argument("--bpm-tolerance", dest="bpm_tolerance",
                        default=0.06, type=float,
                        help="BPM match window as a fraction (0.06 = 6%%)")

    n = sub.add_parser("next", help="rank compatible next tracks for a seed")
    add_reco_args(n)
    n.add_argument("--limit", type=int, default=10)
    n.set_defaults(func=cmd_next)

    r = sub.add_parser("runway", help="plan a flowing sequence after a seed")
    add_reco_args(r)
    r.add_argument("--depth", type=int, default=3, help="how many tracks to line up")
    r.set_defaults(func=cmd_runway)

    e = sub.add_parser("enrich", help="fill genre/BPM/key from Discogs + GetSongBPM")
    e.add_argument("--all", action="store_true",
                   help="re-enrich every track, not just those missing data")
    e.add_argument("--limit", type=int, default=0, help="cap how many tracks to process")
    e.set_defaults(func=cmd_enrich)

    a = sub.add_parser("analyze", help="estimate BPM/key from free preview audio (iTunes/Deezer + librosa)")
    a.add_argument("--all", action="store_true",
                   help="re-analyse every track, not just those missing BPM/key")
    a.add_argument("--limit", type=int, default=0, help="cap how many tracks to process")
    a.set_defaults(func=cmd_analyze)

    v = sub.add_parser("vibe", help="find sonically-similar tracks via cosine.club audio embeddings")
    v.add_argument("query", nargs="+", help="a track in your catalog to seed from")
    v.add_argument("--limit", type=int, default=15, help="how many similar tracks to show")
    v.set_defaults(func=cmd_vibe)

    sd = sub.add_parser("seed", help="grow the universe from an artist's Discogs catalog")
    sd.add_argument("artist", nargs="+", help="artist name(s) to pull, e.g. \"John Digweed\"")
    sd.add_argument("--max-releases", type=int, default=10, dest="max_releases",
                    help="how many recent releases per artist to pull")
    sd.set_defaults(func=cmd_seed)

    c = sub.add_parser("config", help="view or set API keys")
    csub = c.add_subparsers(dest="action", required=True)
    csub.add_parser("show", help="show configured keys").set_defaults(action="show")
    cset = csub.add_parser("set", help="set a key")
    cset.add_argument("name", choices=[
        "discogs_token", "getsongbpm_key", "cosine_key",
        "tidal_client_id", "tidal_client_secret", "spotify_client_id"])
    cset.add_argument("value")
    cset.set_defaults(action="set")
    c.set_defaults(func=cmd_config)

    return p


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.db is None:
        from .catalog import DEFAULT_DB_PATH
        args.db = DEFAULT_DB_PATH
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
