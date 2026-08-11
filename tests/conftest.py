"""Shared fixtures: throwaway RSA keys and a config wired to the fake servers."""

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi_copier.config import load_config

# One 2048-bit keypair generation takes ~0.1s; four accounts across the whole
# session is cheap enough to build once and share.
_KEY_CACHE = []


def _new_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem, key.public_key()


@pytest.fixture(scope="session")
def keypairs():
    """Four (pem, public_key) pairs: one master plus three followers."""
    if not _KEY_CACHE:
        _KEY_CACHE.extend(_new_keypair() for _ in range(4))
    return _KEY_CACHE


@pytest.fixture
def accounts(keypairs, tmp_path):
    """Writes each key to disk and returns account descriptors.

    Each entry is {"key_id", "path", "public_key"}.
    """
    names = ["master", "follower1", "follower2", "follower3"]
    out = {}
    for name, (pem, public_key) in zip(names, keypairs):
        path = tmp_path / f"{name}.pem"
        path.write_bytes(pem)
        out[name] = {"key_id": f"key-{name}", "path": str(path),
                     "public_key": public_key}
    return out


@pytest.fixture
def public_keys(accounts):
    """key id -> public key, the map the fake servers verify against."""
    return {a["key_id"]: a["public_key"] for a in accounts.values()}


@pytest.fixture
def make_config(accounts, tmp_path):
    """Builds a config file from overrides and loads it.

    followers defaults to one 1x follower; pass a list of dicts to override,
    each keyed by account name ("follower1", ...) plus sizing options.
    """
    def _make(followers=None, **settings):
        followers = followers or [{"account": "follower1", "multiplier": 1}]
        raw = {
            "master": {
                "name": "Master",
                "key_id": accounts["master"]["key_id"],
                "private_key_path": accounts["master"]["path"],
            },
            "followers": [
                {
                    "name": f.get("name", f["account"]),
                    "key_id": accounts[f["account"]]["key_id"],
                    "private_key_path": accounts[f["account"]]["path"],
                    **{k: v for k, v in f.items()
                       if k in ("multiplier", "fixed_count", "max_count")},
                }
                for f in followers
            ],
            "settings": settings,
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return load_config(str(path))
    return _make
