import numpy as np
import pandas as pd

def build_observation(ticker_history_df: pd.DataFrame, position_state: dict) -> np.ndarray:
    """
    SHARED OBSERVATION BUILDER
    Must be used by both the Training Environment and the Live Scorer.
    Returns a normalized float32 numpy array.
    """
    features = []
    
    # Use the first row's close as the reference price for normalization
    ref_price = ticker_history_df.iloc[0]['Close']
    if pd.isna(ref_price) or ref_price == 0:
        ref_price = 1e-9
        
    for _, row in ticker_history_df.iterrows():
        close = row['Close']
        rsi = row.get('RSI', 50.0)
        macd = row.get('MACD', 0.0)
        sma50 = row.get('SMA_50', close)
        sma200 = row.get('SMA_200', close)
        atr = row.get('ATR', close * 0.02)
        vol_ratio = row.get('Volume_ratio', 1.0)
        
        close_safe = max(close, 1e-9)
        sma50_safe = max(sma50, 1e-9)
        sma200_safe = max(sma200, 1e-9)
        
        # 7 features per row
        features.append(np.clip((close / ref_price) - 1.0, -1.0, 1.0))
        features.append(np.clip(rsi / 100.0, 0.0, 1.0))
        features.append(np.clip(macd / close_safe, -0.1, 0.1))
        features.append(np.clip((close / sma50_safe) - 1.0, -0.5, 0.5))
        features.append(np.clip((close / sma200_safe) - 1.0, -0.5, 0.5))
        features.append(np.clip(atr / close_safe, 0.0, 0.1))
        features.append(np.clip(vol_ratio / 5.0, 0.0, 1.0))

    # 4 portfolio/context features
    features.append(np.clip(position_state['balance'] / position_state['initial_balance'], 0.0, 2.0))
    features.append(1.0 if position_state['in_position'] else 0.0)
    features.append(np.clip(position_state['unrealized_pnl'], -0.5, 0.5))
    features.append(np.clip(position_state['days_held'] / position_state['max_days'], 0.0, 1.0))

    obs = np.array(features, dtype=np.float32)
    obs = np.nan_to_num(obs, nan=0.0)  # Safety net for missing data
    
    return obs