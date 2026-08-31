"""
collapse_guard_callback.py

Watches training-time diagnostics and flags (or halts) the run if the
policy looks like it's collapsing toward a near-uniform/degenerate
output - the failure mode we diagnosed in ai_scorer.py's near-1/7
probabilities. Cheap insurance: catch this at 50k steps, not after a
multi-hour run finishes.
"""

import numpy as np
from stable_baselines3.common.callbacks import BaseCallback


class CollapseGuardCallback(BaseCallback):
    def __init__(
        self,
        check_every_steps: int = 10_000,
        max_entropy_for_n_actions: int = 3,   # matches Discrete(3) in v4
        entropy_ratio_halt: float = 0.98,     # halt if entropy > 98% of max
        consecutive_bad_checks_to_halt: int = 3,
        verbose: int = 1,
    ):
        super().__init__(verbose)
        self.check_every_steps = check_every_steps
        self.max_entropy = float(np.log(max_entropy_for_n_actions))
        self.entropy_ratio_halt = entropy_ratio_halt
        self.consecutive_bad_checks_to_halt = consecutive_bad_checks_to_halt
        self._bad_streak = 0
        self._last_check_step = 0

    def _on_step(self) -> bool:
        if self.num_timesteps - self._last_check_step < self.check_every_steps:
            return True
        self._last_check_step = self.num_timesteps

        entropy_loss = self.model.logger.name_to_value.get("train/entropy_loss")
        value_loss = self.model.logger.name_to_value.get("train/value_loss")
        if entropy_loss is None:
            return True  # nothing logged yet (e.g. before first rollout update)

        # SB3 logs entropy_loss as the NEGATIVE mean entropy.
        entropy = -entropy_loss
        ratio = entropy / self.max_entropy if self.max_entropy > 0 else 0.0

        if self.verbose:
            print(f"[CollapseGuard] step={self.num_timesteps} entropy={entropy:.4f} "
                  f"({ratio*100:.1f}% of max) value_loss={value_loss}")

        if ratio >= self.entropy_ratio_halt:
            self._bad_streak += 1
            print(f"⚠️  [CollapseGuard] entropy at {ratio*100:.1f}% of max for "
                  f"{self._bad_streak} consecutive check(s) - policy may be collapsing "
                  f"toward a uniform/degenerate output.")
        else:
            self._bad_streak = 0

        if self._bad_streak >= self.consecutive_bad_checks_to_halt:
            print(f"🛑 [CollapseGuard] entropy stayed near-max for "
                  f"{self._bad_streak} consecutive checks - halting training. "
                  f"Check reward scale (look for outlier rewards dominating "
                  f"the batch) before restarting.")
            return False  # returning False stops training

        return True