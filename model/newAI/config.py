import os

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "../logs")
DATA_DIR = os.path.join(BASE_DIR, "../data/train")
MACRO_DIR = "macro"

# Environment Parameters (UPDATED FOR BETTER PERFORMANCE)
ENV_KWARGS = {
    "data_dir": DATA_DIR,
    "macro_dir": MACRO_DIR,
    "lookback_window": 20,
    "transaction_cost": 0.001,  # 0.1% per trade
    "slippage": 0.001,          # 0.1% slippage estimate
    "initial_balance": 10000,
    "max_position_pct": 0.85,    # 85% max position
    "target_atr_mult": 1.2,     # CHANGED: Tighter targets (from 2.0)
    "stop_atr_mult": 0.8,       # CHANGED: Tighter stops (from 1.5)
    "pdt_min_balance": 25000,   # Pattern Day Trader rule
    "max_day_trades": 3,
    "reward_scaling": 10.0,     # CHANGED: Stronger signal (from 0.01)
}

# Training Hyperparameters (UPDATED)
TOTAL_TIMESTEPS = 1_000_000     # CHANGED: Train longer (from 500k)
TEST_TIMESTEPS = 10_000
N_ENVS = 4                      # Number of parallel environments
LEARNING_RATE = 3e-5            # CHANGED: Lower for stability (from 3e-4)
BATCH_SIZE = 64
N_STEPS = 2048                  # Steps per env per update

# LSTM Hyperparameters
POLICY_KWARGS = {
    "lstm_hidden_size": 128,
    "n_lstm_layers": 2,
    "shared_lstm": True,
    "enable_critic_lstm": False,
}