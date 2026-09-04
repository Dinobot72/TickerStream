import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from app.services.data_prep_live import (
    add_indicators, 
    _build_stock_features, 
    get_live_observation,
    OBS_DIM
)

@pytest.fixture
def sample_df():
    dates = pd.date_range("2023-01-01", periods=30)
    return pd.DataFrame({
        "Open": np.random.uniform(100, 150, 30),
        "High": np.random.uniform(100, 150, 30),
        "Low": np.random.uniform(100, 150, 30),
        "Close": np.random.uniform(100, 150, 30),
        "Volume": np.random.randint(1000, 10000, 30)
    }, index=dates)

class TestDataPrepLive:
    def test_add_indicators(self, sample_df):
        df_ind = add_indicators(sample_df)
        assert "SMA_50" in df_ind.columns
        assert "RSI" in df_ind.columns
        assert "MACD" in df_ind.columns

    def test_build_stock_features_length(self, sample_df):
        # Needs 7 features over 20 lookback days = 140 features[cite: 2]
        df_ind = add_indicators(sample_df).fillna(0)
        features = _build_stock_features(df_ind)
        assert len(features) == 140
        assert all(isinstance(f, float) for f in features)

    @patch('app.services.data_prep_live._fetch_with_indicators')
    def test_get_live_observation_shape(self, mock_fetch, sample_df):
        mock_fetch.return_value = add_indicators(sample_df).fillna(0)
        candidates = ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]
        
        obs = get_live_observation(
            candidates=candidates,
            balance=10000.0,
            held_ticker=None,
            shares=0
        )
        
        assert isinstance(obs, np.ndarray)
        assert obs.shape == (OBS_DIM,) # 707 dimensions[cite: 2]