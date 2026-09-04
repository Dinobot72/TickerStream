"""
AI Scoring Engine - SIMPLIFIED VERSION
Uses trained RecurrentPPO model to score trading opportunities
"""

import os
import pickle
import sys
import numpy as np
import torch as th
from sb3_contrib import RecurrentPPO
from typing import Dict, Optional

# Add the project root to sys.path so the backend can find the model directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from app.services.data_prep_live import fetch_live_history
from model.newAI.shared_obs import build_observation, get_window, PositionState
 
# Match TradingEnvV4 discrete actions
HOLD, BUY, SELL = 0, 1, 2
 
 
class AIScorer:
    """
    Wrapper around the trained AI model for scoring stocks.
    Handles LSTM state management.
 
    NOTE: A single AIScorer instance is shared across every active
    user's PortfolioManager (see tasks/scheduler.py) so the model is
    only loaded once. LSTM state is keyed by `state_key` (held ticker,
    or a combined key of the candidate window when nothing is held) so
    state from one user's held position won't be confused with
    another's, as long as callers pass consistent held_ticker/candidates
    per user.
    """
 
    def __init__( self, model_path: str = "./model/logs/best_model/best_model" ):
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
 
    def _action_probs(self, obs_tensor: np.ndarray, lstm_state, episode_start: bool) -> np.ndarray:
        """Get the policy's probability over all 7 discrete actions for this step."""
        policy = self.model.policy
        policy.set_training_mode(False)
 
        obs_t, _ = policy.obs_to_tensor(obs_tensor)
 
        if lstm_state is None:
            zeros = np.concatenate(
                [np.zeros(policy.lstm_hidden_state_shape) for _ in range(1)], axis=1
            )
            lstm_state = (zeros, zeros)
 
        states = (
            th.tensor(lstm_state[0], dtype=th.float32, device=policy.device),
            th.tensor(lstm_state[1], dtype=th.float32, device=policy.device),
        )
        episode_starts = th.tensor(
            np.array([episode_start]), dtype=th.float32, device=policy.device
        )
 
        with th.no_grad():
            distribution, _ = policy.get_distribution(obs_t, states, episode_starts)
 
        return distribution.distribution.probs.cpu().numpy()[0]
 
    def score_stock(
        self,
        ticker: str,
        balance: float,
        shares: int,
        entry_price: float = 0.0,
        days_held: int = 0,
        initial_balance: float = 10_000.0,
    ) -> Dict:
        """
        Score a SINGLE stock and return trading signal.
        """
        # 1. Fetch live data with indicators
        df = fetch_live_history(ticker)
        if df is None or df.empty:
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "error": "Could not build observation (insufficient data)",
            }
            
        current_price = float(df.iloc[-1]['Close'])
        
        # 2. Build the exact observation array used during training
        position = PositionState(
            balance=balance,
            initial_balance=initial_balance,
            in_position=(shares > 0),
            entry_price=entry_price,
            current_price=current_price,
            days_held=days_held,
            max_days=252
        )
        
        try:
            # get_window pads automatically if history < 20 days
            window = get_window(df, len(df))
            obs = build_observation(window, position)
        except Exception as e:
             return {"action": "HOLD", "confidence": 0.0, "error": f"Observation error: {e}"}

        # 3. LSTM State Management (Now simplified to just track the ticker)
        state_key = ticker
        
        if state_key not in self.lstm_states:
            self.lstm_states[state_key] = None
            self.episode_starts[state_key] = True
        else:
            self.episode_starts[state_key] = False
 
        try:
            obs_tensor = obs.reshape(1, -1)
            prev_state = self.lstm_states[state_key]
            episode_start_flag = self.episode_starts[state_key]
            episode_start = np.array([episode_start_flag])
 
            # Real action-probabilities BEFORE the state update, for confidence.
            probs = self._action_probs(obs_tensor, prev_state, episode_start_flag)
 
            action, self.lstm_states[state_key] = self.model.predict(
                obs_tensor,
                state=prev_state,
                episode_start=episode_start,
                deterministic=True,
            )
            raw_action = int(action.item())
            confidence = float(probs[raw_action])
 
            # Decode the new 3-action space
            if raw_action == HOLD:
                predicted_action = "HOLD"
            elif raw_action == BUY:
                predicted_action = "BUY"
            elif raw_action == SELL:
                predicted_action = "SELL" if shares > 0 else "HOLD"
            else:
                predicted_action = "HOLD"
 
            return {
                "action": predicted_action,
                "confidence": confidence,
                "current_price": current_price,
                "raw_action": raw_action,
            }
 
        except Exception as e:
            print(f"❌ Error during model predict: {e}")
            return {"action": "HOLD", "confidence": 0.0, "error": str(e)}
 
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