"""
任务唯一性同步工具 (Task Unique Sync)

设计意图：
    统一维护 task_uniques 表，确保在任务被编辑/重生成后，唯一性指纹仍然正确。

改动原因：
    任务内容可被用户手动修改或被 AI 重生成，若不同步指纹，会导致：
    - 去重失效（旧指纹仍占位）
    - 新任务插入时触发不必要的唯一约束冲突
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.task_fingerprint import task_fingerprint
from app.db.models.task import Task
from app.db.models.task_unique import TaskUnique


async def sync_task_unique(db: AsyncSession, task: Task) -> None:
    """
    同步某个任务的 TaskUnique 记录。

    改动原因：
        将“创建/更新 TaskUnique”逻辑收敛到一个函数，避免在多处路由重复实现且出现不一致。
    """
    fp = task_fingerprint(task.description, task.criteria)

    result = await db.execute(select(TaskUnique).where(TaskUnique.task_id == task.id))
    row = result.scalar_one_or_none()
    if row:
        row.goal_id = task.goal_id
        row.scheduled_date = task.scheduled_date
        row.fingerprint = fp
        return

    db.add(TaskUnique(goal_id=task.goal_id, scheduled_date=task.scheduled_date, task_id=task.id, fingerprint=fp))

