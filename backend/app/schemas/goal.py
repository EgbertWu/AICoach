"""
用户目标 Pydantic 模式 (UserGoal Schemas)

设计意图：
    定义 UserGoal 在 API 层的数据契约（Contract）。

增量升级说明：
    - UserGoalResponse 新增 goal_type / roadmap_summary 字段
    - 新增 UserPreferencesResponse / UserPreferencesUpdate 模式
    改动原因：前端需要展示目标类型和路线图摘要，需要读写用户偏好。
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class UserGoalCreate(BaseModel):
    """
    创建目标的请求体模式。
    """
    content: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="用户的目标内容（自然语言），至少 1 个字符，最多 2000 字符",
        examples=["我希望在一个月内学会 Python 基础，能够独立编写简单的数据处理脚本"],
    )


class UserGoalResponse(BaseModel):
    """
    目标的响应体模式。

    增量字段：
    - goal_type: 目标类型（daily / long_term）
    - roadmap_summary: 路线图摘要（仅 long_term 有值）
    - target_duration_days: 长期目标天数
    - start_date: 长期目标开始日期
    """
    id: int = Field(..., description="目标唯一标识")
    user_id: int = Field(..., description="所属用户 ID")
    content: str = Field(..., description="目标内容")
    created_at: datetime = Field(..., description="目标创建时间")
    goal_type: str = Field("daily", description="目标类型：daily / long_term")
    roadmap_summary: str | None = Field(None, description="路线图摘要（长期目标专用）")
    target_duration_days: int | None = Field(None, description="长期目标天数")
    start_date: date | None = Field(None, description="长期目标开始日期")

    model_config = {"from_attributes": True}


class UserGoalWithTasksResponse(BaseModel):
    """
    包含任务列表的目标响应体。
    """
    id: int = Field(..., description="目标唯一标识")
    user_id: int = Field(..., description="所属用户 ID")
    content: str = Field(..., description="目标内容")
    created_at: datetime = Field(..., description="目标创建时间")
    goal_type: str = Field("daily", description="目标类型：daily / long_term")
    roadmap_summary: str | None = Field(None, description="路线图摘要")
    target_duration_days: int | None = Field(None, description="长期目标天数")
    start_date: date | None = Field(None, description="长期目标开始日期")
    tasks: list["TaskResponse"] = Field(default_factory=list, description="关联的任务列表")

    model_config = {"from_attributes": True}


# ===== 用户偏好模式 =====
# 改动原因：前端需要读写偏好并持久化

class UserPreferencesResponse(BaseModel):
    """用户偏好响应体。"""
    quiet_hours_start: str = Field("23:00", description="休息开始时间")
    quiet_hours_end: str = Field("06:00", description="休息结束时间")
    allow_quiet_hours: bool = Field(False, description="是否允许在休息时间安排任务")
    timezone: str = Field("Asia/Shanghai", description="用户时区")

    model_config = {"from_attributes": True}


class UserPreferencesUpdate(BaseModel):
    """用户偏好更新请求体。所有字段可选。"""
    quiet_hours_start: str | None = Field(None, description="休息开始时间（HH:MM）")
    quiet_hours_end: str | None = Field(None, description="休息结束时间（HH:MM）")
    allow_quiet_hours: bool | None = Field(None, description="是否允许在休息时间安排任务")
    timezone: str | None = Field(None, description="用户时区")


# 延迟导入避免循环引用
from app.schemas.task import TaskResponse  # noqa: E402

UserGoalWithTasksResponse.model_rebuild()
