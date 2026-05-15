"""Candle aggregation and pair management."""
import json
import time
import threading
from datetime import datetime
from collections import defaultdict

import pandas as pd

import pocketoptionapi.global_value as global_value
from trading_system import config
from trading_system.logger import log


class MarketData:
    """Wraps the Pocket Option API and maintains per-pair OHLC DataFrames."""

    def __init__(self, api):
        self._api = api
        self._lock = threading.Lock()
        self._frames: dict[str, pd.DataFrame] = {}
        self._pairs: dict[str, dict] = {}

    # ── pair discovery ───────────────────────────────────────────────────────

    def refresh_pairs(self) -> bool:
        try:
            raw = global_value.PayoutData
            if raw is None:
                return False
            data = json.loads(raw)
        except Exception as e:
            log.error("refresh_pairs parse error: %s", e)
            return False

        pairs: dict[str, dict] = {}
        for pair in data:
            if len(pair) < 19:
                continue
            active = pair[14]
            payout = pair[5]
            symbol = pair[1]
            if active and payout >= config.MIN_PAYOUT and "_otc" in symbol:
                pairs[symbol] = {"id": pair[0], "payout": payout, "type": pair[3]}

        with self._lock:
            self._pairs = pairs

        log.info("Tradeable pairs found: %d", len(pairs))
        return bool(pairs)

    def get_pairs(self) -> list[str]:
        with self._lock:
            return list(self._pairs.keys())

    # ── candle fetching ──────────────────────────────────────────────────────

    def load_candles(self, symbol: str) -> bool:
        try:
            ok = self._api.get_candles(symbol, config.CANDLE_PERIOD)
            if ok and symbol in global_value.pairs and "history" in global_value.pairs[symbol]:
                df = self._build_df(global_value.pairs[symbol]["history"])
                if df is not None and len(df) > 5:
                    with self._lock:
                        self._frames[symbol] = df
                    return True
        except Exception as e:
            log.error("load_candles %s: %s", symbol, e)
        return False

    def get_df(self, symbol: str) -> pd.DataFrame | None:
        with self._lock:
            return self._frames.get(symbol)

    def append_live_candle(self, symbol: str, history: list) -> None:
        """Extend an existing frame with fresh tick history."""
        with self._lock:
            existing = self._frames.get(symbol)
        new_df = self._build_df(history, existing)
        if new_df is not None:
            with self._lock:
                self._frames[symbol] = new_df

    # ── helpers ──────────────────────────────────────────────────────────────

    def _build_df(self, history: list, existing: pd.DataFrame | None = None) -> pd.DataFrame | None:
        try:
            df1 = pd.DataFrame(history).reset_index(drop=True)
            df1 = df1.sort_values("time").reset_index(drop=True)
            df1["time"] = pd.to_datetime(df1["time"], unit="s")
            df1.set_index("time", inplace=True)
            df = df1["price"].resample(f"{config.CANDLE_PERIOD}s").ohlc()
            df.reset_index(inplace=True)
            df = df.loc[df["time"] < datetime.fromtimestamp(self._next_bar_ts())]

            if existing is not None:
                ts = datetime.timestamp(df.iloc[0]["time"])
                old = existing[
                    existing["time"].apply(datetime.timestamp) < ts
                ]
                df = pd.concat([old, df], ignore_index=True)
                df.sort_values("time", inplace=True)
                df.reset_index(drop=True, inplace=True)

            return df
        except Exception as e:
            log.debug("_build_df error: %s", e)
            return None

    def _next_bar_ts(self) -> int:
        p = config.CANDLE_PERIOD
        now = int(datetime.now().timestamp())
        sec = datetime.now().second

        if p == 60:
            return (now - sec) + 60
        if p == 30:
            base = now - sec
            return base + (30 if sec < 30 else 60)
        if p == 15:
            slot = (sec // 15) * 15
            return (now - sec) + slot + 15
        return ((now // p) + 1) * p
