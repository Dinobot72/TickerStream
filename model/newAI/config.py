import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "../logs")
DATA_DIR = os.path.join(BASE_DIR, "../data/train")

# v3: RIDE WINNERS, CUT LOSERS
ENV_KWARGS = {
    "data_dir": DATA_DIR,
    "lookback_window": 20,
    "transaction_cost": 0.001,
    "slippage": 0.001,
    "initial_balance": 10000,
    "max_position_pct": 0.50,
    "initial_stop_pct": 0.08,           # Start with -8% stop
    "trailing_stop_trigger": 0.20,      # Trail after +20% gain
    "trailing_stop_distance": 0.15,     # Trail 15% below peak
    "episode_length": 252,              # 1 year episodes
    "reward_scaling": 1.0,
}

# Training
TOTAL_TIMESTEPS = 2_000_000
TEST_TIMESTEPS  = 5_000
N_ENVS          = 8
LEARNING_RATE   = 5e-5          # Lower for stability
BATCH_SIZE      = 256
N_STEPS         = 1024

POLICY_KWARGS = {
    "lstm_hidden_size": 256,
    "n_lstm_layers": 2,
    "shared_lstm": True,
    "enable_critic_lstm": False,
    "net_arch": [256, 128],
}