"""
Mean-Reversion Scalp Strategy
Signal: Bollinger Band squeeze release + RSI extreme + price rejection wick.
Returns  1 (long), -1 (short), 0 (no trade).
"""
import pandas as pd
from quantum_edge import config, indicators as ind


def signal(df1m: pd.DataFrame, df5m: pd.DataFrame | None = None) -> int:
    if len(df1m) < config.BB_PERIOD + 10:
        return 0

    df = df1m.copy()
    df["rsi"] = ind.rsi(df["close"], config.RSI_PERIOD)
    bb_u, bb_m, bb_l = ind.bollinger(df["close"], config.BB_PERIOD, config.BB_STD)
    df["bb_u"], df["bb_m"], df["bb_l"] = bb_u, bb_m, bb_l
    df["sqz"] = ind.squeeze(df, config.BB_PERIOD, config.BB_STD)

    # Detect squeeze release (was squeezed, now expanded)
    prev_sqz = df["sqz"].iat[-2] if len(df) > 1 else False
    curr_sqz = df["sqz"].iat[-1]
    squeeze_release = prev_sqz and not curr_sqz

    last = len(df) - 1
    close  = df["close"].iat[last]
    open_  = df["open"].iat[last]
    high   = df["high"].iat[last]
    low    = df["low"].iat[last]
    rsi_v  = df["rsi"].iat[last]

    body   = abs(close - open_)
    wick_l = open_ - low if close > open_ else close - low
    wick_u = high - open_ if close > open_ else high - close

    # Long: price touches lower BB, RSI oversold, bullish rejection wick
    if (close < df["bb_l"].iat[last]
            and rsi_v < config.RSI_OS + 10
            and wick_l > body * 0.5
            and close > open_):
        return 1

    # Short: price touches upper BB, RSI overbought, bearish rejection wick
    if (close > df["bb_u"].iat[last]
            and rsi_v > config.RSI_OB - 10
            and wick_u > body * 0.5
            and close < open_):
        return -1

    # Squeeze release long/short
    if squeeze_release:
        if close > bb_m.iat[last] and rsi_v > 50:
            return 1
        if close < bb_m.iat[last] and rsi_v < 50:
            return -1

    return 0
