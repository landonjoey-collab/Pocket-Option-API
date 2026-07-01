"""
Pregame: pre-session market scanner for the PocketOption trading bot.

Connects to the API, scans all qualifying assets, runs multi-indicator
technical analysis, and prints a ranked pregame report so you can see
the best call/put setups before the trading session begins.

Usage (standalone):
    python pregame.py

Usage (imported):
    from pregame import run
    results = run(ssid=ssid, demo=True)
"""

import json
import math
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import talib.abstract as ta

import pocketoptionapi.global_value as global_value
from pocketoptionapi.stable_api import PocketOption


# ── Configuration defaults ────────────────────────────────────────────────────

MIN_PAYOUT = 80       # minimum payout % to consider an asset
CANDLE_PERIOD = 60    # candle size in seconds
TOP_N = 10            # assets shown in the summary
# Tuple of substrings that must appear in the symbol name; () = accept all
SCAN_TYPES: Tuple[str, ...] = ("_otc",)

# Indicator periods
_RSI_PERIOD = 14
_EMA_FAST = 8
_EMA_SLOW = 21
_MACD_FAST, _MACD_SLOW, _MACD_SIG = 12, 26, 9
_BB_WINDOW = 20
_BB_STD = 2.0
_ADX_PERIOD = 14
_MIN_CANDLES = max(_BB_WINDOW, _MACD_SLOW, _ADX_PERIOD, _EMA_SLOW) + 10


# ── Indicator helpers ─────────────────────────────────────────────────────────

def _rsi(close: pd.Series) -> pd.Series:
    return ta.RSI(close, timeperiod=_RSI_PERIOD)


def _ema(close: pd.Series, period: int) -> pd.Series:
    return ta.EMA(close, timeperiod=period)


