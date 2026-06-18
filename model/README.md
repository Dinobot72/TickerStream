# TickerStream AI — Model

Training pipeline for the `RecurrentPPO` reinforcement-learning agent that powers the autonomous trading bot in the backend.

## Stack

- `gymnasium` for the custom trading environment
- `stable-baselines3` + `sb3-contrib` (`RecurrentPPO`, `MlpLstmPolicy`) for training
- PyTorch as the underlying tensor/training framework
- `yfinance` + `pandas`/`numpy` for historical data collection and technical indicators

## Setup

```bash
cd model
pip install -r requirements.txt
```

This installs a minimal set (`gymnasium`, `stable-baselines3[extra]`, `yfinance`, `pandas`, `numpy`); the heavier ML dependencies (`torch`, `sb3-contrib`) currently live in `backend/requirements.txt` since the backend also needs them to run inference.

## Pipeline overview

1. **`newAI/data_collector.py`** — loads (or scrapes from Wikipedia) the S&P 500 ticker universe into `model/universe.csv`, then fetches 10 years of OHLCV history per ticker plus a handful of macro tickers (`SPY`, `QQQ`, `IWM`, `VIX`) via `newAI/data_prep.py`, saving each as a `.parquet` file under `model/data/train/`.
2. **`newAI/data_prep.py`** — computes technical indicators (SMA 20/50/200, EMA 12/26, MACD, RSI, Bollinger Bands, ATR, volume ratio) used both for training data and for live inference.
3. **`newAI/advanced_training_env.py`** — a `gymnasium.Env` (`AdvancedTradingEnv`, v3) that:
   - Observes 5 candidate tickers × 20-day lookback × 7 features, plus 7 portfolio-state features (707-dim total).
   - Has a `Discrete(N_CANDIDATES + 2)` action space: hold, buy one of 5 candidates, or sell the current position.
   - Manages risk internally with an 8% initial stop-loss and a trailing stop that activates after a 20% gain and trails 15% below the peak — the agent is never asked to manually set stops.
   - Rewards are shaped to scale super-linearly with large wins (encouraging the agent to "let winners run") while penalizing invalid actions, excessive idling with no position, and large losses.
4. **`newAI/main.py`** — CLI entry point:
   ```bash
   python main.py --mode train        # full training run (5M timesteps, 8 parallel envs)
   python main.py --mode test_train   # quick smoke-test run (50k timesteps)
   python main.py --mode evaluate     # roll out the best checkpoint on held-out tickers
   python main.py --mode benchmark    # random-action baseline for comparison
   ```
   Training uses an 80/20 train/test ticker split, `VecNormalize` observation normalization, periodic checkpointing, and an `EvalCallback` that tracks the best model by held-out reward.
5. **`newAI/callbacks.py`** — `TensorboardCallback` logs portfolio value, win rate, and holding period to TensorBoard; `MetricLoggerCallback` writes a row every 10 steps to `training_metrics.csv`, consumed by the live monitor below.
6. **`newAI/config.py`** — all environment and training hyperparameters (episode length, stop/trail percentages, learning rate, batch size, LSTM size, etc.) in one place.

## Live training monitor

`newAI/monitor/live_monitor_server.py` is a small Flask app that tails `training_metrics.csv` and serves a single-page dashboard (also available standalone as `newAI/monitor/trading_dashboard_live.html`) showing live portfolio value, drawdown, win rate, and a recent-trades table while a training run is in progress. Run it separately from the `model` directory while `main.py --mode train` is running, then open `http://localhost:5000`.

## Connecting to the backend

The backend loads a saved checkpoint directly:

```python
RecurrentPPO.load("./model/logs/best_model/best_model")
```

(see `backend/app/services/ai_scorer.py` and `portfolio_manager.py`). The model directory referenced there (`model/logs/best_model/`) is produced by `EvalCallback` during training and is **not checked into version control** (see `.gitignore`) — you need to either train your own model or copy a trained checkpoint into that path before the backend's bot features will work end-to-end.

## Known issues / cleanup candidates

- The root project README's "How the Trading Bot Works" section references older filenames (`trading_env.py`, `strategy_engine.py`, `train_model.py`) that don't match the actual code, which lives in `newAI/` (`advanced_training_env.py`, `main.py`) — worth updating that section to match the current pipeline.
- `backend/app/services/data_prep_live.py` (used for live inference) and `model/newAI/advanced_training_env.py` (used for training) independently implement the same feature engineering — any change to one must be mirrored in the other, or live inference will silently diverge from what the model was actually trained on.
- No automated tests cover the environment's reward logic or training/inference observation parity — a regression test that feeds identical price data through both code paths and asserts matching observations would catch drift early.