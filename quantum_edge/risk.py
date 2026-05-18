"""
Position sizing + drawdown guard.
ATR-based stop/take-profit levels; per-pair cooldown after losses.
"""
import time
from datetime import date
from quantum_edge import config
from quantum_edge.logger import log
from quantum_edge.indicators import atr
import pandas as pd


class RiskManager:
    def __init__(self, balance: float):
        self.balance = balance
        self._session_balance = balance
        self._session_date = date.today()
        self._daily_pnl = 0.0
        self._consecutive_losses = 0
        self._cooldowns: dict[str, float] = {}

    # ── public ───────────────────────────────────────────────────────────────

    def refresh_balance(self, balance: float) -> None:
        self.balance = balance

    def reset_if_new_day(self) -> None:
        today = date.today()
        if today != self._session_date:
            log.info("New day — resetting daily P&L and loss counter.")
            self._session_date = today
            self._session_balance = self.balance
            self._daily_pnl = 0.0
            self._consecutive_losses = 0

    def trading_allowed(self) -> bool:
        if self._consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            log.warning("Max consecutive losses (%d). Trading paused.", self._consecutive_losses)
            return False
        if self._daily_pnl < 0:
            dd = abs(self._daily_pnl) / max(self._session_balance, 1) * 100
            if dd >= config.MAX_DAILY_LOSS_PCT:
                log.warning("Daily drawdown %.1f%% >= limit %.1f%%. Halted.", dd, config.MAX_DAILY_LOSS_PCT)
                return False
        return True

    def pair_allowed(self, symbol: str) -> bool:
        cd = self._cooldowns.get(symbol, 0)
        return time.time() >= cd

    def size_position(
        self, symbol: str, entry: float, df: pd.DataFrame, crash_severity: float = 0.0
    ) -> tuple[float, float, float]:
        """
        Returns (qty, sl_distance, tp_distance).
        Sizes to risk ACCOUNT_RISK_PCT% of balance per trade.
        During high crash severity, stake is reduced and stops widened
        to account for extreme volatility.
        """
        a = atr(df, config.ATR_PERIOD).iat[-1]
        if a <= 0:
            return 0.0, 0.0, 0.0

        # In a crash, volatility spikes — widen stops, reduce size
        vol_scalar = 1.0 + crash_severity          # e.g. severity=0.6 → 1.6× wider stops
        risk_scalar = 1.0 - crash_severity * 0.5   # e.g. severity=0.6 → 0.7× smaller stake

        risk_amount = self.balance * config.ACCOUNT_RISK_PCT / 100 * risk_scalar
        sl_distance = a * config.ATR_SL_MULTIPLIER * vol_scalar
        tp_distance = a * config.ATR_TP_MULTIPLIER * vol_scalar

        qty = risk_amount / sl_distance

        return qty, sl_distance, tp_distance

    def record_result(self, symbol: str, pnl: float) -> None:
        self._daily_pnl += pnl
        self.balance += pnl
        if pnl < 0:
            self._consecutive_losses += 1
            self._cooldowns[symbol] = time.time() + config.COOLDOWN_AFTER_LOSS
            log.warning("[LOSS] %s pnl=%.2f | streak=%d daily_pnl=%.2f",
                        symbol, pnl, self._consecutive_losses, self._daily_pnl)
        else:
            self._consecutive_losses = 0
            log.info("[WIN] %s pnl=%.2f | daily_pnl=%.2f", symbol, pnl, self._daily_pnl)

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses

    @property
    def daily_pnl_pct(self) -> float:
        base = max(self._session_balance, 1)
        return self._daily_pnl / base * 100
