"""A stand-in for Kalshi's REST + WebSocket API, used by the test suite.

It is deliberately strict about authentication: every request must carry a
valid RSA-PSS signature over `timestamp + METHOD + path`, verified against the
public half of the key the client signed with. That makes the tests exercise
kalshi_copier.auth for real instead of mocking it away.
"""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from websockets.asyncio.server import serve

PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                  salt_length=padding.PSS.DIGEST_LENGTH)


def verify_signature(public_key, signature_b64, message):
    """True if signature_b64 is a valid RSA-PSS-SHA256 signature of message."""
    try:
        public_key.verify(base64.b64decode(signature_b64),
                          message.encode("utf-8"), PSS, hashes.SHA256())
        return True
    except (InvalidSignature, ValueError):
        return False


def check_auth_headers(headers, public_keys, method, path):
    """Returns the authenticated key id, or None if the headers don't check out.

    public_keys maps key id -> public key object.
    """
    key_id = headers.get("KALSHI-ACCESS-KEY")
    timestamp = headers.get("KALSHI-ACCESS-TIMESTAMP")
    signature = headers.get("KALSHI-ACCESS-SIGNATURE")
    if not (key_id and timestamp and signature):
        return None
    public_key = public_keys.get(key_id)
    if public_key is None:
        return None
    if not verify_signature(public_key, signature, timestamp + method + path):
        return None
    return key_id


# --------------------------------------------------------------------- REST


class _RestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # keep pytest output clean

    def _reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authenticate(self):
        path = self.path.split("?")[0]
        key_id = check_auth_headers(self.headers, self.server.public_keys,
                                    self.command, path)
        if key_id is None:
            self.server.auth_failures.append((self.command, path))
            self._reply(401, {"error": "invalid signature"})
        return key_id

    def do_GET(self):
        key_id = self._authenticate()
        if key_id is None:
            return
        if self.path.split("?")[0].endswith("/portfolio/balance"):
            self._reply(200, {"balance": self.server.balances.get(key_id, 100_000)})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        key_id = self._authenticate()
        if key_id is None:
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if not self.path.split("?")[0].endswith("/portfolio/orders"):
            self._reply(404, {"error": "not found"})
            return
        if key_id in self.server.reject_keys:
            self._reply(400, {"error": "insufficient balance"})
            return
        self.server.orders.append((key_id, body))
        self._reply(201, {"order": dict(body, order_id=f"ord-{len(self.server.orders)}",
                                        status="executed")})


class FakeRestServer:
    """Records every order it accepts so tests can assert on them."""

    def __init__(self, public_keys):
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _RestHandler)
        self._server.public_keys = public_keys
        self._server.orders = []
        self._server.auth_failures = []
        self._server.balances = {}
        self._server.reject_keys = set()
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def api_base(self):
        host, port = self._server.server_address
        return f"http://{host}:{port}/trade-api/v2"

    @property
    def orders(self):
        return self._server.orders

    @property
    def auth_failures(self):
        return self._server.auth_failures

    def orders_for(self, key_id):
        return [body for kid, body in self._server.orders if kid == key_id]

    def set_balance(self, key_id, cents):
        self._server.balances[key_id] = cents

    def reject_orders_from(self, key_id):
        self._server.reject_keys.add(key_id)


# ---------------------------------------------------------------- WebSocket


class FakeFillServer:
    """Serves the authenticated `fill` channel and lets tests push fills."""

    def __init__(self, public_keys):
        self.public_keys = public_keys
        self.subscribers = set()
        self.rejected = 0
        self._server = None

    async def start(self):
        self._server = await serve(self._handle, "127.0.0.1", 0)
        return self

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    @property
    def ws_url(self):
        sock = next(iter(self._server.sockets))
        host, port = sock.getsockname()[:2]
        return f"ws://{host}:{port}"

    async def _handle(self, websocket):
        headers = websocket.request.headers
        if check_auth_headers(headers, self.public_keys, "GET",
                              "/trade-api/ws/v2") is None:
            self.rejected += 1
            await websocket.close(code=1008, reason="invalid signature")
            return
        try:
            async for raw in websocket:
                msg = json.loads(raw)
                if msg.get("cmd") == "subscribe":
                    self.subscribers.add(websocket)
                    await websocket.send(json.dumps({
                        "id": msg.get("id"),
                        "type": "subscribed",
                        "msg": {"channel": "fill", "sid": 1},
                    }))
        except Exception:
            pass
        finally:
            self.subscribers.discard(websocket)

    async def send_fill(self, **fill):
        """Push one fill message to every subscribed client."""
        payload = json.dumps({"type": "fill", "sid": 1, "msg": fill})
        for ws in list(self.subscribers):
            await ws.send(payload)
