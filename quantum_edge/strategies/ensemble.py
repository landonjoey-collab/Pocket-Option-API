"""
Ensemble signal combiner.

Normal market: weighted vote across trend + momentum + reversion.
Crisis market : crash strategy gets overriding weight;
                threshold is lowered so a single strong signal fires.
"""
import pandas as pd
from quantum_edge import config
from quantum_edge.strategies import trend, momentum, reversion, crash


def get_signal(df1m: pd.DataFrame, df5m: pd.DataFrame | None = None) -> tuple[int, dict]:
    """
    Returns (signal, breakdown) where:
      signal    = 1 (long) | -1 (short) | 0 (no trade)
      breakdown = per-strategy raw signals, weights, and crash state
    """
    # Always run crash detector first
    crash_sig, crash_state = crash.signal(df1m, df5m)

    raw = {
        "trend":     trend.signal(df1m, df5m),
        "momentum":  momentum.signal(df1m, df5m),
        "reversion": reversion.signal(df1m, df5m),
        "crash":     crash_sig,
    }

    breakdown = {**raw, "crash_regime": crash_state.regime,
                 "crash_severity": round(crash_state.severity, 2),
                 "drop_pct": round(crash_state.drop_pct, 2)}

    # ── Crisis mode ───────────────────────────────────────────────────────────
    if crash_state.regime in ("crash", "bounce") and crash_state.severity >= 0.45:
        # In a crash, the crash strategy alone can trigger a trade
        if crash_sig != 0:
            return crash_sig, breakdown

        # If crash strategy is neutral but severity is moderate,
        # still require other strategies to agree directionally
        long_score  = sum(config.STRATEGY_WEIGHTS.get(k, 0.1) for k, v in raw.items() if v ==  1)
        short_score = sum(config.STRATEGY_WEIGHTS.get(k, 0.1) for k, v in raw.items() if v == -1)
        threshold   = config.SIGNAL_THRESHOLD * 0.8   # 20% lower threshold in volatile markets

        if long_score >= threshold:
            return 1, breakdown
        if short_score >= threshold:
            return -1, breakdown
        return 0, breakdown

    # ── Normal mode ───────────────────────────────────────────────────────────
    weights = config.STRATEGY_WEIGHTS
    long_score  = sum(weights[k] for k, v in raw.items() if v ==  1 and k in weights)
    short_score = sum(weights[k] for k, v in raw.items() if v == -1 and k in weights)

    if long_score >= config.SIGNAL_THRESHOLD:
        return 1, breakdown
    if short_score >= config.SIGNAL_THRESHOLD:
        return -1, breakdown
    return 0, breakdown
