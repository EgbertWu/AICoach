"""
用户偏好 API 端点 (User Preferences Endpoint)

设计意图：
    提供用户偏好（Quiet Hours 等）的读写接口。

改动原因：
    前端需要读写偏好并持久化。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models.user import User
from app.schemas.goal import UserPreferencesResponse, UserPreferencesUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户的偏好设置。

    改动原因：前端需要读取偏好来展示 Quiet Hours 设置。
    """
    # 重新从数据库加载用户（确保拿到最新数据）
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return UserPreferencesResponse(
        quiet_hours_start=user.quiet_hours_start,
        quiet_hours_end=user.quiet_hours_end,
        allow_quiet_hours=user.allow_quiet_hours,
        timezone=user.timezone,
    )


@router.patch("/preferences", response_model=UserPreferencesResponse)
async def update_preferences(
    body: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    更新当前用户的偏好设置。

    改动原因：前端需要写入偏好来持久化 Quiet Hours 设置。
    """
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_fields = body.model_dump(exclude_unset=True)

    if "quiet_hours_start" in update_fields:
        user.quiet_hours_start = update_fields["quiet_hours_start"]
    if "quiet_hours_end" in update_fields:
        user.quiet_hours_end = update_fields["quiet_hours_end"]
    if "allow_quiet_hours" in update_fields:
        user.allow_quiet_hours = update_fields["allow_quiet_hours"]
    if "timezone" in update_fields:
        user.timezone = update_fields["timezone"]

    await db.commit()
    await db.refresh(user)

    logger.info("用户偏好已更新: user_id=%d, changes=%s", user.id, list(update_fields.keys()))

    return UserPreferencesResponse(
        quiet_hours_start=user.quiet_hours_start,
        quiet_hours_end=user.quiet_hours_end,
        allow_quiet_hours=user.allow_quiet_hours,
        timezone=user.timezone,
    )
