"""
Quantum Edge Pro — Configuration
All settings are overridable via environment variables.
"""
import os

# ── Exchange ─────────────────────────────────────────────────────────────────
EXCHANGE_ID      = os.environ.get("QE_EXCHANGE", "binance")
API_KEY          = os.environ.get("QE_API_KEY", "")
API_SECRET       = os.environ.get("QE_API_SECRET", "")
USE_TESTNET      = os.environ.get("QE_TESTNET", "1") == "1"   # 1 = paper, 0 = live
FUTURES_MODE     = os.environ.get("QE_FUTURES", "1") == "1"   # 1 = USDT-M futures

# ── Symbols to scan (USDT pairs) ─────────────────────────────────────────────
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
    "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
]

# ── Timeframes ────────────────────────────────────────────────────────────────
PRIMARY_TF   = "1m"    # main scalp timeframe
CONFIRM_TF   = "5m"    # trend confirmation (higher timeframe)
CANDLES_FAST = 200     # candles to fetch on primary
CANDLES_SLOW = 100     # candles to fetch on confirm

# ── Risk management ───────────────────────────────────────────────────────────
ACCOUNT_RISK_PCT     = 1.0    # max % of balance risked per trade
MAX_OPEN_POSITIONS   = 4      # concurrent positions cap
LEVERAGE             = 5      # futures leverage (1 = spot-equivalent)
ATR_SL_MULTIPLIER    = 1.5    # stop loss = 1.5 × ATR
ATR_TP_MULTIPLIER    = 3.0    # take profit = 3.0 × ATR  (2:1 R:R)
MAX_HOLD_CANDLES     = 30     # force-close after 30 primary-TF candles

# ── Martingale / drawdown guard ───────────────────────────────────────────────
MAX_CONSECUTIVE_LOSSES = 5
MAX_DAILY_LOSS_PCT     = 8.0
COOLDOWN_AFTER_LOSS    = 60   # seconds to wait per pair after a loss

# ── Strategy weights (must sum to 1) ─────────────────────────────────────────
STRATEGY_WEIGHTS = {
    "trend":     0.40,
    "momentum":  0.35,
    "reversion": 0.25,
}
SIGNAL_THRESHOLD = 0.55   # weighted vote must exceed this to open trade

# ── Indicator parameters ──────────────────────────────────────────────────────
EMA_FAST     = 9
EMA_SLOW     = 21
EMA_TREND    = 50
ADX_PERIOD   = 14
ADX_MIN      = 22
RSI_PERIOD   = 14
RSI_OB       = 70
RSI_OS       = 30
STOCH_K      = 14
STOCH_D      = 3
MACD_FAST    = 12
MACD_SLOW    = 26
MACD_SIGNAL  = 9
BB_PERIOD    = 20
BB_STD       = 2.0
ATR_PERIOD   = 14
SQUEEZE_BB_MULTIPLIER = 1.5
SQUEEZE_KC_MULTIPLIER = 1.0

# ── Engine ────────────────────────────────────────────────────────────────────
SCAN_INTERVAL        = 10    # seconds between full scans
RECONNECT_DELAY      = 5
MAX_RECONNECT        = 10
BALANCE_REFRESH_S    = 30

# ── Logging / output ──────────────────────────────────────────────────────────
LOG_LEVEL      = os.environ.get("QE_LOG_LEVEL", "INFO")
LOG_FILE       = os.environ.get("QE_LOG_FILE", "quantum_edge.log")
TRADE_CSV      = os.environ.get("QE_TRADE_CSV", "trades.csv")
DASHBOARD_FPS  = 2    # dashboard refresh rate
