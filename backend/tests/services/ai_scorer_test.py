import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock
from app.services.ai_scorer import AIScorer

@pytest.fixture
def mock_dependencies():
    with patch('app.services.ai_scorer.RecurrentPPO.load') as mock_load, \
         patch('app.services.ai_scorer.fetch_live_history') as mock_fetch, \
         patch('app.services.ai_scorer.build_observation') as mock_build, \
         patch('app.services.ai_scorer.get_window') as mock_window:
        
        mock_model = MagicMock()
        # Returns (action, next_state). 1 = BUY
        mock_model.predict.return_value = (np.array([1]), (np.zeros((1, 1, 64)), np.zeros((1, 1, 64))))
        
        mock_policy = MagicMock()
        mock_policy.obs_to_tensor.return_value = (MagicMock(), MagicMock())
        
        # Define the LSTM hidden state shape for the zero-state initialization
        mock_policy.lstm_hidden_state_shape = (1, 1, 64)
        
        # Explicitly set the device to 'cpu' to satisfy th.tensor()
        mock_policy.device = 'cpu'
        
        # Properly mock the PyTorch tensor chain: probs.cpu().numpy()
        mock_dist = MagicMock()
        mock_probs = MagicMock()
        mock_probs.cpu.return_value.numpy.return_value = np.array([[0.2, 0.7, 0.1]])
        mock_dist.distribution.probs = mock_probs
        
        mock_policy.get_distribution.return_value = (mock_dist, None)
        mock_model.policy = mock_policy
        mock_load.return_value = mock_model
        
        # Use a real pandas DataFrame so df.iloc[-1]['Close'] correctly yields 150.0
        mock_df = pd.DataFrame({'Close': [150.0]})
        mock_fetch.return_value = mock_df
        
        # Mock Observation
        mock_build.return_value = np.zeros(100)
        
        yield mock_load, mock_fetch, mock_build

@pytest.fixture
def scorer(mock_dependencies):
    return AIScorer(model_path="dummy_path")

class TestAIScorer:
    def test_score_stock_buy_action(self, scorer, mock_dependencies):
        result = scorer.score_stock(
            ticker="AAPL",
            balance=10000.0,
            shares=0
        )
        
        assert result["action"] == "BUY"
        assert result["confidence"] == 0.7
        assert result["current_price"] == 150.0
        assert result["raw_action"] == 1
        assert "AAPL" in scorer.lstm_states

    def test_score_stock_insufficient_data(self, scorer):
        with patch('app.services.ai_scorer.fetch_live_history') as mock_fetch:
            mock_fetch.return_value = None
            
            result = scorer.score_stock("AAPL", 10000.0, 0)
            
            assert result["action"] == "HOLD"
            assert "insufficient data" in result["error"]

    def test_reset_state(self, scorer):
        scorer.lstm_states["AAPL"] = np.array([0.1])
        scorer.episode_starts["AAPL"] = False
        
        scorer.reset_state("AAPL")
        assert "AAPL" not in scorer.lstm_states
        assert "AAPL" not in scorer.episode_starts