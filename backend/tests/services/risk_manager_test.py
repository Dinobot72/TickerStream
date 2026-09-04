import pytest
from unittest.mock import patch, MagicMock
from app.services.risk_manager import RiskManager

@pytest.fixture
def rm():
    return RiskManager(user_id=1)

class TestRiskManager:
    @patch('app.services.risk_manager.get_db_connection')
    def test_can_trade_insufficient_funds(self, mock_db, rm):
        mock_cursor = MagicMock()
        mock_db.return_value.cursor.return_value = mock_cursor
        
        # Return 100 balance, no holdings[cite: 5]
        mock_cursor.fetchone.return_value = {"balance": 100.0}
        mock_cursor.fetchall.return_value = []
        
        allowed, msg = rm.can_trade(ticker="AAPL", action="BUY", price=150.0, quantity=1)
        assert not allowed
        assert "Insufficient funds" in msg

    @patch('app.services.risk_manager.get_db_connection')
    @patch.object(RiskManager, '_check_daily_loss')
    def test_can_trade_max_position_size(self, mock_loss, mock_db, rm):
        mock_loss.return_value = True
        mock_cursor = MagicMock()
        mock_db.return_value.cursor.return_value = mock_cursor
        
        # 10,000 balance. Max position is 20% = 2000[cite: 5]
        mock_cursor.fetchone.return_value = {"balance": 10000.0}
        mock_cursor.fetchall.return_value = []
        
        allowed, msg = rm.can_trade(ticker="AAPL", action="BUY", price=100.0, quantity=25)
        assert not allowed
        assert "Position too large" in msg

    @patch.object(RiskManager, '_get_portfolio')
    @patch.object(RiskManager, '_check_daily_loss')
    def test_can_trade_daily_loss_limit(self, mock_loss, mock_portfolio, rm):
        mock_portfolio.return_value = (10000.0, {})
        mock_loss.return_value = False  # Limit exceeded[cite: 5]
        
        allowed, msg = rm.can_trade(ticker="AAPL", action="BUY", price=50.0, quantity=10)
        assert not allowed
        assert "Daily loss limit exceeded" in msg