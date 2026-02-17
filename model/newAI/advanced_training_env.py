import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
import os
from typing import Optional, Dict, Any

class AdvancedTradingEnv(gym.Env):
    """
    FIXED Trading Environment with:
    - Balanced reward function (wins > losses)
    - Invalid action prevention
    - Proper capital utilization incentives
    """
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        tickers: list = None,
        data_dir: str = "model/data/train",
        macro_dir: str = "macro",
        lookback_window: int = 20,
        transaction_cost: float = 0.001,
        slippage: float = 0.001,
        initial_balance: float = 10000,
        max_position_pct: float = 0.5,  # INCREASED from 0.25
        target_atr_mult: float = 1.2,   # DECREASED from 2.0
        stop_atr_mult: float = 0.8,     # DECREASED from 1.5
        pdt_min_balance: float = 25000,
        max_day_trades: int = 3,
        reward_scaling: float = 10.0,   # INCREASED from 1.0
        render_mode: Optional[str] = None,
    ):
        super().__init__()
        self.data_dir = data_dir
        self.macro_dir = os.path.join(data_dir, macro_dir)
        self.lookback = lookback_window
        self.transaction_cost = transaction_cost
        self.slippage = slippage
        self.initial_balance = initial_balance
        self.max_position_pct = max_position_pct
        self.target_atr_mult = target_atr_mult
        self.stop_atr_mult = stop_atr_mult
        self.pdt_min_balance = pdt_min_balance
        self.max_day_trades = max_day_trades
        self.reward_scaling = reward_scaling
        self.render_mode = render_mode

        if tickers is not None:
            self.tickers = tickers
        else:
            ticker_files = [f for f in os.listdir(data_dir) if f.endswith('.parquet') and f != 'macro']
            self.tickers = [f.replace('.parquet', '') for f in ticker_files]

        # Observation space
        self.n_stock_features = 7 
        self.obs_dim = 3 + (lookback_window * self.n_stock_features) + 2
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(self.obs_dim,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)

        # State variables
        self.current_step = 0
        self.df = None
        self.ticker = None
        self.balance = initial_balance
        self.shares = 0
        self.entry_price = 0
        self.entry_step = 0
        self.target_price = 0
        self.stop_price = 0
        self.day_trades_used = 0
        self.last_trade_day = None
        self.portfolio_values = []
        self.prev_portfolio_value = initial_balance
        
        # Tracking for debugging
        self.invalid_action_count = 0
        self.total_steps = 0

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        self.ticker = np.random.choice(self.tickers)
        self.df = pd.read_parquet(os.path.join(self.data_dir, f"{self.ticker}.parquet"))
        
        self.balance = self.initial_balance
        self.shares = 0
        self.entry_price = 0
        self.entry_step = 0
        self.target_price = 0
        self.stop_price = 0
        self.day_trades_used = 0
        self.portfolio_values = [self.initial_balance]
        self.prev_portfolio_value = self.initial_balance
        
        # Reset tracking
        if self.invalid_action_count > 0:
            print(f"📊 Episode ended - Invalid actions: {self.invalid_action_count}/{self.total_steps} ({self.invalid_action_count/max(1,self.total_steps)*100:.1f}%)")
        self.invalid_action_count = 0
        self.total_steps = 0
        
        # Start at random point
        max_start = len(self.df) - self.lookback - 200
        if max_start < self.lookback:
            self.current_step = self.lookback
        else:
            self.current_step = self.np_random.integers(self.lookback, max_start)
            
        return self._get_obs(), self._get_info()

    def _get_obs(self):
        # PLACEHOLDER - You need to implement your actual observation logic here
        # This should return recent price data, indicators, position state, etc.
        return np.zeros(self.obs_dim, dtype=np.float32) 

    def step(self, action: int):
        self.total_steps += 1
        terminated = False
        truncated = False
        current_price = self.df.iloc[self.current_step]['Close']
        
        # Track trade outcomes
        trade_closed = False
        is_win = False
        holding_period = 0
        invalid_action_penalty = 0.0

        # --- VALIDATION: Prevent Invalid Actions ---
        original_action = action
        if action == 1 and self.shares > 0:
            # Can't buy when already holding
            action = 0  # Force to HOLD
            invalid_action_penalty = -5.0
            self.invalid_action_count += 1
            if self.invalid_action_count % 100 == 1:  # Log occasionally
                print(f"⚠️  Step {self.current_step}: Blocked invalid BUY (already holding {self.shares} shares)")
        
        elif action == 2 and self.shares == 0:
            # Can't sell when no position
            action = 0  # Force to HOLD
            invalid_action_penalty = -5.0
            self.invalid_action_count += 1
            if self.invalid_action_count % 100 == 1:  # Log occasionally
                print(f"⚠️  Step {self.current_step}: Blocked invalid SELL (no position)")

        # --- 1. Check Auto-Exits (Target/Stop) ---
        if self.shares > 0:
            if current_price >= self.target_price:  # Take Profit
                self._execute_sell(current_price)
                trade_closed = True
                is_win = True
            elif current_price <= self.stop_price:  # Stop Loss
                self._execute_sell(current_price)
                trade_closed = True
                is_win = False
        
        # --- 2. Agent Action (after validation) ---
        if not trade_closed: 
            if action == 1 and self.shares == 0:  # BUY (validated)
                cost = self.balance * self.max_position_pct
                shares = int(cost / current_price)
                if shares > 0:
                    total_cost = shares * current_price * (1 + self.transaction_cost + self.slippage)
                    if total_cost <= self.balance:  # Safety check
                        self.balance -= total_cost
                        self.shares = shares
                        self.entry_price = current_price
                        self.entry_step = self.current_step
                        # Set targets
                        atr = self.df.iloc[self.current_step]['ATR']
                        self.target_price = current_price + (self.target_atr_mult * atr)
                        self.stop_price = current_price - (self.stop_atr_mult * atr)

            elif action == 2 and self.shares > 0:  # SELL (validated)
                is_win = current_price > self.entry_price
                self._execute_sell(current_price)
                trade_closed = True

        # --- 3. Step & Termination ---
        self.current_step += 1
        if self.current_step >= len(self.df) - 1:
            terminated = True
            # Force close at end
            if self.shares > 0:
                current_price = self.df.iloc[self.current_step]['Close']
                is_win = current_price > self.entry_price
                self._execute_sell(current_price)
                trade_closed = True

        # --- 4. Calculate Portfolio Value ---
        if self.current_step < len(self.df):
            current_price = self.df.iloc[self.current_step]['Close']
        portfolio_value = self.balance + (self.shares * current_price)
        
        # --- 5. REWARD CALCULATION (FIXED & BALANCED!) ---
        reward = 0.0
        
        # A) Portfolio Change (primary signal - scaled up)
        portfolio_change = portfolio_value - self.prev_portfolio_value
        reward += portfolio_change * self.reward_scaling
        
        # B) Invalid Action Penalty (enforced above)
        reward += invalid_action_penalty
        
        # C) Incentive for Capital Deployment
        if self.shares > 0:
            reward += 0.05  # Small reward per step for being invested
        
        # D) Penalty for Hoarding Cash
        if action == 0 and self.shares == 0 and original_action == 0:  # Intentional hold with no position
            reward -= 0.02
        
        # E) Trade Outcome Rewards (WINS >> LOSSES)
        if trade_closed:
            profit = portfolio_value - self.prev_portfolio_value
            profit_pct = (profit / self.prev_portfolio_value) * 100
            
            if is_win:
                # BIG bonus for wins
                reward += profit_pct * 50.0  # 50x multiplier
                reward += 2.0  # Flat win bonus
                
                # Extra bonus for quick profitable trades
                if holding_period < 15:
                    reward += 1.0
            else:
                # SMALLER penalty for losses (encourage exploration)
                reward += profit_pct * 20.0  # Only 20x multiplier (2.5x less than wins)
                reward -= 0.5  # Small flat loss penalty
                
                # Extra penalty for holding losers too long
                if holding_period > 30:
                    reward -= 0.5
        
        # F) Penalty for Overtrading
        if trade_closed and holding_period < 3:
            reward -= 1.0  # Discourage churn
        
        # Update previous value for next step
        self.prev_portfolio_value = portfolio_value

        # --- 6. Info ---
        if trade_closed:
            holding_period = self.current_step - self.entry_step

        info = self._get_info(
            trade_closed=trade_closed, 
            is_win=is_win, 
            holding_period=holding_period,
            invalid_action=(original_action != action)
        )
        
        return self._get_obs(), reward, terminated, truncated, info

    def _execute_sell(self, price):
        proceeds = self.shares * price * (1 - self.transaction_cost - self.slippage)
        self.balance += proceeds
        self.shares = 0
        self.entry_price = 0
        self.target_price = 0
        self.stop_price = 0

    def _get_info(self, trade_closed=False, is_win=False, holding_period=0, invalid_action=False):
        safe_idx = min(self.current_step, len(self.df)-1)
        price = self.df.iloc[safe_idx]['Close']
        
        # Calculate context (Price vs SMA200)
        sma200 = self.df.iloc[safe_idx].get('SMA_200', price)
        price_to_sma = price / sma200 if sma200 > 0 else 1.0

        return {
            "ticker": self.ticker,
            "step": self.current_step,
            "balance": self.balance,
            "portfolio_value": self.balance + (self.shares * price),
            "trade_closed": trade_closed,
            "is_win": is_win,
            "holding_period": holding_period,
            "price_vs_sma": price_to_sma,
            "day_trades_used": self.day_trades_used,
            "shares": self.shares,
            "invalid_action": invalid_action
        }