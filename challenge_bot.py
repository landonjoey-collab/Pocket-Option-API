"""
Prop Firm Challenge Bot
-----------------------
Enforces challenge rules automatically:
  - Daily drawdown limit  (default 5%)
  - Total drawdown limit  (default 10%)
  - Profit target         (default 10%)
  - Fixed trade sizing    (default 1% of starting balance)
  - Full trade log (CSV)

Strategy: Supertrend + Dual EMA crossover on Heikin-Ashi candles
"""
import time, math, json, threading, csv, os
import numpy as np
import pandas as pd
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from datetime import datetime, date
from tradingapi.stable_api import TradingAPI
import tradingapi.global_value as global_value


# ── Challenge Configuration ───────────────────────────────────────────────────
SSID = """42["auth",{"session":"YOUR_SESSION","isDemo":1,"uid":YOUR_UID,"platform":2}]"""
DEMO = True

PROFIT_TARGET_PCT  = 10.0  # challenge passes when balance grows by this %
MAX_DAILY_LOSS_PCT =  5.0  # stop for the day when daily loss hits this %
MAX_TOTAL_LOSS_PCT = 10.0  # challenge fails when total loss hits this %
TRADE_SIZE_PCT     =  1.0  # each trade = this % of challenge start balance
MIN_PAYOUT         = 80    # skip assets with payout below this
MIN_TRADING_DAYS   =  5    # how many days the challenge requires (informational)

PERIOD     = 30   # candle period in seconds (30 or 60 recommended)
EXPIRATION = 60   # option expiration in seconds

STATE_FILE = "challenge_state.json"
LOG_FILE   = "challenge_trades.csv"
# ─────────────────────────────────────────────────────────────────────────────


class ChallengeGuard:
    """Tracks challenge rules and blocks trades when any limit is breached."""

    def __init__(self, api: TradingAPI):
        self.api   = api
        self.state = self._load_state()
        self._ensure_log()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
        return {
            "challenge_start_balance": None,
            "daily_start_balance":     None,
            "daily_start_date":        None,
            "days_traded":             [],
            "total_trades":            0,
            "total_wins":              0,
        }

    def _save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def _ensure_log(self):
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, "w", newline="") as f:
                csv.writer(f).writerow([
                    "timestamp", "asset", "action", "amount", "expiration",
                    "profit", "result", "balance_after",
                    "daily_dd_pct", "total_dd_pct",
                ])

    # ── Balance helpers ───────────────────────────────────────────────────────

    def _get_balance(self, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            b = self.api.get_balance()
            if b is not None:
                return float(b)
            time.sleep(0.5)
        raise RuntimeError("Timed out waiting for balance from server.")

    # ── Initialisation ────────────────────────────────────────────────────────

    def init_balance(self):
        """Call once after connecting. Locks in baselines."""
        balance = self._get_balance()
        today   = str(date.today())

        if self.state["challenge_start_balance"] is None:
            self.state["challenge_start_balance"] = balance
            print(f"[CHALLENGE] Start balance locked: ${balance:.2f}")

        if self.state["daily_start_date"] != today:
            self.state["daily_start_balance"] = balance
            self.state["daily_start_date"]    = today
            if today not in self.state["days_traded"]:
                self.state["days_traded"].append(today)
            print(f"[CHALLENGE] New day — daily baseline: ${balance:.2f}")

        self._save_state()
        return balance

    # ── Trade sizing ──────────────────────────────────────────────────────────

    def trade_size(self):
        """Fixed dollar amount = TRADE_SIZE_PCT of challenge start balance."""
        return round(self.state["challenge_start_balance"] * TRADE_SIZE_PCT / 100, 2)

    # ── Rule checks ───────────────────────────────────────────────────────────

    def can_trade(self):
        """Returns (True, None) or (False, reason). Always check before placing."""
        balance = self._get_balance()
        start   = self.state["challenge_start_balance"]
        daily   = self.state["daily_start_balance"]

        profit_pct   = (balance - start) / start * 100
        total_dd_pct = (start  - balance) / start * 100
        daily_dd_pct = (daily  - balance) / daily * 100

        if profit_pct >= PROFIT_TARGET_PCT:
            return False, (
                f"TARGET REACHED +{profit_pct:.2f}% — challenge passed! "
                f"Balance: ${balance:.2f}"
            )
        if total_dd_pct >= MAX_TOTAL_LOSS_PCT:
            return False, (
                f"TOTAL DRAWDOWN {total_dd_pct:.2f}% exceeded {MAX_TOTAL_LOSS_PCT}% "
                f"— challenge failed. Balance: ${balance:.2f}"
            )
        if daily_dd_pct >= MAX_DAILY_LOSS_PCT:
            return False, (
                f"DAILY DRAWDOWN {daily_dd_pct:.2f}% exceeded {MAX_DAILY_LOSS_PCT}% "
                f"— no more trades today. Balance: ${balance:.2f}"
            )
        return True, None

    # ── Logging & reporting ───────────────────────────────────────────────────

    def log_trade(self, asset, action, amount, expiration, profit, result_str):
        balance = self._get_balance()
        start   = self.state["challenge_start_balance"]
        daily   = self.state["daily_start_balance"]

        daily_dd = max(0.0, (daily  - balance) / daily * 100)
        total_dd = max(0.0, (start  - balance) / start * 100)

        self.state["total_trades"] += 1
        if result_str == "win":
            self.state["total_wins"] += 1
        self._save_state()

        with open(LOG_FILE, "a", newline="") as f:
            csv.writer(f).writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                asset, action, f"{amount:.2f}", expiration,
                f"{profit:.2f}" if profit else "0.00",
                result_str,
                f"{balance:.2f}",
                f"{daily_dd:.2f}",
                f"{total_dd:.2f}",
            ])

    def status(self):
        balance      = self._get_balance()
        start        = self.state["challenge_start_balance"]
        daily        = self.state["daily_start_balance"]
        profit_pct   = (balance - start) / start * 100
        total_dd_pct = max(0.0, (start  - balance) / start * 100)
        daily_dd_pct = max(0.0, (daily  - balance) / daily * 100)
        total  = self.state["total_trades"]
        wins   = self.state["total_wins"]
        winrate = wins / total * 100 if total else 0.0
        days   = len(self.state["days_traded"])

        print(
            f"[STATUS] ${balance:.2f} | "
            f"P&L {profit_pct:+.2f}% (target {PROFIT_TARGET_PCT}%) | "
            f"Daily DD {daily_dd_pct:.2f}% / {MAX_DAILY_LOSS_PCT}% | "
            f"Total DD {total_dd_pct:.2f}% / {MAX_TOTAL_LOSS_PCT}% | "
            f"W/L {wins}/{total - wins} ({winrate:.0f}%) | "
            f"Days {days}/{MIN_TRADING_DAYS}"
        )


