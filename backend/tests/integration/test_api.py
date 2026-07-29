import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin",
    [
        "https://localhost",
        "capacitor://localhost",
        "http://localhost",
    ],
)
async def test_cors_preflight_capacitor_origins(client, origin):
    response = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin


@pytest.mark.asyncio
async def test_cors_preflight_auth_refresh(client):
    response = await client.options(
        "/api/v1/auth/refresh",
        headers={
            "Origin": "https://localhost",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://localhost"


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_guest_auth(client):
    response = await client.post("/api/v1/auth/guest")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["is_guest"] is True


@pytest.mark.asyncio
async def test_refresh_token_flow(client):
    guest = await client.post("/api/v1/auth/guest")
    assert guest.status_code == 200
    tokens = guest.json()

    me = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200

    refreshed = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    me_after = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
    )
    assert me_after.status_code == 200

    stale = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert stale.status_code == 401


@pytest.mark.asyncio
async def test_login_invalid_credentials_capacitor_origin(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "wrong"},
        headers={"Origin": "https://localhost"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
    assert response.headers.get("access-control-allow-origin") == "https://localhost"


@pytest.mark.asyncio
async def test_login_ignores_stale_bearer_token(client):
    guest = await client.post("/api/v1/auth/guest")
    stale_token = guest.json()["access_token"]

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "wrong"},
        headers={
            "Origin": "https://localhost",
            "Authorization": f"Bearer {stale_token}",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_register_and_login_by_email(client):
    username = "emailuser1"
    email = "emailuser1@example.com"
    password = "secret12"

    registered = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert registered.status_code == 200

    by_email = await client.post(
        "/api/v1/auth/login",
        json={"username": email, "password": password},
        headers={"Origin": "https://localhost"},
    )
    assert by_email.status_code == 200
    assert by_email.json()["username"] == username
