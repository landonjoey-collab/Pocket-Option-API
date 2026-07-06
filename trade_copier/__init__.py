"""Pocket Option Trade Copier.

One master account. Unlimited followers. Auto-copied in milliseconds.

Usage:
    python -m trade_copier --config copier_config.json
"""

from trade_copier.account import PocketAccountClient
from trade_copier.copier import TradeCopier
from trade_copier.config import CopierConfig, load_config

__all__ = ["PocketAccountClient", "TradeCopier", "CopierConfig", "load_config"]
__version__ = "0.1.0"
