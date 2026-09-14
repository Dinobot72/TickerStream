import pytest
from unittest.mock import patch, MagicMock
from app.services.portfolio_manager import PortfolioManager
from datetime import datetime, timedelta

@pytest.fixture
def pm():
    mock_scorer = MagicMock()
    return PortfolioManager(user_id=1, scorer=mock_scorer)

class TestPortfolioManager:
    @patch('app.services.portfolio_manager.sqlite3.connect')
    def test_get_position_entry_dates(self, mock_connect, pm):
        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        
        # Avoid mocking datetime; inject a date exactly 10 days ago into the DB response
        ten_days_ago = (datetime.now() - timedelta(days=10)).isoformat()
        mock_cursor.fetchall.return_value = [
            {"ticker": "AAPL", "entry_timestamp": ten_days_ago}
        ]
        
        entry_dates = pm.get_position_entry_dates()
        
        assert "AAPL" in entry_dates
        # Assert approximately 10 days to account for fraction-of-a-second execution delays
        assert entry_dates["AAPL"] in (9, 10, 11)

    @patch.object(PortfolioManager, 'get_current_portfolio')
    @patch.object(PortfolioManager, 'get_position_entry_dates')
    def test_score_all_stocks(self, mock_entry, mock_portfolio, pm):
        mock_portfolio.return_value = (10000.0, {"AAPL": {"quantity": 10, "purchase_price": 100.0}})
        mock_entry.return_value = {"AAPL": 5}
        
        pm.scorer.score_stock.return_value = {
            "action": "BUY", 
            "confidence": 0.8, 
            "current_price": 150.0
        }
        
        candidates = ["AAPL", "MSFT"]
        opportunities = pm.score_all_stocks(candidates)
        
        assert len(opportunities) == 2
        # Ensure scorer was called individually for MSFT
        pm.scorer.score_stock.assert_any_call(
            ticker="MSFT",
            balance=10000.0,
            shares=0,
            entry_price=0.0,
            days_held=0
        )

    @patch.object(PortfolioManager, 'score_all_stocks')
    @patch.object(PortfolioManager, 'get_watchlist')
    @patch.object(PortfolioManager, 'get_current_portfolio')
    @patch.object(PortfolioManager, 'get_position_entry_dates')
    def test_generate_trade_plan(self, mock_dates, mock_portfolio, mock_watchlist, mock_score, pm):
        mock_watchlist.return_value = ["MSFT"]
        mock_portfolio.return_value = (10000.0, {"AAPL": {"quantity": 10, "purchase_price": 100.0}})
        mock_dates.return_value = {"AAPL": 5}
        
        mock_score.return_value = [
            {"ticker": "MSFT", "action": "BUY", "confidence": 0.8, "current_price": 200.0, "current_position": 0}
        ]
        
        # Mock scorer for the held position loop
        pm.scorer.score_stock.return_value = {
            "action": "SELL", "confidence": 0.9, "current_price": 150.0
        }
        
        trades = pm.generate_trade_plan(min_buy_confidence=0.25, min_sell_confidence=0.60, position_size_pct=0.45)
        
        assert len(trades) == 2
        sell_trade = next(t for t in trades if t["action"] == "SELL")
        assert sell_trade["ticker"] == "AAPL"
        
        buy_trade = next(t for t in trades if t["action"] == "BUY")
        assert buy_trade["ticker"] == "MSFT"
        # 10,000 * 0.45 / 200 = 22.5 -> 22 shares
        assert buy_trade["quantity"] == 22