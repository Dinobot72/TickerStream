"""
trading_env_v4.py

v4: single-ticker Discrete(3) action space (HOLD/BUY/SELL), smooth
reward scaling, imports build_observation() from shared_obs.py so
training and live inference can never drift apart again.

Differences from v3 (advanced_training_env.py), and why:
  - Discrete(3) instead of Discrete(N_CANDIDATES+2): the model no longer
    has to learn "which of 5 tickers" simultaneously with "is now a good
    time to buy" - it scores one ticker at a time, matching how
    PortfolioManager already calls it in production.
  - One smooth reward formula for closed trades instead of tiered
    exponential bonuses (>50%, >20%, +1000 flat bonus, etc). Those
    created a 100-1000x reward-scale gap between ordinary steps and rare
    big wins, which is very likely what collapsed the policy (see
    diagnose_normalization.py results - inputs were fine, outputs were
    flat regardless of input, consistent with a PPO advantage signal
    dominated by reward outliers).
  - No separate normalization scheme fighting VecNormalize: features are
    hand-scaled/clipped here; pair with VecNormalize(norm_obs=False,
    norm_reward=True) - reward normalization is the safety net now,
    not observation normalization.
"""

import os
from typing import Optional, List

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd

from shared_obs import build_observation, get_window, PositionState, OBS_DIM, LOOKBACK

HOLD, BUY, SELL = 0, 1, 2


