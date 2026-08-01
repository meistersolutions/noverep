"""Classified Wikipedia BFS discovery (seed → film/soundtrack credits).

Credits (composer / director / singers / lyricists) come from film and
soundtrack pages — never by stamping the seed onto every song.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import unquote

import httpx

from app.config import settings
from app.services import wikipedia as wiki

PageKind = str  # film | soundtrack | hub | person | other

ProgressCb = Callable[[dict[str, Any]], Awaitable[None] | None]

_SKIP_PREFIXES = (
    "file:",
    "category:",
    "template:",
    "wikipedia:",
    "help:",
    "portal:",
    "talk:",
    "user:",
    "draft:",
    "module:",
    "special:",
    "mediawiki:",
)

_HUB_TOKENS = (
    "discography",
    "filmography",
    "film score",
    "film scores",
    "soundtrack",
    "songs recorded",
    "songs composed",
    "list of songs",
    "list of film",
)


def classify_page(title: str, html: str = "") -> PageKind:
    """Classify a Wikipedia page for crawl routing."""
    low = (title or "").casefold()
    html_low = (html or "").casefold()

    if "soundtrack" in low:
        return "soundtrack"
    if wiki._is_film_hub_title(title) or any(t in low for t in _HUB_TOKENS):
        return "hub"
    if low.startswith("list of "):
        return "hub"
    if re.search(r"\(\d{4} film\)", low) or low.endswith("(film)"):
        return "film"
    if "infobox film" in html_low or "infobox movie" in html_low:
        return "film"
    if "infobox" in html_low and (
        "directed by" in html_low or "music by" in html_low or 'class="vevent"' in html_low
    ):
        return "film"
    if any(
        token in html_low
        for token in (
            "infobox musical artist",
            "infobox person",
            "infobox artist",
            "infobox officeholder",
        )
    ):
        return "person"
    if "(disambiguation)" in low:
        return "other"
    return "other"


def _split_credit_names(raw: str) -> list[str]:
    text = wiki._clean_cell(raw)
    if not text:
        return []
    parts = re.split(r",|;|/|&|\band\b", text, flags=re.I)
    out: list[str] = []
    for part in parts:
        name = part.strip().strip("\"'")
        # Drop parenthetical roles: "X (director)"
        name = re.sub(r"\([^)]*\)", "", name).strip()
        if not name or len(name) < 2:
            continue
        if name.casefold() in out_casefold(out):
            continue
        out.append(name)
    return out


def out_casefold(names: list[str]) -> set[str]:
    return {n.casefold() for n in names}


def extract_infobox_credits(html: str) -> dict[str, Any]:
    """Pull director / music / cast from a film infobox."""
    credits: dict[str, Any] = {
        "directors": [],
        "composer_name": None,
        "actors": [],
        "actresses": [],
        "release_year": None,
        "language": None,
    }
    # Prefer the first infobox table.
    m = re.search(
        r'<table[^>]*class="[^"]*infobox[^"]*"[^>]*>(.*?)</table>',
        html,
        flags=re.I | re.S,
    )
    if not m:
        return credits
    box = m.group(1)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", box, flags=re.I | re.S)
    for row in rows:
        th = re.search(r"<th[^>]*>(.*?)</th>", row, flags=re.I | re.S)
        td = re.search(r"<td[^>]*>(.*?)</td>", row, flags=re.I | re.S)
        if not th or not td:
            continue
        label = wiki._clean_cell(re.sub(r"<[^>]+>", " ", th.group(1))).casefold()
        value_html = td.group(1)
        value_text = wiki._clean_cell(re.sub(r"<[^>]+>", " ", value_html))
        if not label or not value_text:
            continue
        if "directed" in label:
            credits["directors"] = _split_credit_names(value_text)
        elif label in {"music by", "music", "composer", "score by"} or "music by" in label:
            names = _split_credit_names(value_text)
            if names:
                credits["composer_name"] = names[0]
        elif "starring" in label or label == "cast":
            credits["actors"] = _split_credit_names(value_text)
        elif label in {"release date", "released", "release dates"}:
            credits["release_year"] = wiki._year_from_heading(value_text)
        elif label in {"language", "languages"}:
            langs = _split_credit_names(value_text)
            if langs:
                credits["language"] = langs[0]
    return credits


def is_skippable_title(title: str) -> bool:
    low = (title or "").casefold().strip()
    if not low:
        return True
    if any(low.startswith(p) for p in _SKIP_PREFIXES):
        return True
    if low.startswith("list of years") or low in {"main page"}:
        return True
    return False


def is_enqueue_worthy(title: str, *, seed_tokens: list[str] | None = None) -> bool:
    """Only follow film / soundtrack / hub-like links (not arbitrary wiki links)."""
    if is_skippable_title(title):
        return False
    low = title.casefold()
    if "(disambiguation)" in low:
        return False
    if "soundtrack" in low:
        return True
    if wiki._is_film_hub_title(title) or any(t in low for t in _HUB_TOKENS):
        return True
    if low.startswith("list of "):
        # Prefer lists that mention seed tokens when available.
        if seed_tokens and not any(t in low for t in seed_tokens if len(t) > 2):
            # Still allow film-score / song lists without seed in title.
            if not any(t in low for t in ("song", "film", "soundtrack", "discograph", "score")):
                return False
        return True
    if re.search(r"\(\d{4} film\)", low) or low.endswith("(film)"):
        return True
    return False


def extract_content_wiki_links(html: str) -> list[str]:
    """Collect /wiki/ links from page HTML, excluding nav noise when possible."""
    # Drop hatnotes/navboxes roughly by taking body; still filter titles hard.
    titles: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'href="/wiki/([^"#]+)"', html or "", flags=re.I):
        title = unquote(href.replace("_", " "))
        key = title.casefold()
        if key in seen or is_skippable_title(title):
            continue
        seen.add(key)
        titles.append(title)
    return titles


def film_page_candidates(
    film: str, year: int | None, language: str | None = None
) -> list[str]:
    """Ordered Wikipedia titles to try for a filmography row."""
    name = (film or "").strip()
    if not name:
        return []
    out: list[str] = []
    if year:
        out.append(f"{name} ({year} film)")
        if language:
            # Some articles use language in the disambiguator.
            out.append(f"{name} ({year} {language} film)")
            out.append(f"{name} ({language} film)")
    out.append(name)
    if year:
        out.append(f"{name} ({year})")
    # Deduplicate preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        k = t.casefold()
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    return uniq


async def search_seed_pages(client: httpx.AsyncClient, seed: str) -> list[str]:
    """Wikipedia opensearch for the seed; return promising start titles."""
    seed = seed.strip()
    if not seed:
        return []
    data = await wiki._wiki_get(
        client,
        {
            "action": "opensearch",
            "search": seed,
            "limit": 8,
            "format": "json",
        },
    )
    titles = [str(t) for t in (data[1] if isinstance(data, list) and len(data) > 1 else [])]
    start: list[str] = []
    # Exact / near-exact first
    for t in titles:
        if t.casefold() == seed.casefold() or seed.casefold() in t.casefold():
            if t not in start:
                start.append(t)
    for t in titles:
        if t not in start:
            start.append(t)

    # Also try common hubs for the canonical label.
    label = start[0] if start else seed
    # Strip disambiguation / parenthetical for hub templates
    bare = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip() or label
    for suffix in ("discography", "filmography"):
        resolved = await wiki._page_exists(client, f"{bare} {suffix}")
        if resolved and resolved not in start:
            start.append(resolved)
    for candidate in (
        f"List of songs recorded by {bare}",
        f"List of songs composed by {bare}",
        f"List of film scores by {bare}",
    ):
        resolved = await wiki._page_exists(client, candidate)
        if resolved and resolved not in start:
            start.append(resolved)
    return start


def _seed_tokens(seed: str) -> list[str]:
    return [t for t in re.split(r"\W+", seed.casefold()) if t]


def _apply_film_credits(
    works: list[dict[str, Any]],
    credits: dict[str, Any],
    movie_name: str | None,
    *,
    language: str | None = None,
) -> None:
    for w in works:
        if movie_name and not w.get("movie_name"):
            w["movie_name"] = movie_name
        if credits.get("composer_name") and not w.get("composer_name"):
            w["composer_name"] = credits["composer_name"]
        if credits.get("release_year") and not w.get("release_year"):
            w["release_year"] = credits["release_year"]
        lang = language or credits.get("language")
        if lang and not w.get("language"):
            w["language"] = lang
        for field in ("directors", "actors", "actresses"):
            vals = credits.get(field) or []
            if vals and not (w.get(field) or []):
                w[field] = list(vals)
        w.setdefault("source", "wikipedia_bfs")


async def _resolve_enqueue_title(
    client: httpx.AsyncClient,
    raw: str,
    year: int | None = None,
    language: str | None = None,
) -> str | None:
    for candidate in film_page_candidates(raw, year, language):
        resolved = await wiki._page_exists(client, candidate)
        if resolved:
            # Prefer real film pages over disambiguation.
            if "(disambiguation)" in resolved.casefold():
                continue
            return resolved
    search = raw
    if year:
        search = f"{raw} {year}"
    if language:
        search = f"{search} {language}"
    data = await wiki._wiki_get(
        client,
        {
            "action": "opensearch",
            "search": search,
            "limit": 8,
            "format": "json",
        },
    )
    titles = [str(t) for t in (data[1] if isinstance(data, list) and len(data) > 1 else [])]
    picked = wiki._prefer_film_title(titles, raw, year)
    if picked and not is_skippable_title(picked) and "(disambiguation)" not in picked.casefold():
        return picked
    return None


async def crawl_seed_bfs(
    seed: str,
    *,
    max_pages: int | None = None,
    max_depth: int | None = None,
    cursor: dict[str, Any] | None = None,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """BFS crawl from a Wikipedia seed.

    Returns ``{works, cursor, pages_done, seed_pages}``.
    Resume by passing the previous ``cursor``.
    """
    max_pages = settings.discover_max_pages if max_pages is None else max_pages
    max_depth = settings.discover_max_depth if max_depth is None else max_depth
    tokens = _seed_tokens(seed)

    prev = dict(cursor or {})
    queue: list[dict[str, Any]] = list(prev.get("queue") or [])
    seen: set[str] = {str(x).casefold() for x in (prev.get("seen") or [])}
    pages_done = int(prev.get("pages_done") or 0)
    works: list[dict[str, Any]] = []
    seed_pages: list[str] = list(prev.get("seed_pages") or [])
    film_pages: list[str] = list(prev.get("film_pages") or [])
    hub_pages: list[str] = list(prev.get("hub_pages") or [])

    async with httpx.AsyncClient(timeout=90.0, headers=wiki._headers()) as client:
        if not queue and pages_done == 0:
            starts = await search_seed_pages(client, seed)
            seed_pages = list(starts)
            for t in starts:
                queue.append({"title": t, "depth": 0})

        while queue:
            if max_pages and pages_done >= max_pages:
                break
            item = queue.pop(0)
            title = (item.get("title") or "").strip()
            depth = int(item.get("depth") or 0)
            if not title or title.casefold() in seen:
                continue
            if is_skippable_title(title):
                seen.add(title.casefold())
                continue
            if max_depth is not None and depth > max_depth:
                seen.add(title.casefold())
                continue

            seen.add(title.casefold())
            try:
                page_title, html, tables = await wiki._parse_page_html(client, title)
            except Exception:  # noqa: BLE001
                pages_done += 1
                continue

            kind = classify_page(page_title, html)
            pages_done += 1
            page_works: list[dict[str, Any]] = []
            # (title_or_film, year, language)
            enqueue: list[tuple[str, int | None, str | None]] = []
            hint_language = (item.get("language") or None)

            if kind == "film":
                if page_title not in film_pages:
                    film_pages.append(page_title)
                credits = extract_infobox_credits(html)
                page_works = wiki._tables_to_works(tables, page_title=page_title)
                movie_name = re.sub(r"\s*\([^)]*film\)\s*$", "", page_title, flags=re.I).strip()
                _apply_film_credits(
                    page_works, credits, movie_name, language=hint_language
                )
                for link in wiki._extract_soundtrack_page_links(html):
                    enqueue.append((link, None, hint_language))
                for link in extract_content_wiki_links(html):
                    if "soundtrack" in link.casefold():
                        enqueue.append((link, None, hint_language))

            elif kind == "soundtrack":
                credits = extract_infobox_credits(html)
                page_works = wiki._tables_to_works(tables, page_title=page_title)
                movie_name = re.sub(
                    r"\s*\([^)]*soundtrack\)\s*$", "", page_title, flags=re.I
                ).strip()
                _apply_film_credits(
                    page_works, credits, movie_name or None, language=hint_language
                )
                for w in page_works:
                    w["source"] = "wikipedia_soundtrack"

            elif kind in ("hub", "person", "other"):
                if kind == "hub" and page_title not in hub_pages:
                    hub_pages.append(page_title)
                page_works = wiki._tables_to_works(tables, page_title=page_title)
                for w in page_works:
                    w.setdefault("source", "wikipedia_hub")
                # Filmography rows → film pages (title + year + language).
                for film in wiki._tables_to_films(tables):
                    enqueue.append(
                        (film["film"], film.get("year"), film.get("language"))
                    )
                for link in wiki._extract_main_article_links(html):
                    if is_enqueue_worthy(link, seed_tokens=tokens):
                        enqueue.append((link, None, None))
                for link in extract_content_wiki_links(html):
                    if is_enqueue_worthy(link, seed_tokens=tokens):
                        enqueue.append((link, None, None))

            works.extend(page_works)

            # Resolve and push new links.
            if depth < (max_depth if max_depth is not None else 10**9):
                for raw, year, language in enqueue:
                    if not raw:
                        continue
                    # Hub/soundtrack titles can enqueue directly when already wiki-shaped.
                    if year is None and (
                        is_enqueue_worthy(raw, seed_tokens=tokens)
                        or "soundtrack" in raw.casefold()
                        or wiki._is_film_hub_title(raw)
                    ):
                        key = raw.casefold()
                        if key not in seen and not any(
                            (q.get("title") or "").casefold() == key for q in queue
                        ):
                            queue.append(
                                {
                                    "title": raw,
                                    "depth": depth + 1,
                                    "language": language,
                                }
                            )
                        continue
                    resolved = await _resolve_enqueue_title(
                        client, raw, year, language
                    )
                    if not resolved:
                        continue
                    key = resolved.casefold()
                    if key in seen:
                        continue
                    if any((q.get("title") or "").casefold() == key for q in queue):
                        continue
                    queue.append(
                        {
                            "title": resolved,
                            "depth": depth + 1,
                            "language": language,
                        }
                    )
                    await asyncio.sleep(0.05)

            state = {
                "queue": queue,
                "seen": sorted(seen),
                "pages_done": pages_done,
                "seed_pages": seed_pages,
                "film_pages": film_pages,
                "hub_pages": hub_pages,
                "films_total": len(film_pages),
                "film_index": len(film_pages),
                "kind": kind,
                "current_page": page_title,
                "works_delta": page_works,
            }
            if on_progress:
                maybe = on_progress(state)
                if asyncio.iscoroutine(maybe):
                    await maybe
            await asyncio.sleep(0.15)

    return {
        "works": works,
        "cursor": {
            "queue": queue,
            "seen": sorted(seen),
            "pages_done": pages_done,
            "seed_pages": seed_pages,
            "film_pages": film_pages,
            "hub_pages": hub_pages,
            "films_total": len(film_pages),
            "film_index": len(film_pages),
        },
        "pages_done": pages_done,
        "seed_pages": seed_pages,
    }
