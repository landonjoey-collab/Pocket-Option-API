import logging
import sys
from logging.handlers import RotatingFileHandler
from trading_system import config


def _build_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    log.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)

    fh = RotatingFileHandler(
        config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    fh.setFormatter(fmt)
    log.addHandler(fh)

    return log


log = _build_logger("trading")
