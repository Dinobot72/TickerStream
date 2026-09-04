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
from trading_env_v4 import TradingEnvV4
from collapse_guard_callback import CollapseGuardCallback
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
    if len(all_files) < 2:
        raise ValueError(f"Need at least 2 tickers (train/test split), found {len(all_files)}")

    train, test = train_test_split(all_files, test_size=0.2, random_state=42)
    print(f"✅ {len(train)} train tickers, {len(test)} test tickers")
    return train, test

def make_env_fn(tickers_list):
    def _init():
        return TradingEnvV4(tickers=tickers_list, **ENV_KWARGS)
    return _init

def make_vec_normalize(venv, training: bool = True):
    """
    v4: observations are already hand-scaled in shared_obs.py, so
    norm_obs=False here - normalizing twice was part of what saturated
    a chunk of the input on live out-of-distribution tickers (see
    diagnose_normalization.py). norm_reward=True is now the safety net
    instead, paired with the smoother reward formula in TradingEnvV4.
    """
    venv = VecNormalize(venv, norm_obs=False, norm_reward=True, clip_reward=10.0)
    venv.training = training
    return venv

# ------------------------------------------------------------------
# Train
# ------------------------------------------------------------------

def train(test_mode=False):
    print(f"\n{'='*60}")
    print(f"  TICKERSTREAM AI v4 - TRAINING")
    print(f"{'='*60}")
    print(f"\n📋 Configuration:")
    print(f"   Observation size:  {TradingEnvV4.OBS_DIM} features")
    print(f"   Action space:      HOLD / BUY / SELL (single ticker per episode)")
    print(f"   Episode length:    {ENV_KWARGS['episode_length']} days (1 year)")
    print(f"   Parallel envs:     {N_ENVS}")
    print(f"   Total timesteps:   {TOTAL_TIMESTEPS:,}")
    print(f"   Learning rate:     {LEARNING_RATE}")
    print()

    train_tickers, test_tickers = get_tickers()

    with open(os.path.join(LOG_DIR, "test_tickers.pkl"), "wb") as f:
        pickle.dump(test_tickers, f)

    # Training environments
    env = DummyVecEnv([make_env_fn(train_tickers) for _ in range(N_ENVS)])
    env = make_vec_normalize(env, training=True)

    # Eval environment
    eval_env = DummyVecEnv([make_env_fn(test_tickers)])
    eval_env = make_vec_normalize(eval_env, training=False)

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
            n_eval_episodes=10,
            deterministic=True,
            verbose=1
        ),
        TensorboardCallback(),
        MetricLoggerCallback(LOG_DIR),
        # Halts training early if entropy stays near max(ln 3) instead of
        # gradually decreasing - the exact signature of the v3 collapse.
        CollapseGuardCallback(
            check_every_steps=10_000,
            max_entropy_for_n_actions=TradingEnvV4.N_ACTIONS,
        ),
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
    env.save(os.path.join(LOG_DIR, "best_model", "vec_normalize.pkl"))
    print("\n✅ Training complete!")

# ------------------------------------------------------------------
# Evaluate
# ------------------------------------------------------------------

