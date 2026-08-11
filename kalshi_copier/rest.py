"""Minimal Kalshi Trade API v2 REST client (only what the copier needs)."""

import uuid

import requests

ENVIRONMENTS = {
    "demo": {
        "rest": "https://external-api.demo.kalshi.co/trade-api/v2",
        "ws": "wss://external-api.demo.kalshi.co/trade-api/ws/v2",
    },
    "prod": {
        "rest": "https://api.elections.kalshi.com/trade-api/v2",
        "ws": "wss://api.elections.kalshi.com/trade-api/ws/v2",
    },
}

REQUEST_TIMEOUT = 10


class KalshiApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


class KalshiRestClient:
    def __init__(self, signer, environment="demo", api_base=None):
        self.signer = signer
        self.base = (api_base or ENVIRONMENTS[environment]["rest"]).rstrip("/")
        # everything after the host is part of the signed path
        self._path_prefix = "/" + self.base.split("/", 3)[3]
        self._session = requests.Session()

    def _request(self, method, path, body=None, params=None):
        signed_path = self._path_prefix + path
        headers = self.signer.headers(method, signed_path)
        headers["Content-Type"] = "application/json"
        resp = self._session.request(
            method, self.base + path, json=body, params=params,
            headers=headers, timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code >= 400:
            raise KalshiApiError(resp.status_code, resp.text[:500])
        return resp.json() if resp.text else {}

    # ------------------------------------------------------------- endpoints

    def get_balance(self):
        """Available balance in cents."""
        return self._request("GET", "/portfolio/balance").get("balance")

    def get_exchange_status(self):
        return self._request("GET", "/exchange/status")

    def place_order(self, ticker, action, side, count, order_type="market",
                    yes_price=None, no_price=None, client_order_id=None):
        """Place an order.

        action: "buy" | "sell"        side: "yes" | "no"
        count: number of contracts    order_type: "market" | "limit"
        yes_price/no_price: limit price in cents (limit orders only)
        """
        order = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "count": int(count),
            "type": order_type,
            "client_order_id": client_order_id or str(uuid.uuid4()),
        }
        if order_type == "limit":
            if yes_price is not None:
                order["yes_price"] = int(yes_price)
            elif no_price is not None:
                order["no_price"] = int(no_price)
            else:
                raise ValueError("limit orders need yes_price or no_price")
        return self._request("POST", "/portfolio/orders", body=order)