class TradingEnvV4(gym.Env):
    metadata = {"render_modes": ["human"]}
    OBS_DIM = OBS_DIM
    N_ACTIONS = 3

    def __init__(
        self,
        tickers: Optional[List[str]] = None,
        data_dir: str = "model/data/train",
        transaction_cost: float = 0.001,
        slippage: float = 0.001,
        initial_balance: float = 10_000.0,
        position_size_pct: float = 0.50,
        episode_length: int = 252,
        reward_scale: float = 100.0,       # step_return_pct -> reward
        trade_reward_scale: float = 20.0,  # closed-trade profit_pct -> reward
        invalid_action_penalty: float = -0.5,
        render_mode: Optional[str] = None,
    ):
        super().__init__()
        self.data_dir = data_dir
        self.transaction_cost = transaction_cost
        self.slippage = slippage
        self.initial_balance = initial_balance
        self.position_size_pct = position_size_pct
        self.episode_length = episode_length
        self.reward_scale = reward_scale
        self.trade_reward_scale = trade_reward_scale
        self.invalid_action_penalty = invalid_action_penalty
        self.render_mode = render_mode

        if tickers is not None:
            self.tickers = tickers
        else:
            ticker_files = [f for f in os.listdir(data_dir) if f.endswith(".parquet")]
            self.tickers = [f.replace(".parquet", "") for f in ticker_files]
        assert len(self.tickers) >= 1, "need at least one ticker with data"

        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(OBS_DIM,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)  # HOLD, BUY, SELL

        # episode state
        self.df: Optional[pd.DataFrame] = None
        self.ticker: Optional[str] = None
        self.current_step = 0
        self.episode_start_step = 0
        self.balance = initial_balance
        self.shares = 0
        self.in_position = False
        self.entry_price = 0.0
        self.entry_step = 0
        self.prev_portfolio_value = initial_balance
        self.portfolio_history: List[float] = []
        self.invalid_action_count = 0
        self.total_steps_this_episode = 0

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)

        if self.total_steps_this_episode > 0 and self.invalid_action_count > 0:
            pct = self.invalid_action_count / self.total_steps_this_episode * 100
            print(f"📊 Episode end | Invalid: {self.invalid_action_count} ({pct:.1f}%)")

        self.ticker = self.tickers[self.np_random.integers(0, len(self.tickers))]
        self.df = pd.read_parquet(os.path.join(self.data_dir, f"{self.ticker}.parquet"))

        required = LOOKBACK + self.episode_length + 10
        if len(self.df) < required:
            self.episode_start_step = LOOKBACK
        else:
            max_start = len(self.df) - self.episode_length - 5
            self.episode_start_step = int(self.np_random.integers(LOOKBACK, max_start))

        self.current_step = self.episode_start_step
        self.balance = self.initial_balance
        self.shares = 0
        self.in_position = False
        self.entry_price = 0.0
        self.entry_step = 0
        self.prev_portfolio_value = self.initial_balance
        self.portfolio_history = [self.initial_balance]
        self.invalid_action_count = 0
        self.total_steps_this_episode = 0

        return self._get_obs(), self._get_info()

    def _current_price(self) -> float:
        idx = min(self.current_step, len(self.df) - 1)
        return float(self.df.iloc[idx]["Close"])

    def _position_state(self) -> PositionState:
        return PositionState(
            balance=self.balance,
            initial_balance=self.initial_balance,
            in_position=self.in_position,
            entry_price=self.entry_price,
            current_price=self._current_price(),
            days_held=(self.current_step - self.entry_step) if self.in_position else 0,
            max_days=self.episode_length,
        )

    def _get_obs(self) -> np.ndarray:
        window = get_window(self.df, self.current_step, LOOKBACK)
        return build_observation(window, self._position_state())

    def step(self, action: int):
        self.total_steps_this_episode += 1
        terminated = False
        truncated = False
        trade_closed = False
        is_win = False
        profit_pct = 0.0
        holding_period = 0

        price = self._current_price()
        reward = 0.0

        # --- validate + apply action ---
        if action == BUY and self.in_position:
            reward += self.invalid_action_penalty
            self.invalid_action_count += 1
        elif action == SELL and not self.in_position:
            reward += self.invalid_action_penalty
            self.invalid_action_count += 1

        elif action == BUY and not self.in_position and price > 0:
            invest_amount = self.balance * self.position_size_pct
            shares_to_buy = int(invest_amount / price)
            if shares_to_buy > 0:
                total_cost = shares_to_buy * price * (1 + self.transaction_cost + self.slippage)
                if total_cost <= self.balance:
                    self.balance -= total_cost
                    self.shares = shares_to_buy
                    self.in_position = True
                    self.entry_price = price
                    self.entry_step = self.current_step

        elif action == SELL and self.in_position:
            proceeds = self.shares * price * (1 - self.transaction_cost - self.slippage)
            self.balance += proceeds
            profit_pct = (price - self.entry_price) / self.entry_price * 100
            is_win = price > self.entry_price
            holding_period = self.current_step - self.entry_step
            trade_closed = True
            self.shares = 0
            self.in_position = False
            self.entry_price = 0.0

        # action == HOLD (or an invalid action reduced to a no-op): nothing
        # further happens this step - no penalty beyond the invalid-action
        # case above. We deliberately do NOT penalize plain HOLD; punishing
        # patience is what pushed v3 toward compulsive trading.

        # --- advance time ---
        self.current_step += 1
        steps_taken = self.current_step - self.episode_start_step
        if steps_taken >= self.episode_length or self.current_step >= len(self.df) - 1:
            terminated = True
            if self.in_position:
                final_price = self._current_price()
                proceeds = self.shares * final_price * (1 - self.transaction_cost - self.slippage)
                self.balance += proceeds
                profit_pct = (final_price - self.entry_price) / self.entry_price * 100
                is_win = final_price > self.entry_price
                holding_period = self.current_step - self.entry_step
                trade_closed = True
                self.shares = 0
                self.in_position = False
                self.entry_price = 0.0

        # --- reward: one smooth formula, no tiered jackpots ---
        held_price = self._current_price() if self.in_position else 0.0
        portfolio_value = self.balance + (self.shares * held_price)

        step_return_pct = (portfolio_value - self.prev_portfolio_value) / max(self.prev_portfolio_value, 1.0) * 100
        reward += step_return_pct * (self.reward_scale / 100.0)

        if trade_closed:
            # sign-preserving smooth convexity: bigger wins score more,
            # bigger losses score worse, but nothing jumps by 100-1000x
            # relative to an ordinary step's reward.
            sign = 1.0 if profit_pct >= 0 else -1.0
            reward += sign * (abs(profit_pct) ** 1.1) * (self.trade_reward_scale / 100.0)

        self.prev_portfolio_value = portfolio_value
        self.portfolio_history.append(portfolio_value)

        info = self._get_info(trade_closed=trade_closed, is_win=is_win, profit_pct=profit_pct,
                               holding_period=holding_period, portfolio_value=portfolio_value)

        return self._get_obs(), float(reward), terminated, truncated, info

    def _get_info(self, trade_closed=False, is_win=False, profit_pct=0.0, holding_period=0,
                  portfolio_value=None) -> dict:
        if portfolio_value is None:
            held_price = self._current_price() if self.in_position else 0.0
            portfolio_value = self.balance + (self.shares * held_price)
        return {
            "ticker": self.ticker,
            "step": self.current_step,
            "balance": self.balance,
            "portfolio_value": portfolio_value,
            "shares": self.shares,
            "in_position": self.in_position,
            "trade_closed": trade_closed,
            "is_win": is_win,
            "profit_pct": profit_pct,
            "holding_period": holding_period,
            "invalid_action_count": self.invalid_action_count,
        }