import numpy as np
from stable_baselines3 import PPO
import os

current_dir = os.path.dirname(os.path.abspath(__file__))

# Path to the "Brain" (the zip file)
MODEL_PATH = os.path.join(current_dir, '..', '..', 'model', 'ppo_trading_bot.zip')

model = None

# 1. Load the Brain once when the server starts
if os.path.exists(MODEL_PATH):
    try:
        model = PPO.load(MODEL_PATH)
        print(f"Trading model loaded successfully from {MODEL_PATH}")
    except Exception as e:
        print(f"Error loading model: {e}")
else:
    print(f"Warning: Model not found at {MODEL_PATH}")

# 2. The Decision Function (Now accepts 'market_data' instead of reading a file)
def get_bot_decision(balance: float, shares_held: int, market_data: dict):
    """
    market_data: dict containing 'Open', 'High', 'Low', 'Close'
    """
    if model is None:
        return {"error": "Model not loaded"}, 500
    
    if not market_data:
        return {"error": "No market data provided"}, 400

    # Create observation array matching the training environment
    # The model expects: [Balance, Shares, Open, High, Low, Close]
    observation = np.array([
        balance,
        shares_held,
        market_data['Open'],
        market_data['High'],
        market_data['Low'],
        market_data['Close']
    ], dtype=np.float32)

    # Ask the AI for a prediction
    action, _states = model.predict(observation, deterministic=True)

    action_map = {0: 'BUY', 1: 'SELL', 2: 'HOLD'}
    decision = action_map.get(int(action), 'UNKNOWN')

    return {"decision": decision, "action_code": int(action)}