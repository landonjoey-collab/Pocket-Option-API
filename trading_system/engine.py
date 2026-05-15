"""
Core event loop — never sleeps.

Lifecycle:
  1. Connect (with auto-reconnect).
  2. Discover pairs + load initial candles.
  3. Every candle boundary: refresh candles → evaluate strategy → execute trades.
  4. Concurrent watchdog thread maintains heartbeat and refreshes balance.
"""
import time
import threading
import math
from datetime import datetime

import pocketoptionapi.global_value as global_value
from pocketoptionapi.stable_api import PocketOption

from trading_system import config
from trading_system.logger import log
from trading_system.market import MarketData
from trading_system.strategy import get_signal
from trading_system.risk import RiskManager
from trading_system.executor import TradeExecutor


class TradingEngine:
    def __init__(self):
        self._api: PocketOption | None = None
        self._market: MarketData | None = None
        self._risk: RiskManager | None = None
        self._executor: TradeExecutor | None = None
        self._running = threading.Event()
        self._running.set()

    # ── public entry point ───────────────────────────────────────────────────

    def run(self) -> None:
        log.info("=== Trading Engine starting ===")
        while self._running.is_set():
            try:
                if self._connect():
                    self._main_loop()
            except KeyboardInterrupt:
                log.info("Interrupted by user.")
                self._running.clear()
                break
            except Exception as e:
                log.error("Engine crashed: %s — restarting in %ds", e, config.RECONNECT_DELAY)
                time.sleep(config.RECONNECT_DELAY)

    def stop(self) -> None:
        self._running.clear()

    # ── connection ───────────────────────────────────────────────────────────

    def _connect(self) -> bool:
        attempts = 0
        while self._running.is_set():
            attempts += 1
            log.info("Connecting (attempt %d)…", attempts)
            try:
                self._api = PocketOption(config.SSID, config.DEMO)
                self._api.connect()
                deadline = time.time() + 20
                while time.time() < deadline:
                    if global_value.websocket_is_connected:
                        log.info("Connected.")
                        return True
                    time.sleep(0.2)
                log.warning("Connection timeout.")
            except Exception as e:
                log.error("Connect error: %s", e)

            delay = min(config.RECONNECT_DELAY * (2 ** min(attempts - 1, 4)), 120)
            log.info("Retrying in %.0fs…", delay)
            time.sleep(delay)
            if attempts >= config.MAX_RECONNECT:
                log.error("Max reconnect attempts reached.")
                return False
        return False

    # ── main loop ────────────────────────────────────────────────────────────

    def _main_loop(self) -> None:
        time.sleep(2)
        balance = self._api.get_balance() or 1000.0
        log.info("Balance: %.2f", balance)

        self._market = MarketData(self._api)
        self._risk = RiskManager(balance)
        self._executor = TradeExecutor(self._api, self._risk)

        if not self._market.refresh_pairs():
            log.error("No tradeable pairs found.")
            return

        self._load_all_candles()
        self._start_watchdog()

        log.info("=== Event loop running ===")
        while self._running.is_set():
            if not global_value.websocket_is_connected:
                log.warning("WebSocket dropped — reconnecting.")
                break

            self._risk.reset_if_new_day()
            sleep_s = self._seconds_to_next_bar()
            log.info("Next bar in %.1f s", sleep_s)
            self._interruptible_sleep(sleep_s)

            if not self._running.is_set():
                break

            self._refresh_candles()
            self._evaluate_and_trade()

    # ── candle management ────────────────────────────────────────────────────

    def _load_all_candles(self) -> None:
        pairs = self._market.get_pairs()
        log.info("Loading initial candles for %d pairs…", len(pairs))
        for i, sym in enumerate(pairs, 1):
            log.info("  [%d/%d] %s", i, len(pairs), sym)
            self._market.load_candles(sym)
            time.sleep(0.8)

    def _refresh_candles(self) -> None:
        for sym in self._market.get_pairs():
            try:
                if sym in global_value.pairs and "history" in global_value.pairs[sym]:
                    self._market.append_live_candle(sym, global_value.pairs[sym]["history"])
                else:
                    self._market.load_candles(sym)
            except Exception as e:
                log.debug("refresh %s: %s", sym, e)

    # ── strategy evaluation ──────────────────────────────────────────────────

    def _evaluate_and_trade(self) -> None:
        if not self._risk.trading_allowed():
            return

        pairs = self._market.get_pairs()
        signals_found = 0
        for sym in pairs:
            if self._executor.is_trading(sym):
                continue
            df = self._market.get_df(sym)
            if df is None or len(df) < 30:
                continue
            try:
                signal = get_signal(df)
            except Exception as e:
                log.debug("signal error %s: %s", sym, e)
                continue

            if signal == 1:
                self._executor.execute(sym, "call")
                signals_found += 1
            elif signal == -1:
                self._executor.execute(sym, "put")
                signals_found += 1

        if signals_found:
            log.info("Signals dispatched: %d", signals_found)
        else:
            log.info("No signals this bar.")

    # ── watchdog ─────────────────────────────────────────────────────────────

    def _start_watchdog(self) -> None:
        t = threading.Thread(target=self._watchdog, daemon=True, name="watchdog")
        t.start()

    def _watchdog(self) -> None:
        while self._running.is_set():
            try:
                bal = self._api.get_balance()
                if bal:
                    self._risk.update_balance(bal)
                    log.debug("Heartbeat — balance: %.2f", bal)
            except Exception as e:
                log.debug("Watchdog error: %s", e)
            time.sleep(config.HEARTBEAT_INTERVAL)

    # ── timing ───────────────────────────────────────────────────────────────

    def _seconds_to_next_bar(self) -> float:
        p = config.CANDLE_PERIOD
        now = datetime.now()
        ts = int(now.timestamp())
        sec = now.second

        if p == 60:
            return 60 - sec
        if p == 30:
            return 30 - sec if sec < 30 else 60 - sec
        if p == 15:
            rem = sec % 15
            return 15 - rem
        if p in (5, 10):
            rem = sec % p
            return p - rem
        if p in (120, 180, 300, 600):
            minutes = now.minute
            slot = (minutes // (p // 60)) * (p // 60)
            next_slot_min = slot + (p // 60)
            from datetime import datetime as dt
            next_bar = dt(now.year, now.month, now.day, now.hour, 0, 0)
            next_bar = next_bar.replace(minute=next_slot_min % 60)
            if next_slot_min >= 60:
                next_bar = next_bar.replace(hour=now.hour + 1, minute=next_slot_min % 60)
            return max((next_bar - now).total_seconds(), 1)
        return float(p)

    def _interruptible_sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while self._running.is_set() and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))
