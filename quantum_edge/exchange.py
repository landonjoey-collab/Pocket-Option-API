"""
Exchange adapter — wraps ccxt for Binance spot/futures.
Exposes a clean interface: fetch_ohlcv, get_balance, place_order, close_order.
"""
import time
import ccxt
import pandas as pd
from quantum_edge import config
from quantum_edge.logger import log


class Exchange:
    def __init__(self):
        params: dict = {
            "apiKey": config.API_KEY,
            "secret": config.API_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "future" if config.FUTURES_MODE else "spot"},
        }
        if config.USE_TESTNET:
            params["options"]["testnet"] = True
            params["urls"] = {
                "api": {
                    "public":  "https://testnet.binancefuture.com",
                    "private": "https://testnet.binancefuture.com",
                }
            } if config.FUTURES_MODE else {}

        self._ex: ccxt.Exchange = getattr(ccxt, config.EXCHANGE_ID)(params)
        if config.USE_TESTNET and config.FUTURES_MODE:
            self._ex.set_sandbox_mode(True)

        self._markets: dict = {}
        self._last_balance_ts: float = 0
        self._cached_balance: float = 0.0

    # ── connectivity ─────────────────────────────────────────────────────────

    def load_markets(self) -> bool:
        try:
            self._markets = self._ex.load_markets()
            log.info("Markets loaded: %d symbols", len(self._markets))
            return True
        except Exception as e:
            log.error("load_markets: %s", e)
            return False

    def ping(self) -> bool:
        try:
            self._ex.fetch_time()
            return True
        except Exception:
            return False

    # ── data ─────────────────────────────────────────────────────────────────

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame | None:
        try:
            raw = self._ex.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
            df["time"] = pd.to_datetime(df["ts"], unit="ms")
            df.set_index("time", inplace=True)
            df.drop(columns=["ts"], inplace=True)
            return df
        except Exception as e:
            log.debug("fetch_ohlcv %s %s: %s", symbol, timeframe, e)
            return None

    def get_ticker(self, symbol: str) -> dict | None:
        try:
            return self._ex.fetch_ticker(symbol)
        except Exception as e:
            log.debug("ticker %s: %s", symbol, e)
            return None

    # ── account ───────────────────────────────────────────────────────────────

    def get_balance(self, force: bool = False) -> float:
        now = time.time()
        if not force and now - self._last_balance_ts < config.BALANCE_REFRESH_S:
            return self._cached_balance
        try:
            bal = self._ex.fetch_balance()
            usdt = bal.get("USDT", {})
            free = float(usdt.get("free", 0))
            self._cached_balance = free
            self._last_balance_ts = now
            return free
        except Exception as e:
            log.error("get_balance: %s", e)
            return self._cached_balance

    # ── orders ────────────────────────────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int) -> None:
        if not config.FUTURES_MODE:
            return
        try:
            self._ex.set_leverage(leverage, symbol)
        except Exception as e:
            log.debug("set_leverage %s: %s", symbol, e)

    def place_market(self, symbol: str, side: str, qty: float) -> dict | None:
        """side: 'buy' or 'sell'"""
        try:
            order = self._ex.create_market_order(symbol, side, qty)
            log.info("Order placed: %s %s %s qty=%.6f id=%s",
                     side.upper(), symbol, order.get("status"), qty, order.get("id"))
            return order
        except Exception as e:
            log.error("place_market %s %s: %s", side, symbol, e)
            return None

    def place_limit(self, symbol: str, side: str, qty: float, price: float) -> dict | None:
        try:
            order = self._ex.create_limit_order(symbol, side, qty, price)
            return order
        except Exception as e:
            log.error("place_limit %s %s @ %.6f: %s", side, symbol, price, e)
            return None

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            self._ex.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            log.debug("cancel_order %s: %s", order_id, e)
            return False

    def fetch_order(self, order_id: str, symbol: str) -> dict | None:
        try:
            return self._ex.fetch_order(order_id, symbol)
        except Exception as e:
            log.debug("fetch_order %s: %s", order_id, e)
            return None

    def get_min_qty(self, symbol: str) -> float:
        try:
            m = self._markets.get(symbol, {})
            return float(m.get("limits", {}).get("amount", {}).get("min", 0.001))
        except Exception:
            return 0.001

    def get_price_precision(self, symbol: str) -> int:
        try:
            m = self._markets.get(symbol, {})
            return int(m.get("precision", {}).get("price", 2))
        except Exception:
            return 2

    def get_qty_precision(self, symbol: str) -> int:
        try:
            m = self._markets.get(symbol, {})
            return int(m.get("precision", {}).get("amount", 3))
        except Exception:
            return 3
