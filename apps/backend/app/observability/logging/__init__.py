"""Central logging configuration."""

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once at application startup."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers = [handler]

    # Align uvicorn loggers with our formatting instead of its defaults.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
