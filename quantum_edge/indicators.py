"""Pure-pandas technical indicators — zero TA-Lib dependency."""
import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    gain = d.clip(lower=0).ewm(com=n - 1, min_periods=n).mean()
    loss = (-d).clip(lower=0).ewm(com=n - 1, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(s: pd.Series, fast=12, slow=26, signal=9):
    ml = ema(s, fast) - ema(s, slow)
    sl = ema(ml, signal)
    return ml, sl, ml - sl


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(com=n - 1, min_periods=n).mean()


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(s, n)
    std = s.rolling(n).std()
    return mid + k * std, mid, mid - k * std


def keltner(df: pd.DataFrame, n: int = 20, k: float = 1.0):
    mid = ema(df["close"], n)
    a = atr(df, n)
    return mid + k * a, mid, mid - k * a


def squeeze(df: pd.DataFrame, bb_n=20, bb_k=2.0, kc_n=20, kc_k=1.0) -> pd.Series:
    """True when Bollinger Bands are inside Keltner Channel (low-volatility squeeze)."""
    bb_u, _, bb_l = bollinger(df["close"], bb_n, bb_k)
    kc_u, _, kc_l = keltner(df, kc_n, kc_k)
    return (bb_u < kc_u) & (bb_l > kc_l)


def stochastic(df: pd.DataFrame, k_period=14, d_period=3):
    low_min = df["low"].rolling(k_period).min()
    high_max = df["high"].rolling(k_period).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def adx_di(df: pd.DataFrame, n: int = 14):
    h, l, c = df["high"], df["low"], df["close"]
    ph, pl = h.shift(), l.shift()
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    dm_p = np.where((h - ph) > (pl - l), (h - ph).clip(lower=0), 0.0)
    dm_m = np.where((pl - l) > (h - ph), (pl - l).clip(lower=0), 0.0)
    atr_s = pd.Series(tr).ewm(com=n - 1, min_periods=n).mean()
    atr_s.index = df.index
    di_p = 100 * pd.Series(dm_p, index=df.index).ewm(com=n - 1, min_periods=n).mean() / atr_s
    di_m = 100 * pd.Series(dm_m, index=df.index).ewm(com=n - 1, min_periods=n).mean() / atr_s
    dx = (100 * (di_p - di_m).abs() / (di_p + di_m).replace(0, np.nan))
    adx_val = dx.ewm(com=n - 1, min_periods=n).mean()
    return adx_val, di_p, di_m


def supertrend(df: pd.DataFrame, mult=1.3, period=13):
    df = df.copy()
    a = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    bub = hl2 + mult * a
    blb = hl2 - mult * a

    fu = [0.0] * len(df)
    fl = [0.0] * len(df)
    st = [0.0] * len(df)
    stx = [""] * len(df)

    for i in range(period, len(df)):
        fu[i] = bub.iat[i] if bub.iat[i] < fu[i-1] or df["close"].iat[i-1] > fu[i-1] else fu[i-1]
        fl[i] = blb.iat[i] if blb.iat[i] > fl[i-1] or df["close"].iat[i-1] < fl[i-1] else fl[i-1]
        if st[i-1] == fu[i-1]:
            st[i] = fu[i] if df["close"].iat[i] <= fu[i] else fl[i]
        else:
            st[i] = fl[i] if df["close"].iat[i] >= fl[i] else fu[i]
        stx[i] = "up" if df["close"].iat[i] > st[i] else "down"

    df["ST"] = st
    df["STX"] = stx
    return df


def heikinashi(df: pd.DataFrame) -> pd.DataFrame:
    ha = pd.DataFrame(index=df.index)
    ha["close"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha["open"] = (df["open"].shift() + df["close"].shift()) / 2
    ha.loc[ha.index[0], "open"] = (df["open"].iat[0] + df["close"].iat[0]) / 2
    ha["high"] = pd.concat([df["high"], ha["open"], ha["close"]], axis=1).max(axis=1)
    ha["low"] = pd.concat([df["low"], ha["open"], ha["close"]], axis=1).min(axis=1)
    return ha


def crossed_above(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a.shift() < b.shift()) & (a >= b)


def crossed_below(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a.shift() > b.shift()) & (a <= b)
