"""
Crash & Volatility Spike Strategy
Detects market crashes, panic sell-offs, and dead-cat bounce setups.

Two modes:
  1. CRASH SHORT  — ride the panic down (confirmed breakdown, volume surge, no support)
  2. BOUNCE LONG  — capitulation wick reversal (extreme RSI, long lower wick, VWAP reclaim)

Returns  1 (bounce long), -1 (crash short), 0 (no signal), plus a CrashState.
"""
from dataclasses import dataclass
import pandas as pd
import numpy as np
from quantum_edge import indicators as ind


@dataclass
class CrashState:
    regime: str          # "crash" | "bounce" | "normal"
    severity: float      # 0-1 crash severity score
    drop_pct: float      # recent % price drop
    vol_ratio: float     # current volume vs average
    rsi: float
    bb_pct: float        # where price sits in BB band (0=bottom, 1=top)
    note: str = ""


def _vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, np.nan)
    return (tp * vol).cumsum() / vol.cumsum()


def detect_crash_state(df: pd.DataFrame, lookback: int = 20) -> CrashState:
    """Analyse recent candles and return a CrashState."""
    if len(df) < lookback + 10:
        return CrashState("normal", 0.0, 0.0, 1.0, 50.0, 0.5)

    close = df["close"]
    vol   = df["volume"]

    # Drop over last `lookback` candles
    recent_high = df["high"].iloc[-lookback:].max()
    current     = close.iat[-1]
    drop_pct    = (current - recent_high) / recent_high * 100   # negative = drop

    # Volume surge
    avg_vol  = vol.iloc[-lookback * 3:-lookback].mean()
    cur_vol  = vol.iloc[-lookback:].mean()
    vol_ratio = cur_vol / max(avg_vol, 1e-9)

    # RSI
    rsi_val = ind.rsi(close, 14).iat[-1]

    # Bollinger Band position
    bb_u, _, bb_l = ind.bollinger(close, 20, 2.0)
    bb_range = bb_u.iat[-1] - bb_l.iat[-1]
    bb_pct = (current - bb_l.iat[-1]) / max(bb_range, 1e-9)

    # Crash severity (0-1)
    severity = min(1.0, max(0.0,
        (-drop_pct / 5.0) * 0.4 +          # 5% drop = 0.4 score
        min((vol_ratio - 1.0) / 3.0, 0.3) + # 4× vol = 0.3 score
        max(0, (30 - rsi_val) / 30) * 0.3   # deep oversold = 0.3 score
    ))

    if drop_pct < -3.0 and vol_ratio > 1.5 and rsi_val < 40:
        regime = "crash"
        note = f"drop={drop_pct:.1f}% vol×{vol_ratio:.1f} RSI={rsi_val:.0f}"
    elif drop_pct < -5.0 and rsi_val < 25 and bb_pct < 0.05:
        regime = "bounce"
        note = f"capitulation: drop={drop_pct:.1f}% RSI={rsi_val:.0f} BB={bb_pct:.2f}"
    else:
        regime = "normal"
        note = ""

    return CrashState(regime, severity, drop_pct, vol_ratio, rsi_val, bb_pct, note)


def signal(df1m: pd.DataFrame, df5m: pd.DataFrame | None = None) -> tuple[int, CrashState]:
    if len(df1m) < 60:
        return 0, CrashState("normal", 0.0, 0.0, 1.0, 50.0, 0.5)

    state = detect_crash_state(df1m, lookback=20)

    close  = df1m["close"]
    open_  = df1m["open"]
    high   = df1m["high"]
    low    = df1m["low"]
    last   = len(df1m) - 1

    if state.regime == "crash":
        # Confirm: EMA(9) < EMA(21), candle is bearish, no immediate support
        ema9  = ind.ema(close, 9).iat[last]
        ema21 = ind.ema(close, 21).iat[last]
        bearish_candle = close.iat[last] < open_.iat[last]
        breakdown = ema9 < ema21

        # Dead-cat bounce short: price bounces up 1-2% after big drop → fade it
        prev_candles = df1m["close"].iloc[-5:-1]
        small_bounce = close.iat[last] > prev_candles.max() * 1.005

        if breakdown and (bearish_candle or small_bounce):
            return -1, state

    elif state.regime == "bounce":
        # Capitulation reversal: big lower wick, RSI turning up, price above VWAP
        body   = abs(close.iat[last] - open_.iat[last])
        wick_l = min(open_.iat[last], close.iat[last]) - low.iat[last]
        hammer = wick_l > body * 1.5 and close.iat[last] > open_.iat[last]

        rsi_now  = ind.rsi(close, 14).iat[last]
        rsi_prev = ind.rsi(close, 14).iat[last - 1]
        rsi_turning_up = rsi_now > rsi_prev and rsi_now < 35

        vwap_val = _vwap(df1m).iat[last]
        above_vwap = close.iat[last] > vwap_val

        if (hammer or rsi_turning_up) and state.rsi < 32:
            return 1, state

    return 0, state
