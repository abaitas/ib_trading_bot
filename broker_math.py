"""
Pure broker logic: MA computation, trading hours parsing.
No ib_async dependency — safe to import in CI tests.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import pandas as pd

from config import NYC_TZ


def compute_ma_from_bars(
    bars: list[dict[str, Any]] | pd.DataFrame,
    today_date: date,
    period: int,
) -> tuple[float, float, date, list[float]]:
    """Pure: compute last_close, ma, last_bar_date, closes_for_ma from bars."""
    df = pd.DataFrame(bars) if isinstance(bars, list) else bars
    last_bar_raw = df["date"].iloc[-1]
    if isinstance(last_bar_raw, str):
        last_bar_date = datetime.strptime(last_bar_raw, "%Y%m%d").date()
    else:
        last_bar_date = last_bar_raw

    ma_series = df["close"].rolling(period).mean()
    last_close = float(df["close"].iloc[-1])
    ma = float(ma_series.iloc[-1])
    closes_for_ma = df["close"].iloc[-period:].tolist()
    return last_close, ma, last_bar_date, closes_for_ma


def is_trading_day_from_hours(trading_hours: str, now: datetime) -> bool:
    """True if today has a non-CLOSED session in trading hours string."""
    today_str = now.strftime("%Y%m%d")
    for session in trading_hours.split(";"):
        if not session or ":" not in session:
            continue
        if not session.startswith(today_str):
            continue
        _, hours = session.split(":", 1)
        if hours.upper().strip() == "CLOSED":
            return False
        return True
    return False


def parse_trading_sessions_for_today(
    trading_hours: str, now: datetime
) -> tuple[bool, Optional[datetime]]:
    """Parse trading hours string for today. Returns (is_open, end_time or None)."""
    today_str = now.strftime("%Y%m%d")
    for session in trading_hours.split(";"):
        if not session.startswith(today_str):
            continue
        try:
            date_part, hours = session.split(":", 1)
            if hours.upper() == "CLOSED":
                return False, None
            if "-" not in hours:
                continue
            start_str, end_str = hours.split("-")
            if ":" in end_str:
                end_date, end_hhmm = end_str.split(":", 1)
            else:
                end_date, end_hhmm = date_part, end_str
            start_time = datetime.strptime(
                date_part + start_str, "%Y%m%d%H%M"
            ).replace(tzinfo=NYC_TZ)
            end_time = datetime.strptime(
                end_date + end_hhmm, "%Y%m%d%H%M"
            ).replace(tzinfo=NYC_TZ)
            if start_time <= now <= end_time:
                return True, end_time
        except (ValueError, IndexError):
            continue
    return False, None
