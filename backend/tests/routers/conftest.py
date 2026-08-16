import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import auth as auth_router


@pytest.fixture
def client():
    """A minimal app with just the auth router mounted, so these tests
    don't depend on every other router being importable/working."""
    app = FastAPI()
    app.include_router(auth_router.router)
    return TestClient(app)