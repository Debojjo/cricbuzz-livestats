"""Logging setup shared by the whole project."""

import logging
from logging.handlers import RotatingFileHandler

import config

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes to the console and to ``logs/app.log``."""
    logger = logging.getLogger(name)
    if logger.handlers:  # already configured, avoid duplicate lines
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            config.LOG_DIR / "app.log", maxBytes=500_000, backupCount=2
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Read-only filesystems (some cloud hosts): console logging is enough.
        pass

    logger.propagate = False
    return logger
