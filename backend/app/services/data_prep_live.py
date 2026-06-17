"""
Live Data Preparation - v2
Matches AdvancedTradingEnv v2 observation space exactly (707 features).
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional, List, Dict

N_CANDIDATES = 5
LOOKBACK = 20
N_FEATURES = 7
N_PORTFOLIO_FEATURES = 7
OBS_DIM = (N_CANDIDATES * LOOKBACK * N_FEATURES) + N_PORTFOLIO_FEATURES  # 707

def add_indicators(df):
    df = df.copy()
    df['SMA_50']  = df['Close'].rolling(50).mean()
    df['SMA_200'] = df['Close'].rolling(200).mean()
    df['EMA_12']  = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA_26']  = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD']    = df['EMA_12'] - df['EMA_26']
    delta = df['Close'].diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))
    hl  = df['High'] - df['Low']
    hc  = np.abs(df['High'] - df['Close'].shift())
    lc  = np.abs(df['Low']  - df['Close'].shift())
    df['ATR'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()
    df['Volume_SMA']   = df['Volume'].rolling(20).mean()
    df['Volume_ratio'] = df['Volume'] / (df['Volume_SMA'] + 1e-9)
    return df

def _fetch_with_indicators(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="1y", interval="1d")
        if len(hist) < 220:
            return None
        hist = add_indicators(hist)
        hist.dropna(inplace=True)
        return hist if len(hist) >= LOOKBACK else None
    except:
        return None

def _build_stock_features(df):
    window = df.tail(LOOKBACK)
    ref_price = float(window.iloc[0]['Close']) or 1.0
    features = []
    for _, row in window.iterrows():
        close  = float(row['Close'])
        sma50  = float(row.get('SMA_50',  close)) or 1.0
        sma200 = float(row.get('SMA_200', close)) or 1.0
        atr    = float(row.get('ATR',     close * 0.02))
        features.extend([
            float(np.clip((close / ref_price) - 1.0,          -1.0,  1.0)),
            float(np.clip(float(row.get('RSI', 50.0)) / 100.0, 0.0,  1.0)),
            float(np.clip(float(row.get('MACD', 0.0)) / max(close, 1e-9), -0.1, 0.1)),
            float(np.clip((close / sma50)  - 1.0,             -0.5,  0.5)),
            float(np.clip((close / sma200) - 1.0,             -0.5,  0.5)),
            float(np.clip(atr / max(close, 1e-9),              0.0,  0.1)),
            float(np.clip(float(row.get('Volume_ratio', 1.0)) / 5.0, 0.0, 1.0)),
        ])
    while len(features) < LOOKBACK * N_FEATURES:
        features.extend([0.0] * N_FEATURES)
    return features[:LOOKBACK * N_FEATURES]

def get_live_observation(candidates, balance, held_ticker, shares,
                          entry_price=0.0, days_held=0, initial_balance=10000):
    assert len(candidates) == N_CANDIDATES
    features = []
    dfs = {t: _fetch_with_indicators(t) for t in candidates}
    for ticker in candidates:
        df = dfs[ticker]
        features.extend(_build_stock_features(df) if df is not None else [0.0] * (LOOKBACK * N_FEATURES))
    current_price = 0.0
    if held_ticker and dfs.get(held_ticker) is not None:
        current_price = float(dfs[held_ticker].iloc[-1]['Close'])
    portfolio_value = balance + (shares * current_price)
    held_idx = candidates.index(held_ticker) if (held_ticker and held_ticker in candidates) else -1
    features.extend([
        float(np.clip(balance / initial_balance, 0.0, 2.0)),
        float(1.0 if shares > 0 else 0.0),
        float(held_idx / N_CANDIDATES if held_idx >= 0 else -0.2),
        float(np.clip((current_price - entry_price) / max(entry_price, 1e-9), -0.5, 0.5) if entry_price > 0 else 0.0),
        float(np.clip(days_held / 252, 0.0, 1.0)),
        float(0.5),
        float(np.clip(balance / max(portfolio_value, 1e-9), 0.0, 1.0)),
    ])
    obs = np.array(features, dtype=np.float32)
    assert obs.shape == (OBS_DIM,), f"Wrong shape: {obs.shape}"
    return obs

def get_current_price(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="1d")
        return float(hist['Close'].iloc[-1]) if not hist.empty else None
    except:
        return None

if __name__ == "__main__":
    print("=== Testing data_prep_live v2 ===\n")
    candidates = ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]
    obs = get_live_observation(candidates, 10000, None, 0)
    print(f"Shape: {obs.shape}  (expected: ({OBS_DIM},))")
    print(f"Min: {obs.min():.4f}  Max: {obs.max():.4f}  NaNs: {np.isnan(obs).sum()}")