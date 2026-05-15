import logging
import sys
from logging.handlers import RotatingFileHandler
from quantum_edge import config

_BUILT = False
log: logging.Logger


def _build() -> logging.Logger:
    global _BUILT
    logger = logging.getLogger("qe")
    if _BUILT:
        return logger
    _BUILT = True
    logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    fh = RotatingFileHandler(config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


log = _build()
