"""
Main event loop — never sleeps.

Lifecycle:
  1. Connect to exchange, load markets.
  2. Start dashboard thread.
  3. Every SCAN_INTERVAL seconds:
     a. Refresh prices → update dashboard.
     b. Check open positions for SL/TP/timeout exits.
     c. Run ensemble strategy on each symbol → open new trades.
  4. Auto-reconnect on any exchange error.
"""
import time
import threading
from quantum_edge import config
from quantum_edge.logger import log
from quantum_edge.exchange import Exchange
from quantum_edge.risk import RiskManager
from quantum_edge.portfolio import Portfolio, Position
from quantum_edge.dashboard import Dashboard
from quantum_edge.strategies.ensemble import get_signal


class Engine:
    def __init__(self):
        self._ex = Exchange()
        self._risk: RiskManager | None = None
        self._port = Portfolio()
        self._dash = Dashboard()
        self._running = threading.Event()
        self._running.set()
        self._data_1m: dict = {}
        self._data_5m: dict = {}

    # ── entry ─────────────────────────────────────────────────────────────────

    def run(self) -> None:
        log.info("=== Quantum Edge Pro starting ===")
        self._dash.start()
        self._dash.set_status("STARTING")

        while self._running.is_set():
            try:
                if self._connect():
                    self._main_loop()
            except KeyboardInterrupt:
                log.info("Stopped by user.")
                self._running.clear()
                break
            except Exception as e:
                log.error("Engine error: %s — restarting in %ds", e, config.RECONNECT_DELAY)
                self._dash.set_status("RECONNECTING")
                self._interruptible_sleep(config.RECONNECT_DELAY)

        self._dash.stop()
        log.info("Engine stopped.")

    def stop(self) -> None:
        self._running.clear()

    # ── connection ────────────────────────────────────────────────────────────

    def _connect(self) -> bool:
        attempts = 0
        while self._running.is_set():
            attempts += 1
            self._dash.set_status("RECONNECTING")
            log.info("Connecting to %s (attempt %d)…", config.EXCHANGE_ID, attempts)
            if self._ex.load_markets() and self._ex.ping():
                log.info("Exchange connected.")
                return True
            delay = min(config.RECONNECT_DELAY * 2 ** min(attempts - 1, 4), 120)
            log.warning("Connect failed. Retry in %.0fs…", delay)
            self._interruptible_sleep(delay)
            if attempts >= config.MAX_RECONNECT:
                log.error("Max reconnect attempts. Giving up.")
                return False
        return False

    # ── main loop ─────────────────────────────────────────────────────────────

    def _main_loop(self) -> None:
        balance = self._ex.get_balance(force=True)
        log.info("Account balance: %.2f USDT", balance)
        self._risk = RiskManager(balance)
        self._dash.bind(self._port, self._risk, config.EXCHANGE_ID.upper())
        self._dash.set_status("RUNNING")

        # Set leverage for each symbol upfront
        if config.FUTURES_MODE:
            for sym in config.SYMBOLS:
                self._ex.set_leverage(sym, config.LEVERAGE)

        log.info("=== Trading loop started | %d symbols ===", len(config.SYMBOLS))
        while self._running.is_set():
            loop_start = time.monotonic()

            try:
                self._risk.reset_if_new_day()
                balance = self._ex.get_balance()
                if balance:
                    self._risk.refresh_balance(balance)

                self._refresh_market_data()
                self._manage_positions()

                if self._risk.trading_allowed():
                    self._dash.set_status("RUNNING")
                    self._scan_for_entries()
                else:
                    self._dash.set_status("PAUSED")

            except Exception as e:
                log.error("Loop iteration error: %s", e)
                if not self._ex.ping():
                    log.warning("Exchange unreachable — triggering reconnect.")
                    break

            elapsed = time.monotonic() - loop_start
            sleep_for = max(0, config.SCAN_INTERVAL - elapsed)
            self._interruptible_sleep(sleep_for)

    # ── market data ───────────────────────────────────────────────────────────

    def _refresh_market_data(self) -> None:
        for sym in config.SYMBOLS:
            try:
                df1 = self._ex.fetch_ohlcv(sym, config.PRIMARY_TF, config.CANDLES_FAST)
                if df1 is not None and len(df1) >= 50:
                    self._data_1m[sym] = df1

                df5 = self._ex.fetch_ohlcv(sym, config.CONFIRM_TF, config.CANDLES_SLOW)
                if df5 is not None:
                    self._data_5m[sym] = df5

                ticker = self._ex.get_ticker(sym)
                if ticker:
                    self._dash.update_price(sym, ticker["last"], ticker.get("percentage", 0))

            except Exception as e:
                log.debug("data refresh %s: %s", sym, e)

    # ── position management ───────────────────────────────────────────────────

    def _manage_positions(self) -> None:
        for pos in self._port.all_positions():
            sym = pos.symbol
            df = self._data_1m.get(sym)
            if df is None:
                continue

            current = df["close"].iat[-1]
            self._port.update_unrealized(sym, current)

            # Stop-loss check
            if pos.side == "long" and current <= pos.sl:
                self._close_position(pos, current, "stop_loss")
                continue
            if pos.side == "short" and current >= pos.sl:
                self._close_position(pos, current, "stop_loss")
                continue

            # Take-profit check
            if pos.side == "long" and current >= pos.tp:
                self._close_position(pos, current, "take_profit")
                continue
            if pos.side == "short" and current <= pos.tp:
                self._close_position(pos, current, "take_profit")
                continue

            # Max hold time
            if pos.candles_held >= config.MAX_HOLD_CANDLES:
                self._close_position(pos, current, "timeout")

    def _close_position(self, pos, price: float, reason: str) -> None:
        close_side = "sell" if pos.side == "long" else "buy"
        self._ex.place_market(pos.symbol, close_side, pos.qty)
        pnl = self._port.close(pos.symbol, price, reason)
        if pnl is not None:
            self._risk.record_result(pos.symbol, pnl)
            self._dash.add_log(
                f"CLOSED {pos.side.upper()} {pos.symbol} @ {price:.4f}  "
                f"PnL=${pnl:+.2f}  [{reason}]"
            )

    # ── entry scanning ────────────────────────────────────────────────────────

    def _scan_for_entries(self) -> None:
        if self._port.count() >= config.MAX_OPEN_POSITIONS:
            return

        for sym in config.SYMBOLS:
            if self._port.has(sym):
                continue
            if not self._risk.pair_allowed(sym):
                continue
            if self._port.count() >= config.MAX_OPEN_POSITIONS:
                break

            df1 = self._data_1m.get(sym)
            if df1 is None or len(df1) < 50:
                continue
            df5 = self._data_5m.get(sym)

            try:
                signal, breakdown = get_signal(df1, df5)
            except Exception as e:
                log.debug("signal %s: %s", sym, e)
                continue

            if signal == 0:
                continue

            self._open_position(sym, signal, df1, breakdown)

    def _open_position(self, sym: str, signal: int, df, breakdown: dict) -> None:
        current = df["close"].iat[-1]
        qty, sl_dist, tp_dist = self._risk.size_position(sym, current, df)

        min_qty = self._ex.get_min_qty(sym)
        if qty < min_qty:
            log.debug("qty %.6f below min %.6f for %s — skipping", qty, min_qty, sym)
            return

        side = "buy" if signal == 1 else "sell"
        pos_side = "long" if signal == 1 else "short"

        if signal == 1:
            sl_price = round(current - sl_dist, self._ex.get_price_precision(sym))
            tp_price = round(current + tp_dist, self._ex.get_price_precision(sym))
        else:
            sl_price = round(current + sl_dist, self._ex.get_price_precision(sym))
            tp_price = round(current - tp_dist, self._ex.get_price_precision(sym))

        order = self._ex.place_market(sym, side, qty)
        if order is None:
            return

        fill_price = order.get("average") or order.get("price") or current
        pos = Position(
            symbol=sym,
            side=pos_side,
            entry_price=fill_price,
            qty=qty,
            sl=sl_price,
            tp=tp_price,
            order_id=str(order.get("id", "")),
            strategies=breakdown,
        )
        self._port.open(pos)
        self._dash.add_log(
            f"OPENED {pos_side.upper()} {sym} @ {fill_price:.4f}  "
            f"SL={sl_price:.4f}  TP={tp_price:.4f}  "
            f"signals={breakdown}"
        )

    # ── util ─────────────────────────────────────────────────────────────────

    def _interruptible_sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while self._running.is_set() and time.monotonic() < end:
            time.sleep(min(0.5, end - time.monotonic()))
