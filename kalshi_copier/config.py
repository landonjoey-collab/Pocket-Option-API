"""Configuration loading & validation for the Kalshi copier."""

import json
import math
from dataclasses import dataclass, field


@dataclass
class KalshiAccount:
    name: str
    key_id: str
    private_key_path: str


@dataclass
class KalshiFollower(KalshiAccount):
    multiplier: float = 1.0     # follower contracts = round(master contracts * multiplier)
    fixed_count: int = None     # always trade this many contracts (overrides multiplier)
    max_count: int = None       # cap per copied trade

    def size_for(self, master_count):
        if self.fixed_count:
            count = self.fixed_count
        else:
            count = math.floor(master_count * self.multiplier + 0.5)
        if self.max_count is not None:
            count = min(count, self.max_count)
        return count  # may be 0 -> the copier skips the trade

    def size_label(self):
        if self.fixed_count:
            return f"{self.fixed_count} fixed"
        return f"{self.multiplier:g}x"


@dataclass
class KalshiSettings:
    environment: str = "demo"           # "demo" or "prod"
    api_base: str = None                # optional URL overrides
    ws_url: str = None
    order_type: str = "market"          # "market" | "limit"
    limit_slippage_cents: int = 2       # limit orders: master price +/- this buffer
    aggregation_ms: int = 500           # partial fills of one order are merged for this long
    copy_sells: bool = True             # mirror master's closing/sell fills too
    tickers_allowlist: list = field(default_factory=list)
    tickers_blocklist: list = field(default_factory=list)
    daily_max_notional: float = None    # stop copying after master fills this many $ in a day


@dataclass
class KalshiCopierConfig:
    master: KalshiAccount
    followers: list
    settings: KalshiSettings


def load_config(path):
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    m = raw.get("master", {})
    if "key_id" not in m or "private_key_path" not in m:
        raise ValueError('config needs a "master" with "key_id" and "private_key_path"')
    followers_raw = raw.get("followers", [])
    if not followers_raw:
        raise ValueError('config needs at least one entry in "followers"')

    master = KalshiAccount(
        name=m.get("name", "Master"),
        key_id=m["key_id"],
        private_key_path=m["private_key_path"],
    )
    followers = []
    for i, f in enumerate(followers_raw, start=1):
        if "key_id" not in f or "private_key_path" not in f:
            raise ValueError(f'follower #{i} needs "key_id" and "private_key_path"')
        followers.append(KalshiFollower(
            name=f.get("name", f"Follower {i}"),
            key_id=f["key_id"],
            private_key_path=f["private_key_path"],
            multiplier=float(f.get("multiplier", 1.0)),
            fixed_count=f.get("fixed_count"),
            max_count=f.get("max_count"),
        ))

    s = raw.get("settings", {})
    environment = s.get("environment", raw.get("environment", "demo"))
    if environment not in ("demo", "prod"):
        raise ValueError('environment must be "demo" or "prod"')
    order_type = s.get("order_type", "market")
    if order_type not in ("market", "limit"):
        raise ValueError('order_type must be "market" or "limit"')

    settings = KalshiSettings(
        environment=environment,
        api_base=s.get("api_base"),
        ws_url=s.get("ws_url"),
        order_type=order_type,
        limit_slippage_cents=int(s.get("limit_slippage_cents", 2)),
        aggregation_ms=int(s.get("aggregation_ms", 500)),
        copy_sells=bool(s.get("copy_sells", True)),
        tickers_allowlist=s.get("tickers_allowlist", []),
        tickers_blocklist=s.get("tickers_blocklist", []),
        daily_max_notional=s.get("daily_max_notional"),
    )
    return KalshiCopierConfig(master=master, followers=followers, settings=settings)
