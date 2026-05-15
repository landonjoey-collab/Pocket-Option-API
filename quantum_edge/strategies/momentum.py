"""
Momentum Scalp Strategy
Signal: RSI divergence break + Stochastic %K/%D crossover
        filtered by price relative to EMA(21).
Returns  1 (long), -1 (short), 0 (no trade).
"""
import pandas as pd
from quantum_edge import config, indicators as ind


def signal(df1m: pd.DataFrame, df5m: pd.DataFrame | None = None) -> int:
    if len(df1m) < config.RSI_PERIOD + config.STOCH_K + 10:
        return 0

    df = df1m.copy()
    df["rsi"]         = ind.rsi(df["close"], config.RSI_PERIOD)
    df["stoch_k"], df["stoch_d"] = ind.stochastic(df, config.STOCH_K, config.STOCH_D)
    df["ema_slow"]    = ind.ema(df["close"], config.EMA_SLOW)
    df["macd"], df["macd_sig"], df["macd_hist"] = ind.macd(df["close"])

    last = len(df) - 1
    rsi_val   = df["rsi"].iat[last]
    stoch_k   = df["stoch_k"].iat[last]
    stoch_d   = df["stoch_d"].iat[last]
    price     = df["close"].iat[last]
    ema21     = df["ema_slow"].iat[last]

    stoch_cross_up = ind.crossed_above(df["stoch_k"], df["stoch_d"]).iat[last]
    stoch_cross_dn = ind.crossed_below(df["stoch_k"], df["stoch_d"]).iat[last]

    # Long: oversold RSI recovering, stoch bullish cross, price above EMA21
    if (rsi_val < 45 and rsi_val > config.RSI_OS
            and stoch_cross_up and stoch_k < 50
            and price > ema21
            and df["macd_hist"].iat[last] > 0):
        return 1

    # Short: overbought RSI fading, stoch bearish cross, price below EMA21
    if (rsi_val > 55 and rsi_val < config.RSI_OB
            and stoch_cross_dn and stoch_k > 50
            and price < ema21
            and df["macd_hist"].iat[last] < 0):
        return -1

    return 0
