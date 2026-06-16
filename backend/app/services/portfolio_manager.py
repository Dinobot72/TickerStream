"""
Portfolio Manager
Orchestrates stock selection, scoring, and trade generation
"""

from typing import List, Dict, Tuple
from app.services.ai_scorer import AIScorer
from app.services.data_prep_live import get_current_price
import sqlite3


class PortfolioManager:
    """
    High-level portfolio management using AI scoring.
    Handles stock selection, position sizing, and trade generation.
    """
    
    def __init__(self, user_id: int, model_path: str, db_path: str = "tickerstream.db"):
        """
        Initialize portfolio manager.
        
        Args:
            user_id: Database user ID
            model_path: Path to trained AI model
            db_path: Path to SQLite database
        """
        self.user_id = user_id
        self.db_path = db_path
        self.scorer = AIScorer(model_path)
        
    def get_db_connection(self):
        """Create database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_current_portfolio(self) -> Tuple[float, Dict[str, int]]:
        """
        Get current balance and holdings.
        
        Returns:
            (balance, holdings_dict) where holdings_dict[ticker] = quantity
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get balance
        cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (self.user_id,))
        row = cursor.fetchone()
        balance = row['balance'] if row else 0.0
        
        # Get holdings
        cursor.execute("SELECT ticker, quantity FROM holdings WHERE user_id = ? AND quantity > 0", (self.user_id,))
        holdings = {row['ticker']: row['quantity'] for row in cursor.fetchall()}
        
        conn.close()
        return balance, holdings
    
    def get_watchlist(self) -> List[str]:
        """Get user's watchlist tickers."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT ticker FROM bot_watchlist WHERE user_id = ?", (self.user_id,))
        tickers = [row['ticker'] for row in cursor.fetchall()]
        
        conn.close()
        return tickers
    
    def get_day_trades_used(self) -> int:
        """Count day trades in last 5 days."""
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
        
        return result['day_trades'] if result else 0
    
    def score_all_stocks(self, candidates: List[str]) -> List[Dict]:
        """
        Score all candidate stocks using AI.
        
        Args:
            candidates: List of ticker symbols
            
        Returns:
            List of scored opportunities sorted by confidence
        """
        balance, holdings = self.get_current_portfolio()
        day_trades = self.get_day_trades_used()
        
        opportunities = []
        
        for ticker in candidates:
            shares = holdings.get(ticker, 0)
            entry_price = 0.0  # Simplified - would fetch from holdings table in production
            
            score = self.scorer.score_stock(
                ticker=ticker,
                balance=balance,
                shares=shares,
                entry_price=entry_price,
                day_trades_used=day_trades
            )
            
            if "error" not in score:
                opportunities.append({
                    "ticker": ticker,
                    "action": score['action'],
                    "confidence": score['confidence'],
                    "probabilities": score['probabilities'],
                    "current_price": score.get('current_price', 0),
                    "current_position": shares
                })
        
        # Sort by confidence (highest first)
        opportunities.sort(key=lambda x: x['confidence'], reverse=True)
        
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
        # Get candidates from watchlist
        candidates = self.get_watchlist()
        
        if not candidates:
            print("⚠️  No stocks in watchlist. Cannot generate trades.")
            return []
        
        # Score all candidates
        opportunities = self.score_all_stocks(candidates)
        
        # Also score existing holdings (not in watchlist)
        balance, holdings = self.get_current_portfolio()
        for ticker in holdings.keys():
            if ticker not in candidates:
                score = self.scorer.score_stock(ticker, balance, holdings[ticker])
                if "error" not in score:
                    opportunities.append({
                        "ticker": ticker,
                        "action": score['action'],
                        "confidence": score['confidence'],
                        "probabilities": score['probabilities'],
                        "current_price": score.get('current_price', 0),
                        "current_position": holdings[ticker]
                    })
        
        trades = []
        
        # 1. SELL SIGNALS (free up capital first)
        for opp in opportunities:
            if opp['action'] == 'SELL' and opp['current_position'] > 0:
                if opp['confidence'] >= min_sell_confidence:
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
        num_current_positions = len([h for h in holdings.values() if h > 0])
        num_sells = len([t for t in trades if t['action'] == 'SELL'])
        slots_available = max_positions - num_current_positions + num_sells
        
        if slots_available > 0:
            buy_candidates = [
                o for o in opportunities 
                if o['action'] == 'BUY' 
                and o['current_position'] == 0  # Not already holding
                and o['confidence'] >= min_buy_confidence
            ]
            
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
        
        return trades
    
    def get_portfolio_summary(self) -> Dict:
        """Get summary of current portfolio with AI scores."""
        balance, holdings = self.get_current_portfolio()
        
        total_value = balance
        positions = []
        
        for ticker, qty in holdings.items():
            price = get_current_price(ticker)
            if price:
                value = qty * price
                total_value += value
                
                score = self.scorer.score_stock(ticker, balance, qty)
                
                positions.append({
                    "ticker": ticker,
                    "quantity": qty,
                    "price": price,
                    "value": value,
                    "ai_signal": score.get('action', 'UNKNOWN'),
                    "confidence": score.get('confidence', 0)
                })
        
        return {
            "balance": balance,
            "total_value": total_value,
            "positions": positions,
            "num_positions": len(positions)
        }


if __name__ == "__main__":
    # Test the portfolio manager
    print("=== Testing Portfolio Manager ===\n")
    
    try:
        pm = PortfolioManager(
            user_id=11,
            model_path="../../../model/logs/best_model/best_model",
            db_path="../../tickerstream.db"
        )
        
        # Get portfolio summary
        summary = pm.get_portfolio_summary()
        print(f"Portfolio Value: ${summary['total_value']:,.2f}")
        print(f"Cash Balance: ${summary['balance']:,.2f}")
        print(f"Positions: {summary['num_positions']}\n")
        
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