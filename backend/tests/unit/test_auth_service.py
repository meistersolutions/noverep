from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.config import settings
from app.infrastructure.auth.auth_service import (
    _hash_refresh_token,
    create_access_token,
    decode_token,
)


def test_create_and_decode_access_token():
    user_id = uuid4()
    token = create_access_token(user_id, "tester")
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["username"] == "tester"


def test_refresh_token_hash_is_stable():
    assert _hash_refresh_token("abc") == _hash_refresh_token("abc")
    assert _hash_refresh_token("abc") != _hash_refresh_token("def")


def test_access_token_uses_short_ttl():
    before = datetime.now(UTC)
    token = create_access_token(uuid4(), "tester")
    payload = decode_token(token)
    assert payload is not None
    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
    delta = exp - before
    assert timedelta(minutes=settings.jwt_access_expire_minutes - 1) <= delta <= timedelta(
        minutes=settings.jwt_access_expire_minutes + 1
    )
