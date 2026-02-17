import os
import argparse
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from sb3_contrib import RecurrentPPO

# --- Import Local Modules ---
from config import (
    ENV_KWARGS, LOG_DIR, DATA_DIR, 
    TOTAL_TIMESTEPS, TEST_TIMESTEPS, N_ENVS, POLICY_KWARGS, LEARNING_RATE
)
from advanced_training_env import AdvancedTradingEnv
from callbacks import TensorboardCallback, MetricLoggerCallback

# Ensure directories exist
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.join(LOG_DIR, "models"), exist_ok=True)
os.makedirs(os.path.join(LOG_DIR, "plots"), exist_ok=True)

# --- Helper Functions ---

def get_tickers():
    """
    Load all available tickers and split them into Train (80%) and Test (20%) sets.
    """
    # Load all parquet files excluding macro data
    all_files = [f.replace('.parquet', '') for f in os.listdir(DATA_DIR) if f.endswith('.parquet') and f != 'macro']
    
    if not all_files:
        raise ValueError(f"No training data found in {DATA_DIR}. Please run data collection first.")
    
    # 80/20 Split
    train, test = train_test_split(all_files, test_size=0.2, random_state=42)
    return train, test

def make_env_fn(tickers_list):
    """
    Factory function required by Stable Baselines 3 to create environments.
    """
    def _init():
        return AdvancedTradingEnv(tickers=tickers_list, **ENV_KWARGS)
    return _init

# --- Core Modes ---

def train(test_mode=False):
    """
    Main training loop.
    test_mode=True runs a short loop to verify code works.
    """
    print(f"--- STARTING TRAINING (Test Mode: {test_mode}) ---")
    print(f"🔧 UPDATED HYPERPARAMETERS:")
    print(f"   - Reward Scaling: {ENV_KWARGS['reward_scaling']}")
    print(f"   - Max Position: {ENV_KWARGS['max_position_pct']*100}%")
    print(f"   - Target/Stop: {ENV_KWARGS['target_atr_mult']}x / {ENV_KWARGS['stop_atr_mult']}x ATR")
    print(f"   - Learning Rate: {LEARNING_RATE}")
    print(f"   - Entropy Coef: 0.15 (increased exploration)")
    
    # 1. Prepare Data
    train_tickers, test_tickers = get_tickers()
    print(f"\n📊 Training on {len(train_tickers)} tickers.")
    print(f"📊 Holding out {len(test_tickers)} tickers for testing.")
    
    # Save test tickers
    with open(os.path.join(LOG_DIR, "test_tickers.pkl"), "wb") as f:
        pickle.dump(test_tickers, f)

    # 2. Create Environments
    env = DummyVecEnv([make_env_fn(train_tickers) for _ in range(N_ENVS)])
    env = VecNormalize(env, norm_obs=True, norm_reward=True, clip_obs=10.)
    
    eval_env = DummyVecEnv([make_env_fn(train_tickers)])
    eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=True, clip_obs=10.)

    # 3. Configure Run
    if test_mode:
        steps = TEST_TIMESTEPS
        eval_freq = 500
        save_freq = 1000
        prefix = "ppo_test"
    else:
        steps = TOTAL_TIMESTEPS
        eval_freq = 5000
        save_freq = 10000
        prefix = "ppo_trading"

    # 4. Callbacks
    callbacks = [
        CheckpointCallback(save_freq=save_freq, save_path=os.path.join(LOG_DIR, "models"), name_prefix=prefix),
        EvalCallback(eval_env, best_model_save_path=os.path.join(LOG_DIR, "best_model"), eval_freq=eval_freq, deterministic=True),
        TensorboardCallback(),
        MetricLoggerCallback(LOG_DIR)
    ]

    # 5. Initialize Model with UPDATED hyperparameters
    print("\n🤖 Initializing RecurrentPPO model...")
    model = RecurrentPPO(
        "MlpLstmPolicy",
        env,
        verbose=1,
        tensorboard_log=os.path.join(LOG_DIR, "tensorboard"),
        learning_rate=LEARNING_RATE,        # 3e-5 (lower for stability)
        ent_coef=0.15,                      # INCREASED from 0.01 for more exploration
        clip_range=0.3,                     # INCREASED from 0.2 for larger updates
        vf_coef=0.5,                        # Value function coefficient
        max_grad_norm=0.5,                  # Gradient clipping
        policy_kwargs=POLICY_KWARGS
    )

    print(f"\n🚀 Starting training for {steps:,} timesteps...")
    print("=" * 60)

    # 6. Train
    model.learn(total_timesteps=steps, callback=callbacks)
    
    # 7. Save Artifacts
    model.save(os.path.join(LOG_DIR, "models", "final_model"))
    env.save(os.path.join(LOG_DIR, "vec_normalize.pkl"))
    print("\n✅ Training Complete. Models and stats saved.")

