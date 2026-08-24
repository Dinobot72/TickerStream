"""
diagnose_normalization.py

Checks whether the loaded VecNormalize stats are collapsing different
tickers' observations into a near-identical, clip-saturated vector -
which would fully explain near-uniform action probabilities regardless
of input.

Run from backend/:
    python diagnose_normalization.py
"""

import sys
import numpy as np

sys.path.insert(0, ".")
from app.services.ai_scorer import AIScorer  # noqa: E402
from app.services.data_prep_live import get_live_observation  # noqa: E402

MODEL_PATH = "../model/logs/best_model/best_model"
FILLER = ["SPY", "QQQ", "AAPL", "MSFT"]
TEST_TICKERS = ["AAPL", "PFSA", "SLE"]


def describe(name, arr):
    n_at_pos_clip = np.sum(arr >= 9.999)
    n_at_neg_clip = np.sum(arr <= -9.999)
    print(
        f"    {name:22s} min={arr.min():8.3f}  max={arr.max():8.3f}  "
        f"mean={arr.mean():8.3f}  std={arr.std():8.3f}  "
        f"clipped(+10)={n_at_pos_clip:4d}  clipped(-10)={n_at_neg_clip:4d}  of {arr.size}"
    )


def main():
    print(f"Loading model + VecNormalize from {MODEL_PATH} ...")
    scorer = AIScorer(model_path=MODEL_PATH)

    if scorer.obs_rms is None:
        print("❌ obs_rms is None - VecNormalize stats never actually loaded. That's the bug.")
        return

    mean = np.asarray(scorer.obs_rms.mean)
    var = np.asarray(scorer.obs_rms.var)
    print(f"\nobs_rms.mean: shape={mean.shape} min={mean.min():.4f} max={mean.max():.4f} mean={mean.mean():.4f}")
    print(f"obs_rms.var:  shape={var.shape} min={var.min():.6f} max={var.max():.4f} mean={var.mean():.4f}")
    n_tiny_var = np.sum(var < 1e-6)
    print(f"# dims with var < 1e-6 (would blow up normalization): {n_tiny_var} / {var.size}")

    raw_obs = {}
    for ticker in TEST_TICKERS:
        print(f"\n--- {ticker} ---")
        candidates = [ticker] + FILLER
        obs = get_live_observation(
            candidates=candidates, balance=10_000, held_ticker=None,
            shares=0, entry_price=0.0, days_held=0, initial_balance=10_000,
        )
        if obs is None:
            print("  could not build observation, skipped")
            continue
        raw_obs[ticker] = obs
        normed = scorer._normalize(obs)
        describe("raw obs", obs)
        describe("normalized obs", normed)

    if "AAPL" in raw_obs and "PFSA" in raw_obs:
        raw_diff = np.abs(raw_obs["AAPL"] - raw_obs["PFSA"])
        print(f"\nAAPL vs PFSA raw obs: mean abs diff = {raw_diff.mean():.4f}, "
              f"max abs diff = {raw_diff.max():.4f}, # dims identical = {np.sum(raw_diff < 1e-9)}")
        norm_aapl = scorer._normalize(raw_obs["AAPL"])
        norm_pfsa = scorer._normalize(raw_obs["PFSA"])
        norm_diff = np.abs(norm_aapl - norm_pfsa)
        print(f"AAPL vs PFSA normalized obs: mean abs diff = {norm_diff.mean():.4f}, "
              f"max abs diff = {norm_diff.max():.4f}, # dims identical = {np.sum(norm_diff < 1e-6)}")


if __name__ == "__main__":
    main()