"""
Open position tracker + trade journal.
"""
import csv
import os
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from quantum_edge import config
from quantum_edge.logger import log


@dataclass
class Position:
    symbol: str
    side: str                    # "long" | "short"
    entry_price: float
    qty: float
    sl: float                    # absolute stop-loss price
    tp: float                    # absolute take-profit price
    order_id: str
    open_ts: float = field(default_factory=time.time)
    candles_held: int = 0
    unrealized_pnl: float = 0.0
    strategies: dict = field(default_factory=dict)
    _last_candle_ts: object = field(default=None, repr=False, compare=False)


class Portfolio:
    def __init__(self):
        self._lock = threading.Lock()
        self._positions: dict[str, Position] = {}
        self._closed: list[dict] = []
        self._init_csv()

    # ── positions ─────────────────────────────────────────────────────────────

    def open(self, pos: Position) -> None:
        with self._lock:
            self._positions[pos.symbol] = pos
        log.info("OPENED %s %s entry=%.6f sl=%.6f tp=%.6f qty=%.6f",
                 pos.side.upper(), pos.symbol, pos.entry_price, pos.sl, pos.tp, pos.qty)

    def close(self, symbol: str, exit_price: float, reason: str = "") -> float | None:
        with self._lock:
            pos = self._positions.pop(symbol, None)
        if pos is None:
            return None
        mult = 1 if pos.side == "long" else -1
        pnl = mult * (exit_price - pos.entry_price) * pos.qty
        log.info("CLOSED %s %s exit=%.6f pnl=%.2f reason=%s",
                 pos.side.upper(), symbol, exit_price, pnl, reason)
        self._record(pos, exit_price, pnl, reason)
        return pnl

    def get(self, symbol: str) -> Position | None:
        with self._lock:
            return self._positions.get(symbol)

    def has(self, symbol: str) -> bool:
        with self._lock:
            return symbol in self._positions

    def all_positions(self) -> list[Position]:
        with self._lock:
            return list(self._positions.values())

    def count(self) -> int:
        with self._lock:
            return len(self._positions)

    def update_unrealized(self, symbol: str, current_price: float, candle_ts=None) -> None:
        with self._lock:
            pos = self._positions.get(symbol)
            if pos:
                mult = 1 if pos.side == "long" else -1
                pos.unrealized_pnl = mult * (current_price - pos.entry_price) * pos.qty
                if candle_ts is not None:
                    if candle_ts != pos._last_candle_ts:
                        pos.candles_held += 1
                        pos._last_candle_ts = candle_ts
                else:
                    pos.candles_held += 1

    def recent_trades(self, n: int = 20) -> list[dict]:
        with self._lock:
            return list(self._closed[-n:])

    # ── private ───────────────────────────────────────────────────────────────

    def _init_csv(self) -> None:
        if not os.path.exists(config.TRADE_CSV):
            with open(config.TRADE_CSV, "w", newline="") as f:
                csv.writer(f).writerow(
                    ["timestamp", "symbol", "side", "entry", "exit",
                     "qty", "pnl", "reason", "held_candles"]
                )

    def _record(self, pos: Position, exit_price: float, pnl: float, reason: str) -> None:
        row = {
            "timestamp": datetime.now().isoformat(),
            "symbol": pos.symbol,
            "side": pos.side,
            "entry": pos.entry_price,
            "exit": exit_price,
            "qty": pos.qty,
            "pnl": round(pnl, 4),
            "reason": reason,
            "held_candles": pos.candles_held,
        }
        self._closed.append(row)
        with open(config.TRADE_CSV, "a", newline="") as f:
            csv.writer(f).writerow(row.values())
