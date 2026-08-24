import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
import os
from typing import Optional

from observation_builder import build_observation

class AdvancedTradingEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        tickers: list,
        data_dir: str = "model/data/train",
        lookback_window: int = 20,
        transaction_cost: float = 0.001,
        slippage: float = 0.001,
        initial_balance: float = 10000,
        max_position_pct: float = 1.0, 
        episode_length: int = 252,
        reward_scaling: float = 100.0,
        **kwargs # Absorb leftover kwargs from config cleanly
    ):
        super().__init__()
        self.tickers = tickers
        self.data_dir = data_dir
        self.lookback = lookback_window
        self.transaction_cost = transaction_cost
        self.slippage = slippage
        self.initial_balance = initial_balance
        self.max_position_pct = max_position_pct
        self.episode_length = episode_length
        
        # Core reward constants based on architecture
        self.REWARD_SCALE = reward_scaling
        self.SCALE_CONST = 10.0
        self.small_invalid_action_penalty = 0.05
        
        # Action Space: 0=HOLD, 1=BUY, 2=SELL
        self.action_space = spaces.Discrete(3)
        
        # Observation Space (Lookback * 7 features per row + 4 state features)
        self.OBS_DIM = (self.lookback * 7) + 4
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(self.OBS_DIM,), dtype=np.float32)
        
        # Data cache so resets are lightning fast (avoids reloading disk)
        self.data_cache = {}
        self.current_ticker = None
        self.df = None
        
        self.current_step = 0
        self.start_step = 0
        self.balance = self.initial_balance
        self.shares = 0
        self.entry_price = 0.0
        self.entry_step = 0
        self.prev_portfolio_value = self.initial_balance

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        
        # Pick a random ticker from the universe
        self.current_ticker = self.np_random.choice(self.tickers)
        
        # Load and cache dataframe
        if self.current_ticker not in self.data_cache:
            path = os.path.join(self.data_dir, f"{self.current_ticker}.parquet")
            self.data_cache[self.current_ticker] = pd.read_parquet(path)
            
        self.df = self.data_cache[self.current_ticker]
        
        # Find a valid starting step
        min_required = self.lookback + self.episode_length + 5
        if len(self.df) < min_required:
            self.start_step = self.lookback
        else:
            max_start = len(self.df) - self.episode_length - 2
            self.start_step = int(self.np_random.integers(self.lookback, max_start))
            
        self.current_step = self.start_step
        self.balance = self.initial_balance
        self.shares = 0
        self.entry_price = 0.0
        self.entry_step = 0
        self.prev_portfolio_value = self.initial_balance
        
        return self._get_obs(), self._get_info()

    def _get_obs(self):
        # Window ends exactly at current_step (inclusive)
        start = self.current_step - self.lookback + 1
        window_df = self.df.iloc[start : self.current_step + 1]
        
        # Safety pad if at very edge of data
        if len(window_df) < self.lookback:
            pad_size = self.lookback - len(window_df)
            padding = pd.DataFrame(np.zeros((pad_size, len(window_df.columns))), columns=window_df.columns)
            window_df = pd.concat([padding, window_df])
            
        in_pos = self.shares > 0
        current_price = self.df.iloc[self.current_step]['Close']
        unrealized_pnl = ((current_price / self.entry_price) - 1.0) if in_pos and self.entry_price > 0 else 0.0
        days_held = (self.current_step - self.entry_step) if in_pos else 0
        
        position_state = {
            'balance': self.balance,
            'initial_balance': self.initial_balance,
            'in_position': in_pos,
            'unrealized_pnl': unrealized_pnl,
            'days_held': days_held,
            'max_days': self.episode_length
        }
        
        return build_observation(window_df, position_state)

    def step(self, action: int):
        row = self.df.iloc[self.current_step]
        price = float(row['Close'])
        
        reward = 0.0
        trade_closed = False
        profit_pct = 0.0
        is_win = False
        holding_period = 0
        
        # --- Apply Action ---
        if action == 1: # BUY
            if self.shares == 0 and price > 0:
                invest_amount = self.balance * self.max_position_pct
                shares_to_buy = invest_amount / price
                cost = shares_to_buy * price * (1 + self.transaction_cost + self.slippage)
                
                if shares_to_buy > 0 and cost <= self.balance:
                    self.balance -= cost
                    self.shares = shares_to_buy
                    self.entry_price = price
                    self.entry_step = self.current_step
                else:
                    reward -= self.small_invalid_action_penalty
            else:
                reward -= self.small_invalid_action_penalty
                
        elif action == 2: # SELL
            if self.shares > 0:
                proceeds = self.shares * price * (1 - self.transaction_cost - self.slippage)
                self.balance += proceeds
                profit_pct = (price - self.entry_price) / self.entry_price
                
                trade_closed = True
                is_win = profit_pct > 0
                holding_period = self.current_step - self.entry_step
                
                self.shares = 0
                self.entry_price = 0.0
                self.entry_step = 0
            else:
                reward -= self.small_invalid_action_penalty
                
        elif action == 0: # HOLD
            pass 
            
        # --- Advance Time ---
        self.current_step += 1
        terminated = False
        steps_taken = self.current_step - self.start_step
        out_of_data = self.current_step >= len(self.df) - 1
        
        # Calculate new portfolio value based on tomorrow's price
        next_price = self.df.iloc[self.current_step]['Close']
        new_portfolio_value = self.balance + (self.shares * next_price)
        
        # Base Reward (Return %)
        step_return_pct = (new_portfolio_value - self.prev_portfolio_value) / max(self.prev_portfolio_value, 1.0)
        reward += step_return_pct * self.REWARD_SCALE
        
        # --- Convex Reward For Closing Trades ---
        if trade_closed:
            reward += np.sign(profit_pct) * (abs(profit_pct) ** 1.1) * self.SCALE_CONST
            
        # --- Termination ---
        if steps_taken >= self.episode_length or out_of_data:
            terminated = True
            
            if self.shares > 0:
                # Force close at end of episode, applying the EXACT SAME logic as a standard SELL
                proceeds = self.shares * next_price * (1 - self.transaction_cost - self.slippage)
                self.balance += proceeds
                profit_pct = (next_price - self.entry_price) / self.entry_price
                trade_closed = True
                is_win = profit_pct > 0
                holding_period = self.current_step - self.entry_step
                self.shares = 0
                
                reward += np.sign(profit_pct) * (abs(profit_pct) ** 1.1) * self.SCALE_CONST
                new_portfolio_value = self.balance
                
        self.prev_portfolio_value = new_portfolio_value
        info = self._get_info(trade_closed, is_win, holding_period, profit_pct, new_portfolio_value)
        
        return self._get_obs(), float(reward), terminated, False, info

    def _get_info(self, trade_closed=False, is_win=False, holding_period=0, profit_pct=0.0, p_val=None):
        row = self.df.iloc[self.current_step]
        price = float(row['Close'])
        sma200 = float(row.get('SMA_200', price))
        
        return {
            "ticker": self.current_ticker,
            "step": self.current_step,
            "balance": self.balance,
            "portfolio_value": p_val if p_val else self.prev_portfolio_value,
            "shares": self.shares,
            "trade_closed": trade_closed,
            "is_win": is_win,
            "holding_period": holding_period,
            "profit_pct": profit_pct,
            "price_vs_sma": price / sma200 if sma200 > 0 else 1.0
        }