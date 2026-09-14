import pytest
from unittest.mock import patch, MagicMock
from app.services.screener import run_market_scan

class TestScreener:
    @patch('app.services.screener.yf.screen')
    @patch('app.services.screener.update_bot_watchlist')
    def test_run_market_scan_filters(self, mock_update, mock_screen):
        mock_screen.return_value = {
            'quotes': [
                {
                    'symbol': 'NVDA', 
                    'quoteType': 'EQUITY', 
                    'regularMarketPrice': 105.0, 
                    'regularMarketChangePercent': -1.5,
                    'regularMarketVolume': 1000000
                }
            ]
        }
        
        results = run_market_scan()
        
        # Verify Yahoo query was called
        assert mock_screen.called
        
        # Check sort field (should be sorting by lowest percent change first)
        call_kwargs = mock_screen.call_args.kwargs
        assert call_kwargs['sortField'] == 'percentchange'
        assert call_kwargs['sortAsc'] is True
        
        # Check result
        assert len(results) == 1
        assert "NVDA" in results
        mock_update.assert_called_once()
        
    @patch('app.services.screener.yf.screen')
    def test_run_market_scan_empty(self, mock_screen):
        mock_screen.return_value = {}
        results = run_market_scan()
        assert results == []