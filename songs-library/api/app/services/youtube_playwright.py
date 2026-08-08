"""Playwright YouTube search fallback (from youtube-csv-mapper).

Runs Chromium like a normal user. Used when Data API is unset and yt-dlp is
blocked or returns no hit. Browser work is pinned to a single thread.
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
import threading
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
WATCH_ID_RE = re.compile(r"(?:v=|/shorts/|youtu\.be/)([A-Za-z0-9_-]{11})")
HEXISH_RE = re.compile(r"^[0-9a-f]{11}$", re.I)

_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="yt-playwright"
)
_state_lock = threading.Lock()
_pw = None
_browser = None
_page = None
_init_error: str | None = None


def playwright_available() -> bool:
    if not settings.youtube_playwright_fallback:
        return False
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return _init_error is None


def playwright_status() -> dict:
    return {
        "enabled": bool(settings.youtube_playwright_fallback),
        "available": playwright_available(),
        "headless": bool(settings.youtube_playwright_headless),
        "init_error": _init_error,
    }


def looks_like_video_id(vid: str | None) -> bool:
    if not vid or not VIDEO_ID_RE.fullmatch(vid):
        return False
    if HEXISH_RE.fullmatch(vid):
        return False
    return True


def parse_view_count(text: str | None) -> int | None:
    if not text:
        return None
    raw = re.sub(r"views?", "", text.casefold()).replace(",", "").strip()
    mult = 1.0
    if raw.endswith("k"):
        mult = 1_000.0
        raw = raw[:-1]
    elif raw.endswith("m"):
        mult = 1_000_000.0
        raw = raw[:-1]
    elif raw.endswith("b"):
        mult = 1_000_000_000.0
        raw = raw[:-1]
    try:
        return int(float(raw) * mult)
    except ValueError:
        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else None


def _dismiss_consent(page) -> None:
    candidates = [
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'button:has-text("Accept")',
        'tp-yt-paper-button:has-text("Accept")',
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=800):
                loc.click(timeout=1500)
                page.wait_for_timeout(500)
                return
        except Exception:  # noqa: BLE001
            continue


def _extract_from_search_page(page) -> dict[str, Any]:
    items = page.locator("ytd-video-renderer, ytd-rich-item-renderer").all()
    for item in items[:12]:
        try:
            link = item.locator('a[href*="watch?v="], a[href*="/shorts/"]').first
            if link.count() == 0:
                continue
            href = link.get_attribute("href") or ""
            m = WATCH_ID_RE.search(href)
            if not m or not looks_like_video_id(m.group(1)):
                continue
            video_id = m.group(1)
            views_text = ""
            try:
                views_text = (
                    item.locator(
                        "span.inline-metadata-item, #metadata-line span, ytd-video-meta-block span"
                    ).first.inner_text(timeout=1000)
                    or ""
                ).strip()
            except Exception:  # noqa: BLE001
                views_text = ""
            return {
                "youtube_video_id": video_id,
                "view_count": parse_view_count(views_text),
            }
        except Exception:  # noqa: BLE001
            continue
    return {}


def _ensure_page():
    global _pw, _browser, _page, _init_error
    if _page is not None:
        return _page
    with _state_lock:
        if _page is not None:
            return _page
        try:
            from playwright.sync_api import sync_playwright

            _pw = sync_playwright().start()
            _browser = _pw.chromium.launch(headless=bool(settings.youtube_playwright_headless))
            context = _browser.new_context(
                locale="en-IN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            _page = context.new_page()
            _page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=60_000)
            _dismiss_consent(_page)
            _init_error = None
            logger.info("youtube_playwright_browser_ready")
            return _page
        except Exception as exc:  # noqa: BLE001
            _init_error = str(exc)
            logger.warning("youtube_playwright_init_failed", extra={"error": str(exc)})
            _close_browser_unlocked()
            raise


def _close_browser_unlocked() -> None:
    global _pw, _browser, _page
    for obj, method in ((_browser, "close"), (_pw, "stop")):
        try:
            if obj is not None:
                getattr(obj, method)()
        except Exception:  # noqa: BLE001
            pass
    _pw = None
    _browser = None
    _page = None


def _search_on_thread(query: str, *, open_watch: bool) -> tuple[str | None, int | None]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    page = _ensure_page()
    url = "https://www.youtube.com/results?search_query=" + re.sub(r"\s+", "+", query.strip())
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    _dismiss_consent(page)
    try:
        page.wait_for_selector("ytd-video-renderer, ytd-rich-item-renderer", timeout=20_000)
    except PlaywrightTimeout:
        return None, None

    hit = _extract_from_search_page(page)
    video_id = hit.get("youtube_video_id")
    views = hit.get("view_count")
    if not video_id:
        return None, None

    if open_watch:
        try:
            page.goto(
                f"https://www.youtube.com/watch?v={video_id}",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            _dismiss_consent(page)
            page.wait_for_timeout(1000)
            for sel in (
                "yt-formatted-string#info span:has-text('views')",
                "#info-container span:has-text('views')",
                "yt-formatted-string:has-text('views')",
            ):
                try:
                    loc = page.locator(sel).first
                    if not loc.count():
                        continue
                    vt = (loc.inner_text(timeout=1500) or "").strip()
                    parsed = parse_view_count(vt)
                    if parsed:
                        views = parsed
                        break
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass

    return video_id, views if isinstance(views, int) and views > 0 else None


def search_youtube_playwright(query: str) -> tuple[str | None, int | None]:
    """Search YouTube via Playwright. Safe to call from any thread."""
    if not settings.youtube_playwright_fallback:
        return None, None
    try:
        import playwright  # noqa: F401
    except ImportError:
        logger.warning("youtube_playwright_not_installed")
        return None, None

    try:
        future = _executor.submit(
            _search_on_thread,
            query,
            open_watch=bool(settings.youtube_playwright_open_watch),
        )
        return future.result(timeout=float(settings.youtube_playwright_timeout_seconds))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "youtube_playwright_search_failed",
            extra={"error": str(exc), "query": query},
        )
        # Reset browser on hard failures so the next call can retry init.
        def _reset() -> None:
            with _state_lock:
                _close_browser_unlocked()

        try:
            _executor.submit(_reset).result(timeout=15)
        except Exception:  # noqa: BLE001
            pass
        return None, None
