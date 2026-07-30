#!/usr/bin/env python3
"""Map YouTube video IDs locally, then bulk-update Songs Library via API.

Runs on your home machine (residential IP) so Google web search is more likely
to work than from Render. Default is dry-run — nothing is written until --apply.

Examples:
  # Resolve 50 unmapped Ilaiyaraaja songs (preview only)
  python map_youtube_local.py --composer Ilaiyaraaja --limit 50

  # Same, then PATCH the library
  python map_youtube_local.py --composer Ilaiyaraaja --limit 50 --apply

  # Prefer YouTube Data API if you have a key locally
  set YOUTUBE_API_KEY=your_key
  python map_youtube_local.py --method youtube_api --limit 100 --apply

  # Resume after interrupt (skips song ids already in the results file)
  python map_youtube_local.py --limit 200 --apply --results out.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VIDEO_ID_RE = re.compile(r"(?:v=|/shorts/|youtu\.be/)([A-Za-z0-9_-]{11})")
WATCH_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?[^\"'<>\s]*v=|youtu\.be/)([A-Za-z0-9_-]{11})",
    re.I,
)
# Google often wraps links as /url?q=https://www.youtube.com/watch%3Fv%3D...
GOOGLE_URL_RE = re.compile(
    r"/url\?q=(https?://(?:www\.)?(?:youtube\.com/watch[^&\"'<>\s]+|youtu\.be/[^&\"'<>\s]+))",
    re.I,
)

DEFAULT_BASE = "https://songs-library.onrender.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _http_json(method: str, url: str, *, body: dict | None = None, timeout: float = 60.0):
    data = None
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(err_body)
        except Exception:
            detail = err_body
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc


def _http_text(url: str, *, timeout: float = 30.0) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_unmapped(
    base: str,
    *,
    composer: str | None,
    limit: int,
) -> list[dict]:
    """Page through /api/songs and keep rows without youtube_video_id."""
    out: list[dict] = []
    offset = 0
    page = 200
    while len(out) < limit:
        params: dict[str, str] = {"limit": str(page), "offset": str(offset)}
        if composer:
            params["composer"] = composer
        url = f"{base.rstrip('/')}/api/songs?{urllib.parse.urlencode(params)}"
        _status, batch = _http_json("GET", url)
        if not batch:
            break
        for song in batch:
            if song.get("youtube_video_id"):
                continue
            out.append(song)
            if len(out) >= limit:
                break
        if len(batch) < page:
            break
        offset += page
        time.sleep(0.15)
    return out[:limit]


def build_query(song: dict) -> str:
    parts = [song.get("song_name") or ""]
    if song.get("movie_name"):
        parts.append(song["movie_name"])
    if song.get("composer_name"):
        parts.append(song["composer_name"])
    parts.append("site:youtube.com")
    return " ".join(p for p in parts if p)


def extract_first_video_id(html: str) -> str | None:
    for m in GOOGLE_URL_RE.finditer(html):
        decoded = urllib.parse.unquote(m.group(1))
        vid = VIDEO_ID_RE.search(decoded)
        if vid:
            return vid.group(1)
    for m in WATCH_RE.finditer(html):
        return m.group(1)
    # Last resort: any 11-char id next to youtube watch markers in the page.
    for m in VIDEO_ID_RE.finditer(html):
        return m.group(1)
    return None


def search_google_udm14(query: str) -> str | None:
    """Google Web results (udm=14) → first YouTube video id."""
    params = {
        "q": query,
        "udm": "14",
        "hl": "en",
        "num": "10",
    }
    url = "https://www.google.com/search?" + urllib.parse.urlencode(params)
    html = _http_text(url)
    lowered = html.lower()
    if "unusual traffic" in lowered or "captcha" in lowered or "/sorry/" in lowered:
        raise RuntimeError("Google blocked/captcha — slow down, open a browser once, retry later")
    if "consent.google.com" in lowered and "youtube.com/watch" not in lowered:
        raise RuntimeError("Google consent page returned — open google.com in a browser, accept, retry")
    return extract_first_video_id(html)


def search_youtube_data_api(query: str, api_key: str) -> str | None:
    params = {
        "part": "snippet",
        "type": "video",
        "maxResults": "5",
        "q": query,
        "key": api_key,
        "regionCode": "IN",
    }
    url = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params)
    _status, payload = _http_json("GET", url, timeout=30.0)
    for item in (payload or {}).get("items") or []:
        vid = ((item.get("id") or {}).get("videoId") or "").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return vid
    return None


def patch_song(base: str, song_id: str, video_id: str) -> dict:
    url = f"{base.rstrip('/')}/api/songs/{song_id}"
    _status, updated = _http_json(
        "PATCH",
        url,
        body={
            "youtube_video_id": video_id,
            "playability": "mapped",
        },
    )
    return updated or {}


def load_results(path: Path) -> dict:
    if not path.exists():
        return {"updated_at": None, "items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_results(path: Path, data: dict) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=os.environ.get("SONGS_LIBRARY_URL", DEFAULT_BASE))
    parser.add_argument("--composer", default=None, help="Filter by composer name")
    parser.add_argument("--limit", type=int, default=50, help="Max unmapped songs to process")
    parser.add_argument(
        "--method",
        choices=("google", "youtube_api"),
        default="google",
        help="google = web search udm=14 (local IP); youtube_api = Data API key",
    )
    parser.add_argument("--delay", type=float, default=2.5, help="Seconds between searches")
    parser.add_argument("--jitter", type=float, default=1.0, help="Extra random delay 0..jitter")
    parser.add_argument("--apply", action="store_true", help="PATCH mapped ids to Songs Library")
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("youtube_map_results.json"),
        help="Progress / review file",
    )
    parser.add_argument("--dry-fetch-only", action="store_true", help="Only list unmapped songs and exit")
    args = parser.parse_args()

    api_key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if args.method == "youtube_api" and not api_key:
        print("ERROR: --method youtube_api requires YOUTUBE_API_KEY in the environment", file=sys.stderr)
        return 2

    print(f"Library: {args.base}")
    print(f"Fetching up to {args.limit} unmapped songs…")
    songs = fetch_unmapped(args.base, composer=args.composer, limit=args.limit)
    print(f"Got {len(songs)} unmapped")

    if args.dry_fetch_only:
        for s in songs[:20]:
            print(f"  - {s.get('song_name')} / {s.get('movie_name')} [{s.get('id')}]")
        if len(songs) > 20:
            print(f"  … and {len(songs) - 20} more")
        return 0

    store = load_results(args.results)
    by_id = {item["id"]: item for item in store.get("items") or [] if item.get("id")}
    resolved = 0
    failed = 0
    applied = 0
    skipped = 0

    try:
        for i, song in enumerate(songs, 1):
            sid = song["id"]
            existing = by_id.get(sid)
            if existing and existing.get("youtube_video_id"):
                skipped += 1
                video_id = existing["youtube_video_id"]
                print(f"[{i}/{len(songs)}] skip (cached) {song.get('song_name')} → {video_id}")
            else:
                query = build_query(song)
                print(f"[{i}/{len(songs)}] search: {query}")
                try:
                    if args.method == "youtube_api":
                        video_id = search_youtube_data_api(query.replace(" site:youtube.com", ""), api_key)
                    else:
                        video_id = search_google_udm14(query)
                except Exception as exc:
                    print(f"  ERROR: {exc}")
                    failed += 1
                    by_id[sid] = {
                        "id": sid,
                        "song_name": song.get("song_name"),
                        "movie_name": song.get("movie_name"),
                        "composer_name": song.get("composer_name"),
                        "query": query,
                        "youtube_video_id": None,
                        "error": str(exc),
                    }
                    # Stop hard on Google blocks so you don't burn the IP.
                    if "captcha" in str(exc).lower() or "blocked" in str(exc).lower() or "consent" in str(exc).lower():
                        print("Stopping early due to Google block.")
                        break
                    time.sleep(args.delay + random.uniform(0, args.jitter))
                    continue

                if not video_id:
                    print("  → no video id")
                    failed += 1
                    by_id[sid] = {
                        "id": sid,
                        "song_name": song.get("song_name"),
                        "movie_name": song.get("movie_name"),
                        "composer_name": song.get("composer_name"),
                        "query": query,
                        "youtube_video_id": None,
                        "error": "not_found",
                    }
                else:
                    print(f"  → {video_id}")
                    resolved += 1
                    by_id[sid] = {
                        "id": sid,
                        "song_name": song.get("song_name"),
                        "movie_name": song.get("movie_name"),
                        "composer_name": song.get("composer_name"),
                        "query": query,
                        "youtube_video_id": video_id,
                        "error": None,
                    }

                time.sleep(args.delay + random.uniform(0, args.jitter))

            video_id = (by_id.get(sid) or {}).get("youtube_video_id")
            if args.apply and video_id:
                try:
                    patch_song(args.base, sid, video_id)
                    applied += 1
                    by_id[sid]["applied"] = True
                    print(f"  applied PATCH {sid}")
                except Exception as exc:
                    print(f"  PATCH failed: {exc}")
                    by_id[sid]["applied"] = False
                    by_id[sid]["apply_error"] = str(exc)

            if i % 5 == 0:
                store["items"] = list(by_id.values())
                save_results(args.results, store)
    finally:
        store["items"] = list(by_id.values())
        save_results(args.results, store)

    print()
    print(f"Done. resolved={resolved} failed={failed} skipped_cached={skipped} applied={applied}")
    print(f"Results file: {args.results.resolve()}")
    if not args.apply:
        print("Dry-run only. Re-run with --apply to PATCH Songs Library.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
