import pytest
from app.core import database

def insert_holding(user_id, ticker="AAPL", quantity=10, purchase_price=150.0):
    conn = database.get_db_connection()
    conn.execute(
        "INSERT INTO holdings (user_id, ticker, quantity, purchase_price) VALUES (?, ?, ?, ?)",
        (user_id, ticker, quantity, purchase_price),
    )
    conn.commit()
    conn.close()


def insert_trade(user_id, ticker="AAPL", action="BUY", quantity=5, price=150.0):
    conn = database.get_db_connection()
    conn.execute(
        "INSERT INTO trades (user_id, ticker, action, quantity, price) VALUES (?, ?, ?, ?, ?)",
        (user_id, ticker, action, quantity, price),
    )
    conn.commit()
    conn.close()

class TestUserInfo:


    def test_get_user_info(self, client, logged_in_user):
        resp = client.get(f"/api/user/{logged_in_user}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == logged_in_user
        assert body["username"] == "testuser"
        assert body["balance"] == 0.0

    def test_get_user_info_not_authorized(self, client, logged_in_user):
        resp = client.get(f"/api/user/{logged_in_user + 1}")
        assert resp.status_code == 403
        response_data = resp.json()
        assert f"not authorized" in response_data["detail"]

class TestDeposit:
    def test_deposit(self, client, logged_in_user):
        resp = client.post(f"/api/user/{logged_in_user}/deposit", json={"amount": 100.00})
        assert resp.status_code == 200
        response_data = resp.json()
        assert response_data["message"] == "Deposit successful"
        assert response_data["new_balance"] == 100.00

    def test_deposit_not_authorized(self, client, logged_in_user):
        resp = client.post(f"/api/user/{logged_in_user + 1}/deposit", json={"amount": 100.00})
        assert resp.status_code == 403
        response_data = resp.json()
        assert response_data["detail"] == "Unauthorized"

    def test_deposit_failed(self, client, logged_in_user):
        resp = client.post(f"/api/user/{logged_in_user}/deposit", json={"amount": "not a number"})
        assert resp.status_code == 422
        response_data = resp.json()
        assert response_data["detail"][0]["msg"] == "Input should be a valid number, unable to parse string as a number"


class TestHoldings:
    def test_get_holdings(self, client, logged_in_user):
        resp = client.get(f"/api/holdings/{logged_in_user}")
        assert resp.status_code == 200
        response_data = resp.json()
        assert len(response_data) == 0
        insert_holding(logged_in_user)
        resp = client.get(f"/api/holdings/{logged_in_user}")
        assert resp.status_code == 200
        response_data = resp.json()
        assert len(response_data) == 1

    def test_get_holldings_not_authorized(self, client, logged_in_user):
        resp = client.get(f"/api/holdings/{logged_in_user + 1}")
        assert resp.status_code == 403
        response_data = resp.json()
        assert response_data["detail"] == "Unauthorized"

    def test_get_holdings_excludes_zero_quantity(self, client, logged_in_user):
        insert_holding(logged_in_user, ticker="AAPL", quantity=0)
        resp = client.get(f"/api/holdings/{logged_in_user}")
        assert resp.json() == []

class TestTradesActivity:
    def test_get_activity(self, client, logged_in_user):
        insert_trade(logged_in_user, ticker="TSLA", action="BUY")
        resp = client.get(f"/api/activity/{logged_in_user}")
        assert resp.status_code == 200
        assert resp.json()[0]["ticker"] == "TSLA"

    def test_get_activity_respects_limit(self, client, logged_in_user):
        for _ in range(5):
            insert_trade(logged_in_user)
        resp = client.get(f"/api/activity/{logged_in_user}?limit=2")
        assert len(resp.json()) == 2

    def test_get_activity_not_authorized(self, client, logged_in_user):
        resp = client.get(f"/api/activity/{logged_in_user + 1}")
        assert resp.status_code == 403

class TestWatchlist:
    def test_add_and_get_watchlist(self, client, logged_in_user):
        add_resp = client.post(f"/api/watchlist/{logged_in_user}", json={"ticker": "nvda"})
        assert add_resp.status_code == 200
        assert add_resp.json()["message"] == "Added to watchlist"

        get_resp = client.get(f"/api/watchlist/{logged_in_user}")
        assert get_resp.json()[0]["ticker"] == "NVDA"  # confirms uppercasing

    def test_add_watchlist_duplicate(self, client, logged_in_user):
        client.post(f"/api/watchlist/{logged_in_user}", json={"ticker": "NVDA"})
        resp = client.post(f"/api/watchlist/{logged_in_user}", json={"ticker": "NVDA"})
        assert resp.json()["message"] == "Already in watchlist"

    def test_add_watchlist_not_authorized(self, client, logged_in_user):
        resp = client.post(f"/api/watchlist/{logged_in_user + 1}", json={"ticker": "NVDA"})
        assert resp.status_code == 403

    def test_remove_watchlist(self, client, logged_in_user):
        client.post(f"/api/watchlist/{logged_in_user}", json={"ticker": "NVDA"})
        resp = client.delete(f"/api/watchlist/{logged_in_user}/NVDA")
        assert resp.status_code == 200
        assert client.get(f"/api/watchlist/{logged_in_user}").json() == []

    def test_remove_watchlist_not_authorized(self, client, logged_in_user):
        resp = client.delete(f"/api/watchlist/{logged_in_user + 1}/NVDA")
        assert resp.status_code == 403

    def test_get_watchlist_not_authorized(self, client, logged_in_user):
        resp = client.get(f"/api/watchlist/{logged_in_user + 1}")
        assert resp.status_code == 403


class TestPortfolioBalance:
    def test_get_portfolio_balance(self, client, logged_in_user):
        client.post(f"/api/user/{logged_in_user}/deposit", json={"amount": 250.0})
        resp = client.get(f"/api/user/{logged_in_user}/portfolio")
        assert resp.status_code == 200
        assert resp.json()["balance"] == 250.0

    def test_get_portfolio_balance_not_authorized(self, client, logged_in_user):
        resp = client.get(f"/api/user/{logged_in_user + 1}/portfolio")
        assert resp.status_code == 403
    def test_get_portfolio__balance(self, client):
        pass

    def test_get_portfolio__balance_not_authorized(self, client):
        pass

    def test_get_portfolio__balance_failed(self, client):
        pass