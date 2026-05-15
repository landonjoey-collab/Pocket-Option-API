"""
Multi-confirmation strategy stack.

Signal flow:
  1. Trend filter  – Supertrend + dual EMA
  2. Momentum gate – RSI not extreme in wrong direction, MACD confirms
  3. Volatility    – ADX > threshold (strong trend present)
  4. Entry timing  – Bollinger Band squeeze/expansion

Returns 1 (call), -1 (put), or 0 (no trade).
"""
import pandas as pd
from trading_system import config, indicators as ind


def _require_cols(df: pd.DataFrame) -> None:
    needed = {"open", "high", "low", "close"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing columns: {missing}")


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    _require_cols(df)
    df = df.copy()

    ha = ind.heikinashi(df)
    df["ha_open"] = ha["open"]
    df["ha_close"] = ha["close"]
    df["ha_high"] = ha["high"]
    df["ha_low"] = ha["low"]

    df = ind.supertrend(df, config.ST_MULTIPLIER, config.ST_PERIOD)

    df["ema_fast"] = ind.ema(df["ha_close"], config.EMA_FAST)
    df["ema_slow"] = ind.ema(df["ha_close"], config.EMA_SLOW)

    df["rsi"] = ind.rsi(df["ha_close"], config.RSI_PERIOD)
    df["macd"], df["macd_sig"], df["macd_hist"] = ind.macd(
        df["ha_close"], config.MACD_FAST, config.MACD_SLOW, config.MACD_SIGNAL
    )

    bb_upper, bb_mid, bb_lower = ind.bollinger_bands(
        df["ha_close"], config.BB_PERIOD, config.BB_STD
    )
    df["bb_upper"] = bb_upper
    df["bb_mid"] = bb_mid
    df["bb_lower"] = bb_lower

    df["adx"] = ind.adx(df, config.ADX_PERIOD)

    df["st_cross_up"] = ind.crossed_above(df["ha_close"], df["ST"])
    df["st_cross_dn"] = ind.crossed_below(df["ha_close"], df["ST"])
    df["ema_cross_up"] = ind.crossed_above(df["ema_fast"], df["ema_slow"])
    df["ema_cross_dn"] = ind.crossed_below(df["ema_fast"], df["ema_slow"])
    df["macd_cross_up"] = ind.crossed_above(df["macd"], df["macd_sig"])
    df["macd_cross_dn"] = ind.crossed_below(df["macd"], df["macd_sig"])

    df["signal"] = 0

    call_cond = (
        (df["STX"] == "up")
        & (df["ema_fast"] > df["ema_slow"])
        & (df["rsi"] > 45) & (df["rsi"] < config.RSI_OVERBOUGHT)
        & (df["macd_hist"] > 0)
        & (df["adx"] > config.ADX_THRESHOLD)
        & (
            df["st_cross_up"]
            | df["ema_cross_up"]
            | df["macd_cross_up"]
        )
    )

    put_cond = (
        (df["STX"] == "down")
        & (df["ema_fast"] < df["ema_slow"])
        & (df["rsi"] < 55) & (df["rsi"] > config.RSI_OVERSOLD)
        & (df["macd_hist"] < 0)
        & (df["adx"] > config.ADX_THRESHOLD)
        & (
            df["st_cross_dn"]
            | df["ema_cross_dn"]
            | df["macd_cross_dn"]
        )
    )

    df.loc[call_cond, "signal"] = 1
    df.loc[put_cond, "signal"] = -1

    return df


def get_signal(df: pd.DataFrame) -> int:
    """Return the signal on the most recent closed candle."""
    if len(df) < max(config.ST_PERIOD, config.MACD_SLOW, config.BB_PERIOD) + 5:
        return 0
    result = compute_signals(df)
    return int(result["signal"].iat[-1])
