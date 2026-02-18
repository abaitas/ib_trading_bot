"""
Logging setup: daily file, console, NYC timestamps.
"""
import logging
import os
from datetime import datetime

from config import NYC_TZ


class NYCFormatter(logging.Formatter):
    """Format log timestamps in America/New_York timezone."""

    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self.NYC_TZ = NYC_TZ

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=self.NYC_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


class SuppressOrderCanceledFilter(logging.Filter):
    """Suppress IB Error 202 (Order Canceled) — expected when we cancel orders."""

    def filter(self, record):
        msg = record.getMessage()
        if "Error 202" in msg and "Order Canceled" in msg:
            return False
        return True


def setup_daily_logger(log_dir="logs"):
    """Configure daily logger with file + console, NYC timestamps."""
    os.makedirs(log_dir, exist_ok=True)
    log_filename = datetime.now(NYC_TZ).strftime("%Y-%m-%d") + ".log"
    log_path = os.path.join(log_dir, log_filename)

    logger = logging.getLogger("daily_logger")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        formatter = NYCFormatter(
            "| %(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = logging.FileHandler(log_path, mode="a")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        db_logger = logging.getLogger("db")
        db_logger.setLevel(logging.INFO)
        if not db_logger.handlers:
            db_logger.addHandler(file_handler)
            db_logger.addHandler(console_handler)

        ib_wrapper = logging.getLogger("ib_async.wrapper")
        ib_wrapper.addFilter(SuppressOrderCanceledFilter())

    return logger
