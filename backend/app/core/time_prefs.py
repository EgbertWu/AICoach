"""
时间偏好模块 (Time Preferences)

设计意图：
    产品级的时间规则引擎，可复用、可测试，不散落在路由中。
    负责解析 HH:MM 时间、判断是否在休息时间、规范化时间窗口。

改动原因：
    LLM 偶尔会生成违规时间窗，必须有第二道保险确保体验一致。
    所有"会产生/修改 planned 时间窗"的路径都应调用此模块。
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def parse_hhmm(hhmm_str: str) -> time:
    """
    将 HH:MM 格式的字符串解析为 time 对象。

    Args:
        hhmm_str: 时间字符串，格式为 "HH:MM"

    Returns:
        time 对象

    Raises:
        ValueError: 格式不正确时抛出
    """
    parts = hhmm_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"时间格式不正确，期望 HH:MM，得到 '{hhmm_str}'")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"时间值超出范围: {hhmm_str}")
    return time(hour=hour, minute=minute)


def is_within_quiet_hours(
    dt: datetime,
    quiet_start: str,
    quiet_end: str,
    timezone_str: str = "Asia/Shanghai",
) -> bool:
    """
    判断给定时间是否在休息时间（quiet hours）内。

    支持跨日区间，例如 23:00-06:00 表示从晚上 11 点到次日早上 6 点。

    Args:
        dt: 待判断的 datetime（naive 或 aware 均可）
        quiet_start: 休息开始时间，如 "23:00"
        quiet_end: 休息结束时间，如 "06:00"
        timezone_str: 用户时区，默认 "Asia/Shanghai"

    Returns:
        True 表示在休息时间内，False 表示不在
    """
    tz = ZoneInfo(timezone_str)
    # 确保 dt 有时区信息
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)

    start_t = parse_hhmm(quiet_start)
    end_t = parse_hhmm(quiet_end)

    # 提取当前时间（去掉日期和时区，只保留时分）
    current_time = dt.hour * 60 + dt.minute
    start_minutes = start_t.hour * 60 + start_t.minute
    end_minutes = end_t.hour * 60 + end_t.minute

    if start_minutes <= end_minutes:
        # 不跨日的情况，例如 01:00-06:00
        return start_minutes <= current_time <= end_minutes
    else:
        # 跨日的情况，例如 23:00-06:00
        return current_time >= start_minutes or current_time <= end_minutes


def normalize_planned_window(
    planned_start_at: datetime | None,
    planned_end_at: datetime | None,
    quiet_hours_start: str = "23:00",
    quiet_hours_end: str = "06:00",
    allow_quiet_hours: bool = False,
    timezone_str: str = "Asia/Shanghai",
) -> tuple[datetime | None, datetime | None, bool, str]:
    """
    规范化计划时间窗口，确保不落入休息时间。

    当 allow_quiet_hours=False 时，如果时间窗口落入休息时间，
    自动修正到最近的合理区间（06:00-23:00）。

    Args:
        planned_start_at: 计划开始时间
        planned_end_at: 计划截止时间
        quiet_hours_start: 休息开始时间，默认 "23:00"
        quiet_hours_end: 休息结束时间，默认 "06:00"
        allow_quiet_hours: 是否允许在休息时间安排任务，默认 False
        timezone_str: 用户时区，默认 "Asia/Shanghai"

    Returns:
        元组 (new_start, new_end, adjusted, reason)：
        - new_start: 修正后的开始时间
        - new_end: 修正后的截止时间
        - adjusted: 是否进行了修正
        - reason: 修正原因（未修正时为空字符串）
    """
    tz = ZoneInfo(timezone_str)
    quiet_end_time = parse_hhmm(quiet_hours_end)
    quiet_start_time = parse_hhmm(quiet_hours_start)

    adjusted = False
    reason = ""

    def _ensure_aware(dt: datetime) -> datetime:
        """确保 datetime 有时区信息。"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt

    def _to_local_naive(dt: datetime) -> datetime:
        """转换为本地 naive datetime（用于日期操作）。"""
        aware = _ensure_aware(dt)
        local = aware.astimezone(tz)
        return local.replace(tzinfo=None)

    # 时间窗口为空，无需修正
    if planned_start_at is None and planned_end_at is None:
        return None, None, False, ""

    # 允许休息时间安排：不做 quiet hours 修正，但仍统一转成本地 naive，避免时区信息写入 DB 后发生偏移
    if allow_quiet_hours:
        return (
            _to_local_naive(planned_start_at) if planned_start_at is not None else None,
            _to_local_naive(planned_end_at) if planned_end_at is not None else None,
            False,
            "",
        )

    # 处理开始时间
    new_start = planned_start_at
    if planned_start_at is not None:
        local_start = _to_local_naive(planned_start_at)
        if is_within_quiet_hours(local_start, quiet_hours_start, quiet_hours_end, timezone_str):
            # 修正到休息结束时间（如 06:00）
            new_start = datetime.combine(
                local_start.date(),
                quiet_end_time,
                tzinfo=tz,
            )
            adjusted = True
            reason = f"任务开始时间 {local_start.strftime('%H:%M')} 落入休息时间 ({quiet_hours_start}-{quiet_hours_end})，已自动调整到 {quiet_hours_end}"

    # 处理结束时间
    new_end = planned_end_at
    if planned_end_at is not None:
        local_end = _to_local_naive(planned_end_at)
        if is_within_quiet_hours(local_end, quiet_hours_start, quiet_hours_end, timezone_str):
            # 修正到休息开始时间（如 23:00）
            new_end = datetime.combine(
                local_end.date(),
                quiet_start_time,
                tzinfo=tz,
            )
            adjusted = True
            if reason:
                reason += f"，结束时间调整到 {quiet_hours_start}"
            else:
                reason = f"任务结束时间 {local_end.strftime('%H:%M')} 落入休息时间 ({quiet_hours_start}-{quiet_hours_end})，已自动调整到 {quiet_hours_start}"

    # 确保修正后 start < end
    if new_start is not None and new_end is not None:
        aware_start = _ensure_aware(new_start)
        aware_end = _ensure_aware(new_end)
        if aware_start >= aware_end:
            # 如果修正后开始时间 >= 结束时间，将结束时间延后到休息开始时间
            new_end = datetime.combine(
                _to_local_naive(new_start).date(),
                quiet_start_time,
                tzinfo=tz,
            )
            if not adjusted:
                adjusted = True
                reason = "时间窗口修正后开始时间不早于结束时间，已自动调整结束时间"

    # 统一转成本地 naive（数据库字段为 naive DateTime），避免前端/后端混用带时区的 ISO 串导致时间偏移
    return (
        _to_local_naive(new_start) if new_start is not None else None,
        _to_local_naive(new_end) if new_end is not None else None,
        adjusted,
        reason,
    )
