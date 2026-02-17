"""
Live Data Preparation for Production Trading
Ensures observations match training environment EXACTLY
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add technical indicators matching training environment.
    IMPORTANT: This must match data_prep.py from training!
    """
    df = df.copy()

    # Simple Moving Averages
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()

    # Exponential Moving Averages
    df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()

    # MACD
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # ATR (Average True Range)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(window=14).mean()

    # Volume indicators
    df['Volume_SMA'] = df['Volume'].rolling(window=20).mean()
    df['Volume_ratio'] = df['Volume'] / (df['Volume_SMA'] + 1e-9)  # Avoid division by zero

    # Price relative to SMA
    df['Close_to_SMA50'] = (df['Close'] - df['SMA_50']) / (df['SMA_50'] + 1e-9)
    df['Close_to_SMA200'] = (df['Close'] - df['SMA_200']) / (df['SMA_200'] + 1e-9)

    return df


def get_live_observation(
    ticker: str, 
    balance: float, 
    shares: int,
    entry_price: float = 0.0,
    day_trades_used: int = 0
) -> Optional[np.ndarray]:
    """
    Build observation array matching training environment EXACTLY.
    
    Returns:
        np.array of shape (145,) or None if insufficient data
        
    Observation structure (must match advanced_training_env.py):
        - Account state (3): balance, shares, entry_price
        - Last 20 days × 7 features (140): Close, RSI, MACD, SMA_50, SMA_200, ATR, Volume_ratio
        - Context (2): price_vs_sma200, day_trades_used
    """
    try:
        # Fetch enough history for all indicators (need 200+ days for SMA_200)
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y", interval="1d")
        
        if len(hist) < 220:  # Need at least 200 for SMA_200 + 20 for lookback
            print(f"⚠️  {ticker}: Insufficient history ({len(hist)} days)")
            return None
        
        # Calculate ALL technical indicators
        hist = add_indicators(hist)
        hist.dropna(inplace=True)
        
        if len(hist) < 20:
            print(f"⚠️  {ticker}: Not enough data after indicator calculation")
            return None
        
        # Get last 20 days for lookback window
        lookback = hist.tail(20)
        latest = lookback.iloc[-1]
        
        # Build observation array (MUST MATCH TRAINING!)
        features = []
        
        # 1. Account State (3 features)
        features.extend([
            float(balance),
            float(shares),
            float(entry_price if entry_price > 0 else latest['Close'])
        ])
        
        # 2. Last 20 Days of Market Data (140 features = 20 days × 7 features)
        for i in range(20):
            row = lookback.iloc[i]
            features.extend([
                float(row['Close']),
                float(row.get('RSI', 50.0)),  # Default to neutral if missing
                float(row.get('MACD', 0.0)),
                float(row.get('SMA_50', row['Close'])),
                float(row.get('SMA_200', row['Close'])),
                float(row.get('ATR', 1.0)),
                float(row.get('Volume_ratio', 1.0))
            ])
        
        # 3. Context Features (2 features)
        sma200 = latest.get('SMA_200', latest['Close'])
        price_vs_sma = latest['Close'] / sma200 if sma200 > 0 else 1.0
        
        features.extend([
            float(price_vs_sma),
            float(day_trades_used)
        ])
        
        # Verify observation size
        obs = np.array(features, dtype=np.float32)
        assert obs.shape == (145,), f"Wrong observation shape: {obs.shape}, expected (145,)"
        
        return obs
    
    except Exception as e:
        print(f"❌ Error building observation for {ticker}: {e}")
        return None


def get_current_price(ticker: str) -> Optional[float]:
    """Quick helper to just get current price."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
        return None
    except:
        return None


if __name__ == "__main__":
    # Test the observation builder
    print("=== Testing Live Observation Builder ===\n")
    
    test_tickers = ["AAPL", "MSFT", "GOOGL"]
    
    for ticker in test_tickers:
        print(f"Testing {ticker}...")
        obs = get_live_observation(ticker, balance=10000, shares=0)
        
        if obs is not None:
            print(f"  ✅ Observation shape: {obs.shape}")
            print(f"  First 5 features: {obs[:5]}")
            print(f"  Last 5 features: {obs[-5:]}")
        else:
            print(f"  ❌ Failed to build observation")
        print()