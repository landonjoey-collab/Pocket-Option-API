"""Configuration loading & validation for the trade copier."""

import json
from dataclasses import dataclass, field


@dataclass
class AccountConfig:
    name: str
    ssid: str
    demo: bool = None  # None = auto-detect from the SSID's isDemo field


@dataclass
class FollowerConfig(AccountConfig):
    multiplier: float = 1.0        # follower amount = master amount * multiplier
    fixed_amount: float = None     # overrides multiplier when set
    min_amount: float = 1.0
    max_amount: float = None

    def size_for(self, master_amount):
        amount = self.fixed_amount if self.fixed_amount else master_amount * self.multiplier
        if self.max_amount is not None:
            amount = min(amount, self.max_amount)
        return round(max(amount, self.min_amount), 2)

    def size_label(self):
        if self.fixed_amount:
            return f"${self.fixed_amount:g} fixed"
        return f"{self.multiplier:g}x"


@dataclass
class CopierSettings:
    daily_goal: float = None       # stop copying once master's realized PnL >= this
    daily_loss: float = None       # stop copying once master's realized PnL <= this (negative)
    assets_allowlist: list = field(default_factory=list)
    assets_blocklist: list = field(default_factory=list)
    copy_expiration: bool = True   # mirror master's expiration; else use default
    default_expiration: int = 60   # seconds
    min_expiration: int = 5


@dataclass
class CopierConfig:
    master: AccountConfig
    followers: list
    settings: CopierSettings


def load_config(path):
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    if "master" not in raw or "ssid" not in raw.get("master", {}):
        raise ValueError('config needs a "master" section with an "ssid"')
    followers_raw = raw.get("followers", [])
    if not followers_raw:
        raise ValueError('config needs at least one entry in "followers"')

    master = AccountConfig(
        name=raw["master"].get("name", "Master"),
        ssid=raw["master"]["ssid"],
        demo=raw["master"].get("demo"),
    )
    followers = []
    for i, f in enumerate(followers_raw, start=1):
        if "ssid" not in f:
            raise ValueError(f"follower #{i} is missing an ssid")
        followers.append(FollowerConfig(
            name=f.get("name", f"Follower {i}"),
            ssid=f["ssid"],
            demo=f.get("demo"),
            multiplier=float(f.get("multiplier", 1.0)),
            fixed_amount=f.get("fixed_amount"),
            min_amount=float(f.get("min_amount", 1.0)),
            max_amount=f.get("max_amount"),
        ))

    s = raw.get("settings", {})
    settings = CopierSettings(
        daily_goal=s.get("daily_goal"),
        daily_loss=s.get("daily_loss"),
        assets_allowlist=s.get("assets_allowlist", []),
        assets_blocklist=s.get("assets_blocklist", []),
        copy_expiration=bool(s.get("copy_expiration", True)),
        default_expiration=int(s.get("default_expiration", 60)),
        min_expiration=int(s.get("min_expiration", 5)),
    )
    if settings.daily_loss is not None and settings.daily_loss > 0:
        settings.daily_loss = -settings.daily_loss  # accept 1000 to mean -1000

    return CopierConfig(master=master, followers=followers, settings=settings)
