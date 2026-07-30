"""Keep Songs Library awake on Render free tier via periodic health pings.

Render spins down free web services after ~15 minutes with no *inbound* HTTP.
In-process discovery/enrich workers die with the container — they do not count
as activity.

NoRepeat (when itself awake) pings Songs Library every minute. Songs Library
also pings NoRepeat back when configured. Limitation: if **both** free-tier
services sleep, neither can wake the other until a user (or external cron)
hits one of them.
"""

from __future__ import annotations

import asyncio

import structlog

from app.config import settings
from app.infrastructure.external.songs_library_client import SongsLibraryClient

logger = structlog.get_logger()


async def songs_library_keepalive_loop(stop_event: asyncio.Event) -> None:
    if not settings.songs_library_enabled or not settings.songs_library_url:
        logger.info("songs_library_keepalive_disabled")
        return

    client = SongsLibraryClient()
    interval = max(30, int(settings.songs_library_keepalive_seconds))
    logger.info(
        "songs_library_keepalive_started",
        url=settings.songs_library_url,
        interval_seconds=interval,
    )

    # Immediate wake on API boot so the first user request is less likely to 502.
    try:
        ok = await client.health()
        logger.info("songs_library_keepalive_ping", ok=ok, boot=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("songs_library_keepalive_ping_failed", error=str(exc), boot=True)

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break
        except TimeoutError:
            pass
        try:
            ok = await client.health()
            logger.info("songs_library_keepalive_ping", ok=ok)
        except Exception as exc:  # noqa: BLE001
            logger.warning("songs_library_keepalive_ping_failed", error=str(exc))
