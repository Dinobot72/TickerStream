import pytest
from unittest.mock import patch, MagicMock
from app.services.risk_manager import RiskManager

@pytest.fixture
def rm():
    return RiskManager(user_id=1)

class TestRiskManager:
    @patch('app.services.risk_manager.get_db_connection')
    @patch.object(RiskManager, '_check_daily_loss')
    def test_can_trade_max_position_size(self, mock_loss, mock_db, rm):
        mock_loss.return_value = True
        mock_cursor = MagicMock()
        mock_db.return_value.cursor.return_value = mock_cursor
        
        # 10,000 balance. Max position is 50% = 5000[cite: 13].
        mock_cursor.fetchone.return_value = {"balance": 10000.0}
        mock_cursor.fetchall.return_value = []
        
        # Cost is 4500 (45% of balance) - Should pass
        allowed, msg = rm.can_trade(ticker="AAPL", action="BUY", price=100.0, quantity=45)
        assert allowed
        
        # Cost is 5500 (55% of balance) - Should fail
        allowed, msg = rm.can_trade(ticker="AAPL", action="BUY", price=100.0, quantity=55)
        assert not allowed
        assert "Position too large" in msg

    @patch.object(RiskManager, '_get_portfolio')
    @patch.object(RiskManager, '_count_recent_day_trades')
    @patch.object(RiskManager, '_check_daily_loss')
    def test_can_trade_pdt_limit(self, mock_loss, mock_pdt, mock_portfolio, rm):
        mock_loss.return_value = True
        # Balance under $25k PDT limit
        mock_portfolio.return_value = (10000.0, {})
        # Hit max day trades (3)
        mock_pdt.return_value = 3 
        
        allowed, msg = rm.can_trade(ticker="AAPL", action="BUY", price=100.0, quantity=10)
        assert not allowed
        assert "PDT Protection" in msg