"""Centralized logging configuration for the application."""

import logging
import sys


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the application logger.

    Sets up a consistent log format across the entire application
    with timestamps, log level, module name, and the message.

    Args:
        level: The log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        The configured root application logger.
    """
    log_format = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    logger = logging.getLogger("fleximarket")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.addHandler(handler)

    # Prevent duplicate logs if called multiple times
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the fleximarket namespace.

    Usage:
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Processing settlement file")

    Args:
        name: Usually __name__ of the calling module.

    Returns:
        A child logger with the given name.
    """
    return logging.getLogger(f"fleximarket.{name}")
