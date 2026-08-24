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
    print(f"  TICKERSTREAM AI - ARCHITECTURE UPDATE (Single Stock, Shared Obs)")
    print(f"{'='*60}")

    train_tickers, test_tickers = get_tickers()

    with open(os.path.join(LOG_DIR, "test_tickers.pkl"), "wb") as f:
        pickle.dump(test_tickers, f)

    # Observation is manually scaled in build_observation, so norm_obs=False!
    # Rewards get normalized here for stability.
    raw_env = DummyVecEnv([make_env_fn(train_tickers) for _ in range(N_ENVS)])
    train_env = VecNormalize(raw_env, norm_obs=False, norm_reward=True, clip_reward=10.0)

    eval_env = DummyVecEnv([make_env_fn(test_tickers)])
    eval_env = VecNormalize(eval_env, norm_obs=False, norm_reward=True, clip_reward=10.0)

    steps = TEST_TIMESTEPS if test_mode else TOTAL_TIMESTEPS
    eval_freq = 1000 if test_mode else 10000
    save_freq = 2000 if test_mode else 20000
    prefix = "ppo_test" if test_mode else "ppo_trading"

    callbacks = [
        CheckpointCallback(save_freq=save_freq, save_path=os.path.join(LOG_DIR, "models"), name_prefix=prefix),
        EvalCallback(
            eval_env, best_model_save_path=os.path.join(LOG_DIR, "best_model"),
            eval_freq=eval_freq, n_eval_episodes=5, deterministic=True, verbose=1
        ),
        TensorboardCallback(),
        MetricLoggerCallback(LOG_DIR)
    ]

    print("🤖 Initializing RecurrentPPO...")
    model = RecurrentPPO(
        "MlpLstmPolicy",
        train_env,
        device="cpu",
        verbose=1,
        tensorboard_log=os.path.join(LOG_DIR, "tensorboard"),
        learning_rate=LEARNING_RATE,
        n_steps=N_STEPS,
        batch_size=BATCH_SIZE,
        ent_coef=0.01,
        clip_range=0.2,
        vf_coef=0.5,
        max_grad_norm=0.5,
        gamma=0.99,
        gae_lambda=0.95,
        policy_kwargs=POLICY_KWARGS
    )

    print(f"\n🚀 Training for {steps:,} timesteps...\n")
    model.learn(total_timesteps=steps, callback=callbacks)

    model.save(os.path.join(LOG_DIR, "models", "final_model"))
    train_env.save(os.path.join(LOG_DIR, "vec_normalize.pkl"))
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

    # No observation normalization needed based on new architecture constraint
    env = DummyVecEnv([make_env_fn(test_tickers)])
    env = VecNormalize.load(os.path.join(LOG_DIR, "vec_normalize.pkl"), env)
    env.training = False
    env.norm_reward = False  # Disable reward norm for realistic eval values

    model = RecurrentPPO.load(os.path.join(LOG_DIR, "best_model", "best_model"))

    obs = env.reset()
    ai_portfolio = []
    trade_log = []
    lstm_states = None
    episode_starts = np.ones(1, dtype=bool)

    # 1 Episode exactly = 1 year of trading for a single stock
    for step in range(ENV_KWARGS.get('episode_length', 252) * 5): # Evaluate across ~5 sequential tickers
        action, lstm_states = model.predict(obs, state=lstm_states, episode_start=episode_starts, deterministic=True)
        obs, rewards, dones, infos = env.step(action)
        episode_starts = dones
        info = infos[0]
        
        # Track portfolio
        ai_portfolio.append(info['portfolio_value'])

        if info.get('trade_closed'):
            trade_log.append({
                "Step": len(ai_portfolio) - 1,  # Global step count for the graph
                "Ticker": info.get('ticker', 'UNKNOWN'),
                "Result": "WIN" if info.get('is_win') else "LOSS",
                "Holding_Period": info.get('holding_period', 0),
            })
            
        if dones[0]:
            # Reset LSTM states strictly when an episode forces a reset (moving to next ticker)
            lstm_states = None 

    # 1. Output the Standard Portfolio Value Baseline Graph
    plt.figure(figsize=(12, 5))
    plt.plot(ai_portfolio, label='AI Agent', color='blue', linewidth=2)
    plt.axhline(y=10000, color='gray', linestyle='--', alpha=0.5, label='Starting Balance')
    plt.title("AI Agent Performance - Test Tickers")
    plt.xlabel("Global Steps")
    plt.ylabel("Portfolio Value ($)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(LOG_DIR, "plots", "eval_base.png"))
    print(f"Base valuation plot saved.")

    # 2. Output the Fixed Trade Map Scatter Overlay Graph
    if trade_log:
        df_trades = pd.DataFrame(trade_log)
        df_trades.to_csv(os.path.join(LOG_DIR, "test_trades.csv"), index=False)
        
        win_rate = df_trades['Result'].eq('WIN').mean()
        print(f"\nTotal Trades: {len(df_trades)}")
        print(f"Win Rate: {win_rate:.2%}")
        
        plt.figure(figsize=(14, 6))
        plt.plot(ai_portfolio, label='AI Agent Portfolio Value', color='blue', linewidth=2, alpha=0.3)
        plt.axhline(y=10000, color='gray', linestyle='--', alpha=0.5, label='Starting Balance')
        
        added_win_label, added_loss_label, added_buy_label = False, False, False
        
        for idx, row in df_trades.iterrows():
            sell_step = int(row['Step'])
            holding_period = int(row['Holding_Period'])
            buy_step = max(0, sell_step - holding_period)
            
            sell_val = ai_portfolio[min(sell_step, len(ai_portfolio)-1)]
            buy_val = ai_portfolio[buy_step]
            
            is_win = row['Result'] == 'WIN'
            color = 'green' if is_win else 'red'
            sell_marker = '^' if is_win else 'v'
            
            win_label = 'Winning Trade (Sell)' if (is_win and not added_win_label) else None
            loss_label = 'Losing Trade (Sell)' if (not is_win and not added_loss_label) else None
            buy_label = 'Buy Point' if not added_buy_label else None
            
            if is_win: added_win_label = True
            else: added_loss_label = True
            added_buy_label = True
            
            plt.scatter(buy_step, buy_val, color='black', marker='o', s=40, label=buy_label, zorder=4)
            plt.scatter(sell_step, sell_val, color=color, marker=sell_marker, s=80, label=win_label if is_win else loss_label, zorder=5)
            plt.plot([buy_step, sell_step], [buy_val, sell_val], color=color, linestyle='--', linewidth=1.5, zorder=3, alpha=0.8)
            
        plt.title(f"AI Agent Trade History (Win Rate: {win_rate:.1%})")
        plt.xlabel("Global Environment Steps")
        plt.ylabel("Portfolio Value ($)")
        plt.legend(loc='upper left')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(LOG_DIR, "plots", "trade_plot.png"))
        print("Trade scatter plot with holding periods saved successfully.")
    else:
        print("⚠ No trades were executed during this evaluation period to plot.")
        
    final_val = ai_portfolio[-1] if ai_portfolio else 10000
    print(f"Final Portfolio: ${final_val:,.2f} ({(final_val/10000-1)*100:+.1f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["train", "test_train", "evaluate"], required=True)
    args = parser.parse_args()

    if args.mode == "train": train(test_mode=False)
    elif args.mode == "test_train": train(test_mode=True)
    elif args.mode == "evaluate": evaluate()