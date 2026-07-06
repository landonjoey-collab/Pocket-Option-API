"""Lightweight async websocket client for a single Pocket Option account.

Self-contained on purpose: the bundled ``pocketoptionapi`` package keeps all
account state in a module-level singleton (``global_value``), so it can only
ever drive one account per process. The copier needs one master plus N
followers in a single event loop, so each account gets its own instance of
this client instead.

Protocol notes (socket.io v4 over a raw websocket):
  - server greets with ``0{"sid": ...}``           -> reply ``40``
  - server confirms with ``40{"sid": ...}``        -> reply with the SSID auth
  - server pings with ``2``                        -> reply ``3``
  - events arrive as ``451-["eventName",{"_placeholder":true,"num":0}]``
    followed by one binary frame carrying the JSON payload
  - orders are placed with ``42["openOrder",{...}]``
"""

import asyncio
import json
import ssl
import time
import uuid

import websockets

REAL_REGIONS = [
    "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-us-north.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-asia.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-fr.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-hk.po.market/socket.io/?EIO=4&transport=websocket",
]

DEMO_REGIONS = [
    "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket",
]

WS_HEADERS = {
    "Origin": "https://pocketoption.com",
    "Cache-Control": "no-cache",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

PING_INTERVAL = 20
ORDER_TIMEOUT = 10


class OrderError(Exception):
    """The broker rejected an openOrder request."""


def parse_ssid(ssid):
    """Accept the full ``42["auth",{...}]`` string copied from the browser
    (or just the JSON part) and return the auth payload as a dict."""
    raw = ssid.strip()
    if raw.startswith("42"):
        raw = raw[2:]
    try:
        event = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "SSID is not valid JSON. Copy the full auth message from the "
            'browser, e.g. 42["auth",{"session":"...","isDemo":1,...}]'
        ) from exc
    if isinstance(event, list) and len(event) == 2 and event[0] == "auth":
        payload = event[1]
    elif isinstance(event, dict):
        payload = event
    else:
        raise ValueError("Unrecognized SSID format")
    if "session" not in payload:
        raise ValueError('SSID payload is missing the "session" field')
    return payload


