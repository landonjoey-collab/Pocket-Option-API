"""Trade copier orchestrator: one master account, unlimited followers.

Listens to the master's websocket session for newly opened deals (works
whether the master trades manually in the browser or through a bot) and
mirrors each trade to every follower concurrently, sized per follower.
"""

import asyncio
import time

from trade_copier.account import PocketAccountClient, OrderError

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"


class TradeCopier:
    def __init__(self, config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.paused_reason = None
        self.master_pnl = 0.0        # realized PnL since the copier started
        self.copied = 0

        self.master = PocketAccountClient(
            name=config.master.name,
            ssid=config.master.ssid,
            demo=config.master.demo,
            on_deal_opened=self._on_master_deal,
            on_deal_closed=self._on_master_deal_closed,
        )
        self.followers = []
        for fcfg in config.followers:
            client = PocketAccountClient(name=fcfg.name, ssid=fcfg.ssid, demo=fcfg.demo)
            self.followers.append((fcfg, client))

    # ------------------------------------------------------------------- run

    async def run(self):
        self._banner()
        self._log(f"connecting master ({self.master.name})...")
        await self.master.start()

        if self.dry_run:
            self._log(f"{YELLOW}DRY RUN{RESET} — followers will not be connected, "
                      "master trades are only logged")
        else:
            await asyncio.gather(*(client.start() for _, client in self.followers))
            for fcfg, client in self.followers:
                bal = f"${client.balance:,.2f}" if client.balance is not None else "?"
                self._log(f"  {GREEN}●{RESET} {fcfg.name}  size {fcfg.size_label()}  "
                          f"balance {bal}")

        self._log(f"{GREEN}AUTO COPY active{RESET} — watching {self.master.name} "
                  f"for new trades ({len(self.followers)} follower(s))")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self):
        await asyncio.gather(
            self.master.close(),
            *(client.close() for _, client in self.followers),
            return_exceptions=True,
        )

    # ----------------------------------------------------------- master events

    async def _on_master_deal(self, deal):
        asset = deal.get("asset", "?")
        amount = float(deal.get("amount", 0) or 0)
        direction = self._direction_of(deal)
        duration = self._duration_of(deal)

        self._log(f"{CYAN}MASTER TRADE{RESET}  {asset}  "
                  f"{self._dir_label(direction)}  ${amount:g}  {duration}s")

        skip = self._skip_reason(asset, amount, direction)
        if skip:
            self._log(f"{YELLOW}not copied:{RESET} {skip}")
            return
        if self.dry_run:
            for fcfg, _ in self.followers:
                self._log(f"  {DIM}would copy to {fcfg.name}: "
                          f"${fcfg.size_for(amount):g}{RESET}")
            return

        started = time.perf_counter()
        results = await asyncio.gather(
            *(self._copy_to(fcfg, client, asset, amount, direction, duration)
              for fcfg, client in self.followers),
            return_exceptions=True,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        ok = sum(1 for r in results if r is True)
        self.copied += 1
        self._log(f"copied to {ok}/{len(self.followers)} followers "
                  f"in {elapsed_ms:.0f} ms")

    async def _copy_to(self, fcfg, client, asset, amount, direction, duration):
        size = fcfg.size_for(amount)
        try:
            await client.place_order(asset, size, direction, duration)
            self._log(f"  {GREEN}✓{RESET} {fcfg.name}  ${size:g}  ({fcfg.size_label()})")
            return True
        except OrderError as exc:
            self._log(f"  {RED}✗{RESET} {fcfg.name}  ${size:g}  — {exc}")
            return False

    async def _on_master_deal_closed(self, deal):
        profit = deal.get("profit")
        if profit is None:
            return
        self.master_pnl += float(profit)
        color = GREEN if profit >= 0 else RED
        self._log(f"master deal closed: {color}{profit:+.2f}{RESET}  "
                  f"(session PnL {self.master_pnl:+.2f})")
        self._check_risk_limits()

    # ----------------------------------------------------------------- guards

    def _check_risk_limits(self):
        s = self.config.settings
        if self.paused_reason:
            return
        if s.daily_goal is not None and self.master_pnl >= s.daily_goal:
            self.paused_reason = f"daily goal reached ({self.master_pnl:+.2f})"
        elif s.daily_loss is not None and self.master_pnl <= s.daily_loss:
            self.paused_reason = f"daily loss limit hit ({self.master_pnl:+.2f})"
        if self.paused_reason:
            self._log(f"{YELLOW}COPYING PAUSED:{RESET} {self.paused_reason}")

    def _skip_reason(self, asset, amount, direction):
        if self.paused_reason:
            return self.paused_reason
        if amount <= 0:
            return "master amount is zero/unknown"
        if direction not in ("call", "put"):
            return f"unknown direction in deal ({direction!r})"
        s = self.config.settings
        if s.assets_allowlist and asset not in s.assets_allowlist:
            return f"{asset} not in assets_allowlist"
        if asset in s.assets_blocklist:
            return f"{asset} is in assets_blocklist"
        return None

    # ---------------------------------------------------------------- parsing

    @staticmethod
    def _direction_of(deal):
        action = deal.get("action")
        if isinstance(action, str) and action.lower() in ("call", "put"):
            return action.lower()
        command = deal.get("command")
        if command in (0, "0"):
            return "call"
        if command in (1, "1"):
            return "put"
        return None

    def _duration_of(self, deal):
        s = self.config.settings
        if s.copy_expiration:
            opened = deal.get("openTimestamp") or deal.get("openTime")
            closed = deal.get("closeTimestamp") or deal.get("closeTime")
            if isinstance(opened, (int, float)) and isinstance(closed, (int, float)) \
                    and closed > opened:
                return max(int(closed - opened), s.min_expiration)
        return s.default_expiration

    # ------------------------------------------------------------------- misc

    @staticmethod
    def _dir_label(direction):
        if direction == "call":
            return f"{GREEN}▲ CALL{RESET}"
        if direction == "put":
            return f"{RED}▼ PUT{RESET}"
        return "?"

    def _banner(self):
        s = self.config.settings
        print(f"\n{CYAN}╔══════════════════════════════════════════════╗{RESET}")
        print(f"{CYAN}║        POCKET OPTION  TRADE COPIER           ║{RESET}")
        print(f"{CYAN}╚══════════════════════════════════════════════╝{RESET}")
        print(f"  master:    {self.config.master.name}")
        for fcfg in self.config.followers:
            print(f"  follower:  {fcfg.name}  ({fcfg.size_label()})")
        goal = f"+${s.daily_goal:g}" if s.daily_goal is not None else "off"
        loss = f"-${abs(s.daily_loss):g}" if s.daily_loss is not None else "off"
        print(f"  daily goal {goal}   daily loss {loss}\n")

    @staticmethod
    def _log(msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
