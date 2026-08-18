import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import auth as auth_router
from app.routers import portfolio
from app.routers import trading


@pytest.fixture
def client():
    """A minimal app with just the auth router mounted, so these tests
    don't depend on every other router being importable/working."""
    app = FastAPI()
    app.include_router(auth_router.router)
    app.include_router(portfolio.router)
    app.include_router(trading.router)
    return TestClient(app)

@pytest.fixture
def logged_in_user(client):
    """Registers + logs in a user, returns their user_id. The client's
    cookie jar now carries auth for every subsequent request in the test."""
    client.post("/api/register", json={
        "username": "testuser",
        "password": "testpass123",
        "first_name": "Test",
        "last_name": "User",
    })
    resp = client.post("/api/login", json={
        "username": "testuser",
        "password": "testpass123",
    })
    return resp.json()["user_id"]
