"""
Tests for the Alpaca broker integration.

Nothing here touches the network. The Alpaca client is replaced with fakes so
the logic under test is our order handling, gating and state sync — not
alpaca-py's HTTP layer.
"""

import pytest
from cryptography.fernet import Fernet

from app.core import crypto, database
from app.services import broker as broker_mod


# --- Fakes --------------------------------------------------------------------

class FakeAccount:
    account_number = "PA12345"
    status = "ACTIVE"
    cash = 5000.0
    buying_power = 10000.0
    equity = 7500.0
    portfolio_value = 7500.0
    currency = "USD"
    trading_blocked = False
    account_blocked = False
    pattern_day_trader = False
    daytrade_count = 0


class FakePosition:
    symbol = "AAPL"
    qty = "10"
    avg_entry_price = "150.00"
    market_value = "1550"
    unrealized_pl = "50"
    current_price = "155"


class FakeOrder:
    def __init__(self, status="filled", qty=10, filled_qty=10, price=150.25):
        self.id = "order-uuid-1"
        self.client_order_id = "ts-test-1"
        self.status = status
        self.symbol = "AAPL"
        self.side = "buy"
        self.qty = qty
        self.filled_qty = filled_qty
        self.filled_avg_price = price


class FakeTradingClient:
    """Stands in for alpaca.trading.client.TradingClient."""
    order_status = "filled"
    filled_qty = 10
    fill_price = 150.25

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def get_account(self):
        return FakeAccount()

    def get_all_positions(self):
        return [FakePosition()]

    def submit_order(self, request):
        return FakeOrder(self.order_status, filled_qty=self.filled_qty, price=self.fill_price)

    def get_order_by_id(self, order_id):
        return FakeOrder(self.order_status, filled_qty=self.filled_qty, price=self.fill_price)


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    """Every test gets a fresh, valid Fernet key."""
    monkeypatch.setenv("BROKER_ENCRYPTION_KEY", Fernet.generate_key().decode())
    crypto.reset_cache()
    yield
    crypto.reset_cache()


@pytest.fixture
def fake_alpaca(monkeypatch):
    monkeypatch.setattr(broker_mod, "TradingClient", FakeTradingClient)
    monkeypatch.setattr(broker_mod, "BROKER_FILL_POLL_TIMEOUT", 0.05)
    monkeypatch.setattr(broker_mod, "BROKER_FILL_POLL_INTERVAL", 0.01)
    return FakeTradingClient


@pytest.fixture
def linked_user(logged_in_user, fake_alpaca):
    broker_mod.save_credentials(logged_in_user, "PKTESTKEY", "TESTSECRET", mode="paper")
    return logged_in_user


# --- Credential storage -------------------------------------------------------

class TestCredentialStorage:
    def test_keys_are_not_stored_in_plaintext(self, linked_user):
        conn = database.get_db_connection()
        row = conn.execute(
            "SELECT api_key_encrypted, secret_key_encrypted FROM broker_accounts WHERE user_id = ?",
            (linked_user,),
        ).fetchone()
        conn.close()
        assert "PKTESTKEY" not in row["api_key_encrypted"]
        assert "TESTSECRET" not in row["secret_key_encrypted"]

    def test_stored_keys_decrypt_back(self, linked_user):
        conn = database.get_db_connection()
        row = conn.execute(
            "SELECT api_key_encrypted FROM broker_accounts WHERE user_id = ?", (linked_user,)
        ).fetchone()
        conn.close()
        assert crypto.decrypt(row["api_key_encrypted"]) == "PKTESTKEY"

    def test_linking_defaults_to_paper_and_not_live_confirmed(self, linked_user):
        link = broker_mod.get_link(linked_user)
        assert link.mode == "paper"
        assert link.live_confirmed_at is None

    def test_missing_encryption_key_refuses_to_store(self, logged_in_user, fake_alpaca, monkeypatch):
        """Storing plaintext API keys is never an acceptable fallback."""
        monkeypatch.delenv("BROKER_ENCRYPTION_KEY", raising=False)
        crypto.reset_cache()
        with pytest.raises(crypto.CredentialEncryptionUnavailable):
            broker_mod.save_credentials(logged_in_user, "PKTESTKEY", "TESTSECRET")

    def test_unlink_removes_credentials(self, linked_user):
        assert broker_mod.delete_credentials(linked_user) is True
        assert broker_mod.get_link(linked_user) is None

    def test_relinking_clears_prior_live_confirmation(self, linked_user, fake_alpaca):
        conn = database.get_db_connection()
        conn.execute(
            "UPDATE broker_accounts SET live_confirmed_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (linked_user,),
        )
        conn.commit()
        conn.close()
        broker_mod.save_credentials(linked_user, "PKNEWKEY", "NEWSECRET", mode="paper")
        assert broker_mod.get_link(linked_user).live_confirmed_at is None


