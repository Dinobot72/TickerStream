import sqlite3
from datetime import datetime, timedelta
from app.core.database import get_db_connection

# --- CONFIGURATION ---
PDT_MIN_BALANCE = 25000.0       # SEC rule: $25k minimum for pattern day traders
MAX_POSITION_PCT = 0.20         # Never put >20% of buying power into one trade
MAX_DAY_TRADES = 3              # Max day trades in rolling 5-day window
DAILY_LOSS_LIMIT_PCT = 0.02     # Halt trading if portfolio drops 2% in one day

class RiskManager:
    def __init__(self, user_id: int):
        self.user_id = user_id

    def _get_portfolio(self):
        """Return (balance, holdings_dict) where holdings_dict[ticker] = quantity."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (self.user_id,))
        row = cursor.fetchone()
        balance = row['balance'] if row else 0.0

        cursor.execute("SELECT ticker, quantity FROM holdings WHERE user_id = ?", (self.user_id,))
        holdings = {r['ticker']: r['quantity'] for r in cursor.fetchall()}
        conn.close()
        return balance, holdings

    def _count_recent_day_trades(self):
        """
        Count distinct (date, ticker) where both a BUY and a SELL occurred on the same day
        within the last 5 trading days.
        """
        conn = get_db_connection()
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
        conn.close()
        return len(day_trades)

    def _check_daily_loss(self):
        """Return True if portfolio loss today is within limit."""
        conn = get_db_connection()
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        # Get start-of-day balance from just before market open (simplified: use yesterday's closing balance)
        # For simplicity, we'll get the balance at the start of today by looking at the last trade before today.
        # Alternatively, store daily snapshots. We'll approximate: fetch balance from portfolios (current) and
        # assume any drop from previous day's close is today's loss. This is rough but okay for initial version.
        cursor.execute("""
            SELECT balance FROM portfolios WHERE user_id = ?
        """, (self.user_id,))
        current_balance = cursor.fetchone()['balance']

        # Get closing balance from end of previous trading day (last trade before today)
        cursor.execute("""
            SELECT balance FROM portfolios WHERE user_id = ? AND date(timestamp) < date('now')
            ORDER BY timestamp DESC LIMIT 1
        """, (self.user_id,))
        row = cursor.fetchone()
        if row is None:
            # No previous day, assume no loss
            return True
        prev_balance = row['balance']
        conn.close()

        if prev_balance == 0:
            return True
        loss_pct = (prev_balance - current_balance) / prev_balance
        return loss_pct <= DAILY_LOSS_LIMIT_PCT

    def can_trade(self, ticker: str, action: str, price: float, quantity: int):
        """
        Returns (True, "OK") if trade is allowed, otherwise (False, "reason").
        """
        balance, holdings = self._get_portfolio()
        ticker = ticker.upper()

        # 1. Basic cash check for BUY
        if action.upper() == "BUY":
            cost = price * quantity
            if cost > balance:
                return False, f"Insufficient funds. Need ${cost:.2f}, have ${balance:.2f}"

        # 2. Position sizing (only for BUY)
        if action.upper() == "BUY":
            # Max allowed based on current buying power
            max_cost = balance * MAX_POSITION_PCT
            if cost > max_cost:
                return False, f"Position too large. Max allowed is ${max_cost:.2f} ({MAX_POSITION_PCT*100}% of balance)."

        # 3. Daily loss limit
        if not self._check_daily_loss():
            return False, "Daily loss limit exceeded. Trading halted until tomorrow."

        # 4. PDT rule (only if balance < $25k)
        if balance < PDT_MIN_BALANCE:
            recent_day_trades = self._count_recent_day_trades()

            if recent_day_trades >= MAX_DAY_TRADES:
                # Already at limit. We can only SELL positions held from previous days.
                if action.upper() == "BUY":
                    return False, f"PDT Protection: You have {recent_day_trades} day trades. Cannot open new positions."

                # For SELL, check if we bought this ticker today. If so, this would be a day trade.
                if action.upper() == "SELL":
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    today = datetime.now().strftime('%Y-%m-%d')
                    cursor.execute("""
                        SELECT 1 FROM trades
                        WHERE user_id=? AND ticker=? AND action='BUY' AND date(timestamp)=?
                    """, (self.user_id, ticker, today))
                    bought_today = cursor.fetchone()
                    conn.close()
                    if bought_today:
                        return False, "PDT Protection: Selling this today would exceed day trade limit."

        return True, "Trade approved"