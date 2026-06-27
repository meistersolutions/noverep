"""Tests for asyncpg database URL normalization."""

from app.infrastructure.database.url import prepare_asyncpg_url


def test_neon_sslmode_converted():
    raw = "postgresql://user:pass@ep-cool.neon.tech/neondb?sslmode=require"
    url, args = prepare_asyncpg_url(raw)
    assert url.startswith("postgresql+asyncpg://")
    assert "sslmode" not in url
    assert args.get("ssl") is True


def test_asyncpg_ssl_query_removed():
    raw = "postgresql+asyncpg://user:pass@host/db?ssl=require"
    url, args = prepare_asyncpg_url(raw)
    assert "ssl=" not in url.split("?")[-1] if "?" in url else True
    assert args.get("ssl") is True


def test_local_url_unchanged():
    raw = "postgresql+asyncpg://noverep:secret@localhost:5432/noverep"
    url, args = prepare_asyncpg_url(raw)
    assert url == raw
    assert args == {}
