# File: trading_bot/bot/strategy_engine.py
import pandas as pd
import numpy as np
from stable_baselines3 import PPO
import os

current_dir = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(current_dir, '..', '..', 'model', 'ppo_trading_bot.zip')
DATA_FILE = os.path.join(current_dir, '..', '..', 'model', 'data', 'AAPL_historical_data.csv')


try:
    model = PPO.load(MODEL_PATH)
    print("Trading model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

def get_latest_market_data():
    df = pd.read_csv(DATA_FILE, header=None)
    header_row = df.iloc[0].tolist()
    columns = ['date'] + header_row[1:]
    df.columns = columns
    df = df.iloc[3:].copy()
    df = df.apply(pd.to_numeric, errors='coerce').dropna()

    return df.iloc[-1].to_dict()

def get_bot_decision(balance: float, shares_held: int):
    if model is None:
        return {"error": "Model not loaded"}, 500
    
    latest_data = get_latest_market_data()

    observation = np.array([
        balance,
        shares_held,
        latest_data['Open'],
        latest_data['High'],
        latest_data['Low'],
        latest_data['Close']
    ], dtype=np.float32)

    action, _states = model.predict(observation, deterministic=True)

    action_map = {0: 'BUY', 1: 'SELL', 2: 'HOLD'}
    decision = action_map.get(int(action), 'UNKNOWN')

    return {"decision": decision, "action_code": int(action)}


