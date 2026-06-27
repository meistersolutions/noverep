import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


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
    assert data["is_guest"] is True
