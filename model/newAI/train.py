import os
import gymnasium as gym
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from sb3_contrib import RecurrentPPO
from advanced_training_env import AdvancedTradingEnv

# Configuration
ENV_KWARGS = {
    "data_dir": "model/data/train",
    "macro_dir": "macro",
    "lookback_window": 20,
    "transaction_cost": 0.001,
    "slippage": 0.001,
    "initial_balance": 10000,
    "max_position_pct": 0.25,
    "target_atr_mult": 2.0,
    "stop_atr_mult": 1.5,
    "pdt_min_balance": 25000,
    "max_day_trades": 3,
    "reward_scaling": 0.01,  # to keep rewards manageable
}
TOTAL_TIMESTEPS = 500_000
TEST_TIMESTEPS = 10000
N_ENVS = 4
LOG_DIR = "model/logs"
os.makedirs(LOG_DIR, exist_ok=True)

def make_env():
    def _init():
        return AdvancedTradingEnv(**ENV_KWARGS)
    return _init

if __name__ == "__main__":

    if input("Are you testing? (y/n) ").lower() == "y":
        steps = TEST_TIMESTEPS
        eval_f = 250
        save_f = 500
        prefix = "ppo_trading_test"
    else:
        steps = TOTAL_TIMESTEPS
        eval_f = 5000
        save_f = 10000
        prefix = "ppo_trading"
        
    # Create vectorized environment
    env = DummyVecEnv([make_env() for _ in range(N_ENVS)])
    env = VecNormalize(env, norm_obs=True, norm_reward=True, clip_obs=10.)

    # Evaluation environment (single, for monitoring)
    eval_env = DummyVecEnv([make_env()])
    eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=True, clip_obs=10.)

    # Callbacks
    checkpoint_callback = CheckpointCallback(
        save_freq=10000,
        save_path=os.path.join(LOG_DIR, "models"),
        name_prefix="ppo_trading"
    )
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=os.path.join(LOG_DIR, "best_model"),
        log_path=LOG_DIR,
        eval_freq=5000,
        deterministic=True,
        render=False
    )

    # Initialize model
    # Use RecurrentPPO from sb3_contrib for LSTM support
    model = RecurrentPPO(
        "MlpLstmPolicy",
        env,
        verbose=1,
        tensorboard_log=os.path.join(LOG_DIR, "tensorboard"),
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,
        policy_kwargs={
            "lstm_hidden_size": 128,
            "n_lstm_layers": 2,
            "shared_lstm": True,
            "enable_critic_lstm": False,
        }
    )

    # Train
    model.learn(
        total_timesteps=steps,
        callback=[checkpoint_callback, eval_callback]
    )

    # Save final model
    model.save(os.path.join(LOG_DIR, "models", "final_model"))
    env.save(os.path.join(LOG_DIR, "vec_normalize.pkl"))