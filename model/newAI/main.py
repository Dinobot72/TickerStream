import os
import argparse
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize, SubprocVecEnv
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from sb3_contrib import RecurrentPPO

from config import (
    ENV_KWARGS, LOG_DIR, DATA_DIR,
    TOTAL_TIMESTEPS, TEST_TIMESTEPS, N_ENVS, POLICY_KWARGS,
    LEARNING_RATE, BATCH_SIZE, N_STEPS
)
from advanced_training_env import AdvancedTradingEnv
from callbacks import TensorboardCallback, MetricLoggerCallback

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.join(LOG_DIR, "models"), exist_ok=True)
os.makedirs(os.path.join(LOG_DIR, "plots"), exist_ok=True)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def get_tickers():
    all_files = [
        f.replace('.parquet', '') 
        for f in os.listdir(DATA_DIR) 
        if f.endswith('.parquet')
    ]
    if not all_files:
        raise ValueError(f"No training data found in {DATA_DIR}.")
    
    # Need at least 5 tickers for N_CANDIDATES
    if len(all_files) < 5:
        raise ValueError(f"Need at least 5 tickers, found {len(all_files)}")

    train, test = train_test_split(all_files, test_size=0.2, random_state=42)
    print(f"✅ {len(train)} train tickers, {len(test)} test tickers")
    return train, test

def make_env_fn(tickers_list):
    def _init():
        return AdvancedTradingEnv(tickers=tickers_list, **ENV_KWARGS)
    return _init

# ------------------------------------------------------------------
# Train
# ------------------------------------------------------------------

def train(test_mode=False):
    print(f"\n{'='*60}")
    print(f"  TICKERSTREAM AI v2 - TRAINING")
    print(f"{'='*60}")
    print(f"\n📋 Configuration:")
    print(f"   Observation size:  {AdvancedTradingEnv.OBS_DIM} features")
    print(f"   Candidates/step:   {AdvancedTradingEnv.N_CANDIDATES} stocks visible at once")
    print(f"   Episode length:    {ENV_KWARGS['episode_length']} days (1 year)")
    # print(f"   Stop loss:         {ENV_KWARGS['stop_loss_pct']*100:.0f}%")
    # print(f"   Take profit:       {ENV_KWARGS['take_profit_pct']*100:.0f}%")
    print(f"   Parallel envs:     {N_ENVS}")
    print(f"   Total timesteps:   {TOTAL_TIMESTEPS:,}")
    print(f"   Learning rate:     {LEARNING_RATE}")
    print()

    train_tickers, test_tickers = get_tickers()

    with open(os.path.join(LOG_DIR, "test_tickers.pkl"), "wb") as f:
        pickle.dump(test_tickers, f)

    # Training environments
    env = DummyVecEnv([make_env_fn(train_tickers) for _ in range(N_ENVS)])
    env = VecNormalize(env, norm_obs=True, norm_reward=False, clip_obs=10.)

    # Eval environment
    eval_env = DummyVecEnv([make_env_fn(test_tickers)])
    eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=False, clip_obs=10.)

    steps    = TEST_TIMESTEPS if test_mode else TOTAL_TIMESTEPS
    eval_freq = 1000 if test_mode else 10000
    save_freq = 2000 if test_mode else 20000
    prefix   = "ppo_test" if test_mode else "ppo_trading"

    callbacks = [
        CheckpointCallback(
            save_freq=save_freq,
            save_path=os.path.join(LOG_DIR, "models"),
            name_prefix=prefix
        ),
        EvalCallback(
            eval_env,
            best_model_save_path=os.path.join(LOG_DIR, "best_model"),
            eval_freq=eval_freq,
            n_eval_episodes=10,       # Average over 10 episodes for stable eval
            deterministic=True,
            verbose=1
        ),
        TensorboardCallback(),
        MetricLoggerCallback(LOG_DIR)
    ]

    print("🤖 Initializing RecurrentPPO...")
    model = RecurrentPPO(
        "MlpLstmPolicy",
        env,
        verbose=1,
        tensorboard_log=os.path.join(LOG_DIR, "tensorboard"),
        learning_rate=LEARNING_RATE,
        n_steps=N_STEPS,
        batch_size=BATCH_SIZE,
        ent_coef=0.01,              # Lower entropy - let it converge
        clip_range=0.2,
        vf_coef=0.5,
        max_grad_norm=0.5,
        gamma=0.99,                 # Value future rewards
        gae_lambda=0.95,
        policy_kwargs=POLICY_KWARGS
    )

    print(f"\n🚀 Training for {steps:,} timesteps...\n")
    model.learn(total_timesteps=steps, callback=callbacks)

    model.save(os.path.join(LOG_DIR, "models", "final_model"))
    env.save(os.path.join(LOG_DIR, "vec_normalize.pkl"))
    print("\n✅ Training complete!")

