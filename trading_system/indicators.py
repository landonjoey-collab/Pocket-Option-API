"""Pure-pandas/numpy indicator library — no TA-Lib required."""
import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(series: pd.Series, period: int = 20, std: float = 2.0):
    mid = sma(series, period)
    sd = series.rolling(period).std()
    upper = mid + std * sd
    lower = mid - std * sd
    return upper, mid, lower


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat(
        [h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def supertrend(df: pd.DataFrame, multiplier: float = 1.3, period: int = 13):
    df = df.copy()
    df["atr"] = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    df["basic_ub"] = hl2 + multiplier * df["atr"]
    df["basic_lb"] = hl2 - multiplier * df["atr"]

    final_ub = [0.0] * len(df)
    final_lb = [0.0] * len(df)
    st = [0.0] * len(df)
    direction = [""] * len(df)

    for i in range(period, len(df)):
        bub = df["basic_ub"].iat[i]
        blb = df["basic_lb"].iat[i]
        pc = df["close"].iat[i - 1]
        c = df["close"].iat[i]

        final_ub[i] = bub if bub < final_ub[i - 1] or pc > final_ub[i - 1] else final_ub[i - 1]
        final_lb[i] = blb if blb > final_lb[i - 1] or pc < final_lb[i - 1] else final_lb[i - 1]

        if st[i - 1] == final_ub[i - 1]:
            st[i] = final_ub[i] if c <= final_ub[i] else final_lb[i]
        else:
            st[i] = final_lb[i] if c >= final_lb[i] else final_ub[i]

        direction[i] = "up" if c > st[i] else "down"

    df["ST"] = st
    df["STX"] = direction
    return df


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_h = h.shift(1)
    prev_l = l.shift(1)
    prev_c = c.shift(1)

    tr = pd.concat(
        [h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1
    ).max(axis=1)

    dm_plus = np.where((h - prev_h) > (prev_l - l), (h - prev_h).clip(lower=0), 0)
    dm_minus = np.where((prev_l - l) > (h - prev_h), (prev_l - l).clip(lower=0), 0)

    s = pd.Series
    atr_s = s(tr).ewm(com=period - 1, min_periods=period).mean()
    di_plus = 100 * s(dm_plus).ewm(com=period - 1, min_periods=period).mean() / atr_s
    di_minus = 100 * s(dm_minus).ewm(com=period - 1, min_periods=period).mean() / atr_s

    dx = (100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan))
    adx_val = dx.ewm(com=period - 1, min_periods=period).mean()
    adx_val.index = df.index
    return adx_val


def heikinashi(df: pd.DataFrame) -> pd.DataFrame:
    ha = pd.DataFrame(index=df.index)
    ha["close"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha["open"] = (df["open"].shift(1) + df["close"].shift(1)) / 2
    ha["open"].iat[0] = (df["open"].iat[0] + df["close"].iat[0]) / 2
    ha["high"] = pd.concat([df["high"], ha["open"], ha["close"]], axis=1).max(axis=1)
    ha["low"] = pd.concat([df["low"], ha["open"], ha["close"]], axis=1).min(axis=1)
    return ha


def crossed_above(s1: pd.Series, s2: pd.Series) -> pd.Series:
    return (s1.shift(1) < s2.shift(1)) & (s1 >= s2)


def crossed_below(s1: pd.Series, s2: pd.Series) -> pd.Series:
    return (s1.shift(1) > s2.shift(1)) & (s1 <= s2)
