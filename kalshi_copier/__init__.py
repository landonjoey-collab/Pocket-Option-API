"""Kalshi Trade Copier.

One master account. Unlimited followers. Auto-copied in milliseconds —
built on Kalshi's official REST + WebSocket API.

Usage:
    python -m kalshi_copier --config kalshi_config.json
"""

from kalshi_copier.auth import KalshiSigner
from kalshi_copier.rest import KalshiRestClient
from kalshi_copier.ws import KalshiFillListener
from kalshi_copier.copier import KalshiCopier
from kalshi_copier.config import load_config

__all__ = ["KalshiSigner", "KalshiRestClient", "KalshiFillListener",
           "KalshiCopier", "load_config"]
__version__ = "0.1.0"
