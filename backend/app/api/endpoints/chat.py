"""
聊天会话 API 端点

改动原因：
    聊天只是交互层，真正生成必须走现有可靠的计划生成与落库流程。
    提供 Chat 会话的 CRUD + 对话推理 + 定稿生成计划的完整流程。
"""

import json
import logging
from datetime import date as date_type, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.chat_planner import ChatPlannerAgent
from app.agents.dispatch_service import dispatch_daily_tasks
from app.agents.planner import PlannerAgent
from app.agents.roadmap_agent import RoadmapAgent
from app.api.dependencies import get_current_user, get_db
from app.core.time_prefs import normalize_planned_window
from app.db.models.chat import ChatMessage, ChatSession, PlanMode, SessionStatus
from app.db.models.task import Task, TaskStatus
from app.db.models.user import User
from app.db.models.user_goal import GoalType, UserGoal
from app.schemas.chat import (
    ChatFinalizeResponse,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionListItem,
    ChatStepResponse,
    SessionState,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/sessions", response_model=ChatSessionListItem)
async def create_session(
    body: ChatSessionCreate | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建新的聊天会话。

    改动原因：用户开始新的对话时需要创建会话记录。
    """
    session = ChatSession(
        user_id=current_user.id,
        title=body.title if body else None,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info("创建聊天会话: session_id=%d, user_id=%d", session.id, current_user.id)
    return ChatSessionListItem.model_validate(session)


@router.get("/sessions", response_model=list[ChatSessionListItem])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    返回当前用户的会话列表（按更新时间倒序）。

    改动原因：左侧历史对话列表需要展示所有会话。
    """
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [ChatSessionListItem.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    返回指定会话的详情（含消息列表）。

    改动原因：打开历史会话时需要加载完整对话上下文。
    """
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")

    return ChatSessionDetail.model_validate(session)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    删除指定会话及其所有消息。

    改动原因：用户需要管理历史会话，清理不需要的对话记录。
    """
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")

    # 先删除关联消息，再删除会话
    await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    msg_result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    for msg in msg_result.scalars().all():
        await db.delete(msg)
    await db.delete(session)
    await db.commit()
    return {"message": "会话已删除"}


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    重命名指定会话。

    改动原因：用户需要自定义会话标题以便区分不同对话。
    """
    new_title = body.get("title")
    if not new_title or not isinstance(new_title, str) or not new_title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")

    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")

    session.title = new_title.strip()[:50]
    await db.commit()
    return {"message": "会话已重命名", "title": session.title}


@router.post("/sessions/{session_id}/messages", response_model=ChatStepResponse)
async def send_message(
    session_id: int,
    body: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    发送消息并获取助手回复。

    改动原因：核心对话交互——写入用户消息 -> 调用 ChatPlannerAgent -> 写入助手消息 -> 返回状态。
    """
    # 1. 查询并验证会话
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")

    if session.status == SessionStatus.FINALIZED:
        raise HTTPException(status_code=400, detail="该会话已定稿，无法继续对话")

    # 2. 保存用户消息
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=body.content,
    )
    db.add(user_msg)
    await db.flush()

    # 3. 获取完整对话历史
    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    all_messages = msg_result.scalars().all()
    session_messages = [{"role": m.role, "content": m.content} for m in all_messages]

    # 4. 构造用户偏好
    user_prefs = {
        "quiet_hours_start": current_user.quiet_hours_start,
        "quiet_hours_end": current_user.quiet_hours_end,
        "allow_quiet_hours": current_user.allow_quiet_hours,
        "timezone": current_user.timezone,
    }

    # 4.5 检测当前是否有进行中的计划（互斥原则）
    # 改动原因：同一时间不能有多个计划，需要在聊天阶段就提醒用户
    conflict_warning: str | None = None
    from datetime import date as date_type
    from sqlalchemy import or_
    today = date_type.today()
    active_plan_result = await db.execute(
        select(UserGoal.id, UserGoal.content, UserGoal.goal_type)
        .where(UserGoal.user_id == current_user.id)
        .order_by(UserGoal.created_at.desc())
        .limit(1)
    )
    latest_goal = active_plan_result.first()
    if latest_goal:
        # 检查该目标下是否有未完成的任务（含今天排期或无排期的日计划任务）
        pending_count_result = await db.execute(
            select(func.count(Task.id))
            .join(UserGoal, Task.goal_id == UserGoal.id)
            .where(
                UserGoal.user_id == current_user.id,
                Task.status == TaskStatus.PENDING,
                or_(
                    Task.scheduled_date == today,
                    Task.scheduled_date.is_(None),
                ),
            )
        )
        pending_count = pending_count_result.scalar() or 0
        if pending_count > 0:
            conflict_warning = (
                f"你今天还有 {pending_count} 个未完成的任务"
                f"（来自计划「{latest_goal.content[:30]}」）。"
                f"继续生成新计划将替换当前计划。你可以先完成现有任务，或在 Dashboard 中管理。"
            )
            # 将冲突信息注入 user_prefs，让 LLM 在对话中提醒用户
            user_prefs["conflict_warning"] = conflict_warning

    # 5. 调用 ChatPlannerAgent
    agent = ChatPlannerAgent()
    try:
        step_result = await agent.step(session_messages, user_prefs)
    except RuntimeError as e:
        logger.error("ChatPlannerAgent 调用失败: %s", e)
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {e}") from e
    except ValueError as e:
        logger.error("ChatPlannerAgent 解析失败: %s", e)
        raise HTTPException(status_code=500, detail=f"AI 返回了无法解析的内容: {e}") from e

    # 6. 保存助手消息
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=step_result["assistant_text"],
    )
    db.add(assistant_msg)

    # 7. 更新会话状态
    if step_result.get("plan_mode") and step_result["plan_mode"] != "unknown":
        session.plan_mode = PlanMode(step_result["plan_mode"])

    # 自动生成标题（取首条用户消息的前 30 字符）
    if not session.title and session_messages:
        first_user_msg = next((m["content"] for m in session_messages if m["role"] == "user"), None)
        if first_user_msg:
            session.title = first_user_msg[:30] + ("..." if len(first_user_msg) > 30 else "")

    await db.commit()

    # 8. 构造响应
    extracted = step_result.get("extracted", {})
    session_state = SessionState(
        plan_mode=step_result.get("plan_mode", "unknown"),
        ready_to_finalize=step_result.get("ready_to_finalize", False),
        next_questions=step_result.get("next_questions", []),
        goal_summary=extracted.get("goal_summary"),
        allow_quiet_hours=extracted.get("allow_quiet_hours"),
        conflict_warning=conflict_warning,
    )

    return ChatStepResponse(
        assistant_message=step_result["assistant_text"],
        session_state=session_state,
    )


@router.post("/sessions/{session_id}/finalize", response_model=ChatFinalizeResponse)
async def finalize_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    定稿会话并生成计划。

    改动原因：对话只是交互层，真正生成必须复用现有可靠的计划生成与落库流程。
    - daily：复用 PlannerAgent 生成当天任务
    - long_term：复用 RoadmapAgent + dispatch_today 能力
    """
    # 1. 查询并验证会话
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")

    if session.status == SessionStatus.FINALIZED:
        raise HTTPException(status_code=400, detail="该会话已定稿")

    # 2. 获取对话历史
    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    all_messages = msg_result.scalars().all()
    session_messages = [{"role": m.role, "content": m.content} for m in all_messages]

    # 3. 提取最终约束
    agent = ChatPlannerAgent()
    try:
        constraints = await agent.extract_final_constraints(session_messages)
    except Exception as e:
        logger.warning("约束提取失败，使用降级方案: %s", e)
        user_messages = [m.content for m in all_messages if m.role == "user"]
        constraints = {
            "goal_summary": user_messages[0][:500] if user_messages else "用户目标",
            "duration_days": None,
            "start_date": date_type.today().isoformat(),
            "allow_quiet_hours": False,
        }

    goal_summary = constraints.get("goal_summary", "用户目标")
    duration_days = constraints.get("duration_days")
    allow_quiet_hours = constraints.get("allow_quiet_hours", False)

    # 判断计划模式：优先使用会话已判断的模式，否则根据 duration_days 推断
    plan_mode = session.plan_mode
    if plan_mode == PlanMode.UNKNOWN:
        if duration_days and duration_days > 1:
            plan_mode = PlanMode.LONG_TERM
        else:
            plan_mode = PlanMode.DAILY

    # 4. 根据模式生成计划（复用现有逻辑）
    any_adjusted = False
    all_reasons: list[str] = []
    saved_tasks: list[Task] = []

    if plan_mode == PlanMode.LONG_TERM:
        # 长期计划：Roadmap + 今日派发
        if not duration_days:
            duration_days = 30

        today = date_type.today()

        try:
            roadmap_data = await RoadmapAgent.generate_roadmap(goal_summary, duration_days)
        except (ValueError, RuntimeError) as e:
            logger.error("Roadmap 生成失败: %s", e)
            raise HTTPException(status_code=502, detail=f"AI 生成路线图失败: {e}") from e

        roadmap_data["start_date"] = today.isoformat()

        try:
            summary = await RoadmapAgent.generate_summary(roadmap_data)
        except Exception as e:
            logger.warning("摘要生成失败，使用降级方案: %s", e)
            summary = f"长期计划：{roadmap_data.get('title', '未知')}，共 {duration_days} 天"

        user_goal = UserGoal(
            content=goal_summary,
            user_id=current_user.id,
            goal_type=GoalType.LONG_TERM,
            target_duration_days=duration_days,
            start_date=today,
            roadmap_json=json.dumps(roadmap_data, ensure_ascii=False),
            roadmap_summary=summary,
        )
        db.add(user_goal)
        await db.flush()

        try:
            task_dicts = await dispatch_daily_tasks(
                roadmap_json=roadmap_data,
                target_date=today,
                quiet_hours_start=current_user.quiet_hours_start,
                quiet_hours_end=current_user.quiet_hours_end,
                allow_quiet_hours=current_user.allow_quiet_hours or allow_quiet_hours,
            )
        except (ValueError, RuntimeError) as e:
            logger.error("每日派发失败: %s", e)
            raise HTTPException(status_code=502, detail=f"AI 派发今日任务失败: {e}") from e

        for task_dict in task_dicts:
            task = Task(
                goal_id=user_goal.id,
                description=task_dict["description"],
                criteria=task_dict["criteria"],
                planned_start_at=datetime.fromisoformat(task_dict["planned_start_at"]) if task_dict.get("planned_start_at") else None,
                planned_end_at=datetime.fromisoformat(task_dict["planned_end_at"]) if task_dict.get("planned_end_at") else None,
                scheduled_date=today,
            )
            db.add(task)
            saved_tasks.append(task)

            if task_dict.get("time_adjusted"):
                any_adjusted = True
                if task_dict.get("adjusted_reason"):
                    all_reasons.append(task_dict["adjusted_reason"])

        redirect_hint = "已创建长期计划，系统将每日自动派发今日任务"

    else:
        # 每日计划：直接使用 PlannerAgent，传入完整对话上下文
        # 改动原因：让 PlannerAgent 参考对话中的具体安排（如"今晚看视频"），
        # 而不是仅凭一句话摘要生成脱离实际的计划
        conversation_context = "\n".join(
            f"[{m.role}]: {m.content}" for m in all_messages
        )
        planner = PlannerAgent()
        try:
            task_dicts = await planner.generate_tasks_from_goal(
                goal_summary,
                context=conversation_context,
                quiet_hours_start=current_user.quiet_hours_start,
                quiet_hours_end=current_user.quiet_hours_end,
            )
        except RuntimeError as e:
            logger.error("计划生成失败: %s", e)
            raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {e}") from e
        except ValueError as e:
            logger.error("计划生成失败: %s", e)
            raise HTTPException(status_code=500, detail=f"AI 返回了无法解析的内容: {e}") from e

        user_goal = UserGoal(
            content=goal_summary,
            user_id=current_user.id,
            goal_type=GoalType.DAILY,
        )
        db.add(user_goal)
        await db.flush()

        for task_dict in task_dicts:
            # 应用 quiet hours 兜底
            start_at = datetime.fromisoformat(task_dict["planned_start_at"]) if task_dict.get("planned_start_at") else None
            end_at = datetime.fromisoformat(task_dict["planned_end_at"]) if task_dict.get("planned_end_at") else None

            new_start, new_end, adjusted, reason = normalize_planned_window(
                planned_start_at=start_at,
                planned_end_at=end_at,
                quiet_hours_start=current_user.quiet_hours_start,
                quiet_hours_end=current_user.quiet_hours_end,
                allow_quiet_hours=current_user.allow_quiet_hours or allow_quiet_hours,
                timezone_str=current_user.timezone,
            )

            if adjusted:
                any_adjusted = True
                all_reasons.append(reason)
                task_dict["planned_start_at"] = new_start.isoformat() if new_start else None
                task_dict["planned_end_at"] = new_end.isoformat() if new_end else None

            task = Task(
                goal_id=user_goal.id,
                description=task_dict["description"],
                criteria=task_dict["criteria"],
                planned_start_at=new_start,
                planned_end_at=new_end,
            )
            db.add(task)
            saved_tasks.append(task)

        redirect_hint = "已生成今日计划"

    # 5. 更新会话状态
    session.status = SessionStatus.FINALIZED
    session.linked_goal_id = user_goal.id

    await db.commit()
    await db.refresh(user_goal)
    for task in saved_tasks:
        await db.refresh(task)

    logger.info(
        "会话定稿成功: session_id=%d, goal_id=%d, mode=%s, tasks=%d",
        session_id, user_goal.id, plan_mode.value, len(saved_tasks),
    )

    return ChatFinalizeResponse(
        goal_id=user_goal.id,
        goal_type=plan_mode.value,
        goal_content=goal_summary,
        roadmap_summary=user_goal.roadmap_summary,
        tasks_count=len(saved_tasks),
        redirect_hint=redirect_hint,
        time_adjusted=any_adjusted,
        adjusted_reason="；".join(all_reasons) if all_reasons else "",
    )
