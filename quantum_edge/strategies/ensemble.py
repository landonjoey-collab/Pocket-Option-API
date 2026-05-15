"""
Ensemble signal combiner.
Collects weighted votes from all strategies; fires when total exceeds threshold.
"""
import pandas as pd
from quantum_edge import config
from quantum_edge.strategies import trend, momentum, reversion


def get_signal(df1m: pd.DataFrame, df5m: pd.DataFrame | None = None) -> tuple[int, dict]:
    """
    Returns (signal, breakdown) where:
      signal    = 1 (long) | -1 (short) | 0 (no trade)
      breakdown = per-strategy raw signals and weights
    """
    raw = {
        "trend":     trend.signal(df1m, df5m),
        "momentum":  momentum.signal(df1m, df5m),
        "reversion": reversion.signal(df1m, df5m),
    }

    weights = config.STRATEGY_WEIGHTS
    long_score  = sum(weights[k] for k, v in raw.items() if v ==  1)
    short_score = sum(weights[k] for k, v in raw.items() if v == -1)

    if long_score >= config.SIGNAL_THRESHOLD:
        return 1, raw
    if short_score >= config.SIGNAL_THRESHOLD:
        return -1, raw
    return 0, raw
