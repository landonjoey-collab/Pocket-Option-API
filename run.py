#!/usr/bin/env python3
"""
Quantum Edge Pro — Entry Point

Quick start (paper trading):
    pip install -r requirements_qe.txt
    QE_API_KEY=<key> QE_API_SECRET=<secret> QE_TESTNET=1 python run.py

Live trading (Binance USDT-M futures):
    QE_API_KEY=<key> QE_API_SECRET=<secret> QE_TESTNET=0 QE_FUTURES=1 python run.py

All settings live in quantum_edge/config.py and can be overridden via env vars.
"""
import signal
import sys
from quantum_edge.engine import Engine
from quantum_edge.logger import log
from quantum_edge import config


def _banner() -> None:
    mode  = "TESTNET/PAPER" if config.USE_TESTNET else "*** LIVE ***"
    mtype = "FUTURES" if config.FUTURES_MODE else "SPOT"
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║       QUANTUM EDGE PRO  Auto-Trader      ║")
    print(f"  ║  Exchange : {config.EXCHANGE_ID.upper():<30}║")
    print(f"  ║  Mode     : {mode:<30}║")
    print(f"  ║  Market   : {mtype:<30}║")
    print(f"  ║  Symbols  : {len(config.SYMBOLS)} pairs{'':<24}║")
    print(f"  ║  Leverage : {config.LEVERAGE}×{'':<29}║")
    print(f"  ║  Risk/trade: {config.ACCOUNT_RISK_PCT}%{'':<28}║")
    print("  ╚══════════════════════════════════════════╝")
    print()


def main() -> None:
    if not config.API_KEY or not config.API_SECRET:
        print("ERROR: QE_API_KEY and QE_API_SECRET environment variables must be set.")
        print("  Example:  QE_API_KEY=xxx QE_API_SECRET=yyy python run.py")
        sys.exit(1)

    _banner()
    engine = Engine()

    def _shutdown(sig, frame):
        log.info("Shutdown signal received.")
        engine.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    engine.run()


if __name__ == "__main__":
    main()
