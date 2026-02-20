import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
import os
from typing import Optional, List, Dict

class AdvancedTradingEnv(gym.Env):
    """
    v3: DYNAMIC RISK MANAGEMENT
    
    Key changes from v2:
    1. Trailing stop loss (ride winners, cut losers)
    2. NO fixed take profit (AI learns when to exit)
    3. Exponential rewards for big wins
    4. Momentum-based exits
    """
    metadata = {"render_modes": ["human"]}

    N_CANDIDATES = 5
    LOOKBACK = 20
    N_FEATURES = 7
    N_PORTFOLIO_FEATURES = 7
    OBS_DIM = (N_CANDIDATES * LOOKBACK * N_FEATURES) + N_PORTFOLIO_FEATURES

    def __init__(
        self,
        tickers: list = None,
        data_dir: str = "model/data/train",
        lookback_window: int = 20,
        transaction_cost: float = 0.001,
        slippage: float = 0.001,
        initial_balance: float = 10000,
        max_position_pct: float = 0.50,
        initial_stop_pct: float = 0.08,        # NEW: Start at -8%
        trailing_stop_trigger: float = 0.20,    # NEW: Trail after +20%
        trailing_stop_distance: float = 0.15,   # NEW: Trail 15% below peak
        episode_length: int = 252,
        reward_scaling: float = 1.0,
        render_mode: Optional[str] = None,
    ):
        super().__init__()
        self.data_dir = data_dir
        self.lookback = lookback_window
        self.transaction_cost = transaction_cost
        self.slippage = slippage
        self.initial_balance = initial_balance
        self.max_position_pct = max_position_pct
        self.initial_stop_pct = initial_stop_pct
        self.trailing_stop_trigger = trailing_stop_trigger
        self.trailing_stop_distance = trailing_stop_distance
        self.episode_length = episode_length
        self.reward_scaling = reward_scaling
        self.render_mode = render_mode

        if tickers is not None:
            self.tickers = tickers
        else:
            ticker_files = [f for f in os.listdir(data_dir) if f.endswith('.parquet')]
            self.tickers = [f.replace('.parquet', '') for f in ticker_files]
        
        assert len(self.tickers) >= self.N_CANDIDATES

        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(self.OBS_DIM,), dtype=np.float32)
        self.action_space = spaces.Discrete(self.N_CANDIDATES + 2)

        # State
        self.candidate_tickers: List[str] = []
        self.candidate_dfs: List[pd.DataFrame] = []
        self.current_step = 0
        self.episode_start_step = 0
        self.balance = initial_balance
        self.shares = 0
        self.held_ticker: Optional[str] = None
        self.held_ticker_idx: int = -1
        self.entry_price = 0.0
        self.entry_step = 0
        self.stop_price = 0.0
        self.highest_price = 0.0  # NEW: Track peak for trailing stop
        self.prev_portfolio_value = initial_balance
        self.portfolio_history: List[float] = []
        self.invalid_action_count = 0
        self.total_steps_this_episode = 0

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)

        if self.total_steps_this_episode > 0 and self.invalid_action_count > 0:
            pct = self.invalid_action_count / self.total_steps_this_episode * 100
            print(f"📊 Episode end | Invalid: {self.invalid_action_count} ({pct:.1f}%)")

        chosen_indices = self.np_random.choice(len(self.tickers), size=self.N_CANDIDATES, replace=False)
        self.candidate_tickers = [self.tickers[i] for i in chosen_indices]
        
        self.candidate_dfs = []
        for ticker in self.candidate_tickers:
            path = os.path.join(self.data_dir, f"{ticker}.parquet")
            df = pd.read_parquet(path)
            self.candidate_dfs.append(df)

        min_len = min(len(df) for df in self.candidate_dfs)
        required = self.lookback + self.episode_length + 50
        
        if min_len < required:
            self.episode_start_step = self.lookback
        else:
            max_start = min_len - self.episode_length - 10
            self.episode_start_step = int(self.np_random.integers(self.lookback, max_start))
        
        self.current_step = self.episode_start_step
        self.balance = self.initial_balance
        self.shares = 0
        self.held_ticker = None
        self.held_ticker_idx = -1
        self.entry_price = 0.0
        self.entry_step = 0
        self.stop_price = 0.0
        self.highest_price = 0.0
        self.prev_portfolio_value = self.initial_balance
        self.portfolio_history = [self.initial_balance]
        self.invalid_action_count = 0
        self.total_steps_this_episode = 0

        return self._get_obs(), self._get_info()

    def _get_obs(self) -> np.ndarray:
        features = []

        for stock_idx, df in enumerate(self.candidate_dfs):
            start = self.current_step - self.lookback
            end = self.current_step
            start = max(0, start)
            window = df.iloc[start:end]
            
            if len(window) < self.lookback:
                pad = self.lookback - len(window)
                padding = pd.DataFrame(np.zeros((pad, len(window.columns))), columns=window.columns)
                window = pd.concat([padding, window])

            ref_price = window.iloc[0]['Close'] or 1.0

            for _, row in window.iterrows():
                close  = row['Close']
                sma50  = row.get('SMA_50',  close) or 1.0
                sma200 = row.get('SMA_200', close) or 1.0
                atr    = row.get('ATR', close * 0.02)
                
                features.extend([
                    float(np.clip((close / ref_price) - 1.0,                     -1.0,  1.0)),
                    float(np.clip(float(row.get('RSI', 50.0)) / 100.0,            0.0,  1.0)),
                    float(np.clip(float(row.get('MACD', 0.0)) / max(close, 1e-9),-0.1,  0.1)),
                    float(np.clip((close / sma50)  - 1.0,                        -0.5,  0.5)),
                    float(np.clip((close / sma200) - 1.0,                        -0.5,  0.5)),
                    float(np.clip(atr / max(close, 1e-9),                         0.0,  0.1)),
                    float(np.clip(float(row.get('Volume_ratio', 1.0)) / 5.0,     0.0,  1.0)),
                ])

        current_price = 0.0
        if self.held_ticker_idx >= 0:
            safe_idx = min(self.current_step, len(self.candidate_dfs[self.held_ticker_idx]) - 1)
            current_price = self.candidate_dfs[self.held_ticker_idx].iloc[safe_idx]['Close']
        
        portfolio_value = self.balance + (self.shares * current_price)
        
        balance_norm = self.balance / self.initial_balance
        in_position = 1.0 if self.shares > 0 else 0.0
        held_idx_norm = self.held_ticker_idx / self.N_CANDIDATES if self.held_ticker_idx >= 0 else -0.2
        unrealized_pnl = ((current_price - self.entry_price) / self.entry_price) if self.entry_price > 0 and current_price > 0 else 0.0
        days_held = (self.current_step - self.entry_step) / self.episode_length if self.entry_step > 0 else 0.0
        episode_progress = (self.current_step - self.episode_start_step) / self.episode_length
        cash_ratio = self.balance / portfolio_value if portfolio_value > 0 else 1.0

        features.extend([
            float(np.clip(balance_norm,    0.0,  2.0)),
            float(in_position),
            float(held_idx_norm),
            float(np.clip(unrealized_pnl, -0.5,  0.5)),
            float(np.clip(days_held,       0.0,  1.0)),
            float(np.clip(episode_progress,0.0,  1.0)),
            float(np.clip(cash_ratio,      0.0,  1.0)),
        ])

        obs = np.array(features, dtype=np.float32)
        assert obs.shape == (self.OBS_DIM,)
        assert not np.any(np.isnan(obs))
        return obs

    def step(self, action: int):
        self.total_steps_this_episode += 1
        terminated = False
        truncated = False
        trade_closed = False
        is_win = False
        holding_period = 0
        invalid_action_penalty = 0.0

        prices = self._get_current_prices()

        # Validation
        original_action = action
        if 1 <= action <= self.N_CANDIDATES and self.shares > 0:
            action = 0
            invalid_action_penalty = -2.0
            self.invalid_action_count += 1
        elif action == self.N_CANDIDATES + 1 and self.shares == 0:
            action = 0
            invalid_action_penalty = -2.0
            self.invalid_action_count += 1

        # TRAILING STOP LOGIC (NEW)
        if self.shares > 0 and self.held_ticker_idx >= 0:
            current_price = prices[self.held_ticker_idx]
            
            # Update highest price seen
            if current_price > self.highest_price:
                self.highest_price = current_price
            
            unrealized_gain = (current_price - self.entry_price) / self.entry_price
            
            # Activate trailing stop after threshold gain
            if unrealized_gain > self.trailing_stop_trigger:
                # Lock in (1 - trailing_stop_distance) of gains
                locked_in_price = self.entry_price + (self.highest_price - self.entry_price) * (1 - self.trailing_stop_distance)
                self.stop_price = max(self.stop_price, locked_in_price)
            
            # Check stop
            if current_price <= self.stop_price:
                is_win = current_price > self.entry_price
                holding_period = self.current_step - self.entry_step
                self._execute_sell(current_price)
                trade_closed = True

        # Execute agent action
        if not trade_closed:
            if 1 <= action <= self.N_CANDIDATES and self.shares == 0:
                stock_idx = action - 1
                price = prices[stock_idx]
                
                if price > 0:
                    invest_amount = self.balance * self.max_position_pct
                    shares_to_buy = int(invest_amount / price)
                    
                    if shares_to_buy > 0:
                        total_cost = shares_to_buy * price * (1 + self.transaction_cost + self.slippage)
                        
                        if total_cost <= self.balance:
                            self.balance -= total_cost
                            self.shares = shares_to_buy
                            self.held_ticker = self.candidate_tickers[stock_idx]
                            self.held_ticker_idx = stock_idx
                            self.entry_price = price
                            self.entry_step = self.current_step
                            self.highest_price = price
                            self.stop_price = price * (1 - self.initial_stop_pct)

            elif action == self.N_CANDIDATES + 1 and self.shares > 0:
                current_price = prices[self.held_ticker_idx]
                is_win = current_price > self.entry_price
                holding_period = self.current_step - self.entry_step
                self._execute_sell(current_price)
                trade_closed = True

        # Time step
        self.current_step += 1
        steps_taken = self.current_step - self.episode_start_step
        
        if steps_taken >= self.episode_length:
            terminated = True
            if self.shares > 0 and self.held_ticker_idx >= 0:
                final_prices = self._get_current_prices()
                final_price = final_prices[self.held_ticker_idx]
                is_win = final_price > self.entry_price
                holding_period = self.current_step - self.entry_step
                self._execute_sell(final_price)
                trade_closed = True
        else:
            for df in self.candidate_dfs:
                if self.current_step >= len(df) - 1:
                    terminated = True
                    break

        # Portfolio value
        current_prices = self._get_current_prices()
        held_price = current_prices[self.held_ticker_idx] if self.held_ticker_idx >= 0 else 0.0
        portfolio_value = self.balance + (self.shares * held_price)
        self.portfolio_history.append(portfolio_value)

        # EXPONENTIAL REWARD (NEW)
        reward = 0.0
        portfolio_change = portfolio_value - self.prev_portfolio_value
        reward += portfolio_change * self.reward_scaling
        reward += invalid_action_penalty

        if self.shares > 0:
            reward += 0.02
        if action == 0 and self.shares == 0 and original_action == 0:
            reward -= 0.01

        if trade_closed:
            if self.entry_price > 0:
                profit_pct = (portfolio_value - self.prev_portfolio_value) / max(self.prev_portfolio_value, 1) * 100

                if is_win:
                    # EXPONENTIAL SCALING FOR BIG WINS
                    if profit_pct > 50:
                        reward += (profit_pct ** 1.5) * 5.0   # 100% = 50,000 reward!
                    elif profit_pct > 20:
                        reward += (profit_pct ** 1.3) * 10.0  # 50% = 6,800 reward
                    else:
                        reward += profit_pct * 50.0           # 10% = 500 reward
                    
                    # Massive bonus for riding winners
                    if holding_period > 20 and profit_pct > 30:
                        reward += 1000.0
                    
                else:
                    # Losses penalized less to encourage risk
                    reward += profit_pct * 10.0
                    reward -= 50.0

        # Sharpe bonus at episode end
        if terminated and len(self.portfolio_history) > 10:
            returns = np.diff(self.portfolio_history) / np.maximum(self.portfolio_history[:-1], 1)
            if len(returns) > 0:
                mean_ret = np.mean(returns)
                std_ret = np.std(returns) + 1e-9
                sharpe = mean_ret / std_ret
                reward += sharpe * 10.0

        self.prev_portfolio_value = portfolio_value

        info = self._get_info(
            trade_closed=trade_closed,
            is_win=is_win,
            holding_period=holding_period,
            invalid_action=(original_action != action),
            portfolio_value=portfolio_value
        )

        return self._get_obs(), float(reward), terminated, truncated, info

    def _get_current_prices(self) -> List[float]:
        prices = []
        for df in self.candidate_dfs:
            safe_idx = min(self.current_step, len(df) - 1)
            prices.append(float(df.iloc[safe_idx]['Close']))
        return prices

    def _execute_sell(self, price: float):
        proceeds = self.shares * price * (1 - self.transaction_cost - self.slippage)
        self.balance += proceeds
        self.shares = 0
        self.held_ticker = None
        self.held_ticker_idx = -1
        self.entry_price = 0.0
        self.stop_price = 0.0
        self.highest_price = 0.0

    def _get_info(self, trade_closed=False, is_win=False, holding_period=0,
                  invalid_action=False, portfolio_value=None) -> Dict:
        if portfolio_value is None:
            prices = self._get_current_prices()
            held_price = prices[self.held_ticker_idx] if self.held_ticker_idx >= 0 else 0.0
            portfolio_value = self.balance + (self.shares * held_price)

        ref_idx = self.held_ticker_idx if self.held_ticker_idx >= 0 else 0
        df = self.candidate_dfs[ref_idx]
        safe_idx = min(self.current_step, len(df) - 1)
        row = df.iloc[safe_idx]
        price = row['Close']
        sma200 = row.get('SMA_200', price)
        price_vs_sma = price / sma200 if sma200 > 0 else 1.0

        return {
            "ticker": self.held_ticker or self.candidate_tickers[0],
            "candidates": self.candidate_tickers,
            "step": self.current_step,
            "balance": self.balance,
            "portfolio_value": portfolio_value,
            "shares": self.shares,
            "held_ticker": self.held_ticker,
            "trade_closed": trade_closed,
            "is_win": is_win,
            "holding_period": holding_period,
            "price_vs_sma": price_vs_sma,
            "day_trades_used": 0,
            "invalid_action": invalid_action,
        }