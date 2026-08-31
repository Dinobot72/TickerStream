"""
Live Data Preparation
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional

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

def fetch_live_history(ticker: str) -> Optional[pd.DataFrame]:
    """
    Fetches raw history and adds indicators for shared_obs.py.
    """
    try:
        hist = yf.Ticker(ticker).history(period="1y", interval="1d")
        if len(hist) < 220:
            return None
        hist = add_indicators(hist)
        hist.dropna(inplace=True)
        return hist
    except Exception as e:
        print(f"Error fetching live data for {ticker}: {e}")
        return None

def get_current_price(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="1d")
        return float(hist['Close'].iloc[-1]) if not hist.empty else None
    except:
        return None