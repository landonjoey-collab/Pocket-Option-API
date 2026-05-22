class Base(object):
    """Class for Trading API Base websocket object."""
    # pylint: disable=too-few-public-methods

    def __init__(self):
        self.__name = None

    @property
    def name(self):
        return self.__name
