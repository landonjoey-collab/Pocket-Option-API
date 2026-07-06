"""Authenticated WebSocket listener for the master account's `fill` channel.

Every executed trade on the master account arrives here in real time,
regardless of whether it was placed in the app, on the website, or by a bot.
"""

import asyncio
import json

import websockets

from kalshi_copier.rest import ENVIRONMENTS

WS_SIGNED_PATH = "/trade-api/ws/v2"


class KalshiFillListener:
    def __init__(self, signer, environment="demo", ws_url=None, on_fill=None):
        self.signer = signer
        self.url = ws_url or ENVIRONMENTS[environment]["ws"]
        self.on_fill = on_fill
        self.connected = asyncio.Event()
        self._closing = False
        self._runner = None

    async def start(self):
        self._runner = asyncio.create_task(self._run_forever(), name="kalshi-fills")
        await asyncio.wait_for(self.connected.wait(), timeout=30)

    async def close(self):
        self._closing = True
        if self._runner:
            self._runner.cancel()

    async def _run_forever(self):
        backoff = 1
        while not self._closing:
            try:
                headers = self.signer.headers("GET", WS_SIGNED_PATH)
                async with websockets.connect(
                    self.url, additional_headers=headers, ping_interval=10,
                ) as ws:
                    backoff = 1
                    await ws.send(json.dumps({
                        "id": 1,
                        "cmd": "subscribe",
                        "params": {"channels": ["fill"]},
                    }))
                    async for raw in ws:
                        await self._on_message(raw)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                self.connected.clear()
                self._log(f"fill stream error ({exc}); reconnecting in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _on_message(self, raw):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        mtype = msg.get("type")
        if mtype == "subscribed":
            self.connected.set()
            self._log("subscribed to master fill stream")
        elif mtype == "fill":
            fill = msg.get("msg", {})
            if self.on_fill:
                result = self.on_fill(fill)
                if asyncio.iscoroutine(result):
                    await result
        elif mtype == "error":
            self._log(f"server error: {msg.get('msg')}")

    @staticmethod
    def _log(text):
        print(f"[fills] {text}", flush=True)