# ── Strategy ─────────────────────────────────────────────────────────────────

def _supertrend(df, multiplier, period):
    df["TR"]  = ta.TRANGE(df)
    df["ATR"] = ta.SMA(df["TR"], period)
    df["basic_ub"] = (df["high"] + df["low"]) / 2 + multiplier * df["ATR"]
    df["basic_lb"] = (df["high"] + df["low"]) / 2 - multiplier * df["ATR"]
    df["final_ub"] = 0.0
    df["final_lb"] = 0.0
    for i in range(period, len(df)):
        df["final_ub"].iat[i] = (
            df["basic_ub"].iat[i]
            if df["basic_ub"].iat[i] < df["final_ub"].iat[i - 1]
            or df["close"].iat[i - 1] > df["final_ub"].iat[i - 1]
            else df["final_ub"].iat[i - 1]
        )
        df["final_lb"].iat[i] = (
            df["basic_lb"].iat[i]
            if df["basic_lb"].iat[i] > df["final_lb"].iat[i - 1]
            or df["close"].iat[i - 1] < df["final_lb"].iat[i - 1]
            else df["final_lb"].iat[i - 1]
        )
    df["ST"] = 0.0
    for i in range(period, len(df)):
        prev_st  = df["ST"].iat[i - 1]
        prev_ub  = df["final_ub"].iat[i - 1]
        prev_lb  = df["final_lb"].iat[i - 1]
        close    = df["close"].iat[i]
        ub, lb   = df["final_ub"].iat[i], df["final_lb"].iat[i]
        if   prev_st == prev_ub and close <= ub: df["ST"].iat[i] = ub
        elif prev_st == prev_ub and close >  ub: df["ST"].iat[i] = lb
        elif prev_st == prev_lb and close >= lb: df["ST"].iat[i] = lb
        elif prev_st == prev_lb and close <  lb: df["ST"].iat[i] = ub
    df["STX"] = np.where(df["ST"] > 0.0, np.where(df["close"] < df["ST"], "down", "up"), np.nan)
    df.drop(["basic_ub", "basic_lb", "final_ub", "final_lb"], inplace=True, axis=1)
    df.fillna(0, inplace=True)
    return df


def _make_df(df0, history):
    df1 = pd.DataFrame(history).sort_values("time").reset_index(drop=True)
    df1["time"] = pd.to_datetime(df1["time"], unit="s")
    df1.set_index("time", inplace=True)
    df = df1["price"].resample(f"{PERIOD}s").ohlc().reset_index()
    df = df.loc[df["time"] < datetime.fromtimestamp(_next_candle_ts(sleep=False))]
    if df0 is not None:
        ts = datetime.timestamp(df.iloc[0]["time"])
        extras = [df0.iloc[x] for x in range(len(df0)) if datetime.timestamp(df0.iloc[x]["time"]) < ts]
        if extras:
            df = pd.concat([df, pd.DataFrame(extras)], ignore_index=True)
            df = df.sort_values("time").reset_index(drop=True)
    return df


