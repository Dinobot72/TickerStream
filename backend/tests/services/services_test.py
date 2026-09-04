import pytest
from unittest.mock import patch, MagicMock
from app.services.services import get_stock_metrics, get_historical_data

class TestServices:
    @patch('app.services.services.yf.Ticker')
    def test_get_stock_metrics_formatting(self, mock_ticker):
        mock_ticker.return_value.info = {
            'marketCap': 2500000000,
            'trailingPE': 15.5,
            'dividendYield': 0.02,
            'volume': 1000000
        }
        
        metrics = get_stock_metrics("AAPL")
        assert metrics["market_cap"] == "2,500,000,000.00"
        assert metrics["pe_ratio"] == "15.50"

    @patch('app.services.services.yf.Ticker')
    def test_get_historical_data(self, mock_ticker):
        import pandas as pd
        mock_hist = MagicMock()
        # Mock DataFrame iteration for historical data mapping[cite: 7]
        df = pd.DataFrame({"Close": [150.0]}, index=pd.to_datetime(["2023-01-01"]))
        mock_hist.iterrows.return_value = df.iterrows()
        mock_ticker.return_value.history.return_value = mock_hist
        
        data = get_historical_data("AAPL", "1d")
        assert len(data) == 1
        assert data[0]["price"] == 150.0
        assert "timestamp" in data[0]