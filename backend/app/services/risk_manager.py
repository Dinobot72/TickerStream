import sqlite3
from datetime import datetime, timedelta
from app.core.database import get_db_connection

# --- CONFIGURATION ---
PDT_MIN_BALANCE = 25000.0       # SEC rule: $25k minimum for pattern day traders
MAX_POSITION_PCT = 0.50         # Never put more than this fraction of buying power
                                 # into one trade. NOTE: keep this >= PortfolioManager's
                                 # generate_trade_plan(position_size_pct=...) default,
                                 # or every default-sized BUY gets silently rejected here
                                 # (was 0.40 with a comment claiming 20% - neither matched
                                 # the live 0.45 default actually being used).
MAX_DAY_TRADES = 3              # Max day trades in rolling 5-day window
DAILY_LOSS_LIMIT_PCT = 0.02     # Halt trading if portfolio drops 2% in one day

class RiskManager:
    def __init__(self, user_id: int):
        self.user_id = user_id

    def _get_portfolio(self):
        """Return (balance, holdings_dict) where holdings_dict[ticker] = quantity."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (self.user_id,))
            row = cursor.fetchone()
            balance = row['balance'] if row else 0.0

            cursor.execute("SELECT ticker, quantity FROM holdings WHERE user_id = ?", (self.user_id,))
            holdings = {r['ticker']: r['quantity'] for r in cursor.fetchall()}
            return balance, holdings
        finally:
            conn.close()

    def _count_recent_day_trades(self):
        """
        Count distinct (date, ticker) where both a BUY and a SELL occurred on the same day
        within the last 5 trading days.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            five_days_ago = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
            query = """
                SELECT date(t1.timestamp) as trade_date, t1.ticker
                FROM trades t1
                JOIN trades t2 ON t1.ticker = t2.ticker
                              AND date(t1.timestamp) = date(t2.timestamp)
                              AND t1.user_id = t2.user_id
                WHERE t1.user_id = ?
                  AND t1.timestamp >= ?
                  AND t1.action = 'BUY'
                  AND t2.action = 'SELL'
                GROUP BY trade_date, t1.ticker
            """
            cursor.execute(query, (self.user_id, five_days_ago))
            day_trades = cursor.fetchall()
            return len(day_trades)
        finally:
            conn.close()

    def _check_daily_loss(self):
        """Return True if portfolio loss today is within limit.

        Compares the live `portfolios.balance` against the most recent
        prior-day row in `portfolio_snapshots`. `portfolios` itself only
        ever holds one (mutable) row per user, so it can't tell us what
        the balance was yesterday — the snapshot table can.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT balance FROM portfolios WHERE user_id = ?
            """, (self.user_id,))
            current_row = cursor.fetchone()
            if current_row is None:
                # No portfolio row at all yet — nothing to compare against.
                return True
            current_balance = current_row['balance']

            # Most recent snapshot strictly before today.
            cursor.execute("""
                SELECT balance FROM portfolio_snapshots
                WHERE user_id = ? AND snapshot_date < date('now')
                ORDER BY snapshot_date DESC LIMIT 1
            """, (self.user_id,))
            row = cursor.fetchone()
            if row is None:
                # No prior snapshot yet, assume no loss
                return True
            prev_balance = row['balance']

            if prev_balance == 0:
                return True
            loss_pct = (prev_balance - current_balance) / prev_balance
            return loss_pct <= DAILY_LOSS_LIMIT_PCT
        finally:
            conn.close()

    def record_daily_snapshot(self):
        """Record today's balance as a snapshot for future loss comparisons.

        Call this once per day (e.g. on the first trade of the day, or via
        a scheduled job at market open) — NOT on every trade, or every
        snapshot will just equal "now" and the loss check will again
        always compare a balance to itself.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (self.user_id,))
            row = cursor.fetchone()
            if row is None:
                return
            cursor.execute("""
                INSERT INTO portfolio_snapshots (user_id, snapshot_date, balance)
                VALUES (?, date('now'), ?)
                ON CONFLICT(user_id, snapshot_date) DO NOTHING
            """, (self.user_id, row['balance']))
            conn.commit()
        finally:
            conn.close()

    def can_trade(self, ticker: str, action: str, price: float, quantity: int):
        """
        Returns (True, "OK") if trade is allowed, otherwise (False, "reason").
        """
        action = action.upper()
        ticker = ticker.upper()

        if action not in ("BUY", "SELL"):
            return False, f"Unknown action '{action}'. Must be BUY or SELL."
        if quantity <= 0:
            return False, "Quantity must be greater than zero."
        if price <= 0:
            return False, "Price must be greater than zero."

        balance, holdings = self._get_portfolio()
        cost = price * quantity

        # 1. Basic cash check for BUY
        if action == "BUY":
            if cost > balance:
                return False, f"Insufficient funds. Need ${cost:.2f}, have ${balance:.2f}"

            # 2. Position sizing
            max_cost = balance * MAX_POSITION_PCT
            if cost > max_cost:
                return False, f"Position too large. Max allowed is ${max_cost:.2f} ({MAX_POSITION_PCT*100}% of balance)."

        # 2b. Can't sell what you don't hold
        if action == "SELL":
            owned = holdings.get(ticker, 0)
            if quantity > owned:
                return False, f"Insufficient shares. You hold {owned} of {ticker}, tried to sell {quantity}."

        # 3. Daily loss limit
        if not self._check_daily_loss():
            return False, "Daily loss limit exceeded. Trading halted until tomorrow."

        # 4. PDT rule (only if balance < $25k)
        if balance < PDT_MIN_BALANCE:
            recent_day_trades = self._count_recent_day_trades()

            if recent_day_trades >= MAX_DAY_TRADES:
                # Already at limit. We can only SELL positions held from previous days.
                if action == "BUY":
                    return False, f"PDT Protection: You have {recent_day_trades} day trades. Cannot open new positions."

                # For SELL, check if we bought this ticker today. If so, this would be a day trade.
                if action == "SELL":
                    conn = get_db_connection()
                    try:
                        cursor = conn.cursor()
                        today = datetime.now().strftime('%Y-%m-%d')
                        cursor.execute("""
                            SELECT 1 FROM trades
                            WHERE user_id=? AND ticker=? AND action='BUY' AND date(timestamp)=?
                        """, (self.user_id, ticker, today))
                        bought_today = cursor.fetchone()
                    finally:
                        conn.close()
                    if bought_today:
                        return False, "PDT Protection: Selling this today would exceed day trade limit."

        return True, "Trade approved"