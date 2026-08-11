"""Signature and header checks for kalshi_copier.auth."""

import time

from kalshi_copier.auth import KalshiSigner
from tests.fake_kalshi import verify_signature


def test_signature_verifies_against_the_public_key(accounts):
    account = accounts["master"]
    signer = KalshiSigner.from_file(account["key_id"], account["path"])
    assert verify_signature(account["public_key"], signer.sign("hello"), "hello")


def test_signature_does_not_verify_for_different_text(accounts):
    account = accounts["master"]
    signer = KalshiSigner.from_file(account["key_id"], account["path"])
    assert not verify_signature(account["public_key"], signer.sign("hello"), "goodbye")


def test_headers_sign_timestamp_method_and_path(accounts):
    account = accounts["master"]
    signer = KalshiSigner.from_file(account["key_id"], account["path"])
    headers = signer.headers("get", "/trade-api/v2/portfolio/balance")

    assert headers["KALSHI-ACCESS-KEY"] == account["key_id"]
    signed = (headers["KALSHI-ACCESS-TIMESTAMP"] + "GET"
              + "/trade-api/v2/portfolio/balance")
    assert verify_signature(account["public_key"],
                            headers["KALSHI-ACCESS-SIGNATURE"], signed)


def test_timestamp_is_unix_milliseconds(accounts):
    account = accounts["master"]
    signer = KalshiSigner.from_file(account["key_id"], account["path"])
    stamped = int(signer.headers("GET", "/x")["KALSHI-ACCESS-TIMESTAMP"])
    assert abs(stamped - int(time.time() * 1000)) < 5_000


def test_signer_accepts_pem_as_str_or_bytes(accounts, tmp_path):
    pem = (tmp_path / "master.pem").read_bytes()
    from_bytes = KalshiSigner("k", pem)
    from_str = KalshiSigner("k", pem.decode())
    public_key = accounts["master"]["public_key"]
    assert verify_signature(public_key, from_bytes.sign("x"), "x")
    assert verify_signature(public_key, from_str.sign("x"), "x")
