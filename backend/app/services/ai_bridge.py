import stable_baselines3 as sb3
from .market_data import get_full_market_data
import numpy as np

def load_agent():
    try:
        return sb3.PPO.load("./model/ppo_trading_bot")
    except:
        print("Error loading model")
        return None
    
model = load_agent()

def predict_action(balance: float, shares_held: int, market_data: dict):
    """
    market_data: dict containing 'Open', 'High', 'Low', 'Close'
    """
    if model is None:
        return {"decision": "HOLD", "error": "Model not loaded"}
    
    if not market_data:
        return {"decision": "HOLD", "error": "No market data provided"}
    

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
    print(action)
    raw_action = float(action)

    if raw_action > 0.33:
        decision = 'BUY'
        action_code = 0
    elif raw_action < -0.33:
        decision = 'SELL'
        action_code = 1
    else:
        decision = 'HOLD'
        action_code = 2

    return {"decision": decision, "action_code": int(action_code)}
    pass

if __name__ == "__main__":
    model = load_agent()
    print(predict_action(1000, 10, get_full_market_data("AAPL")))

    print(predict_action(1000, 0, get_full_market_data("AAPL")))

    print(predict_action(1000000, 100, {
        "Open": float(400.0),
        "High": float(4000.0),
        "Low": float(150.0),
        "Close": float(400.0)
    }))

    # TEST 1: The "Crash" - Low balance, many shares, price is plummeting.
    # Does he panic SELL?
    print("Panic Sell Test:", predict_action(10, 1000, {
        "Open": 500.0, "High": 505.0, "Low": 10.0, "Close": 15.0
    }))

    # TEST 2: The "Moon" - Massive balance, 0 shares, price is rocketing up.
    # Does he FOMO BUY?
    print("FOMO Buy Test:", predict_action(1000000, 0, {
        "Open": 10.0, "High": 500.0, "Low": 9.0, "Close": 490.0
    }))
