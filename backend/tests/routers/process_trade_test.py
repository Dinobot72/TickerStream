"""
Tests for process_trade() — the single execution choke point shared by the
manual /api/trade/ endpoint and the bot scheduler.

Covers both execution paths (simulated vs broker-routed) and the ledger
invariants the simulated path must not violate.
"""

import pytest
from cryptography.fernet import Fernet

from app.core import crypto, database
from app.routers.trading import process_trade
from app.services import broker as broker_mod

from tests.services.broker_test import FakeTradingClient  # reuse the Alpaca fake


@pytest.fixture
def funded_user(logged_in_user):
    # Registration already creates a portfolio row at 0.00 — fund it rather than
    # inserting a second one.
    conn = database.get_db_connection()
    conn.execute(
        "INSERT INTO portfolios (user_id, balance) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET balance = excluded.balance",
        (logged_in_user, 10000.0),
    )
    conn.commit()
    conn.close()
    return logged_in_user


def _balance(user_id):
    conn = database.get_db_connection()
    row = conn.execute("SELECT balance FROM portfolios WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row["balance"]


def _qty(user_id, ticker):
    conn = database.get_db_connection()
    row = conn.execute(
        "SELECT quantity FROM holdings WHERE user_id = ? AND ticker = ?", (user_id, ticker)
    ).fetchone()
    conn.close()
    return row["quantity"] if row else 0


class TestSimulatedPath:
    def test_buy_debits_cash_and_creates_holding(self, funded_user):
        result = process_trade(funded_user, "AAPL", "BUY", 10, 100.0, False)
        assert "error" not in result
        assert result["mode"] == "simulated"
        assert _balance(funded_user) == 9000.0
        assert _qty(funded_user, "AAPL") == 10

    def test_insufficient_funds_rejected(self, funded_user):
        result = process_trade(funded_user, "AAPL", "BUY", 1000, 100.0, False)
        assert "error" in result
        assert _balance(funded_user) == 10000.0

    def test_zero_quantity_rejected(self, funded_user):
        assert "error" in process_trade(funded_user, "AAPL", "BUY", 0, 100.0, False)

    def test_valid_sell_credits_cash_and_closes_position(self, funded_user):
        process_trade(funded_user, "AAPL", "BUY", 10, 100.0, False)
        result = process_trade(funded_user, "AAPL", "SELL", 10, 110.0, False)
        assert "error" not in result
        assert _balance(funded_user) == 9000.0 + 1100.0
        assert _qty(funded_user, "AAPL") == 0


class TestOversellCannotMintCash:
    """Regression tests.

    The original process_trade() credited sale proceeds and *then* decremented
    holdings, with no check that the shares existed. A SELL signal on a ticker
    the user did not hold created cash out of nothing and drove holdings
    negative — in an app whose whole point is an autonomous bot emitting SELL
    signals, that silently corrupts every downstream P&L number.
    """

    def test_selling_unheld_stock_is_rejected(self, funded_user):
        result = process_trade(funded_user, "TSLA", "SELL", 5, 100.0, False)
        assert "error" in result
        assert _balance(funded_user) == 10000.0

    def test_selling_more_than_held_is_rejected(self, funded_user):
        process_trade(funded_user, "AAPL", "BUY", 10, 100.0, False)
        before = _balance(funded_user)
        result = process_trade(funded_user, "AAPL", "SELL", 999, 100.0, False)
        assert "error" in result
        assert _balance(funded_user) == before

    def test_holdings_never_go_negative(self, funded_user):
        process_trade(funded_user, "AAPL", "BUY", 10, 100.0, False)
        process_trade(funded_user, "AAPL", "SELL", 999, 100.0, False)
        assert _qty(funded_user, "AAPL") == 10

    def test_bot_trades_are_held_to_the_same_rule(self, funded_user):
        """The bot is exactly the caller most likely to emit a bad SELL."""
        result = process_trade(funded_user, "NVDA", "SELL", 50, 100.0, True)
        assert "error" in result


class TestBrokerRouting:
    @pytest.fixture(autouse=True)
    def _encryption(self, monkeypatch):
        monkeypatch.setenv("BROKER_ENCRYPTION_KEY", Fernet.generate_key().decode())
        crypto.reset_cache()
        yield
        crypto.reset_cache()

    @pytest.fixture
    def broker_user(self, funded_user, monkeypatch):
        monkeypatch.setattr(broker_mod, "TradingClient", FakeTradingClient)
        monkeypatch.setattr(broker_mod, "BROKER_FILL_POLL_TIMEOUT", 0.05)
        monkeypatch.setattr(broker_mod, "BROKER_FILL_POLL_INTERVAL", 0.01)
        broker_mod.save_credentials(funded_user, "PKTESTKEY", "TESTSECRET", mode="paper")
        return funded_user

    def test_linked_user_is_routed_to_the_broker(self, broker_user):
        result = process_trade(broker_user, "AAPL", "BUY", 10, 149.00, False)
        assert "error" not in result
        assert result["mode"] == "paper"
        assert result["broker_order_id"] == "order-uuid-1"

    def test_recorded_price_is_the_fill_not_the_quote(self, broker_user):
        """149.00 was the app's quote; 150.25 is what Alpaca actually filled at."""
        result = process_trade(broker_user, "AAPL", "BUY", 10, 149.00, False)
        conn = database.get_db_connection()
        row = conn.execute(
            "SELECT price, mode, status FROM trades WHERE trade_id = ?", (result["trade_id"],)
        ).fetchone()
        conn.close()
        assert row["price"] == 150.25
        assert row["status"] == "FILLED"
        assert row["mode"] == "paper"

    def test_local_state_is_resynced_from_alpaca_after_a_fill(self, broker_user):
        process_trade(broker_user, "AAPL", "BUY", 10, 149.00, False)
        # Balance now reflects Alpaca's cash figure, not local arithmetic.
        assert _balance(broker_user) == 5000.0

    def test_unusable_link_errors_rather_than_silently_simulating(self, broker_user, monkeypatch):
        """The worst failure mode would be faking a trade the user thinks is real."""
        monkeypatch.setattr(broker_mod, "ALLOW_LIVE_TRADING", False)
        conn = database.get_db_connection()
        conn.execute(
            "UPDATE broker_accounts SET mode = 'live', live_confirmed_at = '2026-01-01' "
            "WHERE user_id = ?",
            (broker_user,),
        )
        conn.commit()
        conn.close()

        result = process_trade(broker_user, "AAPL", "BUY", 10, 149.00, False)
        assert "error" in result

        conn = database.get_db_connection()
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM trades WHERE user_id = ?", (broker_user,)
        ).fetchone()["c"]
        conn.close()
        assert count == 0  # nothing recorded, simulated or otherwise

    def test_pending_order_is_recorded_not_dropped(self, broker_user, monkeypatch):
        monkeypatch.setattr(FakeTradingClient, "order_status", "accepted")
        monkeypatch.setattr(FakeTradingClient, "filled_qty", 0)
        result = process_trade(broker_user, "AAPL", "BUY", 10, 149.00, False)
        assert result["status"] == "PENDING"
        conn = database.get_db_connection()
        row = conn.execute(
            "SELECT status, price FROM trades WHERE trade_id = ?", (result["trade_id"],)
        ).fetchone()
        conn.close()
        assert row["status"] == "PENDING"
        assert row["price"] == 149.00  # estimate held until reconciliation
