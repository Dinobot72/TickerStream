import pytest
from unittest.mock import patch
from app.services.market_data import (
    _safe_float,
    get_stock_price,
    get_full_market_data,
    get_stock_metrics,
    screen_stock_gainers
)

class TestMarketData:
    def test_safe_float(self):
        assert _safe_float(15.5) == 15.5
        assert _safe_float("15.5") == 15.5
        assert _safe_float(None) == 0.0
        assert _safe_float(float('inf')) == 0.0
        assert _safe_float(float('nan')) == 0.0

    @patch('app.services.market_data.yf.Ticker')
    def test_get_stock_metrics_missing_fields(self, mock_ticker):
        # Mock yfinance to return info without trailingPE or dividendYield[cite: 3]
        mock_ticker.return_value.info = {
            "marketCap": 1000000,
            "volume": 500000,
            "shortName": "Test Co"
        }
        
        metrics = get_stock_metrics("TEST")
        assert metrics["pe_ratio"] == 0
        assert metrics["dividend_yield"] == 0
        assert metrics["shortName"] == "Test Co"
        assert metrics["market_cap"] == 1000000

    @patch('app.services.market_data.yf.screen')
    def test_screen_stock_gainers(self, mock_screen):
        mock_screen.return_value = {
            'quotes': [
                {'symbol': 'AAPL', 'regularMarketPrice': 150.0, 'regularMarketChangePercent': 5.0}
            ]
        }
        
        gainers = screen_stock_gainers("day_gainers")
        assert len(gainers) == 1
        assert gainers[0]["ticker"] == "AAPL"
        assert gainers[0]["price"] == 150.0