# ------------------------------------------------------------------
# Evaluate
# ------------------------------------------------------------------

def evaluate():
    print("--- RUNNING EVALUATION ---")

    try:
        with open(os.path.join(LOG_DIR, "test_tickers.pkl"), "rb") as f:
            test_tickers = pickle.load(f)
    except FileNotFoundError:
        print("❌ No test_tickers.pkl - run training first")
        return

    env = DummyVecEnv([make_env_fn(test_tickers)])
    env = VecNormalize.load(os.path.join(LOG_DIR, "vec_normalize.pkl"), env)
    env.training = False

    model = RecurrentPPO.load(os.path.join(LOG_DIR, "best_model", "best_model"))

    obs = env.reset()
    ai_portfolio = []
    trade_log = []
    lstm_states = None
    episode_starts = np.ones(1, dtype=bool)

    for step in range(2000):
        action, lstm_states = model.predict(
            obs, state=lstm_states,
            episode_start=episode_starts, deterministic=True
        )
        obs, rewards, dones, infos = env.step(action)
        episode_starts = dones

        info = infos[0]
        ai_portfolio.append(info['portfolio_value'])

        if info.get('trade_closed'):
            trade_log.append({
                "Step": step,
                "Ticker": info.get('held_ticker'),
                "Candidates": str(info.get('candidates', [])),
                "Result": "WIN" if info.get('is_win') else "LOSS",
                "Holding_Period": info.get('holding_period', 0),
            })

        if dones[0]:
            break

    # Plot
    plt.figure(figsize=(12, 5))
    plt.plot(ai_portfolio, label='AI Agent', color='blue', linewidth=2)
    plt.axhline(y=10000, color='gray', linestyle='--', alpha=0.5, label='Starting Balance')
    plt.title("AI Agent Performance - Test Tickers (v2)")
    plt.xlabel("Steps")
    plt.ylabel("Portfolio Value ($)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(LOG_DIR, "plots", "eval_v2.png"))
    print(f"Plot saved.")

    if trade_log:
        df_trades = pd.DataFrame(trade_log)
        df_trades.to_csv(os.path.join(LOG_DIR, "test_trades.csv"), index=False)
        win_rate = df_trades['Result'].eq('WIN').mean()
        print(f"\nTotal Trades: {len(df_trades)}")
        print(f"Win Rate: {win_rate:.2%}")
        
        final_val = ai_portfolio[-1] if ai_portfolio else 10000
        print(f"Final Portfolio: ${final_val:,.2f} ({(final_val/10000-1)*100:+.1f}%)")

# ------------------------------------------------------------------
# Benchmark
# ------------------------------------------------------------------

def benchmark():
    print("--- RUNNING RANDOM BENCHMARK ---")

    try:
        with open(os.path.join(LOG_DIR, "test_tickers.pkl"), "rb") as f:
            test_tickers = pickle.load(f)
    except FileNotFoundError:
        print("❌ Run training first")
        return

    env = DummyVecEnv([make_env_fn(test_tickers)])
    env = VecNormalize(env, norm_obs=True, norm_reward=False, clip_obs=10.)
    env.training = False

    obs = env.reset()
    portfolio_values = []

    for _ in range(2000):
        action = [env.action_space.sample()]
        obs, _, dones, infos = env.step(action)
        portfolio_values.append(infos[0]['portfolio_value'])
        if dones[0]:
            break

    with open(os.path.join(LOG_DIR, "benchmark_data.pkl"), "wb") as f:
        pickle.dump(portfolio_values, f)

    final = portfolio_values[-1] if portfolio_values else 10000
    print(f"Random agent final: ${final:,.2f} ({(final/10000-1)*100:+.1f}%)")

# ------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["train", "test_train", "evaluate", "benchmark"],
        required=True
    )
    args = parser.parse_args()

    if args.mode == "train":
        train(test_mode=False)
    elif args.mode == "test_train":
        train(test_mode=True)
    elif args.mode == "evaluate":
        evaluate()
    elif args.mode == "benchmark":
        benchmark()