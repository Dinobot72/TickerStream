import pytest
from unittest.mock import patch, MagicMock
from app.services.portfolio_manager import PortfolioManager

@pytest.fixture
def pm():
    mock_scorer = MagicMock()
    return PortfolioManager(user_id=1, scorer=mock_scorer)

class TestPortfolioManager:
    @patch('app.services.portfolio_manager.sqlite3.connect')
    def test_get_current_portfolio(self, mock_connect, pm):
        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        
        # Mock balance fetch and holding fetch[cite: 4]
        mock_cursor.fetchone.return_value = {"balance": 5000.0}
        mock_cursor.fetchall.return_value = [
            {"ticker": "AAPL", "quantity": 10, "purchase_price": 140.0}
        ]
        
        balance, holdings = pm.get_current_portfolio()
        assert balance == 5000.0
        assert "AAPL" in holdings
        assert holdings["AAPL"]["quantity"] == 10

    def test_build_candidates(self, pm):
        watchlist = ["AAPL", "MSFT"]
        held_tickers = ["TSLA"]
        
        # Must return exactly 5 candidates[cite: 4]
        candidates = pm._build_candidates(watchlist, held_tickers)
        assert len(candidates) == 5
        assert candidates[0] == "TSLA"
        assert "AAPL" in candidates

    @patch.object(PortfolioManager, 'get_current_portfolio')
    @patch.object(PortfolioManager, 'get_watchlist')
    @patch('app.services.portfolio_manager.get_current_price')
    def test_generate_trade_plan(self, mock_price, mock_watchlist, mock_portfolio, pm):
        mock_portfolio.return_value = (10000.0, {"AAPL": {"quantity": 10, "purchase_price": 100.0}})
        mock_watchlist.return_value = ["MSFT"]
        mock_price.return_value = 200.0
        
        # Mock scorer to BUY MSFT and SELL AAPL[cite: 4]
        pm.scorer.score_stock.side_effect = [
            {"action": "BUY", "confidence": 0.8, "current_price": 200.0},  # MSFT
            {"action": "SELL", "confidence": 0.9, "current_price": 150.0}  # AAPL
        ]
        
        trades = pm.generate_trade_plan(min_buy_confidence=0.65, min_sell_confidence=0.60)
        assert len(trades) == 2
        
        sell_trade = next(t for t in trades if t["action"] == "SELL")
        assert sell_trade["ticker"] == "AAPL"
        
        buy_trade = next(t for t in trades if t["action"] == "BUY")
        assert buy_trade["ticker"] == "MSFT"