"""Kalshi trade copier orchestrator.

Listens to the master account's `fill` websocket channel and mirrors each
executed trade to every follower account concurrently, sized per follower.

One master order can fill in several partial chunks, so fills are aggregated
per order_id for a short window (settings.aggregation_ms) and copied once,
with the total count. Without this, a 0.5x follower would see three
1-contract chunks as three skipped trades instead of one 2-contract copy.
"""

import asyncio
import os
import time

from kalshi_copier.auth import KalshiSigner
from kalshi_copier.rest import KalshiRestClient, KalshiApiError
from kalshi_copier.ws import KalshiFillListener

HALT_FILE = "KALSHI_HALT"
HALT_ENV = "KALSHI_COPIER_HALT"


def halt_reason():
    """Emergency kill switch: a KALSHI_HALT file in the working directory or
    KALSHI_COPIER_HALT=1 in the environment stops all copying immediately.
    Trip it with `python -m kalshi_copier --halt`."""
    if os.environ.get(HALT_ENV):
        return f"{HALT_ENV} is set in the environment"
    if os.path.exists(HALT_FILE):
        return f"{HALT_FILE} file present in {os.getcwd()}"
    return None


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"


class KalshiCopier:
    def __init__(self, config, dry_run=False):
        self.config = config
        self.forced_dry_run = not dry_run and not config.settings.enabled
        self.dry_run = dry_run or self.forced_dry_run
        self.paused_reason = None
        self.copied = 0
        self._pending = {}          # order_id -> aggregated fill dict
        self._day = self._today()
        self._day_notional = 0.0    # $ of master fills copied today

        s = config.settings
        master_signer = KalshiSigner.from_file(
            config.master.key_id, config.master.private_key_path)
        self.listener = KalshiFillListener(
            master_signer, environment=s.environment, ws_url=s.ws_url,
            on_fill=self._on_master_fill)
        self.followers = []
        for fcfg in config.followers:
            signer = KalshiSigner.from_file(fcfg.key_id, fcfg.private_key_path)
            client = KalshiRestClient(signer, environment=s.environment,
                                      api_base=s.api_base)
            self.followers.append((fcfg, client))

    # ------------------------------------------------------------------- run

    async def run(self):
        halted = halt_reason()
        if halted:
            self._log(f"{RED}TRADING HALTED{RESET} — {halted}; refusing to start. "
                      "Run `python -m kalshi_copier --resume` to clear the halt.")
            return
        self._banner()
        if self.dry_run:
            self._log(f"{YELLOW}DRY RUN{RESET} — master fills are only logged, "
                      "no follower orders will be placed")
            if self.forced_dry_run:
                self._log(f"{YELLOW}live copying is disabled{RESET} — set "
                          '"enabled": true under "settings" in the config '
                          "to place follower orders")
        else:
            for fcfg, client in self.followers:
                balance = await asyncio.to_thread(client.get_balance)
                self._log(f"  {GREEN}●{RESET} {fcfg.name}  size {fcfg.size_label()}  "
                          f"balance ${(balance or 0) / 100:,.2f}")

        self._log(f"connecting to {self.config.settings.environment} fill stream...")
        await self.listener.start()
        self._log(f"{GREEN}AUTO COPY active{RESET} — watching "
                  f"{self.config.master.name} ({len(self.followers)} follower(s))")
        try:
            while True:
                await asyncio.sleep(1)
                halted = halt_reason()
                if halted:
                    self._log(f"{RED}TRADING HALTED{RESET} — {halted}; "
                              "shutting down")
                    break
        except asyncio.CancelledError:
            pass
        finally:
            await self.listener.close()

    # ------------------------------------------------------------ fill intake

    async def _on_master_fill(self, fill):
        """Aggregate partial fills of the same master order, then copy once."""
        order_id = fill.get("order_id") or fill.get("trade_id")
        count = int(fill.get("count", 0) or 0)
        if order_id is None or count <= 0:
            return
        pending = self._pending.get(order_id)
        if pending:
            pending["count"] += count
            pending["last"] = fill
            return
        self._pending[order_id] = {"count": count, "last": fill}
        asyncio.get_running_loop().create_task(self._flush_later(order_id))

    async def _flush_later(self, order_id):
        await asyncio.sleep(self.config.settings.aggregation_ms / 1000)
        pending = self._pending.pop(order_id, None)
        if pending:
            await self._copy_trade(pending["last"], pending["count"])

    # ---------------------------------------------------------------- copying

    async def _copy_trade(self, fill, count):
        ticker = fill.get("market_ticker", "?")
        action = (fill.get("action") or "buy").lower()
        side = (fill.get("side") or "yes").lower()
        yes_price = fill.get("yes_price")
        price = yes_price if side == "yes" else fill.get("no_price")

        price_label = f"{price}¢" if isinstance(price, (int, float)) else "?"
        self._log(f"{CYAN}MASTER FILL{RESET}  {ticker}  "
                  f"{self._label(action, side)}  {count} @ {price_label}")

        self._roll_day()
        skip = self._skip_reason(ticker, action)
        if skip:
            self._log(f"{YELLOW}not copied:{RESET} {skip}")
            return
        notional = count * price / 100 if isinstance(price, (int, float)) else 0.0
        over_cap = self._reserve_notional(notional)
        if over_cap:
            self._log(f"{YELLOW}not copied:{RESET} {over_cap}")
            return

        if self.dry_run:
            for fcfg, _ in self.followers:
                n = fcfg.size_for(count)
                note = f"{n} contracts" if n else "skip (scales to 0)"
                self._log(f"  {DIM}would copy to {fcfg.name}: {note}{RESET}")
            return

        started = time.perf_counter()
        results = await asyncio.gather(
            *(self._copy_to(fcfg, client, ticker, action, side, count, price)
              for fcfg, client in self.followers),
            return_exceptions=True,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        ok = sum(1 for r in results if r is True)
        self.copied += 1
        self._log(f"copied to {ok}/{len(self.followers)} followers in {elapsed_ms:.0f} ms")

    async def _copy_to(self, fcfg, client, ticker, action, side, count, price):
        n = fcfg.size_for(count)
        if n < 1:
            self._log(f"  {DIM}– {fcfg.name}: scaled count is 0, skipped{RESET}")
            return False
        s = self.config.settings
        kwargs = {}
        order_type = s.order_type
        if order_type == "limit" and isinstance(price, (int, float)):
            # buys pay up to price+slippage; sells accept down to price-slippage
            buffer = s.limit_slippage_cents if action == "buy" else -s.limit_slippage_cents
            limit = max(1, min(99, int(price) + buffer))
            kwargs["yes_price" if side == "yes" else "no_price"] = limit
        else:
            order_type = "market"
        try:
            await asyncio.to_thread(
                client.place_order, ticker, action, side, n,
                order_type=order_type, **kwargs)
            self._log(f"  {GREEN}✓{RESET} {fcfg.name}  {n} contracts  "
                      f"({fcfg.size_label()})")
            return True
        except (KalshiApiError, OSError) as exc:
            self._log(f"  {RED}✗{RESET} {fcfg.name}  {n} contracts — {exc}")
            return False

    # ----------------------------------------------------------------- guards

    def _skip_reason(self, ticker, action):
        halted = halt_reason()
        if halted:
            return f"trading halted ({halted})"
        if self.paused_reason:
            return self.paused_reason
        s = self.config.settings
        if action == "sell" and not s.copy_sells:
            return "copy_sells is disabled"
        if s.tickers_allowlist and ticker not in s.tickers_allowlist:
            return f"{ticker} not in tickers_allowlist"
        if ticker in s.tickers_blocklist:
            return f"{ticker} is in tickers_blocklist"
        return None

    def _roll_day(self):
        """A new UTC day resets the budget and lifts a cap-induced pause."""
        today = self._today()
        if today != self._day:
            self._day = today
            self._day_notional = 0.0
            self.paused_reason = None

    def _reserve_notional(self, dollars):
        """Books `dollars` against today's cap, or returns why it can't.

        The check runs before any follower order is placed, so the trade that
        would breach the cap is skipped rather than filled in full and paused
        afterwards — otherwise one large master fill could overshoot the limit
        by any amount before the guard ever engaged.
        """
        limit = self.config.settings.daily_max_notional
        if limit is not None and self._day_notional + dollars > limit:
            self.paused_reason = (
                f"daily notional limit reached (${self._day_notional:,.2f} of "
                f"${limit:,.2f} used; this trade would add ${dollars:,.2f})")
            self._log(f"{YELLOW}COPYING PAUSED:{RESET} {self.paused_reason}")
            return self.paused_reason
        self._day_notional += dollars
        return None

    # ------------------------------------------------------------------- misc

    @staticmethod
    def _today():
        return time.strftime("%Y-%m-%d", time.gmtime())

    @staticmethod
    def _label(action, side):
        color = GREEN if action == "buy" else RED
        return f"{color}{action.upper()} {side.upper()}{RESET}"

    def _banner(self):
        s = self.config.settings
        env = s.environment.upper()
        print(f"\n{CYAN}╔══════════════════════════════════════════════╗{RESET}")
        print(f"{CYAN}║           KALSHI  TRADE  COPIER              ║{RESET}")
        print(f"{CYAN}╚══════════════════════════════════════════════╝{RESET}")
        print(f"  environment: {env}")
        print(f"  master:      {self.config.master.name}")
        for fcfg in self.config.followers:
            print(f"  follower:    {fcfg.name}  ({fcfg.size_label()})")
        cap = f"${s.daily_max_notional:g}" if s.daily_max_notional else "off"
        print(f"  orders: {s.order_type}   daily notional cap: {cap}\n")

    @staticmethod
    def _log(msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
