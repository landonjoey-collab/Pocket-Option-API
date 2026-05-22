# Trading API

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

> A robust Python SDK for automated binary options trading via WebSocket, with real-time data, technical analysis support, and prop firm challenge tooling.

## Highlights

- **Secure Authentication**: Session-based login and persistent connection management
- **Automated Trading**: Programmatic buy/sell operations
- **Real-Time Data**: WebSocket-based live quotes and trade feedback
- **Technical Analysis**: Historical candle data compatible with TA-Lib, pandas, and finta
- **Stability**: Automatic reconnection and error handling
- **Dual Mode**: Demo and live account support

## Installation

```bash
git clone <your-repo-url>
cd trading-api
pip install -e .
```

## Basic Use

```python
from tradingapi.stable_api import TradingAPI

ssid = """42["auth",{"session":"your_session","isDemo":1,"uid":your_uid,"platform":2}]"""
demo = True  # True for demo, False for live

api = TradingAPI(ssid, demo)
api.connect()

balance = api.get_balance()
print(f"Balance: ${balance:.2f}")

result = api.buy(
    amount=10,
    active="EURUSD_otc",
    action="call",       # "call" or "put"
    expirations=60       # seconds
)
```

## Getting the SSID

1. Log in to the trading platform via browser
2. Open Developer Tools (F12) -> Network tab
3. Filter for WebSocket (WS) connections
4. Find the authentication message containing the SSID
5. Copy the full string: `42["auth",{"session":"...","isDemo":1,...}]`

## License

MIT License - see [LICENSE](LICENSE) for details.

## Disclaimer

This is an unofficial implementation. Use at your own risk.
