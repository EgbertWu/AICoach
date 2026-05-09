"""
时间偏好模块单元测试

改动原因：产品级规则必须可复用、可测试，不散落在路由。
"""

import pytest
from datetime import datetime, time

from app.core.time_prefs import (
    is_within_quiet_hours,
    normalize_planned_window,
    parse_hhmm,
)


class TestParseHhmm:
    """parse_hhmm 函数测试。"""

    def test_normal(self):
        """正常 HH:MM 格式。"""
        assert parse_hhmm("23:00") == time(23, 0)
        assert parse_hhmm("06:30") == time(6, 30)
        assert parse_hhmm("00:00") == time(0, 0)

    def test_invalid_format(self):
        """格式不正确应抛出 ValueError。"""
        with pytest.raises(ValueError):
            parse_hhmm("25:00")
        with pytest.raises(ValueError):
            parse_hhmm("abc")
        with pytest.raises(ValueError):
            parse_hhmm("23")


class TestIsWithinQuietHours:
    """is_within_quiet_hours 函数测试（跨日区间）。"""

    def test_cross_midnight_inside(self):
        """跨日区间 23:00-06:00，22:00 不在区间内。"""
        dt = datetime(2026, 5, 2, 22, 0)
        assert is_within_quiet_hours(dt, "23:00", "06:00") is False

    def test_cross_midnight_start_boundary(self):
        """跨日区间 23:00-06:00，23:00 在区间内。"""
        dt = datetime(2026, 5, 2, 23, 0)
        assert is_within_quiet_hours(dt, "23:00", "06:00") is True

    def test_cross_midnight_midnight(self):
        """跨日区间 23:00-06:00，00:30 在区间内。"""
        dt = datetime(2026, 5, 2, 0, 30)
        assert is_within_quiet_hours(dt, "23:00", "06:00") is True

    def test_cross_midnight_end_boundary(self):
        """跨日区间 23:00-06:00，06:00 在区间内。"""
        dt = datetime(2026, 5, 2, 6, 0)
        assert is_within_quiet_hours(dt, "23:00", "06:00") is True

    def test_cross_midnight_after_end(self):
        """跨日区间 23:00-06:00，07:00 不在区间内。"""
        dt = datetime(2026, 5, 2, 7, 0)
        assert is_within_quiet_hours(dt, "23:00", "06:00") is False

    def test_no_cross_inside(self):
        """不跨日区间 01:00-06:00，03:00 在区间内。"""
        dt = datetime(2026, 5, 2, 3, 0)
        assert is_within_quiet_hours(dt, "01:00", "06:00") is True

    def test_no_cross_outside(self):
        """不跨日区间 01:00-06:00，23:00 不在区间内。"""
        dt = datetime(2026, 5, 2, 23, 0)
        assert is_within_quiet_hours(dt, "01:00", "06:00") is False


class TestNormalizePlannedWindow:
    """normalize_planned_window 函数测试。"""

    def test_allow_quiet_hours(self):
        """允许休息时间安排，不做修正。"""
        start = datetime(2026, 5, 2, 0, 0)
        end = datetime(2026, 5, 2, 1, 30)
        new_start, new_end, adjusted, reason = normalize_planned_window(
            start, end, allow_quiet_hours=True
        )
        assert adjusted is False
        assert new_start == start
        assert new_end == end

    def test_none_times(self):
        """时间窗口为空，无需修正。"""
        new_start, new_end, adjusted, reason = normalize_planned_window(None, None)
        assert adjusted is False
        assert new_start is None
        assert new_end is None

    def test_start_in_quiet_hours(self):
        """开始时间在休息时间内，应修正到 06:00。"""
        start = datetime(2026, 5, 2, 0, 30)
        end = datetime(2026, 5, 2, 9, 0)
        new_start, new_end, adjusted, reason = normalize_planned_window(
            start, end, "23:00", "06:00"
        )
        assert adjusted is True
        assert new_start is not None
        assert new_start.hour == 6
        assert new_start.minute == 0
        assert "休息时间" in reason

    def test_end_in_quiet_hours(self):
        """结束时间在休息时间内，应修正到 23:00。"""
        start = datetime(2026, 5, 2, 20, 0)
        end = datetime(2026, 5, 2, 23, 30)
        new_start, new_end, adjusted, reason = normalize_planned_window(
            start, end, "23:00", "06:00"
        )
        assert adjusted is True
        assert new_end is not None
        assert new_end.hour == 23
        assert new_end.minute == 0

    def test_normal_times(self):
        """正常时间不在休息时间内，不做修正。"""
        start = datetime(2026, 5, 2, 9, 0)
        end = datetime(2026, 5, 2, 10, 30)
        new_start, new_end, adjusted, reason = normalize_planned_window(
            start, end, "23:00", "06:00"
        )
        assert adjusted is False
        assert new_start == start
        assert new_end == end
