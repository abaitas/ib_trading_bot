"""
Tests for broker pure helper functions (no IB/DB).
Imports from broker_math to avoid ib_async in test chain (CI-safe).
"""
import unittest
from datetime import date, datetime

from config import NYC_TZ
from broker_math import (
    compute_ma_from_bars,
    is_trading_day_from_hours,
    parse_trading_sessions_for_today,
)


def _make_bars(n: int, base_close: float = 100.0, start_date: str = "20250101") -> list:
    """Create mock daily bars compatible with util.df. Dates in YYYYMMDD format."""
    from datetime import datetime, timedelta
    base = datetime.strptime(start_date, "%Y%m%d")
    return [
        {
            "date": (base + timedelta(days=i)).strftime("%Y%m%d"),
            "open": base_close + i,
            "high": base_close + i + 1,
            "low": base_close + i - 1,
            "close": base_close + i * 0.5,
            "volume": 1000,
        }
        for i in range(n)
    ]


class TestComputeMaFromBars(unittest.TestCase):
    def test_returns_last_close_and_ma(self):
        bars = _make_bars(45)
        today = date(2025, 2, 14)
        period = 40
        last_close, ma, last_bar_date, closes = compute_ma_from_bars(bars, today, period)
        assert last_close == 100.0 + 44 * 0.5  # 122.0
        assert isinstance(ma, float)
        assert last_bar_date == date(2025, 2, 14)
        assert len(closes) == period

    def test_ma_is_rolling_mean_of_last_n_closes(self):
        bars = _make_bars(45, base_close=100.0)
        today = date(2025, 2, 14)
        period = 40
        _, ma, _, closes = compute_ma_from_bars(bars, today, period)
        expected_ma = sum(closes) / period
        assert abs(ma - expected_ma) < 0.001

    def test_last_close_matches_last_bar(self):
        bars = _make_bars(50)
        today = date(2025, 2, 19)
        period = 40
        last_close, _, last_bar_date, _ = compute_ma_from_bars(bars, today, period)
        expected_close = 100.0 + 49 * 0.5  # 124.5
        assert last_close == expected_close
        assert last_bar_date == date(2025, 2, 19)

    def test_ma_period_configurable(self):
        bars = _make_bars(30)
        today = date(2025, 1, 30)
        period = 20
        last_close, ma, _, closes = compute_ma_from_bars(bars, today, period)
        assert len(closes) == 20
        assert abs(ma - sum(closes) / 20) < 0.001


class TestIsTradingDayFromHours(unittest.TestCase):
    def test_closed_returns_false(self):
        now = datetime(2025, 2, 17, 10, 0, tzinfo=NYC_TZ)
        trading_hours = "20250217:CLOSED"
        assert is_trading_day_from_hours(trading_hours, now) is False

    def test_open_session_returns_true(self):
        now = datetime(2025, 2, 17, 10, 0, tzinfo=NYC_TZ)
        trading_hours = "20250217:0930-1600"
        assert is_trading_day_from_hours(trading_hours, now) is True

    def test_wrong_date_skipped_returns_false(self):
        now = datetime(2025, 2, 17, 10, 0, tzinfo=NYC_TZ)
        trading_hours = "20250218:0930-1600"  # tomorrow
        assert is_trading_day_from_hours(trading_hours, now) is False

    def test_multiple_sessions_finds_today(self):
        now = datetime(2025, 2, 17, 12, 0, tzinfo=NYC_TZ)
        trading_hours = "20250216:CLOSED;20250217:0930-1600"
        assert is_trading_day_from_hours(trading_hours, now) is True


class TestParseTradingSessionsForToday(unittest.TestCase):
    def test_closed_returns_false_none(self):
        now = datetime(2025, 2, 17, 10, 0, tzinfo=NYC_TZ)
        trading_hours = "20250217:CLOSED"
        is_open, end_time = parse_trading_sessions_for_today(trading_hours, now)
        assert is_open is False
        assert end_time is None

    def test_within_session_returns_true_and_end_time(self):
        now = datetime(2025, 2, 17, 10, 30, tzinfo=NYC_TZ)
        # IB format: YYYYMMDD:HHMM-YYYYMMDD:HHMM
        trading_hours = "20250217:0930-20250217:1600"
        is_open, end_time = parse_trading_sessions_for_today(trading_hours, now)
        assert is_open is True
        assert end_time is not None
        assert end_time.hour == 16
        assert end_time.minute == 0

    def test_same_day_short_format(self):
        """Same-day end without date in end_str: YYYYMMDD:HHMM-HHMM"""
        now = datetime(2025, 2, 17, 10, 30, tzinfo=NYC_TZ)
        trading_hours = "20250217:0930-1600"
        is_open, end_time = parse_trading_sessions_for_today(trading_hours, now)
        assert is_open is True
        assert end_time is not None
        assert end_time.hour == 16
        assert end_time.minute == 0

    def test_before_session_returns_false(self):
        now = datetime(2025, 2, 17, 8, 0, tzinfo=NYC_TZ)
        trading_hours = "20250217:0930-20250217:1600"
        is_open, _ = parse_trading_sessions_for_today(trading_hours, now)
        assert is_open is False

    def test_after_session_returns_false(self):
        now = datetime(2025, 2, 17, 17, 0, tzinfo=NYC_TZ)
        trading_hours = "20250217:0930-20250217:1600"
        is_open, _ = parse_trading_sessions_for_today(trading_hours, now)
        assert is_open is False


if __name__ == "__main__":
    unittest.main()

