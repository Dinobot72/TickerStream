from datetime import datetime, timedelta
from app.core import database
from app.services.risk_manager import RiskManager, MAX_DAY_TRADES


def set_balance(user_id, balance):
    conn = database.get_db_connection()
    conn.execute("UPDATE portfolios SET balance = ? WHERE user_id = ?", (balance, user_id))
    conn.commit()
    conn.close()


def add_holding(user_id, ticker, quantity, purchase_price=100.0):
    conn = database.get_db_connection()
    conn.execute(
        "INSERT INTO holdings (user_id, ticker, quantity, purchase_price) VALUES (?, ?, ?, ?)",
        (user_id, ticker, quantity, purchase_price),
    )
    conn.commit()
    conn.close()


def add_trade(user_id, ticker, action, quantity=1, price=100.0):
    conn = database.get_db_connection()
    conn.execute(
        "INSERT INTO trades (user_id, ticker, action, quantity, price) VALUES (?, ?, ?, ?, ?)",
        (user_id, ticker, action, quantity, price),
    )
    conn.commit()
    conn.close()


def add_snapshot(user_id, balance, days_ago=1):
    conn = database.get_db_connection()
    snap_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO portfolio_snapshots (user_id, snapshot_date, balance) VALUES (?, ?, ?)",
        (user_id, snap_date, balance),
    )
    conn.commit()
    conn.close()


class TestBasicValidation:
    def test_unknown_action_rejected(self, logged_in_user):
        allowed, msg = RiskManager(logged_in_user).can_trade("AAPL", "HOLD", 100.0, 1)
        assert allowed is False
        assert "Unknown action" in msg

    def test_zero_quantity_rejected(self, logged_in_user):
        allowed, msg = RiskManager(logged_in_user).can_trade("AAPL", "BUY", 100.0, 0)
        assert allowed is False
        assert "Quantity" in msg

    def test_negative_price_rejected(self, logged_in_user):
        allowed, msg = RiskManager(logged_in_user).can_trade("AAPL", "BUY", -5.0, 1)
        assert allowed is False
        assert "Price" in msg


class TestBuyChecks:
    def test_insufficient_funds(self, logged_in_user):
        set_balance(logged_in_user, 100.0)
        allowed, msg = RiskManager(logged_in_user).can_trade("AAPL", "BUY", 50.0, 5)  # cost 250 > balance
        assert allowed is False
        assert "Insufficient funds" in msg

    def test_position_size_limit(self, logged_in_user):
        set_balance(logged_in_user, 1000.0)  # max position = 500; cost = 550
        allowed, msg = RiskManager(logged_in_user).can_trade("AAPL", "BUY", 50.0, 11)
        assert allowed is False
        assert "Position too large" in msg

    def test_buy_within_limits_approved(self, logged_in_user):
        set_balance(logged_in_user, 10000.0)  # above PDT floor, avoids that branch entirely
        allowed, _ = RiskManager(logged_in_user).can_trade("AAPL", "BUY", 50.0, 5)  # cost 250, well under 20%
        assert allowed is True


class TestSellChecks:
    def test_cannot_sell_unheld_stock(self, logged_in_user):
        set_balance(logged_in_user, 10000.0)
        allowed, msg = RiskManager(logged_in_user).can_trade("AAPL", "SELL", 50.0, 5)
        assert allowed is False
        assert "Insufficient shares" in msg

    def test_cannot_sell_more_than_held(self, logged_in_user):
        set_balance(logged_in_user, 10000.0)
        add_holding(logged_in_user, "AAPL", quantity=3)
        allowed, msg = RiskManager(logged_in_user).can_trade("AAPL", "SELL", 50.0, 5)
        assert allowed is False
        assert "hold 3" in msg

    def test_sell_within_holding_approved(self, logged_in_user):
        set_balance(logged_in_user, 10000.0)
        add_holding(logged_in_user, "AAPL", quantity=10)
        allowed, _ = RiskManager(logged_in_user).can_trade("AAPL", "SELL", 50.0, 5)
        assert allowed is True


class TestDailyLossLimit:
    def test_no_snapshot_defaults_to_allowed(self, logged_in_user):
        set_balance(logged_in_user, 10000.0)
        allowed, _ = RiskManager(logged_in_user).can_trade("AAPL", "BUY", 50.0, 1)
        assert allowed is True

    def test_loss_within_limit_allowed(self, logged_in_user):
        add_snapshot(logged_in_user, balance=10000.0)
        set_balance(logged_in_user, 9900.0)  # 1% loss, limit is 2%
        allowed, _ = RiskManager(logged_in_user).can_trade("AAPL", "BUY", 50.0, 1)
        assert allowed is True

    def test_loss_exceeding_limit_blocks_trade(self, logged_in_user):
        add_snapshot(logged_in_user, balance=10000.0)
        set_balance(logged_in_user, 9000.0)  # 10% loss, exceeds 2% limit
        allowed, msg = RiskManager(logged_in_user).can_trade("AAPL", "BUY", 50.0, 1)
        assert allowed is False
        assert "Daily loss limit" in msg


class TestPDTRule:
    def test_blocks_new_buy_after_max_day_trades(self, logged_in_user):
        set_balance(logged_in_user, 10000.0)  # under PDT_MIN_BALANCE triggers the check
        for i in range(MAX_DAY_TRADES):
            ticker = f"TICK{i}"
            add_trade(logged_in_user, ticker, "BUY")
            add_trade(logged_in_user, ticker, "SELL")
        allowed, msg = RiskManager(logged_in_user).can_trade("NEWSTOCK", "BUY", 50.0, 1)
        assert allowed is False
        assert "PDT Protection" in msg

    def test_allows_sell_of_position_not_bought_today(self, logged_in_user):
        set_balance(logged_in_user, 10000.0)
        add_holding(logged_in_user, "OLDSTOCK", quantity=10)  # never appears in trades table
        for i in range(MAX_DAY_TRADES):
            ticker = f"TICK{i}"
            add_trade(logged_in_user, ticker, "BUY")
            add_trade(logged_in_user, ticker, "SELL")
        allowed, _ = RiskManager(logged_in_user).can_trade("OLDSTOCK", "SELL", 50.0, 5)
        assert allowed is True

    def test_pdt_rule_skipped_above_min_balance(self, logged_in_user):
        set_balance(logged_in_user, 30000.0)  # above PDT_MIN_BALANCE, rule doesn't apply
        for i in range(MAX_DAY_TRADES):
            ticker = f"TICK{i}"
            add_trade(logged_in_user, ticker, "BUY")
            add_trade(logged_in_user, ticker, "SELL")
        allowed, _ = RiskManager(logged_in_user).can_trade("NEWSTOCK", "BUY", 50.0, 1)
        assert allowed is True