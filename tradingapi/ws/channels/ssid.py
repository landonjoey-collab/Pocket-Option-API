from tradingapi.ws.channels.base import Base


class Ssid(Base):
    """Class for Trading API API ssid websocket chanel."""
    # pylint: disable=too-few-public-methods

    name = "ssid"

    def __call__(self, ssid):
        self.send_websocket_request(self.name, ssid)
