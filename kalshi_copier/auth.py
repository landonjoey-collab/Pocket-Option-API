"""Kalshi API-key authentication.

Every request carries three headers:
    KALSHI-ACCESS-KEY        the API key id
    KALSHI-ACCESS-TIMESTAMP  unix time in milliseconds
    KALSHI-ACCESS-SIGNATURE  base64( RSA-PSS-SHA256( timestamp + METHOD + path ) )

The signed path includes the API prefix (e.g. /trade-api/v2/portfolio/orders)
but never the query string.
"""

import base64
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class KalshiSigner:
    def __init__(self, key_id, private_key_pem):
        """private_key_pem: PEM bytes/str of the RSA private key Kalshi
        generated when the API key was created."""
        self.key_id = key_id
        if isinstance(private_key_pem, str):
            private_key_pem = private_key_pem.encode()
        self._key = serialization.load_pem_private_key(private_key_pem, password=None)

    @classmethod
    def from_file(cls, key_id, private_key_path):
        with open(private_key_path, "rb") as fh:
            return cls(key_id, fh.read())

    def sign(self, text):
        signature = self._key.sign(
            text.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()

    def headers(self, method, path):
        """Auth headers for a request. path must include the /trade-api/...
        prefix and exclude any query string."""
        timestamp = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": self.sign(timestamp + method.upper() + path),
        }