class PocketAccountClient:
    """One authenticated Pocket Option websocket session.

    Callbacks (all optional, may be sync or async):
      on_deal_opened(deal: dict)  -- a new deal appeared on this account
      on_deal_closed(deal: dict)  -- a deal finished (deal["profit"] is set)
    """

    def __init__(self, name, ssid, demo=None, on_deal_opened=None, on_deal_closed=None):
        self.name = name
        self.auth_payload = parse_ssid(ssid)
        if demo is None:
            demo = bool(self.auth_payload.get("isDemo", 1))
        self.demo = demo
        self.uid = self.auth_payload.get("uid")
        self.on_deal_opened = on_deal_opened
        self.on_deal_closed = on_deal_closed

        self.balance = None
        self.connected = asyncio.Event()
        self._ws = None
        self._pending_event = None       # name of the 451- event awaiting its binary frame
        self._seen_deal_ids = set()
        self._order_waiters = {}         # requestId -> Future resolved with the deal dict
        self._runner = None
        self._closing = False

    # ------------------------------------------------------------------ setup

    def _auth_message(self):
        return '42["auth",' + json.dumps(self.auth_payload) + "]"

    def _regions(self):
        return DEMO_REGIONS if self.demo else REAL_REGIONS

    async def start(self):
        """Connect and keep the session alive in the background. Returns once
        the account is authenticated."""
        self._runner = asyncio.create_task(self._run_forever(), name=f"po-{self.name}")
        await asyncio.wait_for(self.connected.wait(), timeout=60)

    async def close(self):
        self._closing = True
        if self._runner:
            self._runner.cancel()
        if self._ws:
            await self._ws.close()

    async def _run_forever(self):
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        backoff = 1
        while not self._closing:
            for url in self._regions():
                try:
                    async with websockets.connect(
                        url, ssl=ssl_ctx, additional_headers=WS_HEADERS,
                        ping_interval=None,
                    ) as ws:
                        self._ws = ws
                        backoff = 1
                        ping = asyncio.create_task(self._ping_loop(ws))
                        try:
                            async for message in ws:
                                await self._on_message(message)
                        finally:
                            ping.cancel()
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    self._log(f"connection error ({exc}); trying next server", "WARN")
                finally:
                    self.connected.clear()
                    self._fail_pending_orders("connection lost")
                if self._closing:
                    return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _ping_loop(self, ws):
        while True:
            await asyncio.sleep(PING_INTERVAL)
            await ws.send('42["ps"]')

    # -------------------------------------------------------------- messaging

    async def _on_message(self, message):
        if isinstance(message, bytes):
            await self._on_binary(message)
            return

        if message.startswith("0") and "sid" in message:
            await self._ws.send("40")
        elif message == "2":
            await self._ws.send("3")
        elif message.startswith("40") and "sid" in message:
            await self._ws.send(self._auth_message())
        elif message.startswith("451-["):
            event = json.loads(message.split("-", 1)[1])
            await self._on_event(event[0], event[1] if len(event) > 1 else None)
        elif message.startswith("42"):
            try:
                event = json.loads(message[2:])
            except json.JSONDecodeError:
                return
            if isinstance(event, list) and event and event[0] == "NotAuthorized":
                self._log("NotAuthorized: the SSID is invalid or expired", "ERROR")
                await self._ws.close()

    async def _on_event(self, name, _placeholder):
        if name == "successauth":
            self.connected.set()
            self._log("connected & authenticated", "INFO")
        elif name in ("failopenOrder", "failOrder"):
            self._fail_pending_orders("broker rejected the order")
        # These events carry their JSON in the next binary frame:
        self._pending_event = name

    async def _on_binary(self, raw):
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        event, self._pending_event = self._pending_event, None

        if isinstance(data, dict) and "balance" in data:
            self.balance = data["balance"]
            return

        if event == "successopenOrder" and isinstance(data, dict):
            await self._handle_opened_deal(data)
        elif event == "updateOpenedDeals" and isinstance(data, list):
            for deal in data:
                if isinstance(deal, dict):
                    await self._handle_opened_deal(deal, from_snapshot=True)
        elif event == "successcloseOrder" and isinstance(data, dict):
            for deal in data.get("deals", []):
                await self._emit(self.on_deal_closed, deal)
        elif isinstance(data, dict) and "requestId" in data and "asset" in data:
            # order echo that arrived without a preceding event marker
            await self._handle_opened_deal(data)

    async def _handle_opened_deal(self, deal, from_snapshot=False):
        deal_id = deal.get("id") or deal.get("requestId")
        if deal_id is None or deal_id in self._seen_deal_ids:
            return
        self._seen_deal_ids.add(deal_id)
        if len(self._seen_deal_ids) > 5000:
            self._seen_deal_ids = set(list(self._seen_deal_ids)[-1000:])

        req_id = str(deal.get("requestId", ""))
        waiter = self._order_waiters.pop(req_id, None)
        if waiter and not waiter.done():
            waiter.set_result(deal)

        # The first updateOpenedDeals after connect is a snapshot of deals
        # opened before we were listening -- don't copy those.
        if from_snapshot and not self._was_just_opened(deal):
            return
        await self._emit(self.on_deal_opened, deal)

    @staticmethod
    def _was_just_opened(deal, window=10):
        opened = deal.get("openTimestamp") or deal.get("openTime")
        if isinstance(opened, (int, float)):
            return time.time() - opened <= window
        return False

    async def _emit(self, callback, deal):
        if callback is None:
            return
        try:
            result = callback(deal)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            self._log(f"callback error: {exc}", "ERROR")

    def _fail_pending_orders(self, reason):
        waiters, self._order_waiters = self._order_waiters, {}
        for waiter in waiters.values():
            if not waiter.done():
                waiter.set_exception(OrderError(reason))

    # ----------------------------------------------------------------- orders

    async def place_order(self, asset, amount, direction, duration):
        """Open a binary option. direction is "call" or "put", duration in
        seconds. Returns the deal dict echoed by the broker."""
        if not self.connected.is_set():
            raise OrderError(f"{self.name} is not connected")
        req_id = uuid.uuid4().hex[:12]
        order = {
            "asset": asset,
            "amount": round(float(amount), 2),
            "action": direction,
            "isDemo": int(self.demo),
            "requestId": req_id,
            "optionType": 100,
            "time": int(duration),
        }
        waiter = asyncio.get_running_loop().create_future()
        self._order_waiters[req_id] = waiter
        await self._ws.send('42["openOrder",' + json.dumps(order) + "]")
        try:
            return await asyncio.wait_for(waiter, timeout=ORDER_TIMEOUT)
        except asyncio.TimeoutError:
            raise OrderError(f"{self.name}: no confirmation within {ORDER_TIMEOUT}s")
        finally:
            self._order_waiters.pop(req_id, None)

    # ------------------------------------------------------------------- misc

    def _log(self, msg, level="INFO"):
        print(f"[{time.strftime('%H:%M:%S')}] [{level}] [{self.name}] {msg}", flush=True)
