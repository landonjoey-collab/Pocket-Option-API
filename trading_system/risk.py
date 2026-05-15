"""Position sizing, martingale, and daily drawdown guard."""
import csv
import os
import threading
from datetime import date, datetime
from trading_system import config
from trading_system.logger import log


class RiskManager:
    def __init__(self, starting_balance: float):
        self._lock = threading.Lock()
        self.starting_balance = starting_balance
        self.current_balance = starting_balance
        self.session_start = date.today()

        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self._stake = config.BASE_STAKE

        self._init_trade_log()

    # ── public ──────────────────────────────────────────────────────────────

    def get_stake(self) -> float:
        with self._lock:
            return min(self._stake, config.MAX_STAKE)

    def record_result(self, pair: str, direction: str, stake: float, profit: float) -> None:
        with self._lock:
            self.current_balance += profit
            self.daily_pnl += profit

            if profit > 0:
                self.consecutive_losses = 0
                self._stake = config.BASE_STAKE
                outcome = "win"
            else:
                self.consecutive_losses += 1
                self._stake = min(self._stake * config.MARTINGALE_FACTOR, config.MAX_STAKE)
                outcome = "loss"

            log.info(
                "[%s] %s %s stake=%.2f profit=%.2f | balance=%.2f losses=%d",
                outcome.upper(), pair, direction, stake, profit,
                self.current_balance, self.consecutive_losses,
            )
            self._write_trade(pair, direction, stake, profit, outcome)

    def trading_allowed(self) -> bool:
        with self._lock:
            if self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
                log.warning("Max consecutive losses reached (%d). Pausing.", self.consecutive_losses)
                return False

            drawdown_pct = abs(self.daily_pnl) / self.starting_balance * 100
            if self.daily_pnl < 0 and drawdown_pct >= config.MAX_DAILY_LOSS_PCT:
                log.warning("Daily loss limit hit (%.1f%%). Halting until next session.", drawdown_pct)
                return False

            return True

    def reset_if_new_day(self) -> None:
        with self._lock:
            today = date.today()
            if today != self.session_start:
                log.info("New trading day. Resetting daily stats.")
                self.session_start = today
                self.daily_pnl = 0.0
                self.consecutive_losses = 0
                self._stake = config.BASE_STAKE

    def update_balance(self, balance: float) -> None:
        with self._lock:
            self.current_balance = balance

    # ── private ─────────────────────────────────────────────────────────────

    def _init_trade_log(self) -> None:
        if not os.path.exists(config.TRADE_LOG_FILE):
            with open(config.TRADE_LOG_FILE, "w", newline="") as f:
                csv.writer(f).writerow(
                    ["timestamp", "pair", "direction", "stake", "profit", "outcome"]
                )

    def _write_trade(self, pair, direction, stake, profit, outcome) -> None:
        with open(config.TRADE_LOG_FILE, "a", newline="") as f:
            csv.writer(f).writerow(
                [datetime.now().isoformat(), pair, direction, stake, profit, outcome]
            )
