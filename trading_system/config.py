import os

# ── Authentication ──────────────────────────────────────────────────────────
SSID = os.environ.get("PO_SSID", "")
DEMO = os.environ.get("PO_DEMO", "1") == "1"

# ── Market filters ──────────────────────────────────────────────────────────
MIN_PAYOUT = 80          # minimum payout % to trade a pair
CANDLE_PERIOD = 30       # seconds per candle (30 | 60 | 120 …)
EXPIRATION = 60          # option expiration in seconds

# ── Position sizing / risk ──────────────────────────────────────────────────
BASE_STAKE = 1.0         # base trade amount ($)
MAX_STAKE = 50.0         # cap for martingale
MARTINGALE_FACTOR = 2.1  # multiply stake after a loss
MAX_CONSECUTIVE_LOSSES = 4
MAX_DAILY_LOSS_PCT = 10.0  # stop trading if daily drawdown > 10 % of balance

# ── Strategy parameters ─────────────────────────────────────────────────────
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2.0
EMA_FAST = 9
EMA_SLOW = 21
ADX_PERIOD = 14
ADX_THRESHOLD = 25       # only trade when trend is strong
ST_MULTIPLIER = 1.3      # supertrend ATR multiplier
ST_PERIOD = 13

# ── Session health ──────────────────────────────────────────────────────────
RECONNECT_DELAY = 5      # seconds between reconnect attempts
MAX_RECONNECT = 20
HEARTBEAT_INTERVAL = 30  # seconds

# ── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE = os.environ.get("LOG_FILE", "trading_system.log")
TRADE_LOG_FILE = os.environ.get("TRADE_LOG_FILE", "trades.csv")