def _next_candle_ts(sleep=True):
    """Returns seconds to sleep (sleep=True) or next candle unix timestamp (sleep=False)."""
    now = datetime.now()
    dt  = int(now.timestamp()) - now.second
    s   = now.second
    if PERIOD == 60:
        dt += 60
    elif PERIOD == 30:
        dt += 30 if s < 30 else 60
        if not sleep: dt -= 30
    elif PERIOD == 15:
        if   s >= 45: dt += 60
        elif s >= 30: dt += 45
        elif s >= 15: dt += 30
        else:         dt += 15
        if not sleep: dt -= 15
    if sleep:
        secs = dt - int(now.timestamp())
        global_value.logger(f"Next candle in {secs}s", "INFO")
        return secs
    return dt


def get_signal(pair):
    """Returns 1 (call), -1 (put), or 0 (no trade)."""
    if "history" not in global_value.pairs[pair]:
        return 0
    history = list(global_value.pairs[pair]["history"])
    df = _make_df(global_value.pairs[pair].get("dataframe"), history)

    ha = qtpylib.heikinashi(df)
    df["open"]  = ha["open"]
    df["close"] = ha["close"]
    df["high"]  = ha["high"]
    df["low"]   = ha["low"]

    df = _supertrend(df, 1.3, 13)
    df["ma1"] = ta.EMA(df["close"], timeperiod=16)
    df["ma2"] = ta.EMA(df["close"], timeperiod=165)
    df["cross"] = 0
    df.loc[qtpylib.crossed_above(df["ST"], df["ma1"]), "cross"] =  1
    df.loc[qtpylib.crossed_below(df["ST"], df["ma1"]), "cross"] = -1

    last = df.iloc[-1]
    if last["STX"] == "up"   and last["ma1"] > last["ma2"] and last["cross"] == 1:
        return 1
    if last["STX"] == "down" and last["ma1"] < last["ma2"] and last["cross"] == -1:
        return -1
    return 0


# ── Setup helpers ─────────────────────────────────────────────────────────────

def _load_pairs():
    try:
        data = json.loads(global_value.PayoutData)
        for pair in data:
            if len(pair) == 19 and pair[14] and "_otc" in pair[1] and pair[5] >= MIN_PAYOUT:
                global_value.pairs[pair[1]] = {"id": pair[0], "payout": pair[5], "type": pair[3]}
        return bool(global_value.pairs)
    except Exception as e:
        global_value.logger(f"_load_pairs: {e}", "ERROR")
        return False


def _load_candles(api: TradingAPI):
    for i, pair in enumerate(global_value.pairs, 1):
        global_value.logger(f"Loading candles {pair} ({i}/{len(global_value.pairs)})", "INFO")
        api.get_candles(pair, PERIOD)
        time.sleep(1)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(api: TradingAPI, guard: ChallengeGuard):
    while not global_value.websocket_is_connected:
        time.sleep(0.1)
    time.sleep(2)

    guard.init_balance()
    guard.status()

    if not _load_pairs():
        print("[ERROR] No tradeable pairs found. Check MIN_PAYOUT or your connection.")
        return
    _load_candles(api)

    print(
        f"[CHALLENGE] Running on {len(global_value.pairs)} assets | "
        f"Trade size: ${guard.trade_size():.2f} | "
        f"Log: {LOG_FILE}"
    )

    while True:
        ok, reason = guard.can_trade()
        if not ok:
            print(f"\n{'='*60}")
            print(f"[CHALLENGE] {reason}")
            print(f"{'='*60}\n")
            guard.status()
            break

        for pair in list(global_value.pairs.keys()):
            ok, reason = guard.can_trade()
            if not ok:
                print(f"[CHALLENGE] {reason}")
                guard.status()
                return

            signal = get_signal(pair)
            if signal == 0:
                continue

            action = "call" if signal == 1 else "put"
            amount = guard.trade_size()
            global_value.logger(f"Signal {action.upper()} | {pair} | ${amount:.2f}", "INFO")

            result, order_id = api.buy(amount=amount, active=pair, action=action, expirations=EXPIRATION)
            if result and order_id:
                profit, outcome = api.check_win(order_id)
                guard.log_trade(pair, action, amount, EXPIRATION, profit, outcome)
                global_value.logger(f"{pair} {action.upper()} → {outcome} | profit: {profit}", "INFO")
                guard.status()

        time.sleep(_next_candle_ts(sleep=True))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    global_value.loglevel = "INFO"

    # Paste your SSID here before running
    # Demo:  '42["auth",{"session":"abc123","isDemo":1,"uid":12345,"platform":2}]'
    # Live:  '42["auth",{"session":"abc123","isDemo":0,"uid":12345,"platform":2}]'

    api   = TradingAPI(SSID, DEMO)
    api.connect()

    guard = ChallengeGuard(api)
    run(api, guard)
