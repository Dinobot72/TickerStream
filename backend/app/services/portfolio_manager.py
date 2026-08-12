import os
from typing import List, Dict, Optional, Tuple
import sqlite3


from app.services.ai_scorer import AIScorer
from app.services.data_prep_live import get_current_price, N_CANDIDATES


_default_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tickerstream.db')
DB_PATH = os.getenv("DATABASE_PATH", _default_path)


class PortfolioManager:
    """
    High-level portfolio management using AI scoring.
    Handles stock selection, position sizing, and trade generation.
    """


    def __init__(
        self,
        user_id: int,
        model_path: str = None,
        db_path: str = DB_PATH, 
        scorer: Optional[AIScorer] = None
    ):
        """
        Initialize portfolio manager.
        
        Args:
            user_id: Database user ID
            model_path: Path to trained AI model. Ignored if `scorer` is provided.
            db_path: Path to SQLite database
            scorer: An already-loaded AIScorer to reuse. The scheduler shares one
                AIScorer instance across every active user's PortfolioManager so the
                (large) RL model is only loaded into memory once, not once per user.
        """
        self.user_id = user_id
        self.scorer = scorer if scorer is not None else AIScorer(model_path)
        self.db_path = db_path

        
    def get_db_connection(self):
        """Create database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_current_portfolio(self) -> Tuple[float, Dict[str, Dict]]:
        """
        Get current balance and holdings.
        
        Returns:
            (balance, holdings) where holdings[ticker] = {"quantity": int, "purchase_price": float}.
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get balance
        cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (self.user_id,))
        row = cursor.fetchone()
        balance = row['balance'] if row else 0.0
        
        # Get holdings
        cursor.execute(
            "SELECT ticker, quantity, purchase_price FROM holdings WHERE user_id = ? AND quantity > 0",
            (self.user_id,),
        )
        holdings = {
            row["ticker"]: {"quantity": row["quantity"], "purchase_price": row["purchase_price"]}
            for row in cursor.fetchall()
        }
        
        conn.close()
        return balance, holdings
    
    def get_watchlist(self) -> List[str]:
        """
        Get the tickers this user's bot should consider trading.
 
        This is the UNION of:
          1. `bot_watchlist` — the screener's picks, synced per-user by
             screener.update_bot_watchlist() whenever the bot is active.
          2. `watchlist` — the user's own manually-curated watchlist (the
             same table backing the Watchlist page). Anything a user tracks
             themselves is automatically eligible for the bot to trade too.
 
        Deduplicated, order not guaranteed.
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
 
        cursor.execute("SELECT ticker FROM bot_watchlist WHERE user_id = ?", (self.user_id,))
        bot_tickers = {row['ticker'] for row in cursor.fetchall()}
 
        cursor.execute("SELECT ticker FROM watchlist WHERE user_id = ?", (self.user_id,))
        personal_tickers = {row['ticker'] for row in cursor.fetchall()}
 
        conn.close()
        return list(bot_tickers | personal_tickers)
    
    def get_day_trades_used(self) -> int:
        """Count day trades (same-day buy+sell pairs) in the last 5 days."""
        """Not currently used as day trades aren't legally available"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT COUNT(DISTINCT date(t1.timestamp) || '-' || t1.ticker) as day_trades
            FROM trades t1
            JOIN trades t2 ON t1.ticker = t2.ticker
                          AND date(t1.timestamp) = date(t2.timestamp)
                          AND t1.user_id = t2.user_id
            WHERE t1.user_id = ?
              AND t1.timestamp >= date('now', '-5 days')
              AND t1.action = 'BUY'
              AND t2.action = 'SELL'
        """
        
        cursor.execute(query, (self.user_id,))
        result = cursor.fetchone()
        conn.close()
        
        return result["day_trades"] if result and result["day_trades"] else 0
    
    def _build_candidates(self, watchlist: List[str], held_tickers: List[str]) -> List[str]:
        """
        Build a fixed-length N_CANDIDATES list for the observation space.

        FIX: v2 requires exactly N_CANDIDATES tickers every call. We pull from the
        watchlist, pad/trim as needed, and ensure any currently-held ticker is included
        (so the model can see its own position in context).
        """
        # Start with held tickers so the model always sees what we own
        pool: List[str] = []
        for t in held_tickers:
            if t not in pool:
                pool.append(t)
        for t in watchlist:
            if t not in pool:
                pool.append(t)

        if len(pool) >= N_CANDIDATES:
            return pool[:N_CANDIDATES]

        # Pad with the first watchlist entries repeated if we don't have enough
        while len(pool) < N_CANDIDATES and watchlist:
            for t in watchlist:
                if len(pool) >= N_CANDIDATES:
                    break
                if t not in pool:
                    pool.append(t)
            break  # Avoid infinite loop if watchlist is tiny

        # Last resort: repeat tickers
        while len(pool) < N_CANDIDATES:
            pool.append(pool[0] if pool else "SPY")

        return pool[:N_CANDIDATES]

    def score_all_stocks(self, candidates: List[str]) -> List[Dict]:
        """
        Score each ticker as a potential trade target.
 
        FIX: Calls AIScorer with the v2 signature — all N_CANDIDATES tickers are
        passed together as the observation window. For each evaluation we rotate the
        ticker of interest to position 0 (held_ticker) so the portfolio features
        reflect that stock's position accurately.
        """
        balance, holdings = self.get_current_portfolio()
        day_trades = self.get_day_trades_used()
        held_tickers = list(holdings.keys())
 
        # Build the fixed-size candidate window
        candidate_window = self._build_candidates(candidates, held_tickers)
 
        opportunities = []
 
        for ticker in candidates:
            holding = holdings.get(ticker, {})
            shares = holding.get("quantity", 0)
            entry_price = holding.get("purchase_price", 0.0)
 
            # Rotate ticker to front of window so it's the "held_ticker" the model focuses on
            window = candidate_window.copy()
            if ticker in window:
                window.remove(ticker)
            window = [ticker] + window[:N_CANDIDATES - 1]
 
            score = self.scorer.score_stock(
                candidates=window,
                held_ticker=ticker if shares > 0 else None,
                balance=balance,
                shares=shares,
                entry_price=entry_price,
                days_held=day_trades,  # approximation; replace with real days_held if tracked
            )
 
            if "error" not in score:
                opportunities.append(
                    {
                        "ticker": ticker,
                        "action": score["action"],
                        "confidence": score["confidence"],
                        "current_price": score.get("current_price") or get_current_price(ticker),
                        "current_position": shares,
                    }
                )
            else:
                print(f"⚠️  Score error for {ticker}: {score['error']}")
 
        opportunities.sort(key=lambda x: x["confidence"], reverse=True)
        return opportunities
    
    def generate_trade_plan(
        self, 
        max_positions: int = 5,
        min_buy_confidence: float = 0.65,
        min_sell_confidence: float = 0.60,
        position_size_pct: float = 0.20
    ) -> List[Dict]:
        """
        Generate a list of trades to execute.
        
        Args:
            max_positions: Maximum number of concurrent positions
            min_buy_confidence: Minimum confidence to open new position
            min_sell_confidence: Minimum confidence to close position
            position_size_pct: % of balance to allocate per position
            
        Returns:
            List of trade dictionaries
        """
        # Get candidates from this user's bot_watchlist + personal watchlist
        candidates = self.get_watchlist()
        print(f'candidates: {candidates}')
        
        if not candidates:
            print(f"⚠️  No stocks in watchlist for user {self.user_id}. Cannot generate trades.")
            return []
        
        # Score all candidates
        opportunities = self.score_all_stocks(candidates)
        print(f'opportunities: {opportunities}')
        
        # Also score existing holdings not already covered above (i.e. positions
        # Also score existing holdings (not in watchlist)
        # the user holds that fell out of their bot_watchlist/personal watchlist).
        balance, holdings = self.get_current_portfolio()
        balance, holdings = self.get_current_portfolio()
        held_tickers = list(holdings.keys())
        day_trades = self.get_day_trades_used()
        
        for ticker in held_tickers:
            if ticker in candidates:
                continue  # already scored above via score_all_stocks
 
            holding = holdings[ticker]
            window = self._build_candidates([ticker], held_tickers)
            if ticker in window:
                window.remove(ticker)
            window = [ticker] + window[:N_CANDIDATES - 1]
 
            score = self.scorer.score_stock(
                candidates=window,
                held_ticker=ticker,
                balance=balance,
                shares=holding["quantity"],
                entry_price=holding["purchase_price"],
                days_held=day_trades,
            )
            print(f'ticker: {ticker}, score: {score}')
            if "error" not in score:
                opportunities.append({
                    "ticker": ticker,
                    "action": score['action'],
                    "confidence": score['confidence'],
                    "current_price": score.get('current_price') or get_current_price(ticker),
                    "current_position": holding["quantity"],
                })
            else:
                print(f"⚠️  Score error for held position {ticker}: {score['error']}")
        
        trades = []
        
        # 1. SELL SIGNALS (free up capital first)
        for opp in opportunities:
            print('sell start')
            if opp['action'] == 'SELL' and opp['current_position'] > 0:
                print('sell criteria met')
                if opp['confidence'] >= min_sell_confidence:
                    print('sell confidence met')
                    trades.append({
                        "ticker": opp['ticker'],
                        "action": "SELL",
                        "quantity": opp['current_position'],
                        "price": opp['current_price'],
                        "confidence": opp['confidence'],
                        "reason": f"AI Exit Signal ({opp['confidence']:.1%} confidence)"
                    })
                    
                    # Reset LSTM state since we're closing position
                    self.scorer.reset_state(opp['ticker'])
        
        # 2. BUY SIGNALS (new positions)
        num_current_positions = len(holdings)
        num_sells = len([t for t in trades if t['action'] == 'SELL'])
        slots_available = max_positions - num_current_positions + num_sells
        print(f'slots available: {slots_available}')
        
        if slots_available > 0:
            buy_candidates = [
                o for o in opportunities 
                if o['action'] == 'BUY' 
                and o['current_position'] == 0  # Not already holding
                and o['confidence'] >= min_buy_confidence
            ]
            print(f'buy candidates: {buy_candidates}')
            
            for opp in buy_candidates[:slots_available]:
                allocation = balance * position_size_pct
                price = opp['current_price']
                
                if price > 0:
                    quantity = int(allocation / price)
                    
                    if quantity > 0:
                        trades.append({
                            "ticker": opp['ticker'],
                            "action": "BUY",
                            "quantity": quantity,
                            "price": price,
                            "confidence": opp['confidence'],
                            "reason": f"AI Entry Signal ({opp['confidence']:.1%} confidence)"
                        })
        print('Generated trade plan')
        return trades
    
    # def get_portfolio_summary(self) -> Dict:
    #     """Get summary of current portfolio with AI scores."""
    #     balance, holdings = self.get_current_portfolio()
        
    #     total_value = balance
    #     positions = []
    #     print(holdings.items())
    #     for ticker, info in holdings.items():
    #         qty = info['quantity']
    #         print(f'ticker: {ticker}')
    #         print(f'qty: {qty}')
    #         price = get_current_price(ticker)
    #         if price:
    #             value = qty * price
    #             total_value += value
                
    #             score = self.scorer.score_stock(ticker, balance, qty)
                
    #             positions.append({
    #                 "ticker": ticker,
    #                 "quantity": qty,
    #                 "price": price,
    #                 "value": value,
    #                 "ai_signal": score.get('action', 'UNKNOWN'),
    #                 "confidence": score.get('confidence', 0)
    #             })
        
    #     return {
    #         "balance": balance,
    #         "total_value": total_value,
    #         "positions": positions,
    #         "num_positions": len(positions)
    #     }


if __name__ == "__main__":
    # Test the portfolio manager
    print("=== Testing Portfolio Manager ===\n")
    
    try:
        pm = PortfolioManager(
            user_id=11,
            model_path="../model/logs/best_model/best_model",
            db_path="./tickerstream.db"
        )
        
        # # Get portfolio summary
        # summary = pm.get_portfolio_summary()
        # print(f"Portfolio Value: ${summary['total_value']:,.2f}")
        # print(f"Cash Balance: ${summary['balance']:,.2f}")
        # print(f"Positions: {summary['num_positions']}\n")
        
        # Generate trade plan
        trades = pm.generate_trade_plan(max_positions=5)
        
        if trades:
            print(f"Generated {len(trades)} trade(s):\n")
            for trade in trades:
                print(f"  {trade['action']} {trade['quantity']} {trade['ticker']} @ ${trade['price']:.2f}")
                print(f"    → {trade['reason']}\n")
        else:
            print("No trades generated (no high-confidence signals)")
            
    except Exception as e:
        print(f"Error: {e}")