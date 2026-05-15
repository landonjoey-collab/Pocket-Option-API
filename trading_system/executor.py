"""Trade execution with result tracking."""
import threading
import time

import pocketoptionapi.global_value as global_value
from trading_system import config
from trading_system.logger import log
from trading_system.risk import RiskManager


class TradeExecutor:
    def __init__(self, api, risk: RiskManager):
        self._api = api
        self._risk = risk
        self._active_trades: dict[str, bool] = {}
        self._lock = threading.Lock()

    def is_trading(self, symbol: str) -> bool:
        with self._lock:
            return self._active_trades.get(symbol, False)

    def execute(self, symbol: str, direction: str) -> None:
        """Fire-and-forget trade in its own thread."""
        with self._lock:
            if self._active_trades.get(symbol):
                log.debug("Already in trade for %s, skipping.", symbol)
                return
            self._active_trades[symbol] = True

        t = threading.Thread(
            target=self._run_trade,
            args=(symbol, direction),
            daemon=True,
            name=f"trade-{symbol}",
        )
        t.start()

    def _run_trade(self, symbol: str, direction: str) -> None:
        stake = self._risk.get_stake()
        action = "call" if direction == "call" else "put"
        log.info("PLACING %s %s stake=%.2f exp=%ds", action.upper(), symbol, stake, config.EXPIRATION)
        try:
            result, order_id = self._api.buy(
                amount=stake,
                active=symbol,
                action=action,
                expirations=config.EXPIRATION,
            )
            if not result or order_id is None:
                log.warning("Order rejected for %s", symbol)
                return

            profit, status = self._api.check_win(order_id)
            profit = profit if profit is not None else -stake
            self._risk.record_result(symbol, direction, stake, profit)

        except Exception as e:
            log.error("Trade error %s: %s", symbol, e)
            self._risk.record_result(symbol, direction, stake, -stake)
        finally:
            with self._lock:
                self._active_trades[symbol] = False
