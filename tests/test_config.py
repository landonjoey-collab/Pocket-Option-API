"""Config loading, validation, and per-follower sizing math."""

import json

import pytest

from kalshi_copier.config import KalshiFollower, load_config


def _follower(**kwargs):
    kwargs.setdefault("name", "F")
    kwargs.setdefault("key_id", "k")
    kwargs.setdefault("private_key_path", "p")
    return KalshiFollower(**kwargs)


# ------------------------------------------------------------------- sizing


@pytest.mark.parametrize("multiplier, master_count, expected", [
    (1, 7, 7),
    (5, 3, 15),
    (0.5, 10, 5),
    (0.5, 3, 2),      # round half up, not banker's rounding
    (0.5, 5, 3),      # 2.5 -> 3
    (0.25, 2, 1),     # 0.5 -> 1
    (0.1, 4, 0),      # 0.4 -> 0, copier skips
])
def test_multiplier_sizing_rounds_half_up(multiplier, master_count, expected):
    assert _follower(multiplier=multiplier).size_for(master_count) == expected


def test_fixed_count_ignores_master_size():
    follower = _follower(fixed_count=1, multiplier=99)
    assert follower.size_for(50) == 1
    assert follower.size_for(1) == 1


def test_max_count_caps_the_scaled_size():
    assert _follower(multiplier=10, max_count=20).size_for(5) == 20
    assert _follower(multiplier=10, max_count=20).size_for(1) == 10


def test_size_labels_describe_the_mode():
    assert _follower(multiplier=2.5).size_label() == "2.5x"
    assert _follower(fixed_count=3).size_label() == "3 fixed"


# ------------------------------------------------------------------ loading


def test_loads_a_full_config(make_config):
    config = make_config(
        followers=[
            {"account": "follower1", "multiplier": 5},
            {"account": "follower2", "multiplier": 2, "max_count": 100},
            {"account": "follower3", "fixed_count": 1},
        ],
        environment="demo", order_type="limit", daily_max_notional=250,
    )
    assert len(config.followers) == 3
    assert config.followers[0].multiplier == 5
    assert config.followers[1].max_count == 100
    assert config.followers[2].fixed_count == 1
    assert config.settings.order_type == "limit"
    assert config.settings.daily_max_notional == 250


def test_defaults_are_conservative(make_config):
    settings = make_config().settings
    assert settings.environment == "demo"        # sandbox, not real money
    assert settings.order_type == "market"
    assert settings.aggregation_ms == 500
    assert settings.copy_sells is True
    assert settings.daily_max_notional is None


def _write(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return str(path)


def test_rejects_config_without_followers(tmp_path):
    path = _write(tmp_path, {"master": {"key_id": "k", "private_key_path": "p"},
                             "followers": []})
    with pytest.raises(ValueError, match="followers"):
        load_config(path)


def test_rejects_master_missing_credentials(tmp_path):
    path = _write(tmp_path, {"master": {"name": "M"},
                             "followers": [{"key_id": "k", "private_key_path": "p"}]})
    with pytest.raises(ValueError, match="master"):
        load_config(path)


def test_rejects_follower_missing_credentials(tmp_path):
    path = _write(tmp_path, {"master": {"key_id": "k", "private_key_path": "p"},
                             "followers": [{"name": "no creds"}]})
    with pytest.raises(ValueError, match="follower #1"):
        load_config(path)


@pytest.mark.parametrize("field, value", [
    ("environment", "production"),   # only demo/prod
    ("order_type", "stop_loss"),     # only market/limit
])
def test_rejects_unknown_enum_values(tmp_path, field, value):
    path = _write(tmp_path, {
        "master": {"key_id": "k", "private_key_path": "p"},
        "followers": [{"key_id": "k2", "private_key_path": "p2"}],
        "settings": {field: value},
    })
    with pytest.raises(ValueError, match=field):
        load_config(path)


def test_example_config_is_valid_json_with_every_sizing_mode():
    with open("kalshi_copier/config.example.json", encoding="utf-8") as fh:
        raw = json.load(fh)
    modes = [set(f) & {"multiplier", "fixed_count", "max_count"}
             for f in raw["followers"]]
    assert {"multiplier"} in modes
    assert any("fixed_count" in m for m in modes)
    assert any("max_count" in m for m in modes)
