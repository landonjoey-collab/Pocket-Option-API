# 🔁 Kalshi Trade Copier

**One master account. Unlimited followers. Auto-copied in milliseconds —
on an official, documented API.**

The copier subscribes to the master account's private **`fill` WebSocket
channel**, so every executed trade — placed in the app, on the website, or by
a bot — is detected the instant it fills. Each fill is mirrored to every
follower account concurrently through Kalshi's REST API, sized per follower
by a contract multiplier or a fixed count.

```
                                 ┌──────────────────────────────┐
                             ┌──▶│ FOLLOWER 1     5x contracts  │
┌──────────────────────┐     │   └──────────────────────────────┘
│    MASTER ACCOUNT    │ AUTO│   ┌──────────────────────────────┐
│  fill stream (WS)    │─COPY┼──▶│ FOLLOWER 2     2x contracts  │
│  daily cap  $1,000   │     │   └──────────────────────────────┘
└──────────────────────┘     │   ┌──────────────────────────────┐
                             └──▶│ FOLLOWER 3     1 fixed       │
                                 └──────────────────────────────┘
```

## Why Kalshi (vs. the Pocket Option copier)

| | Pocket Option | Kalshi |
|---|---|---|
| API | reverse-engineered websocket | official REST + WS ([docs](https://docs.kalshi.com/welcome)) |
| Auth | browser session cookie (SSID) | API keys + RSA request signing |
| Testing | live accounts only | free [demo sandbox](https://docs.kalshi.com/getting_started/demo_env) |
| Multi-account | against ToS territory | sub-accounts officially supported |
| Regulation | offshore | CFTC-regulated US exchange |

## Quick start (demo — no real money)

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a **demo** account at <https://demo.kalshi.co> and generate an API
   key for each account you want to use (Settings → API keys). Save each
   private key as a `.pem` file, e.g. under `keys/`.

3. Create your config:
   ```bash
   cp kalshi_copier/config.example.json kalshi_config.json
   ```
   Fill in each account's `key_id` and `private_key_path`.

4. Dry run first — logs master fills and what would be copied, places nothing:
   ```bash
   python -m kalshi_copier --config kalshi_config.json --dry-run
   ```

5. Go live — set `"enabled": true` under `settings` (without it the copier
   always runs as a dry run), still in the demo environment until you set
   `"environment": "prod"`:
   ```bash
   python -m kalshi_copier --config kalshi_config.json
   ```

## 🛑 Stopping trading

Three ways, in order of severity:

1. **Ctrl+C** the running copier (or kill its process).
2. **Kill switch** — from the copier's working directory:
   ```bash
   python -m kalshi_copier --halt
   ```
   This creates a `KALSHI_HALT` file; a running copier stops within a second
   and refuses to restart until you run `--resume` (or delete the file).
   Setting `KALSHI_COPIER_HALT=1` in the environment does the same. Flipping
   `"enabled"` back to `false` in the config also blocks orders on the next
   start.
3. **Revoke the API keys** in each Kalshi account's Settings → API keys page.
   This is the only step that guarantees nothing anywhere can trade the
   account, no matter what process is still running or where.

Place a trade on the master account and watch it fan out:

```
[12:20:01] MASTER FILL  KXHIGHNY-26JUL07-B58  BUY YES  10 @ 42¢
[12:20:01]   ✓ Follower 1  50 contracts  (5x)
[12:20:01]   ✓ Follower 2  20 contracts  (2x)
[12:20:01]   ✓ Follower 3  1 contracts  (1 fixed)
[12:20:01] copied to 3/3 followers in 231 ms
```

## Configuration reference

### `master` / `followers[]`
| key                | description                                        |
|--------------------|----------------------------------------------------|
| `name`             | display name                                       |
| `key_id`           | the API key id from Kalshi settings                |
| `private_key_path` | path to the RSA private key `.pem` for that key    |
| `multiplier`       | follower contracts = round(master × multiplier)    |
| `fixed_count`      | always trade this many contracts (overrides `multiplier`) |
| `max_count`        | cap per copied trade                               |

### `settings`
| key                    | default    | description                                             |
|------------------------|------------|---------------------------------------------------------|
| `enabled`              | `false`    | must be `true` to place orders; otherwise forces dry-run |
| `environment`          | `"demo"`   | `"demo"` or `"prod"`                                    |
| `order_type`           | `"market"` | `"market"` or `"limit"` (limit pegs to master's fill price) |
| `limit_slippage_cents` | `2`        | limit orders: allowed slippage vs. master's price        |
| `aggregation_ms`       | `500`      | partial fills of one master order are merged this long   |
| `copy_sells`           | `true`     | also mirror master's sell/closing fills                  |
| `tickers_allowlist`    | `[]`       | if non-empty, only copy these markets                    |
| `tickers_blocklist`    | `[]`       | never copy these markets                                 |
| `daily_max_notional`   | off        | daily $ budget of master fills; a trade that would exceed it is skipped and copying pauses until the next UTC day |
| `api_base` / `ws_url`  | per env    | endpoint overrides if Kalshi's URLs change               |

## Multi-account structure that's actually allowed

Kalshi permits **one account per person**, but each account supports up to
**64 sub-accounts**, and an API key can be
[restricted to a single sub-account](https://docs.kalshi.com/getting_started/api_keys).
So the legitimate setups are:

- **Your own sub-accounts** — master strategy on the main account, followers
  are sub-accounts with restricted keys (e.g. different bankroll buckets
  copied at different sizes).
- **Different people** — each person creates their own API key on their own
  account and adds it as a follower entry. Everyone trades their own funds.

## Design notes

- **Fill aggregation**: one master order can fill in several partial chunks.
  Fills are merged per `order_id` for `aggregation_ms` and copied once with
  the total count — otherwise a 0.5x follower would see three 1-contract
  chunks as three skipped trades instead of one 2-contract copy.
- **Sells are copied by default** so follower positions track the master's
  exits proportionally, not just entries.
- **Fan-out is concurrent** (`asyncio.gather` over per-follower REST calls),
  so latency stays roughly one API round-trip regardless of follower count.
- If a follower's scaled size rounds to 0 contracts, that copy is skipped
  and logged rather than forced to 1.
- **The daily cap is checked before ordering**, so the trade that would
  breach it is skipped rather than filled and paused afterwards; a single
  oversized fill therefore can't overshoot the budget.

## Tests

```bash
pip install pytest pytest-asyncio
python -m pytest
```

The suite runs the copier against a local stand-in for Kalshi
(`tests/fake_kalshi.py`): a real websocket server serving the `fill` channel
and a real HTTP server for orders, both of which verify the RSA-PSS
signature on every request against the public half of the test key. So
auth, the websocket subscription, fill aggregation, per-follower sizing, the
risk guards, and the order bodies are all exercised for real — no network
access and no Kalshi credentials required.

## ⚠️ Disclaimer

Event contracts involve risk and you can lose your entire stake. This is an
unofficial tool with no affiliation to Kalshi. Automated copying can amplify
mistakes across accounts — **prove your setup in the demo environment
first**, and review Kalshi's terms and API rules before running against
production. Use at your own risk.