def evaluate(n_episodes=20):
    print(f"--- RUNNING EVALUATION ({n_episodes} episodes) ---")

    try:
        with open(os.path.join(LOG_DIR, "test_tickers.pkl"), "rb") as f:
            test_tickers = pickle.load(f)
    except FileNotFoundError:
        print("❌ No test_tickers.pkl - run training first")
        return

    env = DummyVecEnv([make_env_fn(test_tickers)])
    env = VecNormalize.load(os.path.join(LOG_DIR, "best_model", "vec_normalize.pkl"), env)
    env.training = False

    model = RecurrentPPO.load(os.path.join(LOG_DIR, "best_model", "best_model"))

    obs = env.reset()
    lstm_states = None
    episode_starts = np.ones(1, dtype=bool)

    episode_curves = []
    current_curve = []
    trade_log = []
    episode_idx = 0

    # Safety cap in case an episode never terminates for some reason -
    # avoids an infinite loop instead of trusting `dones` alone.
    max_steps = n_episodes * (ENV_KWARGS.get("episode_length", 252) + 10)
    step = 0
    while episode_idx < n_episodes and step < max_steps:
        action, lstm_states = model.predict(
            obs, state=lstm_states,
            episode_start=episode_starts, deterministic=True
        )
        obs, rewards, dones, infos = env.step(action)
        episode_starts = dones

        info = infos[0]
        current_curve.append(info['portfolio_value'])

        if info.get('trade_closed'):
            trade_log.append({
                "Episode": episode_idx,
                "Step": step,
                "Ticker": info.get('ticker'),
                "Result": "WIN" if info.get('is_win') else "LOSS",
                "Profit_Pct": info.get('profit_pct', 0.0),
                "Holding_Period": info.get('holding_period', 0),
            })

        step += 1
        if dones[0]:
            episode_curves.append(current_curve)
            current_curve = []
            episode_idx += 1

    if current_curve:  # ran out of steps mid-episode - keep partial data
        episode_curves.append(current_curve)

    if not episode_curves:
        print("❌ No completed episodes - check episode_length / data availability")
        return

    finals = np.array([c[-1] for c in episode_curves if c])
    print(f"\nEpisodes completed: {len(episode_curves)}")
    print(f"Mean final portfolio: ${finals.mean():,.2f} ({(finals.mean()/10000-1)*100:+.1f}%)")
    print(f"Std dev:              ${finals.std():,.2f}")
    print(f"Min / Max:            ${finals.min():,.2f} / ${finals.max():,.2f}")

    # Mean curve +/- std band across episodes (truncated to shortest episode
    # so every column of the array has a value from every episode)
    min_len = min(len(c) for c in episode_curves)
    curve_arr = np.array([c[:min_len] for c in episode_curves])
    mean_curve = curve_arr.mean(axis=0)
    std_curve = curve_arr.std(axis=0)

    plt.figure(figsize=(12, 5))
    plt.plot(mean_curve, label=f'AI Agent (mean of {len(episode_curves)} episodes)', color='blue', linewidth=2)
    plt.fill_between(range(min_len), mean_curve - std_curve, mean_curve + std_curve,
                      color='blue', alpha=0.15, label='±1 std')
    plt.axhline(y=10000, color='gray', linestyle='--', alpha=0.5, label='Starting Balance')
    plt.title(f"AI Agent Performance - Test Tickers (v4, n={len(episode_curves)} episodes)")
    plt.xlabel("Steps")
    plt.ylabel("Portfolio Value ($)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(LOG_DIR, "plots", "eval_v4.png"))
    print(f"\nPlot saved.")

    if trade_log:
        df_trades = pd.DataFrame(trade_log)
        df_trades.to_csv(os.path.join(LOG_DIR, "test_trades.csv"), index=False)
        win_rate = df_trades['Result'].eq('WIN').mean()
        print(f"Total Trades: {len(df_trades)} across {len(episode_curves)} episodes")
        print(f"Win Rate: {win_rate:.2%}")

# ------------------------------------------------------------------
# Benchmark
# ------------------------------------------------------------------

def benchmark(n_episodes=20):
    print(f"--- RUNNING RANDOM BENCHMARK ({n_episodes} episodes) ---")

    try:
        with open(os.path.join(LOG_DIR, "test_tickers.pkl"), "rb") as f:
            test_tickers = pickle.load(f)
    except FileNotFoundError:
        print("❌ Run training first")
        return

    env = DummyVecEnv([make_env_fn(test_tickers)])
    env = make_vec_normalize(env, training=False)

    obs = env.reset()
    episode_finals = []
    current_curve = []
    episode_idx = 0

    max_steps = n_episodes * (ENV_KWARGS.get("episode_length", 252) + 10)
    step = 0
    while episode_idx < n_episodes and step < max_steps:
        action = [env.action_space.sample()]
        obs, _, dones, infos = env.step(action)
        current_curve.append(infos[0]['portfolio_value'])
        step += 1
        if dones[0]:
            episode_finals.append(current_curve[-1])
            current_curve = []
            episode_idx += 1

    if not episode_finals and current_curve:
        episode_finals.append(current_curve[-1])

    finals = np.array(episode_finals)
    with open(os.path.join(LOG_DIR, "benchmark_data.pkl"), "wb") as f:
        pickle.dump(finals, f)

    print(f"\nEpisodes completed: {len(finals)}")
    print(f"Mean final: ${finals.mean():,.2f} ({(finals.mean()/10000-1)*100:+.1f}%)")
    print(f"Std dev:    ${finals.std():,.2f}")
    print(f"Min / Max:  ${finals.min():,.2f} / ${finals.max():,.2f}")

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
    parser.add_argument(
        "--episodes", type=int, default=20,
        help="Number of episodes to average over for evaluate/benchmark (default: 20)"
    )
    args = parser.parse_args()

    if args.mode == "train":
        train(test_mode=False)
    elif args.mode == "test_train":
        train(test_mode=True)
    elif args.mode == "evaluate":
        evaluate(n_episodes=args.episodes)
    elif args.mode == "benchmark":
        benchmark(n_episodes=args.episodes)