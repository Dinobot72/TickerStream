import pytest
from unittest.mock import patch, MagicMock
from app.services.screener import run_market_scan, update_bot_watchlist

class TestScreener:
    @patch('app.services.screener.yf.screen')
    @patch('app.services.screener.update_bot_watchlist')
    def test_run_market_scan(self, mock_update, mock_screen):
        mock_screen.return_value = {
            'quotes': [
                {'symbol': 'NVDA', 'quoteType': 'EQUITY', 'regularMarketPrice': 45.0, 'regularMarketChangePercent': 4.5}
            ]
        }
        
        results = run_market_scan()
        assert "NVDA" in results
        mock_update.assert_called_once()

    @patch('app.services.screener.get_active_bot_user_ids')
    @patch('app.services.screener.get_db_connection')
    def test_update_bot_watchlist(self, mock_db, mock_get_users):
        mock_get_users.return_value = [1, 2]
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        
        candidates = [{"ticker": "AAPL"}, {"ticker": "TSLA"}]
        update_bot_watchlist(candidates)
        
        assert mock_conn.commit.called
        assert mock_conn.close.called