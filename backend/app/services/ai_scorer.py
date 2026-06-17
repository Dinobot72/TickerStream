"""
AI Scoring Engine - SIMPLIFIED VERSION
Uses trained RecurrentPPO model to score trading opportunities
"""

from sb3_contrib import RecurrentPPO
import numpy as np
from typing import Dict, List, Optional
from app.services.data_prep_live import get_live_observation, get_current_price, N_CANDIDATES


class AIScorer:
    """
    Wrapper around the trained AI model for scoring stocks.
    Handles LSTM state management.
    """
    
    def __init__(self, model_path: str = "./model/logs/best_model/best_model"):
        """
        Load the trained RecurrentPPO model.
        
        Args:
            model_path: Path to saved model (without .zip extension)
        """
        try:
            self.model = RecurrentPPO.load(model_path)
            self.lstm_states = {}  # Track LSTM hidden states per ticker
            self.episode_starts = {}  # Track if this is a new episode per ticker
            print(f"✅ AI Model loaded from {model_path}")
        except Exception as e:
            print(f"❌ Failed to load AI model: {e}")
            raise
    
    def score_stock(
        self,
        candidates: List[str],
        held_ticker: Optional[str],
        balance: float,
        shares: int,
        entry_price: float = 0.0,
        days_held: int = 0,
        initial_balance: float = 10_000.0,
    ) -> Dict:
        """
        Score a stock and return trading signal.
        
        Args:
            ticker: Stock symbol (e.g., "AAPL")
            balance: Available cash
            shares: Current shares owned of this ticker
            entry_price: Price at which shares were purchased (if any)
            day_trades_used: Number of day trades used in rolling 5-day window
            
        Returns:
            {
                "action": "BUY" | "SELL" | "HOLD",
                "confidence": float (0-1),
                "current_price": float,
                "error": str (only if failed)
            }
        """
        if len(candidates) != N_CANDIDATES:
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "error": f"candidates must have exactly {N_CANDIDATES} tickers, got {len(candidates)}",
            }
 
        # Build observation
        obs = get_live_observation(
            candidates=candidates,
            balance=balance,
            held_ticker=held_ticker,
            shares=shares,
            entry_price=entry_price,
            days_held=days_held,
            initial_balance=initial_balance,
        )
 
        if obs is None:
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "error": "Could not build observation (insufficient data)",
            }
 
        # Use held_ticker as the LSTM state key; fall back to a combined key
        state_key = held_ticker or "_".join(candidates)
 
        current_price = get_current_price(held_ticker) if held_ticker else None
        
        # Initialize LSTM state if needed
        if ticker not in self.lstm_states:
            self.lstm_states[ticker] = None
            self.episode_starts[ticker] = True
        else:
            self.episode_starts[ticker] = False
        
        try:
            # Reshape observation for batch dimension
            obs_tensor = obs.reshape(1, -1)
            episode_start = np.array([self.episode_starts[ticker]])
            
            # Get action from model WITH LSTM state
            action, self.lstm_states[ticker] = self.model.predict(
                obs_tensor,
                state=self.lstm_states[ticker],
                episode_start=episode_start,
                deterministic=True  # Consistent predictions
            )
            
            # Map discrete action to string
            action_map = {0: "HOLD", 1: "BUY", 2: "SELL"}
            predicted_action = action_map[int(action.item())]
            
            # Simplified confidence - always 0.7 for valid predictions
            # (Complex probability extraction was causing issues)
            return {
                "action": predicted_action,
                "confidence": 0.7,
                "current_price": current_price,
            }
            
        except Exception as e:
            print(f"❌ Error during model predict: {e}")
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "error": str(e),
            }
        
    
    def reset_state(self, ticker: str):
        """
        Reset LSTM state for a ticker.
        Call this when closing a position to start fresh.
        """
        if ticker in self.lstm_states:
            del self.lstm_states[ticker]
            del self.episode_starts[ticker]
    
    def reset_all_states(self):
        """Reset all LSTM states (e.g., at market open)."""
        self.lstm_states = {}
        self.episode_starts = {}


if __name__ == "__main__":
    # Test the AI scorer
    print("=== Testing AI Scorer ===\n")
    
    try:
        scorer = AIScorer()
        
        test_cases = [
            ("AAPL", 10000, 0, "No position"),
            ("MSFT", 5000, 50, "Existing position"),
            ("GOOGL", 20000, 0, "Large balance"),
        ]
        
        for ticker, balance, shares, description in test_cases:
            print(f"Test: {description} - {ticker}")
            result = scorer.score_stock(ticker, balance, shares, 0.0, 0)
            
            if "error" in result:
                print(f"  ❌ Error: {result['error']}\n")
                continue
            
            print(f"  Action: {result['action']}")
            print(f"  Confidence: {result['confidence']:.1%}")
            print(f"  Current Price: ${result.get('current_price', 0):.2f}\n")
            
    except Exception as e:
        print(f"Failed to initialize scorer: {e}")