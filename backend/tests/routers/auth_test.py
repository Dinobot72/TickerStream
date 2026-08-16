import pytest
import jwt
from app.routers.auth import get_password_hash, verify_password, create_access_token
from app.core.config import COOKIE_NAME, SECRET_KEY, ALGORITHM


class TestPasswordHashing:
    def test_verify_password_pass(self):
        hashed = get_password_hash("password")
        assert verify_password("password", hashed) is True

    def test_verify_password_fail(self):
        hashed = get_password_hash("password")
        assert verify_password("wrongpassword", hashed) is False

    def test_get_password_hash_produces_different_output_each_time(self):
        # bcrypt salts each hash, so two hashes of the same password
        # should never be identical
        hash1 = get_password_hash("password")
        hash2 = get_password_hash("password")
        assert hash1 != hash2

    def test_get_password_hash_is_verifiable(self):
        hashed = get_password_hash("mypassword")
        assert verify_password("mypassword", hashed) is True


class TestCreateAccessToken:
    def test_create_access_token_contains_claims(self):
        token = create_access_token({"sub": "testuser", "id": 1})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"
        assert payload["id"] == 1

    def test_create_access_token_sets_expiry(self):
        token = create_access_token({"sub": "testuser", "id": 1})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in payload


def register(client, username="testuser", password="testpass123"):
    return client.post("/api/register", json={
        "username": username,
        "password": password,
        "first_name": "Test",
        "last_name": "User",
    })


def login(client, username="testuser", password="testpass123"):
    return client.post("/api/login", json={
        "username": username,
        "password": password,
    })


class TestRegister:
    def test_register_success(self, client, user_dep_unused=None):
        resp = register(client)
        assert resp.status_code == 200
        assert resp.json()["message"] == "User registered successfully"

    def test_register_duplicate_username_fails(self, client):
        register(client)
        resp = register(client)  # same username again
        assert resp.status_code == 400


class TestLogin:
    def test_login_success(self, client):
        register(client)
        resp = login(client)
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "testuser"
        assert "access_token" in body
        assert COOKIE_NAME in resp.cookies

    def test_login_wrong_password(self, client):
        register(client)
        resp = login(client, password="wrongpass")
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = login(client, username="ghost")
        assert resp.status_code == 401


class TestLogout:
    def test_logout_clears_cookie(self, client):
        register(client)
        login(client)
        resp = client.post("/api/logout")
        assert resp.status_code == 200
        # Set-Cookie with past expiry should be present to clear it
        assert COOKIE_NAME in resp.headers.get("set-cookie", "")


class TestAuthStatus:
    def test_auth_status_authenticated(self, client):
        register(client)
        login(client)  # cookie now stored on client.cookies
        resp = client.get("/api/auth/status")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True
        assert resp.json()["user"]["username"] == "testuser"

    def test_auth_status_unauthenticated(self, client):
        resp = client.get("/api/auth/status")
        assert resp.status_code == 401


class TestChangePassword:
    def test_change_password_success(self, client):
        register(client)
        login_resp = login(client)
        user_id = login_resp.json()["user_id"]

        resp = client.post(f"/api/user/{user_id}/change-password", json={
            "current_password": "testpass123",
            "new_password": "newpass456",
        })
        assert resp.status_code == 200

        # old password should no longer work
        assert login(client, password="testpass123").status_code == 401
        # new password should work
        assert login(client, password="newpass456").status_code == 200

    def test_change_password_wrong_current_password(self, client):
        register(client)
        login_resp = login(client)
        user_id = login_resp.json()["user_id"]

        resp = client.post(f"/api/user/{user_id}/change-password", json={
            "current_password": "notmypassword",
            "new_password": "newpass456",
        })
        assert resp.status_code == 400

    def test_change_password_rejects_other_users(self, client):
        register(client)
        login_resp = login(client)
        real_user_id = login_resp.json()["user_id"]

        resp = client.post(f"/api/user/{real_user_id + 999}/change-password", json={
            "current_password": "testpass123",
            "new_password": "newpass456",
        })
        assert resp.status_code == 403