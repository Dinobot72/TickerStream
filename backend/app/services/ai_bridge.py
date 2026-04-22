"""
AI Bridge - Production Interface to Trained Model
"""

from sb3_contrib import RecurrentPPO  # NOT regular PPO!
from .data_prep_live import get_live_observation
import numpy as np

class AIBridge:
    def __init__(self, model_path: str = "./model/logs/best_model/"):
        try:
            self.model = RecurrentPPO.load(model_path)
            self.lstm_states = {}  # Track LSTM state per ticker
            print("AI Model loaded successfully")
        except Exception as e:
            print(f"Error loading model: {e}")
            self.model = None
    
    def predict_action(self, ticker: str, balance: float, shares_held: int):
        """
        Main prediction function with proper observation building.
        """
        if self.model is None:
            return {"decision": "HOLD", "error": "Model not loaded"}
        
        # Build proper observation (145 features)
        obs = get_live_observation(ticker, balance, shares_held)
        
        if obs is None:
            return {"decision": "HOLD", "error": "Insufficient market data"}
        
        # Initialize LSTM state if needed
        if ticker not in self.lstm_states:
            self.lstm_states[ticker] = None
        
        # Predict with LSTM state
        action, self.lstm_states[ticker] = self.model.predict(
            obs.reshape(1, -1),
            state=self.lstm_states[ticker],
            episode_start=np.array([False]),
            deterministic=True
        )
        
        # Map discrete action to decision
        action_map = {0: "HOLD", 1: "BUY", 2: "SELL"}
        decision = action_map[int(action)]
        
        return {
            "decision": decision,
            "action_code": int(action)
        }
    
    def reset_state(self, ticker: str):
        """Reset LSTM state for a ticker (e.g., after closing position)."""
        if ticker in self.lstm_states:
            del self.lstm_states[ticker]

# Singleton instance
ai_bridge = AIBridge()

def predict_action(ticker: str, balance: float, shares_held: int):
    """Legacy interface for compatibility."""
    return ai_bridge.predict_action(ticker, balance, shares_held)