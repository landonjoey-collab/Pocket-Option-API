"""
Trend Scalp Strategy
Signal: EMA(9) × EMA(21) crossover confirmed by Supertrend direction,
        ADX strength gate, and higher-timeframe EMA(50) bias.
Returns  1 (long), -1 (short), 0 (no trade).
"""
import pandas as pd
from quantum_edge import config, indicators as ind


def signal(df1m: pd.DataFrame, df5m: pd.DataFrame | None = None) -> int:
    if len(df1m) < config.EMA_TREND + 10:
        return 0

    df = df1m.copy()
    df["ema_fast"] = ind.ema(df["close"], config.EMA_FAST)
    df["ema_slow"] = ind.ema(df["close"], config.EMA_SLOW)
    df = ind.supertrend(df, mult=1.3, period=13)
    adx, di_p, di_m = ind.adx_di(df, config.ADX_PERIOD)
    df["adx"] = adx
    df["macd"], df["macd_sig"], df["macd_hist"] = ind.macd(df["close"])

    # Higher-timeframe bias
    htf_bias = 0
    if df5m is not None and len(df5m) > config.EMA_TREND:
        ema_trend = ind.ema(df5m["close"], config.EMA_TREND)
        htf_bias = 1 if df5m["close"].iat[-1] > ema_trend.iat[-1] else -1

    last = len(df) - 1
    cross_up = ind.crossed_above(df["ema_fast"], df["ema_slow"]).iat[last]
    cross_dn = ind.crossed_below(df["ema_fast"], df["ema_slow"]).iat[last]
    st_up    = df["STX"].iat[last] == "up"
    st_dn    = df["STX"].iat[last] == "down"
    strong   = df["adx"].iat[last] > config.ADX_MIN
    macd_pos = df["macd_hist"].iat[last] > 0
    macd_neg = df["macd_hist"].iat[last] < 0

    if cross_up and st_up and strong and macd_pos and htf_bias >= 0:
        return 1
    if cross_dn and st_dn and strong and macd_neg and htf_bias <= 0:
        return -1
    return 0
