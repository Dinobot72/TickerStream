import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "../logs")
DATA_DIR = os.path.join(BASE_DIR, "../data/train")

# v4: single-ticker Discrete(3), shared_obs.py observation builder,
# smooth reward scaling (see trading_env_v4.py docstring for why the
# v3 tiered/exponential reward was replaced).
#
# NOTE: v3's trailing-stop-loss mechanic (initial_stop_pct /
# trailing_stop_trigger / trailing_stop_distance) is NOT carried over.
# In v4 the agent decides every SELL itself with no automatic stop-loss
# floor - that's a real behavior change, not an oversight. If you want
# a hard risk floor back, it's worth adding as an env-enforced
# constraint (auto-close on breach) rather than folding it into reward
# shaping again, to avoid recreating the same scale-mismatch problem.
ENV_KWARGS = {
    "data_dir": DATA_DIR,
    "transaction_cost": 0.001,
    "slippage": 0.001,
    "initial_balance": 10000,
    "position_size_pct": 0.85,
    "episode_length": 252,           # 1 year episodes
    "reward_scale": 100.0,           # step portfolio-return% -> reward
    "trade_reward_scale": 40.0,      # closed-trade profit% -> reward
    "invalid_action_penalty": -0.5,
    "invalid_action_penalty": -0.5,
    "holding_decay_start_days": 15,  # no penalty for holds up to this long
    "holding_decay_per_day": 0.05,   # then this much reward lost per extra day held -
                                      # "trade often": makes stale opens actively cost
                                      # something instead of being reward-free forever
}

# Training
TOTAL_TIMESTEPS = 3_000_000
TEST_TIMESTEPS  = 50_000
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