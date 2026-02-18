import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
import os
from typing import Optional, List, Dict

class AdvancedTradingEnv(gym.Env):
    """
    TickerStream Trading Environment v2
    
    KEY IMPROVEMENTS over v1:
    
    1. STOCK SELECTION: The AI now sees 5 candidate stocks simultaneously and
       CHOOSES which one to trade. This teaches it to compare opportunities,
       just like the production screener does.
    
    2. REAL OBSERVATIONS: _get_obs() is fully implemented with all 7 technical
       features per day. v1 returned zeros - the AI was literally blind!
    
    3. MULTI-YEAR EPISODES: Episodes now span 252 days (1 full trading year)
       instead of ~50 steps. The AI learns long-term patterns.
    
    4. SHARPE RATIO REWARD: Rewards profitability relative to risk. A steady
       +10% is rewarded more than a volatile +10%.
    
    5. NORMALIZED OBSERVATIONS: All features are normalized so the LSTM
       doesn't get confused by stocks priced at $5 vs $500.
    
    Observation Space:
        For each of 5 candidate stocks: 20 days × 7 features = 140 features
        Portfolio state: 7 features (balance, position, entry, etc.)
        Total: 5 × 140 + 7 = 707 features
    
    Action Space:
        0  = HOLD (do nothing)
        1  = BUY stock 0
        2  = BUY stock 1
        3  = BUY stock 2
        4  = BUY stock 3
        5  = BUY stock 4
        6  = SELL current position
        Total: 7 discrete actions
    """
    metadata = {"render_modes": ["human"]}

    # Number of candidate stocks visible at once
    N_CANDIDATES = 5
    # Days of history shown per stock
    LOOKBACK = 20
    # Features per day per stock
    N_FEATURES = 7
    # Portfolio state features
    N_PORTFOLIO_FEATURES = 7
    # Total observation size
    OBS_DIM = (N_CANDIDATES * LOOKBACK * N_FEATURES) + N_PORTFOLIO_FEATURES  # 707

    def __init__(
        self,
        tickers: list = None,
        data_dir: str = "model/data/train",
        lookback_window: int = 20,
        transaction_cost: float = 0.001,
        slippage: float = 0.001,
        initial_balance: float = 10000,
        max_position_pct: float = 0.50,
        stop_loss_pct: float = 0.05,       # 5% stop loss
        take_profit_pct: float = 0.10,     # 10% take profit
        episode_length: int = 252,         # 1 trading year
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
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.episode_length = episode_length
        self.reward_scaling = reward_scaling
        self.render_mode = render_mode

        # Load tickers
        if tickers is not None:
            self.tickers = tickers
        else:
            ticker_files = [f for f in os.listdir(data_dir) if f.endswith('.parquet')]
            self.tickers = [f.replace('.parquet', '') for f in ticker_files]
        
        assert len(self.tickers) >= self.N_CANDIDATES, \
            f"Need at least {self.N_CANDIDATES} tickers, got {len(self.tickers)}"

        # Spaces
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, 
            shape=(self.OBS_DIM,), dtype=np.float32
        )
        # 0=Hold, 1-5=Buy candidate 0-4, 6=Sell
        self.action_space = spaces.Discrete(self.N_CANDIDATES + 2)

        # State - initialized properly in reset()
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
        self.target_price = 0.0
        self.prev_portfolio_value = initial_balance
        self.portfolio_history: List[float] = []
        self.invalid_action_count = 0
        self.total_steps_this_episode = 0

    # ------------------------------------------------------------------
    # RESET
    # ------------------------------------------------------------------

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)

        # Print debug stats from previous episode
        if self.total_steps_this_episode > 0 and self.invalid_action_count > 0:
            pct = self.invalid_action_count / self.total_steps_this_episode * 100
            print(f"📊 Episode end | Invalid: {self.invalid_action_count} ({pct:.1f}%)")

        # 1. Pick N_CANDIDATES random stocks for this episode
        #    This is the key change - AI sees a basket, must pick the best
        chosen_indices = self.np_random.choice(
            len(self.tickers), size=self.N_CANDIDATES, replace=False
        )
        self.candidate_tickers = [self.tickers[i] for i in chosen_indices]
        
        # 2. Load data for each candidate
        self.candidate_dfs = []
        for ticker in self.candidate_tickers:
            path = os.path.join(self.data_dir, f"{ticker}.parquet")
            df = pd.read_parquet(path)
            self.candidate_dfs.append(df)

        # 3. Find a valid common start point across all 5 stocks
        #    All stocks must have enough data at the chosen start
        min_len = min(len(df) for df in self.candidate_dfs)
        required = self.lookback + self.episode_length + 50  # buffer
        
        if min_len < required:
            # If too short, start from lookback
            self.episode_start_step = self.lookback
        else:
            # Random start anywhere that allows a full episode
            max_start = min_len - self.episode_length - 10
            self.episode_start_step = int(self.np_random.integers(self.lookback, max_start))
        
        self.current_step = self.episode_start_step

        # 4. Reset portfolio state
        self.balance = self.initial_balance
        self.shares = 0
        self.held_ticker = None
        self.held_ticker_idx = -1
        self.entry_price = 0.0
        self.entry_step = 0
        self.stop_price = 0.0
        self.target_price = 0.0
        self.prev_portfolio_value = self.initial_balance
        self.portfolio_history = [self.initial_balance]
        self.invalid_action_count = 0
        self.total_steps_this_episode = 0

        return self._get_obs(), self._get_info()

    # ------------------------------------------------------------------
    # OBSERVATION - FULLY IMPLEMENTED
    # ------------------------------------------------------------------

    def _get_obs(self) -> np.ndarray:
        """
        Build the full observation vector.
        
        Structure:
            [Stock0_day0_features... Stock0_day19_features...
             Stock1_day0_features... Stock1_day19_features...
             ...
             Stock4_day0_features... Stock4_day19_features...
             Portfolio_features]
        
        Each day's features (7):
            0: normalized_close     (close / close_20_days_ago - 1)
            1: rsi / 100            (0-1 normalized)
            2: macd_normalized      (MACD / close)
            3: sma50_ratio          (close / SMA50 - 1)
            4: sma200_ratio         (close / SMA200 - 1)
            5: atr_ratio            (ATR / close)  - volatility measure
            6: volume_ratio         (volume / avg_volume)
        
        Portfolio features (7):
            0: balance_normalized       (balance / initial_balance)
            1: position_held            (1 if holding any stock, 0 otherwise)
            2: held_ticker_idx          (0-4 which stock we're holding, -1 if none → normalized)
            3: unrealized_pnl_pct       (current profit/loss on open position)
            4: days_held                (how long we've held / episode_length)
            5: progress                 (current_step / episode_length)
            6: cash_ratio               (balance / portfolio_value)
        """
        features = []

        # --- 5 stocks' market data ---
        for stock_idx, df in enumerate(self.candidate_dfs):
            # Get the lookback window for this stock
            start = self.current_step - self.lookback
            end = self.current_step
            
            # Safety clamp
            start = max(0, start)
            window = df.iloc[start:end]
            
            # Pad if window is too short
            if len(window) < self.lookback:
                pad = self.lookback - len(window)
                padding = pd.DataFrame(
                    np.zeros((pad, len(window.columns))), 
                    columns=window.columns
                )
                window = pd.concat([padding, window])

            # Reference price for normalization (20 days ago close)
            ref_price = window.iloc[0]['Close']
            if ref_price == 0:
                ref_price = 1.0

            for _, row in window.iterrows():
                close = row['Close']
                
                # 0: Normalized close (returns relative to start of window)
                norm_close = (close / ref_price) - 1.0 if ref_price > 0 else 0.0
                
                # 1: RSI normalized to 0-1
                rsi = row.get('RSI', 50.0)
                norm_rsi = rsi / 100.0
                
                # 2: MACD normalized by close price
                macd = row.get('MACD', 0.0)
                norm_macd = macd / close if close > 0 else 0.0
                
                # 3: Close vs SMA50 (how far above/below 50-day average)
                sma50 = row.get('SMA_50', close)
                norm_sma50 = (close / sma50) - 1.0 if sma50 > 0 else 0.0
                
                # 4: Close vs SMA200 (is it in an uptrend overall?)
                sma200 = row.get('SMA_200', close)
                norm_sma200 = (close / sma200) - 1.0 if sma200 > 0 else 0.0
                
                # 5: ATR ratio (volatility - higher = riskier)
                atr = row.get('ATR', close * 0.02)
                norm_atr = atr / close if close > 0 else 0.02
                
                # 6: Volume ratio (unusual volume = potential move)
                vol_ratio = row.get('Volume_ratio', 1.0)
                norm_vol = min(vol_ratio, 5.0) / 5.0  # Cap at 5x average

                features.extend([
                    float(np.clip(norm_close, -1.0, 1.0)),
                    float(np.clip(norm_rsi, 0.0, 1.0)),
                    float(np.clip(norm_macd, -0.1, 0.1)),
                    float(np.clip(norm_sma50, -0.5, 0.5)),
                    float(np.clip(norm_sma200, -0.5, 0.5)),
                    float(np.clip(norm_atr, 0.0, 0.1)),
                    float(np.clip(norm_vol, 0.0, 1.0)),
                ])

        # --- Portfolio state features ---
        current_price = 0.0
        if self.held_ticker_idx >= 0:
            safe_idx = min(self.current_step, len(self.candidate_dfs[self.held_ticker_idx]) - 1)
            current_price = self.candidate_dfs[self.held_ticker_idx].iloc[safe_idx]['Close']
        
        portfolio_value = self.balance + (self.shares * current_price)
        
        # 0: How much cash do we have left (relative to start)
        balance_norm = self.balance / self.initial_balance
        
        # 1: Are we in a position?
        in_position = 1.0 if self.shares > 0 else 0.0
        
        # 2: Which stock are we holding? (-1=none, normalized to -0.2 to 1.0)
        held_idx_norm = self.held_ticker_idx / self.N_CANDIDATES if self.held_ticker_idx >= 0 else -0.2
        
        # 3: How much are we up/down on the trade?
        if self.entry_price > 0 and current_price > 0:
            unrealized_pnl = (current_price - self.entry_price) / self.entry_price
        else:
            unrealized_pnl = 0.0
        
        # 4: How long have we been holding?
        days_held = (self.current_step - self.entry_step) / self.episode_length if self.entry_step > 0 else 0.0
        
        # 5: How far through the episode are we?
        episode_progress = (self.current_step - self.episode_start_step) / self.episode_length
        
        # 6: Cash as fraction of total portfolio
        cash_ratio = self.balance / portfolio_value if portfolio_value > 0 else 1.0

        features.extend([
            float(np.clip(balance_norm, 0.0, 2.0)),
            float(in_position),
            float(held_idx_norm),
            float(np.clip(unrealized_pnl, -0.5, 0.5)),
            float(np.clip(days_held, 0.0, 1.0)),
            float(np.clip(episode_progress, 0.0, 1.0)),
            float(np.clip(cash_ratio, 0.0, 1.0)),
        ])

        obs = np.array(features, dtype=np.float32)
        
        # Sanity check
        assert obs.shape == (self.OBS_DIM,), f"Obs shape {obs.shape} != {self.OBS_DIM}"
        assert not np.any(np.isnan(obs)), "NaN in observation!"
        
        return obs

    # ------------------------------------------------------------------
    # STEP
    # ------------------------------------------------------------------

    def step(self, action: int):
        self.total_steps_this_episode += 1
        terminated = False
        truncated = False
        trade_closed = False
        is_win = False
        holding_period = 0
        invalid_action_penalty = 0.0

        # Current prices for all candidates
        prices = self._get_current_prices()

        # ------------------------------------------------------------------
        # ACTION VALIDATION
        # ------------------------------------------------------------------
        original_action = action

        # Actions 1-5: BUY a specific stock (0-indexed as action-1)
        if 1 <= action <= self.N_CANDIDATES:
            if self.shares > 0:
                # Already holding something - can't buy again
                action = 0  # Force HOLD
                invalid_action_penalty = -2.0
                self.invalid_action_count += 1

        # Action 6: SELL
        elif action == self.N_CANDIDATES + 1:
            if self.shares == 0:
                # Nothing to sell
                action = 0  # Force HOLD
                invalid_action_penalty = -2.0
                self.invalid_action_count += 1

        # ------------------------------------------------------------------
        # CHECK AUTO-EXITS (Stop Loss / Take Profit)
        # ------------------------------------------------------------------
        if self.shares > 0 and self.held_ticker_idx >= 0:
            current_price = prices[self.held_ticker_idx]
            
            if current_price <= self.stop_price:  # Stop Loss hit
                is_win = False
                holding_period = self.current_step - self.entry_step
                self._execute_sell(current_price)
                trade_closed = True
                
            elif current_price >= self.target_price:  # Take Profit hit
                is_win = True
                holding_period = self.current_step - self.entry_step
                self._execute_sell(current_price)
                trade_closed = True

        # ------------------------------------------------------------------
        # EXECUTE AGENT ACTION
        # ------------------------------------------------------------------
        if not trade_closed:
            # BUY a candidate stock (actions 1-5)
            if 1 <= action <= self.N_CANDIDATES and self.shares == 0:
                stock_idx = action - 1  # Convert to 0-indexed
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
                            
                            # Set stop loss and take profit
                            self.stop_price = price * (1 - self.stop_loss_pct)
                            self.target_price = price * (1 + self.take_profit_pct)

            # SELL current position (action 6)
            elif action == self.N_CANDIDATES + 1 and self.shares > 0:
                current_price = prices[self.held_ticker_idx]
                is_win = current_price > self.entry_price
                holding_period = self.current_step - self.entry_step
                self._execute_sell(current_price)
                trade_closed = True

        # ------------------------------------------------------------------
        # ADVANCE TIME
        # ------------------------------------------------------------------
        self.current_step += 1
        
        # Check episode end
        steps_taken = self.current_step - self.episode_start_step
        if steps_taken >= self.episode_length:
            terminated = True
            # Force close any open position at episode end
            if self.shares > 0 and self.held_ticker_idx >= 0:
                final_prices = self._get_current_prices()
                final_price = final_prices[self.held_ticker_idx]
                is_win = final_price > self.entry_price
                holding_period = self.current_step - self.entry_step
                self._execute_sell(final_price)
                trade_closed = True
        else:
            # Check if any stock has run out of data
            for df in self.candidate_dfs:
                if self.current_step >= len(df) - 1:
                    terminated = True
                    break

        # ------------------------------------------------------------------
        # CALCULATE PORTFOLIO VALUE
        # ------------------------------------------------------------------
        current_prices = self._get_current_prices()
        
        held_price = current_prices[self.held_ticker_idx] if self.held_ticker_idx >= 0 else 0.0
        portfolio_value = self.balance + (self.shares * held_price)
        self.portfolio_history.append(portfolio_value)

        # ------------------------------------------------------------------
        # REWARD CALCULATION
        # ------------------------------------------------------------------
        reward = 0.0

        # A) Raw portfolio change
        portfolio_change = portfolio_value - self.prev_portfolio_value
        reward += portfolio_change * self.reward_scaling

        # B) Invalid action penalty
        reward += invalid_action_penalty

        # C) Reward for being invested (small nudge to not hoard cash)
        if self.shares > 0:
            reward += 0.02

        # D) Penalty for hoarding cash when no position
        if action == 0 and self.shares == 0 and original_action == 0:
            reward -= 0.01

        # E) Trade outcome bonus/penalty - asymmetric to encourage winning
        if trade_closed:
            if self.entry_price > 0:
                profit_pct = (portfolio_value - self.prev_portfolio_value) / max(self.prev_portfolio_value, 1) * 100

                if is_win:
                    reward += profit_pct * 30.0    # Big bonus for wins
                    reward += 3.0                   # Flat win bonus
                    if 5 <= holding_period <= 30:
                        reward += 1.0               # Bonus for "right" holding period
                else:
                    reward += profit_pct * 15.0    # Smaller penalty for losses
                    reward -= 1.0                   # Flat loss penalty
                    if holding_period > 40:
                        reward -= 1.0               # Penalty for bagholding

        # F) Sharpe-like quality bonus at episode end
        #    Rewards consistent growth, not just final value
        if terminated and len(self.portfolio_history) > 10:
            returns = np.diff(self.portfolio_history) / np.maximum(self.portfolio_history[:-1], 1)
            if len(returns) > 0:
                mean_ret = np.mean(returns)
                std_ret = np.std(returns) + 1e-9
                sharpe = mean_ret / std_ret
                reward += sharpe * 10.0  # Reward consistent performance

        self.prev_portfolio_value = portfolio_value

        info = self._get_info(
            trade_closed=trade_closed,
            is_win=is_win,
            holding_period=holding_period,
            invalid_action=(original_action != action),
            portfolio_value=portfolio_value
        )

        return self._get_obs(), float(reward), terminated, truncated, info

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_current_prices(self) -> List[float]:
        """Get current price for each candidate stock."""
        prices = []
        for df in self.candidate_dfs:
            safe_idx = min(self.current_step, len(df) - 1)
            prices.append(float(df.iloc[safe_idx]['Close']))
        return prices

    def _execute_sell(self, price: float):
        """Execute a sell order and update state."""
        proceeds = self.shares * price * (1 - self.transaction_cost - self.slippage)
        self.balance += proceeds
        self.shares = 0
        self.held_ticker = None
        self.held_ticker_idx = -1
        self.entry_price = 0.0
        self.stop_price = 0.0
        self.target_price = 0.0

    def _get_info(self, trade_closed=False, is_win=False, holding_period=0,
                  invalid_action=False, portfolio_value=None) -> Dict:
        """Return info dict for logging/callbacks."""
        if portfolio_value is None:
            prices = self._get_current_prices()
            held_price = prices[self.held_ticker_idx] if self.held_ticker_idx >= 0 else 0.0
            portfolio_value = self.balance + (self.shares * held_price)

        # SMA context for current held stock (or first candidate if none)
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
            "day_trades_used": 0,  # Kept for callback compatibility
            "invalid_action": invalid_action,
        }