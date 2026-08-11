"""End-to-end tests: a master fill arrives on the websocket and the copier
places correctly sized orders on every follower via REST.

Nothing here is mocked out — the copier talks to a real (local) websocket
server and a real HTTP server, and every request is signature-checked.
"""

import asyncio
import contextlib

import pytest

from kalshi_copier.copier import KalshiCopier
from tests.fake_kalshi import FakeFillServer, FakeRestServer

FILL = {
    "market_ticker": "KXBTCD-26JUL08-B100000",
    "order_id": "master-order-1",
    "action": "buy",
    "side": "yes",
    "count": 10,
    "yes_price": 42,
    "no_price": 58,
}


@pytest.fixture
async def servers(public_keys):
    rest = FakeRestServer(public_keys).start()
    fills = await FakeFillServer(public_keys).start()
    try:
        yield rest, fills
    finally:
        rest.stop()
        await fills.stop()


@contextlib.asynccontextmanager
async def running(config, fills, dry_run=False):
    """Starts a copier and waits until it is subscribed to the fill stream."""
    copier = KalshiCopier(config, dry_run=dry_run)
    task = asyncio.create_task(copier.run())
    done, _ = await asyncio.wait(
        [task, asyncio.create_task(copier.listener.connected.wait())],
        timeout=10, return_when=asyncio.FIRST_COMPLETED)
    if task in done:
        task.result()  # copier died during startup; re-raise its error
        raise AssertionError("copier stopped before subscribing")
    try:
        yield copier
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def wait_for_orders(rest, count, timeout=5):
    """Polls until `count` orders have landed, then returns them."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if len(rest.orders) >= count:
            await asyncio.sleep(0.15)   # let any extras arrive too
            return rest.orders
        await asyncio.sleep(0.02)
    return rest.orders


# ------------------------------------------------------------------ the path


async def test_master_fill_is_copied_to_every_follower(servers, make_config,
                                                       accounts):
    rest, fills = servers
    config = make_config(
        followers=[
            {"account": "follower1", "multiplier": 1},
            {"account": "follower2", "multiplier": 0.5},
            {"account": "follower3", "fixed_count": 3},
        ],
        api_base=rest.api_base, ws_url=fills.ws_url, aggregation_ms=50)

    async with running(config, fills):
        await fills.send_fill(**FILL)
        orders = await wait_for_orders(rest, 3)

    assert len(orders) == 3, "one order per follower"
    assert rest.auth_failures == []

    by_key = {key_id: body for key_id, body in orders}
    assert by_key[accounts["follower1"]["key_id"]]["count"] == 10   # 1x
    assert by_key[accounts["follower2"]["key_id"]]["count"] == 5    # 0.5x
    assert by_key[accounts["follower3"]["key_id"]]["count"] == 3    # fixed

    for body in by_key.values():
        assert body["ticker"] == FILL["market_ticker"]
        assert body["action"] == "buy"
        assert body["side"] == "yes"
        assert body["type"] == "market"
        assert body["client_order_id"]


async def test_partial_fills_of_one_order_are_copied_once(servers, make_config):
    """3 + 4 + 3 contracts on one master order must become a single 10-contract
    copy, not three separate copies."""
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=300)

    async with running(config, fills):
        for chunk in (3, 4, 3):
            await fills.send_fill(**dict(FILL, count=chunk))
            await asyncio.sleep(0.05)
        orders = await wait_for_orders(rest, 1)

    assert len(orders) == 1
    assert orders[0][1]["count"] == 10


async def test_distinct_master_orders_are_copied_separately(servers, make_config):
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50)

    async with running(config, fills):
        await fills.send_fill(**dict(FILL, order_id="a", count=2))
        await fills.send_fill(**dict(FILL, order_id="b", count=5))
        orders = await wait_for_orders(rest, 2)

    assert sorted(body["count"] for _, body in orders) == [2, 5]


async def test_limit_orders_peg_to_the_master_price_plus_slippage(servers,
                                                                 make_config):
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50, order_type="limit",
                         limit_slippage_cents=3)

    async with running(config, fills):
        await fills.send_fill(**FILL)              # buy yes @ 42
        orders = await wait_for_orders(rest, 1)

    body = orders[0][1]
    assert body["type"] == "limit"
    assert body["yes_price"] == 45                 # 42 + 3, paying up to cross


async def test_limit_sells_peg_below_the_master_price(servers, make_config):
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50, order_type="limit",
                         limit_slippage_cents=3)

    async with running(config, fills):
        await fills.send_fill(**dict(FILL, action="sell"))
        orders = await wait_for_orders(rest, 1)

    assert orders[0][1]["yes_price"] == 39         # 42 - 3, accepting less


# --------------------------------------------------------------------- guards


async def test_dry_run_places_no_orders(servers, make_config):
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50)

    async with running(config, fills, dry_run=True):
        await fills.send_fill(**FILL)
        await asyncio.sleep(0.5)

    assert rest.orders == []


async def test_blocklisted_ticker_is_not_copied(servers, make_config):
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50,
                         tickers_blocklist=[FILL["market_ticker"]])

    async with running(config, fills):
        await fills.send_fill(**FILL)
        await asyncio.sleep(0.5)

    assert rest.orders == []


async def test_allowlist_only_copies_listed_tickers(servers, make_config):
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50, tickers_allowlist=["ALLOWED-ONE"])

    async with running(config, fills):
        await fills.send_fill(**dict(FILL, order_id="blocked"))
        await fills.send_fill(**dict(FILL, order_id="ok",
                                     market_ticker="ALLOWED-ONE"))
        orders = await wait_for_orders(rest, 1)

    assert len(orders) == 1
    assert orders[0][1]["ticker"] == "ALLOWED-ONE"


async def test_sells_are_skipped_when_copy_sells_is_off(servers, make_config):
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50, copy_sells=False)

    async with running(config, fills):
        await fills.send_fill(**dict(FILL, action="sell", order_id="s1"))
        await asyncio.sleep(0.4)
        await fills.send_fill(**dict(FILL, action="buy", order_id="b1"))
        orders = await wait_for_orders(rest, 1)

    assert len(orders) == 1
    assert orders[0][1]["action"] == "buy"


async def test_daily_notional_cap_pauses_copying(servers, make_config):
    """10 contracts @ 42c = $4.20 of master notional per fill; a $5 cap must
    let the first through and pause before the second."""
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50, daily_max_notional=5)

    async with running(config, fills) as copier:
        await fills.send_fill(**dict(FILL, order_id="first"))
        await wait_for_orders(rest, 1)
        await fills.send_fill(**dict(FILL, order_id="second"))
        await asyncio.sleep(0.5)

    assert len(rest.orders) == 1
    assert copier.paused_reason and "daily notional" in copier.paused_reason


async def test_single_oversized_fill_cannot_blow_through_the_cap(servers,
                                                                 make_config):
    """A lone fill worth more than the whole daily cap must be refused, not
    copied in full and paused afterwards."""
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50, daily_max_notional=5)

    async with running(config, fills):
        await fills.send_fill(**dict(FILL, count=500))    # $210 against a $5 cap
        await asyncio.sleep(0.5)

    assert rest.orders == []


async def test_a_new_day_lifts_a_cap_induced_pause(servers, make_config):
    """Once tripped, the cap must not wedge the copier permanently."""
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50, daily_max_notional=5)

    async with running(config, fills) as copier:
        await fills.send_fill(**dict(FILL, order_id="first"))
        await wait_for_orders(rest, 1)
        await fills.send_fill(**dict(FILL, order_id="second"))
        await asyncio.sleep(0.4)
        assert copier.paused_reason                       # capped out

        copier._day = "1970-01-01"                        # pretend a day passed
        await fills.send_fill(**dict(FILL, order_id="third"))
        orders = await wait_for_orders(rest, 2)

    assert len(orders) == 2
    assert copier.paused_reason is None


async def test_follower_scaling_to_zero_is_skipped_not_rounded_up(servers,
                                                                  make_config):
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 0.01}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50)

    async with running(config, fills):
        await fills.send_fill(**dict(FILL, count=10))   # 0.1 -> 0
        await asyncio.sleep(0.5)

    assert rest.orders == []


# ---------------------------------------------------------------- resilience


async def test_one_failing_follower_does_not_block_the_others(servers,
                                                              make_config,
                                                              accounts):
    rest, fills = servers
    rest.reject_orders_from(accounts["follower1"]["key_id"])
    config = make_config(
        followers=[{"account": "follower1", "multiplier": 1},
                   {"account": "follower2", "multiplier": 1}],
        api_base=rest.api_base, ws_url=fills.ws_url, aggregation_ms=50)

    async with running(config, fills) as copier:
        await fills.send_fill(**FILL)
        await wait_for_orders(rest, 1)

    # follower2's order still landed even though follower1 was rejected
    assert rest.orders_for(accounts["follower2"]["key_id"])
    assert not rest.orders_for(accounts["follower1"]["key_id"])
    assert copier.paused_reason is None      # a rejection must not pause copying


async def test_malformed_fill_messages_are_ignored(servers, make_config):
    rest, fills = servers
    config = make_config(followers=[{"account": "follower1", "multiplier": 1}],
                         api_base=rest.api_base, ws_url=fills.ws_url,
                         aggregation_ms=50)

    async with running(config, fills):
        await fills.send_fill(**dict(FILL, count=0))            # nothing filled
        await fills.send_fill(**{k: v for k, v in FILL.items()  # no order id
                                 if k != "order_id"})
        await asyncio.sleep(0.4)
        await fills.send_fill(**dict(FILL, order_id="good"))    # still alive
        orders = await wait_for_orders(rest, 1)

    assert len(orders) == 1
