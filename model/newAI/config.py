import os

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "../logs")
DATA_DIR = os.path.join(BASE_DIR, "../data/train")

# ------------------------------------------------------------------
# Environment Parameters
# These must match what AdvancedTradingEnv expects
# ------------------------------------------------------------------
ENV_KWARGS = {
    "data_dir": DATA_DIR,
    "lookback_window": 20,
    "transaction_cost": 0.001,      # 0.1% per side
    "slippage": 0.001,              # 0.1% slippage
    "initial_balance": 10000,
    "max_position_pct": 0.85,       # Use 85% of balance per trade
    "stop_loss_pct": 0.05,          # Exit if down 5%
    "take_profit_pct": 0.10,        # Exit if up 10%
    "episode_length": 252,          # 1 full trading year per episode
    "reward_scaling": 1.0,
}

# ------------------------------------------------------------------
# Training Hyperparameters
# ------------------------------------------------------------------
TOTAL_TIMESTEPS = 2_000_000         # ~7,936 episodes of 252 steps
TEST_TIMESTEPS  = 20_000            # Quick smoke test
N_ENVS          = 8                 # Parallel environments (more = faster)
LEARNING_RATE   = 1e-3              # Conservative - stable learning
BATCH_SIZE      = 256               # Larger batch for stability
N_STEPS         = 1024              # Steps per env before update

# ------------------------------------------------------------------
# LSTM Policy Architecture
# Bigger LSTM = more memory for patterns across 252-day episodes
# ------------------------------------------------------------------
POLICY_KWARGS = {
    "lstm_hidden_size": 256,        # Larger than before (128 → 256)
    "n_lstm_layers": 2,
    "shared_lstm": True,
    "enable_critic_lstm": False,
    "net_arch": [256, 128],         # Deeper network
}