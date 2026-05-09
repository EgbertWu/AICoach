"""
复盘报告 Pydantic 模式 (Review Schemas)

设计意图：
    定义 ReviewReport 在 API 层的数据契约。
    支持单日复盘和周期复盘（周报/月报）。
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    """
    复盘报告的创建模式。

    用于校验 Reviewer Agent（LLM）返回的 JSON 数据。
    """
    completion_rate: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="任务完成率（0.0-100.0）",
        examples=[75.0],
    )
    analysis: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="AI 对执行情况的分析",
    )
    suggestions: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="AI 给出的改进建议",
    )


class ReviewResponse(BaseModel):
    """
    复盘报告的响应体模式。
    """
    id: int = Field(..., description="复盘报告唯一标识")
    goal_id: int | None = Field(None, description="关联的目标 ID（周期复盘时为空）")
    period_type: str = Field("daily", description="复盘类型：daily / weekly / monthly")
    period_label: str = Field("", description="周期标签，如 '2026年5月1日-5月7日 周报'")
    completion_rate: float = Field(..., description="任务完成率")
    analysis: str = Field(..., description="AI 执行分析")
    suggestions: str = Field(..., description="AI 改进建议")
    created_at: datetime = Field(..., description="复盘报告创建时间")

    model_config = {"from_attributes": True}