# --- Gating -------------------------------------------------------------------

class TestLiveTradingGates:
    def _make_live(self, user_id, confirmed=True):
        conn = database.get_db_connection()
        conn.execute(
            "UPDATE broker_accounts SET mode = 'live', live_confirmed_at = ? WHERE user_id = ?",
            ("2026-01-01 00:00:00" if confirmed else None, user_id),
        )
        conn.commit()
        conn.close()

    def test_no_link_returns_none_not_an_error(self, logged_in_user):
        """Users who never link a brokerage keep the simulated behaviour."""
        assert broker_mod.get_broker_for_user(logged_in_user) is None

    def test_disabled_link_falls_back_to_simulation(self, linked_user):
        broker_mod.set_enabled(linked_user, False)
        assert broker_mod.get_broker_for_user(linked_user) is None

    def test_live_refused_when_server_flag_off(self, linked_user, monkeypatch):
        monkeypatch.setattr(broker_mod, "ALLOW_LIVE_TRADING", False)
        self._make_live(linked_user)
        with pytest.raises(broker_mod.LiveTradingDisabled):
            broker_mod.get_broker_for_user(linked_user)

    def test_live_refused_when_never_confirmed(self, linked_user, monkeypatch):
        monkeypatch.setattr(broker_mod, "ALLOW_LIVE_TRADING", True)
        self._make_live(linked_user, confirmed=False)
        with pytest.raises(broker_mod.LiveTradingDisabled):
            broker_mod.get_broker_for_user(linked_user)

    def test_bot_blocked_from_live_by_default(self, linked_user, monkeypatch, fake_alpaca):
        monkeypatch.setattr(broker_mod, "ALLOW_LIVE_TRADING", True)
        monkeypatch.setattr(broker_mod, "ALLOW_LIVE_BOT_TRADING", False)
        self._make_live(linked_user)
        # A human can still trade live...
        assert broker_mod.get_broker_for_user(linked_user, is_bot_trade=False) is not None
        # ...but the RL bot cannot.
        with pytest.raises(broker_mod.LiveTradingDisabled):
            broker_mod.get_broker_for_user(linked_user, is_bot_trade=True)

    def test_bot_live_allowed_once_explicitly_enabled(self, linked_user, monkeypatch, fake_alpaca):
        monkeypatch.setattr(broker_mod, "ALLOW_LIVE_TRADING", True)
        monkeypatch.setattr(broker_mod, "ALLOW_LIVE_BOT_TRADING", True)
        self._make_live(linked_user)
        assert broker_mod.get_broker_for_user(linked_user, is_bot_trade=True) is not None

    def test_paper_client_is_constructed_with_paper_true(self, linked_user, fake_alpaca):
        broker = broker_mod.get_broker_for_user(linked_user)
        assert broker.paper is True


# --- Orders -------------------------------------------------------------------

class TestOrderSubmission:
    def test_filled_order_reports_real_fill_price(self, linked_user, fake_alpaca):
        broker = broker_mod.get_broker_for_user(linked_user)
        result = broker.submit_order("AAPL", "BUY", 10)
        assert result.status == "FILLED"
        assert result.filled_avg_price == 150.25
        assert result.broker_order_id == "order-uuid-1"

    def test_working_order_stays_pending(self, linked_user, fake_alpaca, monkeypatch):
        """A market order placed outside trading hours is accepted, not filled."""
        monkeypatch.setattr(FakeTradingClient, "order_status", "accepted")
        monkeypatch.setattr(FakeTradingClient, "filled_qty", 0)
        broker = broker_mod.get_broker_for_user(linked_user)
        result = broker.submit_order("AAPL", "BUY", 10)
        assert result.status == "PENDING"
        assert result.is_terminal is False

    def test_rejected_order_maps_to_rejected(self, linked_user, fake_alpaca, monkeypatch):
        monkeypatch.setattr(FakeTradingClient, "order_status", "rejected")
        broker = broker_mod.get_broker_for_user(linked_user)
        assert broker.submit_order("AAPL", "BUY", 10).status == "REJECTED"

    def test_partial_fill_maps_to_partial(self, linked_user, fake_alpaca, monkeypatch):
        monkeypatch.setattr(FakeTradingClient, "order_status", "partially_filled")
        monkeypatch.setattr(FakeTradingClient, "filled_qty", 4)
        broker = broker_mod.get_broker_for_user(linked_user)
        result = broker.submit_order("AAPL", "BUY", 10)
        assert result.status == "PARTIAL"
        assert result.filled_qty == 4

    def test_each_order_gets_a_unique_client_order_id(self, linked_user, fake_alpaca):
        """Idempotency key — a retry after a crash must not double the position."""
        captured = []

        class Capturing(FakeTradingClient):
            def submit_order(self, request):
                captured.append(request.client_order_id)
                return FakeOrder()

        broker = broker_mod.AlpacaBroker.__new__(broker_mod.AlpacaBroker)
        broker._client = Capturing()
        broker.paper = True
        broker.user_id = linked_user
        broker.submit_order("AAPL", "BUY", 1)
        broker.submit_order("AAPL", "BUY", 1)
        assert len(set(captured)) == 2


