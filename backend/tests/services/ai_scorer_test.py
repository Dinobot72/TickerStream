import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from app.services.ai_scorer import AIScorer

@pytest.fixture
def mock_ppo():
    with patch('app.services.ai_scorer.RecurrentPPO.load') as mock_load:
        mock_model = MagicMock()
        # Mock predict to return a discrete action (0=HOLD, 1=BUY, 2=SELL) and a dummy hidden state
        mock_model.predict.return_value = (np.array([1]), np.array([0.5, 0.5]))
        mock_load.return_value = mock_model
        yield mock_load

@pytest.fixture
def scorer(mock_ppo):
    return AIScorer(model_path="dummy_path")

class TestAIScorer:
    def test_init_loads_model(self, mock_ppo):
        scorer = AIScorer("dummy_path")
        mock_ppo.assert_called_once_with("dummy_path")
        assert scorer.model is not None

    def test_normalize_obs_without_stats(self, scorer):
        obs = np.array([1.0, 2.0, 3.0])
        scorer.obs_mean = None
        result = scorer._normalize_obs(obs)
        np.testing.assert_array_equal(result, obs)

    @patch('app.services.ai_scorer.get_live_observation')
    @patch('app.services.ai_scorer.get_current_price')
    def test_score_stock_success(self, mock_get_price, mock_get_obs, scorer):
        # Mock dependencies
        mock_get_obs.return_value = np.zeros(707)
        mock_get_price.return_value = 150.0
        
        candidates = ["AAPL", "MSFT", "GOOGL", "AMZN", "SPY"]
        result = scorer.score_stock(
            candidates=candidates,
            held_ticker="AAPL",
            balance=10000.0,
            shares=10
        )
        
        assert result["action"] == "BUY"
        assert result["confidence"] == 0.7
        assert result["current_price"] == 150.0
        assert "AAPL" in scorer.lstm_states

    def test_score_stock_invalid_candidates_length(self, scorer):
        # Must have exactly 5 candidates[cite: 1]
        result = scorer.score_stock(["AAPL"], "AAPL", 10000.0, 10)
        assert result["action"] == "HOLD"
        assert "error" in result

    def test_reset_state(self, scorer):
        scorer.lstm_states["AAPL"] = np.array([0.1])
        scorer.episode_starts["AAPL"] = False
        
        scorer.reset_state("AAPL")
        assert "AAPL" not in scorer.lstm_states
        assert "AAPL" not in scorer.episode_starts