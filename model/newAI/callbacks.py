import os
import csv
import numpy as np
from stable_baselines3.common.callbacks import BaseCallback

class TensorboardCallback(BaseCallback):
    def __init__(self, verbose=0):
        super().__init__(verbose)
        self.portfolio_values = []
        self.holding_periods = []
        self.sma_ratios = []
        self.wins = 0
        self.trades = 0

    def _on_step(self) -> bool:
        infos = self.locals.get('infos', [])
        for info in infos:
            if 'portfolio_value' in info:
                self.portfolio_values.append(info['portfolio_value'])
            
            # Context metric
            if 'price_vs_sma' in info:
                self.sma_ratios.append(info['price_vs_sma'])

            # Trade Metrics
            if info.get('trade_closed'):
                self.trades += 1
                if info.get('is_win'):
                    self.wins += 1
                if info.get('holding_period') > 0:
                    self.holding_periods.append(info['holding_period'])

        # Log every 100 steps
        if self.n_calls % 100 == 0:
            if self.portfolio_values:
                self.logger.record("custom/portfolio_value", np.mean(self.portfolio_values))
                self.portfolio_values = []
            
            if self.sma_ratios:
                self.logger.record("context/price_vs_sma200", np.mean(self.sma_ratios))
                self.sma_ratios = []

            if self.trades > 0:
                self.logger.record("custom/win_rate", self.wins / self.trades)
                self.logger.record("custom/trades_per_100_steps", self.trades)
                if self.holding_periods:
                    self.logger.record("custom/avg_holding_period", np.mean(self.holding_periods))
                
                # Reset counters
                self.wins = 0
                self.trades = 0
                self.holding_periods = []
        return True

class MetricLoggerCallback(BaseCallback):
    def __init__(self, log_dir):
        super().__init__(verbose=0)
        self.csv_file = os.path.join(log_dir, "training_metrics.csv")
        
    def _init_callback(self) -> None:
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["timestep", "portfolio_value", "reward", "balance", "day_trades", "action", "ticker"])

    def _on_step(self) -> bool:
        if self.n_calls % 10 == 0:
            infos = self.locals.get('infos', [])
            if infos:
                info = infos[0]
                with open(self.csv_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        self.num_timesteps,
                        info.get('portfolio_value', 0),
                        self.locals['rewards'][0],
                        info.get('balance', 0),
                        info.get('day_trades_used', 0),
                        self.locals['actions'][0],
                        info.get('ticker', 'N/A')
                    ])
        return True