"""Module for base Trading API base websocket chanel."""


class Base(object):
    """Class for base Trading API websocket chanel."""

    # pylint: disable=too-few-public-methods

    def __init__(self, api):

        self.api = api

    def send_websocket_request(self, name, msg, request_id=""):

        return self.api.send_websocket_request(name, msg, request_id)