# --- State sync ---------------------------------------------------------------

class TestPortfolioSync:
    def test_sync_pulls_cash_and_positions_from_broker(self, linked_user, fake_alpaca):
        broker_mod.sync_portfolio_from_broker(linked_user)
        conn = database.get_db_connection()
        balance = conn.execute(
            "SELECT balance FROM portfolios WHERE user_id = ?", (linked_user,)
        ).fetchone()["balance"]
        holdings = conn.execute(
            "SELECT ticker, quantity, purchase_price FROM holdings WHERE user_id = ?", (linked_user,)
        ).fetchall()
        conn.close()
        assert balance == 5000.0          # cash, not equity
        assert len(holdings) == 1
        assert holdings[0]["ticker"] == "AAPL"
        assert holdings[0]["quantity"] == 10

    def test_sync_uses_cash_not_portfolio_value(self, linked_user, fake_alpaca):
        """Using portfolio_value would let the bot 'spend' money already in stock."""
        broker_mod.sync_portfolio_from_broker(linked_user)
        conn = database.get_db_connection()
        balance = conn.execute(
            "SELECT balance FROM portfolios WHERE user_id = ?", (linked_user,)
        ).fetchone()["balance"]
        conn.close()
        assert balance != FakeAccount.portfolio_value

    def test_sync_removes_positions_closed_outside_the_app(self, linked_user, fake_alpaca):
        """A position sold on Alpaca's own website must disappear locally."""
        conn = database.get_db_connection()
        conn.execute(
            "INSERT INTO holdings (user_id, ticker, quantity, purchase_price) VALUES (?, 'STALE', 99, 1.0)",
            (linked_user,),
        )
        conn.commit()
        conn.close()

        broker_mod.sync_portfolio_from_broker(linked_user)

        conn = database.get_db_connection()
        tickers = {r["ticker"] for r in conn.execute(
            "SELECT ticker FROM holdings WHERE user_id = ?", (linked_user,)
        ).fetchall()}
        conn.close()
        assert "STALE" not in tickers

    def test_sync_without_link_raises(self, logged_in_user):
        with pytest.raises(broker_mod.BrokerNotLinked):
            broker_mod.sync_portfolio_from_broker(logged_in_user)


# --- Reconciliation -----------------------------------------------------------

class TestReconciliation:
    def test_pending_order_is_updated_once_filled(self, linked_user, fake_alpaca):
        conn = database.get_db_connection()
        conn.execute(
            """
            INSERT INTO trades (user_id, ticker, action, quantity, price, is_bot_trade,
                                broker_order_id, status, mode)
            VALUES (?, 'AAPL', 'BUY', 10, 149.00, 0, 'order-uuid-1', 'PENDING', 'paper')
            """,
            (linked_user,),
        )
        conn.commit()
        conn.close()

        result = broker_mod.reconcile_open_orders(linked_user)
        assert result["updated"] == 1

        conn = database.get_db_connection()
        row = conn.execute(
            "SELECT status, price FROM trades WHERE broker_order_id = 'order-uuid-1'"
        ).fetchone()
        conn.close()
        assert row["status"] == "FILLED"
        assert row["price"] == 150.25  # real fill, replacing the estimate

    def test_reconcile_is_a_noop_without_a_link(self, logged_in_user):
        assert broker_mod.reconcile_open_orders(logged_in_user) == {"checked": 0, "updated": 0}