def _macd(close: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    line, signal, hist = ta.MACD(
        close, fastperiod=_MACD_FAST, slowperiod=_MACD_SLOW, signalperiod=_MACD_SIG
    )
    return line, signal, hist


def _bollinger(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mid = tp.rolling(_BB_WINDOW).mean()
    std = tp.rolling(_BB_WINDOW).std(ddof=0)
    return mid + _BB_STD * std, mid, mid - _BB_STD * std


def _adx(df: pd.DataFrame) -> pd.Series:
    # talib.abstract ADX expects a DataFrame with high/low/close columns
    return ta.ADX(df, timeperiod=_ADX_PERIOD)


# ── Signal scorer ─────────────────────────────────────────────────────────────

def _score_asset(df: pd.DataFrame) -> dict:
    """
    Run five indicators and combine their votes into a direction (+1 call /
    -1 put / 0 neutral) and a confidence value in [0, 100].
    """
    if len(df) < _MIN_CANDLES:
        return {"direction": 0, "confidence": 0.0, "rsi": float("nan"),
                "adx": float("nan"), "signals": {}}

    close = df["close"]

    rsi_s = _rsi(close)
    ema_f = _ema(close, _EMA_FAST)
    ema_s = _ema(close, _EMA_SLOW)
    _, _, macd_hist = _macd(close)
    bb_up, _, bb_lo = _bollinger(df)
    adx_s = _adx(df)

    rsi_v = rsi_s.iloc[-1]
    ema_fv, ema_sv = ema_f.iloc[-1], ema_s.iloc[-1]
    prev_ema_fv, prev_ema_sv = ema_f.iloc[-2], ema_s.iloc[-2]
    hist_v, prev_hist_v = macd_hist.iloc[-1], macd_hist.iloc[-2]
    close_v = close.iloc[-1]
    bb_up_v, bb_lo_v = bb_up.iloc[-1], bb_lo.iloc[-1]
    adx_v = adx_s.iloc[-1]

    signals: Dict[str, int] = {}

    # RSI oversold / overbought
    if not math.isnan(rsi_v):
        if rsi_v < 30:
            signals["rsi"] = 1
        elif rsi_v > 70:
            signals["rsi"] = -1
        else:
            signals["rsi"] = 0

    # EMA cross direction (current alignment, with cross bonus)
    if not (math.isnan(ema_fv) or math.isnan(ema_sv)):
        crossed_up = prev_ema_fv <= prev_ema_sv and ema_fv > ema_sv
        crossed_dn = prev_ema_fv >= prev_ema_sv and ema_fv < ema_sv
        if crossed_up:
            signals["ema"] = 1
        elif crossed_dn:
            signals["ema"] = -1
        else:
            signals["ema"] = 1 if ema_fv > ema_sv else -1 if ema_fv < ema_sv else 0

    # MACD histogram momentum
    if not (math.isnan(hist_v) or math.isnan(prev_hist_v)):
        if hist_v > 0 and hist_v > prev_hist_v:
            signals["macd"] = 1
        elif hist_v < 0 and hist_v < prev_hist_v:
            signals["macd"] = -1
        else:
            signals["macd"] = 0

    # Bollinger Band breakout
    if not (math.isnan(bb_up_v) or math.isnan(bb_lo_v)):
        if close_v < bb_lo_v:
            signals["bb"] = 1
        elif close_v > bb_up_v:
            signals["bb"] = -1
        else:
            signals["bb"] = 0

    # ADX trend strength gates the EMA direction
    if not math.isnan(adx_v) and adx_v >= 25:
        signals["adx"] = 1 if ema_fv > ema_sv else -1 if ema_fv < ema_sv else 0
    elif not math.isnan(adx_v):
        signals["adx"] = 0

    if not signals:
        return {"direction": 0, "confidence": 0.0, "rsi": rsi_v,
                "adx": adx_v, "signals": signals}

    bullish = sum(1 for v in signals.values() if v == 1)
    bearish = sum(1 for v in signals.values() if v == -1)
    total = len(signals)

    if bullish > bearish:
        direction = 1
        agreement = bullish / total
    elif bearish > bullish:
        direction = -1
        agreement = bearish / total
    else:
        direction = 0
        agreement = 0.0

    adx_weight = min(adx_v / 50.0, 1.0) if not math.isnan(adx_v) else 0.5
    confidence = round(agreement * 70 + adx_weight * 30, 1)

    return {
        "direction": direction,
        "confidence": confidence,
        "rsi": round(rsi_v, 1) if not math.isnan(rsi_v) else float("nan"),
        "adx": round(adx_v, 1) if not math.isnan(adx_v) else float("nan"),
        "signals": signals,
    }


# ── Data helpers ──────────────────────────────────────────────────────────────

def _build_ohlc(history: list, period: int) -> pd.DataFrame:
    """Convert raw tick history to an OHLC DataFrame resampled to `period` seconds."""
    df = pd.DataFrame(history).sort_values("time").reset_index(drop=True)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    ohlc = df["price"].resample(f"{period}s").ohlc()
    ohlc.dropna(inplace=True)
    ohlc.reset_index(inplace=True)
    return ohlc


def _parse_payouts(raw: str, min_payout: int, scan_types: Tuple[str, ...]) -> dict:
    """Return {symbol: {payout, type, id}} after applying payout and type filters."""
    pairs: dict = {}
    try:
        for p in json.loads(raw):
            if len(p) < 19:
                continue
            symbol: str = p[1]
            active: bool = p[14]
            payout: int = p[5]
            asset_type: str = p[3]
            asset_id: int = p[0]

            if not active or payout < min_payout:
                continue
            if scan_types and not any(t in symbol for t in scan_types):
                continue

            pairs[symbol] = {"payout": payout, "type": asset_type, "id": asset_id}
    except Exception as exc:
        global_value.logger(f"Error parsing payout data: {exc}", "ERROR")
    return pairs


# ── Report renderer ───────────────────────────────────────────────────────────

_ARROW = {1: "↑", -1: "↓", 0: "-"}
_DIR_LABEL = {1: "CALL", -1: "PUT ", 0: "  --"}
_WIDTH = 84


def _render_report(results: List[dict], min_payout: int, period: int) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * _WIDTH)
    print(
        f"  PREGAME REPORT  |  {now}"
        f"  |  Period: {period}s  |  Min payout: {min_payout}%"
    )
    print("=" * _WIDTH)

    if not results:
        print("  No assets passed the filters.")
        print("=" * _WIDTH)
        return

    print(
        f"  {'ASSET':<22} {'PAYOUT':>7} {'DIR':>5} {'CONF%':>6}"
        f" {'RSI':>5} {'ADX':>5}  SIGNALS"
    )
    print("-" * _WIDTH)

    for r in results:
        dir_label = _DIR_LABEL[r["direction"]]
        rsi_str = f"{r['rsi']:5.1f}" if not math.isnan(r["rsi"]) else "  n/a"
        adx_str = f"{r['adx']:5.1f}" if not math.isnan(r["adx"]) else "  n/a"
        sig_str = " ".join(
            f"{k[:3].upper()}{_ARROW[v]}" for k, v in r.get("signals", {}).items()
        )
        print(
            f"  {r['symbol']:<22} {r['payout']:>6}%  {dir_label} {r['confidence']:>6.1f}"
            f" {rsi_str} {adx_str}  {sig_str}"
        )

    print("=" * _WIDTH)

    top_calls = [r for r in results if r["direction"] == 1][:3]
    top_puts = [r for r in results if r["direction"] == -1][:3]

    if top_calls:
        labels = ", ".join(
            f"{r['symbol']} ({r['payout']}%, {r['confidence']}% conf)" for r in top_calls
        )
        print(f"  TOP CALL SETUPS:  {labels}")
    if top_puts:
        labels = ", ".join(
            f"{r['symbol']} ({r['payout']}%, {r['confidence']}% conf)" for r in top_puts
        )
        print(f"  TOP PUT  SETUPS:  {labels}")

    print("=" * _WIDTH)


# ── Public API ────────────────────────────────────────────────────────────────

def run(
    ssid: str,
    demo: bool = True,
    min_payout: int = MIN_PAYOUT,
    period: int = CANDLE_PERIOD,
    top_n: int = TOP_N,
    scan_types: Tuple[str, ...] = SCAN_TYPES,
    save_json: Optional[str] = None,
    connect_timeout: int = 30,
) -> List[dict]:
    """
    Run the pregame scanner.

    Parameters
    ----------
    ssid            PocketOption auth string
    demo            True = demo account, False = real money
    min_payout      Minimum payout percentage to include an asset (default 80)
    period          Candle size in seconds (default 60)
    top_n           Number of assets shown in the printed report (default 10)
    scan_types      Tuple of symbol substrings to include, e.g. ("_otc",)
    save_json       Optional path; if set, the full ranked list is saved as JSON
    connect_timeout Seconds to wait for the WebSocket before giving up

    Returns
    -------
    List of scored asset dicts sorted by confidence descending (directional
    assets first, neutral assets last).
    """
    global_value.loglevel = "INFO"

    api = PocketOption(ssid, demo)
    api.connect()

    global_value.logger("Waiting for WebSocket...", "INFO")
    deadline = time.time() + connect_timeout
    while not global_value.websocket_is_connected:
        if time.time() > deadline:
            global_value.logger("WebSocket connection timed out.", "ERROR")
            return []
        time.sleep(0.2)
    time.sleep(2)

    balance = api.get_balance()
    global_value.logger(f"Balance: {balance}", "INFO")

    global_value.logger("Waiting for payout data...", "INFO")
    deadline = time.time() + 20
    while global_value.PayoutData is None:
        if time.time() > deadline:
            global_value.logger("Timed out waiting for payout data.", "ERROR")
            return []
        time.sleep(0.2)

    qualifying = _parse_payouts(global_value.PayoutData, min_payout, scan_types)
    global_value.logger(f"Qualifying assets: {len(qualifying)}", "INFO")

    if not qualifying:
        global_value.logger(
            "No assets match the filters. Try lowering min_payout or adjusting scan_types.",
            "INFO",
        )
        return []

    global_value.pairs = qualifying

    results: List[dict] = []
    total = len(qualifying)

    for idx, (symbol, meta) in enumerate(qualifying.items(), 1):
        global_value.logger(f"Scanning {symbol} ({idx}/{total})...", "INFO")
        ok = api.get_candles(symbol, period)
        time.sleep(0.5)

        history = global_value.pairs.get(symbol, {}).get("history")
        if not ok or not history or len(history) < _MIN_CANDLES * 3:
            global_value.logger(f"Skipping {symbol}: insufficient data.", "INFO")
            continue

        ohlc = _build_ohlc(history, period)
        if len(ohlc) < _MIN_CANDLES:
            global_value.logger(f"Skipping {symbol}: too few candles after resample.", "INFO")
            continue

        score = _score_asset(ohlc)
        results.append({"symbol": symbol, "payout": meta["payout"], **score})

    # Sort: directional assets first, then by confidence descending
    results.sort(key=lambda r: (-abs(r["direction"]), -r["confidence"]))

    top = results[:top_n]
    _render_report(top, min_payout, period)

    if save_json:
        with open(save_json, "w") as fh:
            json.dump(results, fh, indent=2, default=str)
        global_value.logger(f"Full results saved to {save_json}", "INFO")

    return results


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Replace with your actual SSID before running
    _ssid = """42["auth",{"session":"your_session_here","isDemo":1,"uid":0,"platform":2}]"""
    _demo = True

    run(ssid=_ssid, demo=_demo)
