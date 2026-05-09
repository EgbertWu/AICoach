"""
目标类型识别模块 (Goal Type Classifier)

设计意图：
    根据用户输入的目标文本，自动判断是每日目标还是长期目标。
    保持交互顺滑，用户只需输入一句话，系统自动升级为长期模式。

改动原因：
    避免让用户手动选择目标类型，降低使用门槛。
"""

import re

from app.db.models.user_goal import GoalType


# 长期目标关键词（命中任一则判定为 long_term）
_LONG_TERM_KEYWORDS = [
    r"两个?月",
    r"\d+\s*个?月",
    r"\d+\s*周",
    r"8周",
    r"系统学习",
    r"从零到",
    r"长期",
    r"阶段",
    r"路线图",
    r"课程",
    r"计划表",
    r"学习路线",
    r"掌握",
    r"精通",
    r"独立写",
    r"独立开发",
    r"入门到",
    r"零基础",
    r"从入门",
    r"系统学",
    r"完整学",
    r"全面",
]

_LONG_TERM_PATTERN = re.compile("|".join(_LONG_TERM_KEYWORDS), re.IGNORECASE)


def classify_goal(goal_text: str) -> tuple[GoalType, int | None]:
    """
    根据目标文本判断目标类型并推荐持续天数。

    Args:
        goal_text: 用户输入的目标文本

    Returns:
        元组 (goal_type, recommended_duration_days)：
        - goal_type: daily 或 long_term
        - recommended_duration_days: 推荐天数（仅 long_term 有值）

    示例：
        >>> classify_goal("我要学Python，目标是两个月能独立写数据处理脚本")
        (GoalType.LONG_TERM, 60)
        >>> classify_goal("今天把简历改完")
        (GoalType.DAILY, None)
    """
    if not goal_text or not goal_text.strip():
        return GoalType.DAILY, None

    if _LONG_TERM_PATTERN.search(goal_text):
        # 尝试从文本中提取具体天数
        duration = _extract_duration(goal_text)
        return GoalType.LONG_TERM, duration

    return GoalType.DAILY, None


def _extract_duration(text: str) -> int | None:
    """
    从目标文本中提取持续天数。

    优先级：具体月数 > 具体周数 > 默认 30 天

    Args:
        text: 目标文本

    Returns:
        推荐天数，如 30/56/60 等
    """
    # 匹配 "X个月"
    month_match = re.search(r"(\d+)\s*个?月", text)
    if month_match:
        months = int(month_match.group(1))
        return months * 30

    # 匹配 "X周"
    week_match = re.search(r"(\d+)\s*周", text)
    if week_match:
        weeks = int(week_match.group(1))
        return weeks * 7

    # 默认 30 天
    return 30
