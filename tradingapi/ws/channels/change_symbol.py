from tradingapi.ws.channels.base import Base
import time, random


class ChangeSymbol(Base):
    """Class for Trading API change symbol websocket chanel."""
    # pylint: disable=too-few-public-methods

    name = "sendMessage"

    def __call__(self, active_id, interval):

        data_stream = ["changeSymbol", {
            "asset": active_id,
            "period": interval}]

        self.send_websocket_request(self.name, data_stream)
