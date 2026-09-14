import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from app.services.data_prep_live import add_indicators, fetch_live_history, get_current_price

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

    @patch('app.services.data_prep_live.yf.Ticker')
    def test_fetch_live_history(self, mock_ticker):
        # Generate 250 days of data to pass the len(hist) < 220 check
        dates = pd.date_range("2023-01-01", periods=250)
        large_df = pd.DataFrame({
            "Open": np.random.uniform(100, 150, 250),
            "High": np.random.uniform(100, 150, 250),
            "Low": np.random.uniform(100, 150, 250),
            "Close": np.random.uniform(100, 150, 250),
            "Volume": np.random.randint(1000, 10000, 250)
        }, index=dates)
        
        mock_hist = MagicMock()
        mock_hist.history.return_value = large_df
        mock_ticker.return_value = mock_hist
        
        result = fetch_live_history("AAPL")
        assert result is not None
        assert "RSI" in result.columns

    @patch('app.services.data_prep_live.yf.Ticker')
    def test_fetch_live_history_insufficient_data(self, mock_ticker, sample_df):
        # sample_df is only 30 days, which should trigger the < 220 rejection
        mock_hist = MagicMock()
        mock_hist.history.return_value = sample_df
        mock_ticker.return_value = mock_hist
        
        result = fetch_live_history("AAPL")
        assert result is None
        
    @patch('app.services.data_prep_live.yf.Ticker')
    def test_get_current_price(self, mock_ticker):
        mock_hist = MagicMock()
        mock_hist.history.return_value = pd.DataFrame({"Close": [150.0]})
        mock_ticker.return_value = mock_hist
        
        price = get_current_price("AAPL")
        assert price == 150.0