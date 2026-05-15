#!/usr/bin/env python3
"""
Entry point for the never-sleeping trading system.

Usage:
    # Demo account (default)
    PO_SSID='<your-ssid>' PO_DEMO=1 python run_bot.py

    # Live account
    PO_SSID='<your-ssid>' PO_DEMO=0 python run_bot.py

Environment variables:
    PO_SSID          Pocket Option WebSocket session ID (required)
    PO_DEMO          1 = demo, 0 = live  (default: 1)
    LOG_LEVEL        DEBUG | INFO | WARNING  (default: INFO)
    LOG_FILE         path to rotating log file  (default: trading_system.log)
    TRADE_LOG_FILE   path to CSV trade journal  (default: trades.csv)
"""
import signal
import sys

from trading_system.engine import TradingEngine
from trading_system.logger import log
from trading_system import config


def _banner() -> None:
    mode = "DEMO" if config.DEMO else "LIVE"
    log.info("━" * 60)
    log.info("  Pocket Option Auto-Trader  |  mode=%s", mode)
    log.info("  Candle period : %ds   Expiration: %ds", config.CANDLE_PERIOD, config.EXPIRATION)
    log.info("  Base stake    : $%.2f  Max stake: $%.2f", config.BASE_STAKE, config.MAX_STAKE)
    log.info("  Min payout    : %d%%   ADX thresh: %d", config.MIN_PAYOUT, config.ADX_THRESHOLD)
    log.info("━" * 60)


def main() -> None:
    if not config.SSID:
        log.error("PO_SSID environment variable is not set. Exiting.")
        sys.exit(1)

    _banner()
    engine = TradingEngine()

    def _shutdown(sig, frame):
        log.info("Shutdown signal received. Stopping…")
        engine.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    engine.run()
    log.info("Engine stopped. Goodbye.")


if __name__ == "__main__":
    main()
