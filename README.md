# 🚀 PocketOption API

[![GitHub](https://img.shields.io/badge/GitHub-MrAlpert-blue?style=flat-square&logo=github)](https://github.com/MrAlpert)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

> The Python API is robust and modern for integration with PocketOption, offering a simple and efficient interface for automatic operation.

![Preview of API](pocketoption.png)

## 🔁 Trade Copier

This repo includes a **multi-account trade copier** — one master account,
unlimited followers, auto-copied in milliseconds with per-follower size
multipliers and daily goal/loss guards. See [TRADE_COPIER.md](TRADE_COPIER.md).

```bash
cp trade_copier/config.example.json copier_config.json  # add your SSIDs
python -m trade_copier --dry-run                        # then go live without --dry-run
```

## ✨ Highlights

- 🔐 **Secure Authentication**: Login via SSID and robust session management
- 💹 **Automated Trading**: Programmatic buying and selling operations
- 📊 **Real Time Data**: WebSocket for quotes and operations
- 📈 **Technical Analysis**: Access to historical data and indicators
- 🛡️ **Stability**: Automatic reconnection and error handling
- 🔄 **Universal**: Demo and real account support

## 🛠️ Installation

### For development (recommended):
```bash
git clone https://github.com/Mastaaa1987/PocketOptionAPI-v2.git
cd PocketOptionAPI-v2
pip install -e .
```

### Via pip:
```bash
pip install git+https://github.com/Mastaaa1987/PocketOptionAPI-v2.git
```

## 📖 Basic Use

```python
from pocketoptionapi.stable_api import PocketOption
import logging

# Configure logging (optional)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

# Session configuration
ssid = """42["auth",{"session":"sua_sessao_aqui","isDemo":1,"uid":seu_uid_aqui,"platform":2}]"""
demo = True  # True for demo account, False for real account

# Initialize API
api = PocketOption(ssid, demo)

# Connect
connect = api.connect()
print(connect)

# Check balance
saldo = api.get_balance()
print(f"💰 Saldo: ${saldo:.2f}")

# Perform operation
result = api.buy(
    amount=10,           # Value in $
    active="EURUSD_otc", # Currency pair (note the _otc suffix)
    action="call",       # "call" (High) or "put" (Low)
    expirations=60       # Expiration in seconds
)

if result["success"]:
    print(f"✅ Operation performed: ID {result['order_id']}")
```

## 🎯 Advanced Features

### Real-Time WebSocket
```python
# Callback for real-time pricing
@api.on_price_update
def price_handler(data):
    print(f"📊 {data['asset']}: ${data['price']}")

# Callback for operation results
@api.on_trade_complete
def trade_handler(result):
    print(f"💫 Result: {'✅ Gain' if result['win'] else '❌ Loss'}")
```

### Technical Analysis
```python
# Get candle history
candles = api.get_candles(
    asset="EURUSD_otc",  # Note the _otc suffix for OTC assets
    interval=60,         # Interval in seconds
)

# Data analysis
print(type(candles)) # pandas Dataframe
print(f"📈 Moving average: {candles['close'].rolling(20).mean().iloc[-1]:.5f}")
```

## 🔧 Settings

### Main Dependencies
```txt
websocket-client>=1.6.1
requests>=2.31.0
python-dateutil>=2.8.2
pandas>=2.1.3
```

### Getting the SSID
To get the SSID required for authentication:

1. Log in to the PocketOption platform via browser
2. Open Developer Tools (F12)
3. Go to the "Network" tab
4. Look for WebSocket connections
5. Find the authentication message that contains the SSID
6. Copy the full SSID in the format shown in the example

How To get SSID.docx [HERE](https://github.com/MrAlpert/PocketOptionAPI/raw/refs/heads/master/How%20to%20get%20SSID.docx)

## 🤝 Contributing

Your contribution is very welcome! Follow these steps:

1. 🍴 Fork this repository
2. 🔄 Create a branch for your feature
   ```bash
   git checkout -b feature/MinhaFeature
   ```
3. 💻 Make your changes
4. ✅ Commit using conventional messages
   ```bash
   git commit -m "feat: Adds new functionality"
   ```
5. 📤 Push to your branch
   ```bash
   git push origin feature/MinhaFeature
   ```
6. 🔍 Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This project is an unofficial implementation and has no connection with PocketOption. Use at your own risk.

## 📞 Support

- 💻 Telegram Channel: [@Mr_Alpert_TrustBot](https://t.me/Mr_Alpert_TrustBot)
- 💬 Telegram: [@Mr_Alpert](https://t.me/Mr_Alpert)
- 🎬 YouTube: [@TrustBot.Mr.Alpert](https://www.youtube.com/@TrustBot.Mr.Alpert)

---

<p align="center">
  Powered by <a href="https://github.com/MrAlpert">Mr.Alpert</a>
</p> 
