# 🔁 Pocket Option Trade Copier

**One master account. Unlimited followers. Auto-copied in milliseconds.**

The copier connects to your master account's websocket session and watches for
newly opened trades — whether you place them **manually in the browser** or
through a bot. The moment a trade opens, it is mirrored to every follower
account concurrently, each sized by its own multiplier or fixed amount.

```
                              ┌────────────────────────────┐
                          ┌──▶│ FOLLOWER 1        5x       │
┌───────────────────┐     │   └────────────────────────────┘
│  MASTER ACCOUNT   │ AUTO│   ┌────────────────────────────┐
│  goal   +$1,000   │─COPY┼──▶│ FOLLOWER 2        2x       │
│  loss   -$1,000   │     │   └────────────────────────────┘
└───────────────────┘     │   ┌────────────────────────────┐
                          └──▶│ FOLLOWER 3        $10 fixed│
                              └────────────────────────────┘
```

## Quick start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create your config from the example:
   ```bash
   cp trade_copier/config.example.json copier_config.json
   ```

3. Paste the **SSID** of each account into `copier_config.json`
   (see [Getting the SSID](#getting-the-ssid) below).

4. Do a dry run first — it watches the master and logs what *would* be
   copied, without placing any orders:
   ```bash
   python -m trade_copier --config copier_config.json --dry-run
   ```

5. Go live:
   ```bash
   python -m trade_copier --config copier_config.json
   ```

Place a trade on the master account and watch it fan out:

```
[12:20:01] MASTER TRADE  EURUSD_otc  ▲ CALL  $10  60s
[12:20:01]   ✓ Follower 1  $50  (5x)
[12:20:01]   ✓ Follower 2  $20  (2x)
[12:20:01]   ✓ Follower 3  $10  ($10 fixed)
[12:20:01] copied to 3/3 followers in 187 ms
```

## Configuration reference

### `master`
| key    | description                                   |
|--------|-----------------------------------------------|
| `name` | display name                                  |
| `ssid` | the full `42["auth",{...}]` websocket message |
| `demo` | optional; auto-detected from the SSID         |

### `followers[]`
| key            | default | description                                          |
|----------------|---------|------------------------------------------------------|
| `name`         | auto    | display name                                         |
| `ssid`         | —       | the follower account's SSID                          |
| `multiplier`   | `1.0`   | follower amount = master amount × multiplier         |
| `fixed_amount` | off     | always trade this amount (overrides `multiplier`)    |
| `min_amount`   | `1.0`   | floor for the computed amount                        |
| `max_amount`   | off     | cap for the computed amount                          |

### `settings`
| key                  | default | description                                             |
|----------------------|---------|---------------------------------------------------------|
| `daily_goal`         | off     | pause copying once master session PnL ≥ this            |
| `daily_loss`         | off     | pause copying once master session PnL ≤ this (negative) |
| `assets_allowlist`   | `[]`    | if non-empty, only copy these assets                    |
| `assets_blocklist`   | `[]`    | never copy these assets                                 |
| `copy_expiration`    | `true`  | mirror the master trade's expiration                    |
| `default_expiration` | `60`    | fallback expiration in seconds                          |
| `min_expiration`     | `5`     | shortest expiration ever sent to a follower             |

## Getting the SSID

1. Log in to Pocket Option in the browser with the account you want.
2. Open Developer Tools (F12) → **Network** tab → filter **WS**.
3. Click the `socket.io` websocket connection and open **Messages**.
4. Find the outgoing message that starts with `42["auth",` and copy the
   whole thing into the config. Repeat for each account.

Also see `How to get SSID.docx` in the repository root.

## How it works

- Each account gets its own websocket session
  (`trade_copier/account.py`) — the bundled `pocketoptionapi` package keeps
  state in a module-level singleton and can only drive one account per
  process, so the copier ships its own lightweight multi-account client.
- The master session listens for `successopenOrder` / `updateOpenedDeals`
  events, so trades placed from **any** device or bot on the master account
  are detected.
- Follower orders are fired concurrently with `asyncio.gather`, so the total
  copy latency is roughly one network round-trip regardless of how many
  followers you attach.
- The startup snapshot of already-open deals is ignored — only trades opened
  *after* the copier starts are copied.

## ⚠️ Disclaimer

Trading binary options carries a high level of risk. This is an unofficial
tool with no affiliation to Pocket Option; running it may violate the
platform's terms of service. **Test on demo accounts first.** Use at your
own risk.
