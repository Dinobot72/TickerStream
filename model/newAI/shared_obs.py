"""
shared_obs.py

The ONE place observations get built. Both TradingEnvV4 (training)
and the live AIScorer import build_observation() from here — there is
no second implementation to drift out of sync.

Expects a history dataframe with columns:
    Close, RSI, MACD, SMA_50, SMA_200, ATR, Volume_ratio
(same schema your data_prep.py / data_prep_live.py already produce).
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd

LOOKBACK = 20
N_FEATURES = 7           # per-bar features
N_PORTFOLIO_FEATURES = 4  # balance, in_position, unrealized_pnl, days_held
OBS_DIM = (LOOKBACK * N_FEATURES) + N_PORTFOLIO_FEATURES


@dataclass
class PositionState:
    balance: float
    initial_balance: float
    in_position: bool
    entry_price: float = 0.0
    current_price: float = 0.0
    days_held: int = 0
    max_days: int = 252


def _clip(x: float, lo: float, hi: float) -> float:
    return float(np.clip(x, lo, hi))


def build_observation(history_window: pd.DataFrame, position: PositionState) -> np.ndarray:
    """
    history_window: exactly LOOKBACK rows (oldest -> newest) for ONE ticker.
        Caller is responsible for zero-padding at the start of a series
        (see TradingEnvV4._get_window for the padding convention).
    position: current account/position state for this ticker.

    Returns a flat float32 array of length OBS_DIM. Raises if the window
    isn't exactly LOOKBACK rows long - fail loudly here rather than
    silently produce a wrong-shaped observation.
    """
    if len(history_window) != LOOKBACK:
        raise ValueError(f"history_window must have exactly {LOOKBACK} rows, got {len(history_window)}")

    features = []
    ref_price = history_window.iloc[0]["Close"] or 1.0

    for _, row in history_window.iterrows():
        close = row["Close"]
        sma50 = row.get("SMA_50", close) or 1.0
        sma200 = row.get("SMA_200", close) or 1.0
        atr = row.get("ATR", close * 0.02)

        features.extend([
            _clip((close / ref_price) - 1.0, -1.0, 1.0),
            _clip(float(row.get("RSI", 50.0)) / 100.0, 0.0, 1.0),
            _clip(float(row.get("MACD", 0.0)) / max(close, 1e-9), -0.1, 0.1),
            _clip((close / sma50) - 1.0, -0.5, 0.5),
            _clip((close / sma200) - 1.0, -0.5, 0.5),
            _clip(atr / max(close, 1e-9), 0.0, 0.1),
            _clip(float(row.get("Volume_ratio", 1.0)) / 5.0, 0.0, 1.0),
        ])

    unrealized_pnl = 0.0
    if position.in_position and position.entry_price > 0 and position.current_price > 0:
        unrealized_pnl = (position.current_price - position.entry_price) / position.entry_price

    features.extend([
        _clip(position.balance / position.initial_balance, 0.0, 2.0),
        1.0 if position.in_position else 0.0,
        _clip(unrealized_pnl, -0.5, 0.5),
        _clip(position.days_held / max(position.max_days, 1), 0.0, 1.0),
    ])

    obs = np.array(features, dtype=np.float32)
    assert obs.shape == (OBS_DIM,), f"obs shape {obs.shape} != expected ({OBS_DIM},)"
    assert not np.any(np.isnan(obs)), "NaN in observation - check input dataframe for gaps"
    return obs


def get_window(df: pd.DataFrame, end_idx: int, lookback: int = LOOKBACK) -> pd.DataFrame:
    """
    Shared windowing convention: rows [end_idx - lookback, end_idx), left-padded
    with zeros if not enough history exists yet. Used by both the training env
    (on historical parquet data) and the live scorer (on freshly fetched bars).
    """
    start = max(0, end_idx - lookback)
    window = df.iloc[start:end_idx]
    if len(window) < lookback:
        pad_n = lookback - len(window)
        padding = pd.DataFrame(np.zeros((pad_n, len(window.columns))), columns=window.columns)
        window = pd.concat([padding, window], ignore_index=True)
    return window