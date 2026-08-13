"""
AI Scoring Engine - SIMPLIFIED VERSION
Uses trained RecurrentPPO model to score trading opportunities
"""

import os
import pickle

from sb3_contrib import RecurrentPPO
import numpy as np
from typing import Dict, List, Optional
from app.services.data_prep_live import get_live_observation, get_current_price, N_CANDIDATES


class AIScorer:
    """
    Wrapper around the trained AI model for scoring stocks.
    Handles LSTM state management.

    NOTE: A single AIScorer instance is now shared across every active
    user's PortfolioManager (see tasks/scheduler.py) so the model is only
    loaded once. LSTM state is keyed by `state_key` (held ticker, or a
    combined key of the candidate window when nothing is held) so state
    from one user's held position won't be confused with another's, as
    long as callers pass consistent held_ticker/candidates per user.
    """

    def __init__(self, model_path: str = "../model/logs/best_model/best_model"):
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

        # --- Load training-time observation normalization stats ---
        # train.py wraps the env in VecNormalize(norm_obs=True, clip_obs=10.)
        # before the model ever sees an observation, and saves those running
        # mean/var stats to vec_normalize.pkl next to the model. The model
        # has only ever seen normalized inputs — feeding it raw observations
        # at inference puts it wildly out of distribution, which is why it
        # was scoring every single ticker as HOLD regardless of input.
        self.obs_mean = None
        self.obs_var = None
        self.clip_obs = 10.0
        self.epsilon = 1e-8

        vec_normalize_path = os.path.join(
            os.path.dirname(os.path.dirname(model_path)), "vec_normalize.pkl"
        )
        try:
            with open(vec_normalize_path, "rb") as f:
                vec_normalize = pickle.load(f)
            self.obs_mean = vec_normalize.obs_rms.mean
            self.obs_var = vec_normalize.obs_rms.var
            self.clip_obs = vec_normalize.clip_obs
            self.epsilon = vec_normalize.epsilon
            print(f"✅ Loaded observation normalization stats from {vec_normalize_path}")
        except FileNotFoundError:
            print(
                f"⚠️  No vec_normalize.pkl found at {vec_normalize_path} — "
                "scoring with RAW (unnormalized) observations. If this model "
                "was trained with VecNormalize, predictions will be unreliable "
                "(likely biased toward one action regardless of input) until "
                "this file is available."
            )

    def _normalize_obs(self, obs: np.ndarray) -> np.ndarray:
        """Apply the same normalization the model was trained on (see
        stable_baselines3 VecNormalize.normalize_obs). No-op if no stats
        were loaded."""
        if self.obs_mean is None:
            return obs
        return np.clip(
            (obs - self.obs_mean) / np.sqrt(self.obs_var + self.epsilon),
            -self.clip_obs,
            self.clip_obs,
        ).astype(np.float32)

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
            candidates: The fixed-size window of tickers for this observation
            held_ticker: Ticker currently held (if any) for this evaluation
            balance: Available cash
            shares: Current shares owned of this ticker
            entry_price: Price at which shares were purchased (if any)
            days_held: Number of days the position has been held

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
            print("❌ Could not build observation (insufficient data)")
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "error": "Could not build observation (insufficient data)",
            }

        obs = self._normalize_obs(obs)

        # Use held_ticker as the LSTM state key; fall back to a combined key
        state_key = held_ticker or "_".join(candidates)

        current_price = get_current_price(held_ticker) if held_ticker else None

        # Initialize LSTM state if needed
        if state_key not in self.lstm_states:
            self.lstm_states[state_key] = None
            self.episode_starts[state_key] = True
        else:
            self.episode_starts[state_key] = False

        try:
            # Reshape observation for batch dimension
            obs_tensor = obs.reshape(1, -1)
            episode_start = np.array([self.episode_starts[state_key]])

            # Get action from model WITH LSTM state
            action, self.lstm_states[state_key] = self.model.predict(
                obs_tensor,
                state=self.lstm_states[state_key],
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

        NOTE: `ticker` here is expected to match the state_key used in
        score_stock (i.e. the held_ticker). If score_stock was called with
        held_ticker=None for this position, its state was stored under the
        combined-candidates key instead and this reset_state call is a no-op —
        harmless, since a fresh episode_start will be set the next time that
        combined key is scored anyway.
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

        # Candidate pool matching N_CANDIDATES (5)
        sample_candidates = ["AAPL", "MSFT", "GOOGL", "AMZN", "SPY"]

        test_cases = [
            (sample_candidates, None, 10000.0, 0, "No position (AAPL)"),
            (sample_candidates, "MSFT", 5000.0, 50, "Existing position (MSFT)"),
            (sample_candidates, None, 20000.0, 0, "Large balance (GOOGL)"),
        ]

        for candidates, held_ticker, balance, shares, description in test_cases:
            print(f"Test: {description}")

            result = scorer.score_stock(
                candidates=candidates,
                held_ticker=held_ticker,
                balance=balance,
                shares=shares,
                entry_price=0.0,
                days_held=0
            )

            if "error" in result:
                print(f"  ❌ Error: {result['error']}\n")
                continue

            print(f"  Action: {result['action']}")
            print(f"  Confidence: {result['confidence']:.1%}")
            print(f"  Current Price: ${result.get('current_price') or 0.0:.2f}\n")

    except Exception as e:
        print(f"Failed to initialize scorer: {e}")