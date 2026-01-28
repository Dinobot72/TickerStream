import stable_baselines3 as PPO
import os
from market_data import get_full_market_data, get_stock_data
import numpy as np



current_dir = os.path.dirname(os.path.abspath(__file__))

# Path to the 
MODEL_PATH = os.path.join(current_dir, '..', '..', 'model', 'ppo_trading_bot.zip')

def load_agent():
    try:
        return PPO.load(MODEL_PATH)
    except:
        return None
    
model = load_agent()

def predict_action(balance: float, shares_held: int, market_data: dict):
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
    pass