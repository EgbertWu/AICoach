"""
任务历史记录工具 (Task History Utilities)

设计意图：
    将“写入 TaskEvent 审计表”的逻辑从路由中抽离，形成可复用的核心能力。

改动原因：
    长期任务状态管理需要在多个入口记录事件（派发/新增/编辑/完成/删除/重生成），
    若散落在各个路由中，容易不一致且难以维护。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.task import Task
from app.db.models.task_event import TaskEvent, TaskEventSource, TaskEventType


async def record_task_event(
    db: AsyncSession,
    user_id: int,
    goal_id: int,
    task: Task | None,
    event_type: TaskEventType,
    source: TaskEventSource,
    payload: dict | None = None,
) -> None:
    """
    写入一条任务事件记录。

    改动原因：
        通过统一入口写入 TaskEvent，保证各路由生成的历史记录字段一致。
    """
    event = TaskEvent(
        user_id=user_id,
        goal_id=goal_id,
        task_id=task.id if task else None,
        event_type=event_type,
        source=source,
        scheduled_date=getattr(task, "scheduled_date", None) if task else None,
        description_snapshot=(getattr(task, "description", "") or "")[:1000] if task else "",
        criteria_snapshot=(getattr(task, "criteria", "") or "")[:1000] if task else "",
        payload_json=TaskEvent.build_payload(payload or {}),
    )
    db.add(event)

