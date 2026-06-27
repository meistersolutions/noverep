"""Normalize Postgres URLs for SQLAlchemy asyncpg (Neon, Render, etc.)."""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def prepare_asyncpg_url(database_url: str) -> tuple[str, dict]:
    """
    asyncpg does not accept libpq's sslmode= query param.
    Neon and others often ship postgresql://...?sslmode=require — fix that here.
    """
    url = database_url.strip()
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    connect_args: dict = {}
    needs_ssl = False

    if "sslmode" in query:
        mode = query.pop("sslmode")[0].lower()
        needs_ssl = mode in ("require", "verify-full", "verify-ca", "prefer", "allow")

    if "ssl" in query:
        ssl_val = query.pop("ssl")[0].lower()
        needs_ssl = needs_ssl or ssl_val in ("require", "true", "1", "yes")

    host = parsed.hostname or ""
    if needs_ssl or host.endswith(".neon.tech") or "neon.tech" in host:
        connect_args["ssl"] = True

    flat_query = urlencode([(key, values[0]) for key, values in query.items()])
    clean_url = urlunparse(parsed._replace(query=flat_query))
    return clean_url, connect_args
