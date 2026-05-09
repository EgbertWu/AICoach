"""
任务 Pydantic 模式 (Task Schemas)

设计意图：
    定义 Task 在 API 层的数据契约。

增量升级说明：
    - TaskResponse 新增 scheduled_date 字段
    改动原因：前端需要按天筛选任务，长期计划按天派发需要归属字段。
"""

from datetime import date, datetime

from pydantic import BaseModel, Field, computed_field

from app.db.models.task import TaskStatus


class TaskCreate(BaseModel):
    """创建任务的请求体模式。"""
    goal_id: int = Field(..., description="关联的目标 ID")
    description: str = Field(..., min_length=1, max_length=1000, description="任务描述")
    criteria: str = Field(..., min_length=1, max_length=1000, description="完成标准")
    planned_start_at: datetime | None = Field(None, description="计划开始时间")
    planned_end_at: datetime | None = Field(None, description="计划截止时间")
    scheduled_date: date | None = Field(None, description="归属日期（长期计划按天派发专用）")


class TaskUpdate(BaseModel):
    """更新任务的请求体模式（手动编辑）。"""
    description: str | None = Field(None, description="任务描述（做什么）")
    criteria: str | None = Field(None, description="完成标准（怎么算做完）")
    planned_start_at: datetime | None = Field(None, description="计划开始时间")
    planned_end_at: datetime | None = Field(None, description="计划截止时间")


class TaskCompleteRequest(BaseModel):
    """完成任务的请求体模式。"""
    completion_reason: str | None = Field(
        None,
        description="超时完成原因（可选）",
        examples=["被其他事情打断了"],
    )


class TaskResponse(BaseModel):
    """
    任务的响应体模式。

    增量字段：
    - scheduled_date: 归属日期（长期计划按天派发专用）
    """
    id: int = Field(..., description="任务唯一标识")
    goal_id: int = Field(..., description="关联的目标 ID")
    description: str = Field(..., description="任务描述")
    criteria: str = Field(..., description="完成标准")
    status: TaskStatus = Field(..., description="任务状态")
    planned_start_at: datetime | None = Field(None, description="计划开始时间")
    planned_end_at: datetime | None = Field(None, description="计划截止时间")
    completed_at: datetime | None = Field(None, description="实际完成时间")
    completion_reason: str | None = Field(None, description="超时完成原因")
    created_at: datetime = Field(..., description="任务创建时间")
    scheduled_date: date | None = Field(None, description="归属日期（长期计划按天派发专用）")

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[misc]
    @property
    def is_late(self) -> bool:
        """判断任务是否超时。"""
        if not self.planned_end_at:
            return False

        end_at = self.planned_end_at
        if self.planned_start_at and end_at < self.planned_start_at:
            from datetime import timedelta
            end_at = end_at + timedelta(days=1)

        now = datetime.now()

        if self.status != TaskStatus.COMPLETED:
            return now > end_at

        if self.completed_at:
            return self.completed_at > end_at

        return False


class CompleteTaskResponse(BaseModel):
    """完成任务的响应体。"""
    task: TaskResponse = Field(..., description="更新后的任务")
    is_late: bool = Field(False, description="是否超时完成")
    reason_required: bool = Field(False, description="是否需要填写超时原因")


class RegenerateTaskRequest(BaseModel):
    """重新生成任务的请求体。"""
    user_feedback: str | None = Field(
        None,
        description="用户反馈（可选）",
        examples=["太难了，拆小一点"],
    )