def benchmark():
    """
    Runs a Random Agent on the Test Tickers to create a baseline for comparison.
    """
    print("--- RUNNING RANDOM BENCHMARK ---")
    
    try:
        with open(os.path.join(LOG_DIR, "test_tickers.pkl"), "rb") as f:
            test_tickers = pickle.load(f)
    except FileNotFoundError:
        print("Error: test_tickers.pkl not found. Run --mode train or --mode test_train first.")
        return

    env = DummyVecEnv([make_env_fn(test_tickers)])
    env = VecNormalize(env, norm_obs=True, norm_reward=True, clip_obs=10.)
    env.training = False

    obs = env.reset()
    portfolio_values = []
    
    for _ in range(2000):
        action = [env.action_space.sample()]
        obs, rewards, dones, infos = env.step(action)
        portfolio_values.append(infos[0]['portfolio_value'])
        
        if dones[0]:
            break
            
    with open(os.path.join(LOG_DIR, "benchmark_data.pkl"), "wb") as f:
        pickle.dump(portfolio_values, f)
    
    print(f"Benchmark run complete. Data saved for {len(portfolio_values)} steps.")

def evaluate():
    """
    Runs the Trained AI on Test Tickers, generates plots, and saves a Trade Log CSV.
    """
    print("--- RUNNING EVALUATION ---")
    
    try:
        with open(os.path.join(LOG_DIR, "test_tickers.pkl"), "rb") as f:
            test_tickers = pickle.load(f)
    except FileNotFoundError:
        print("Error: Run training first to generate test set.")
        return

    env = DummyVecEnv([make_env_fn(test_tickers)])
    env = VecNormalize.load(os.path.join(LOG_DIR, "vec_normalize.pkl"), env)
    env.training = False

    model = RecurrentPPO.load(os.path.join(LOG_DIR, "models", "final_model"))

    obs = env.reset()
    ai_portfolio = []
    trade_log = []
    
    lstm_states = None
    episode_starts = np.ones(1, dtype=bool)
    
    print("Simulating trading episode...")
    for step in range(2000):
        action, lstm_states = model.predict(
            obs, 
            state=lstm_states, 
            episode_start=episode_starts, 
            deterministic=True
        )
        obs, rewards, dones, infos = env.step(action)
        episode_starts = dones
        
        info = infos[0]
        ai_portfolio.append(info['portfolio_value'])

        if info.get('trade_closed'):
            trade_log.append({
                "Step": step,
                "Ticker": info.get('ticker'),
                "Result": "WIN" if info.get('is_win') else "LOSS",
                "Profit": info.get('balance') - 10000,
                "Holding_Period": info.get('holding_period', 0),
                "Price_vs_SMA": info.get('price_vs_sma', 0)
            })

        if dones[0]:
            break

    try:
        with open(os.path.join(LOG_DIR, "benchmark_data.pkl"), "rb") as f:
            random_portfolio = pickle.load(f)
    except FileNotFoundError:
        print("Warning: No benchmark data found. Run --mode benchmark to see comparison.")
        random_portfolio = []

    plt.figure(figsize=(12, 6))
    plt.plot(ai_portfolio, label='AI Agent', color='blue', linewidth=2)
    
    if random_portfolio:
        min_len = min(len(ai_portfolio), len(random_portfolio))
        plt.plot(random_portfolio[:min_len], label='Random Baseline', color='gray', linestyle='--', alpha=0.7)
    
    plt.title("Agent Performance on Unseen Test Data")
    plt.xlabel("Steps")
    plt.ylabel("Portfolio Value ($)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plot_path = os.path.join(LOG_DIR, "plots", "evaluation_result.png")
    plt.savefig(plot_path)
    print(f"Evaluation Plot saved to: {plot_path}")

    if trade_log:
        df_trades = pd.DataFrame(trade_log)
        csv_path = os.path.join(LOG_DIR, "test_trades.csv")
        df_trades.to_csv(csv_path, index=False)
        
        win_rate = df_trades['Result'].eq('WIN').mean()
        print(f"\n--- Results Summary ---")
        print(f"Total Trades: {len(df_trades)}")
        print(f"Win Rate: {win_rate:.2%}")
        print(f"Detailed Trade Log saved to: {csv_path}")

# --- CLI Entry Point ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TickerStream AI Training Controller")
    parser.add_argument(
        "--mode", 
        choices=["train", "test_train", "benchmark", "evaluate"], 
        required=True, 
        help="Select operation mode."
    )
    args = parser.parse_args()

    if args.mode == "train":
        train(test_mode=False)
    elif args.mode == "test_train":
        train(test_mode=True)
    elif args.mode == "benchmark":
        benchmark()
    elif args.mode == "evaluate":
        evaluate()