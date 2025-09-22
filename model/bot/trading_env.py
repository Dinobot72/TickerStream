import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

class TradingEnv(gym.Env):
    def __init__(self, df: pd.DataFrame, initial_balance=100_000, transaction_cost_pct=0.001):
        super().__init__()
        self.df = df.reset_index(drop=True)
        self.initial_balance = initial_balance
        self.transaction_cost_pct = transaction_cost_pct

        self.max_steps = len(df) - 1
        self.current_step = 0

        # Agent state
        self.balance = self.initial_balance
        self.shares_held = 0
        self.net_worth = self.initial_balance

        # Action space: [-1, 1] continuous
        # -1 = sell max, 0 = hold, 1 = buy max
        self.action_space = spaces.Box(low=-1, high=1, shape=(1,), dtype=np.float32)

        # Observation space: balance, shares_held, price data (OHLC)
        self.observation_space = spaces.Box(
            low=0, high=np.inf, shape=(6,), dtype=np.float32
        )

    def reset(self, seed=None, options=None):
        self.current_step = 0
        self.balance = self.initial_balance
        self.shares_held = 0
        self.net_worth = self.initial_balance
        return self._get_observation(), {}

    def _get_observation(self):
        row = self.df.iloc[self.current_step]
        observation = np.array([
            self.balance,
            self.shares_held,
            row['Open'],
            row['High'],
            row['Low'],
            row['Close']
        ], dtype=np.float32)
        return observation

    def step(self, action):
        action = np.clip(action[0], -1, 1)
        done = False
        info = {}

        current_price = self.df.iloc[self.current_step]['Close']
        prev_net_worth = self.net_worth

        # SELL
        if action < 0:
            sell_fraction = -action
            shares_to_sell = int(self.shares_held * sell_fraction)
            if shares_to_sell > 0:
                proceeds = shares_to_sell * current_price
                cost = proceeds * self.transaction_cost_pct
                self.balance += proceeds - cost
                self.shares_held -= shares_to_sell

        # BUY
        elif action > 0:
            buy_fraction = action
            available_to_spend = self.balance * buy_fraction
            if available_to_spend > current_price:
                shares_to_buy = int(available_to_spend / current_price)
                cost = shares_to_buy * current_price
                fee = cost * self.transaction_cost_pct
                total_cost = cost + fee
                if total_cost <= self.balance:
                    self.balance -= total_cost
                    self.shares_held += shares_to_buy

        # Update step and net worth
        self.current_step += 1
        self.net_worth = self.balance + self.shares_held * current_price

        # Reward = change in net worth (can be negative)
        reward = self.net_worth - prev_net_worth

        # End of episode
        if self.current_step >= self.max_steps:
            done = True
            final_reward = (self.net_worth - self.initial_balance) / self.initial_balance
            reward += final_reward  # optional end-of-episode bonus

            info['final'] = {
                'step': self.current_step,
                'net_worth': self.net_worth,
                'profit_pct': final_reward * 100,
                'balance': self.balance,
                'shares_held': self.shares_held
            }

        return self._get_observation(), reward, done, False, info
