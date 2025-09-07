import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

class TradingEnv(gym.Env):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df
        self.current_step = 0
        self.initial_balance = 1000
        self.balance = self.initial_balance
        self.shares_held = 0
        self.net_worth = self.initial_balance
        self.max_steps = len(df) - 1

        # Action space: 0 = Buy, 1 = Sell, 2 = Hold
        self.action_space = spaces.Discrete(3)

        # Observation space: This is the data the AI sees at each step.
        # It should include market data and the state of the agent's portfolio.
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
        # A simple observation for demonstration
        row = self.df.iloc[self.current_step]
        observation = [
            self.balance,
            self.shares_held,
            row['Open'],
            row['High'],
            row['Low'],
            row['Close'],
        ]
        return np.array(observation, dtype=np.float32)
    
    def step(self, action):
        self.current_step += 1
        if self.current_step >= self.max_steps:
            terminated = True
            info = {}
            return self._get_observation(), 0, terminated, False, info
        
        current_price = self.df.iloc[self.current_step]['Close']

        if action == 0: # Buy
            buy_price = current_price
            if self.balance > buy_price:
                # Buy all available shares
                self.shares_held += int(self.balance / buy_price)
                self.balance %= buy_price
        elif action == 1: # Sell
            sell_price = current_price
            if self.shares_held > 0:
                self.balance += self.shares_held * sell_price
                self.shares_held = 0

        # Calculate new net worth and reward
        new_net_worth = self.balance + self.shares_held * current_price
        reward = new_net_worth - self.net_worth
        self.net_worth = new_net_worth

        terminated = False
        info = {}
        return self._get_observation(), reward, terminated, False, info 
