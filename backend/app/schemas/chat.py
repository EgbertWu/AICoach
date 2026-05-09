"""
聊天会话 Pydantic 模式 (Chat Schemas)

改动原因：
    前端需要基于 session_state 决定是否展示"生成计划"按钮与提示。
    定义 Chat API 的请求/响应数据契约。
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ===== 请求模式 =====

class ChatSessionCreate(BaseModel):
    """创建聊天会话的请求体（可选标题）。"""
    title: str | None = Field(None, max_length=200, description="会话标题（可选）")


class ChatMessageCreate(BaseModel):
    """发送聊天消息的请求体。"""
    content: str = Field(..., min_length=1, max_length=2000, description="用户消息内容")


# ===== 响应模式 =====

class ChatSessionListItem(BaseModel):
    """会话列表项（用于左侧栏展示）。"""
    id: int = Field(..., description="会话 ID")
    title: str | None = Field(None, description="会话标题")
    status: str = Field(..., description="会话状态：active / finalized")
    plan_mode: str = Field(..., description="计划模式：unknown / daily / long_term")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    """单条聊天消息的响应体。"""
    id: int = Field(..., description="消息 ID")
    session_id: int = Field(..., description="所属会话 ID")
    role: str = Field(..., description="消息角色：user / assistant / system")
    content: str = Field(..., description="消息内容")
    created_at: datetime = Field(..., description="创建时间")

    model_config = {"from_attributes": True}


class ChatSessionDetail(BaseModel):
    """会话详情（含消息列表）。"""
    id: int = Field(..., description="会话 ID")
    title: str | None = Field(None, description="会话标题")
    status: str = Field(..., description="会话状态")
    plan_mode: str = Field(..., description="计划模式")
    linked_goal_id: int | None = Field(None, description="关联的目标 ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    messages: list[ChatMessageResponse] = Field(default_factory=list, description="消息列表")

    model_config = {"from_attributes": True}


class ChatStepResponse(BaseModel):
    """
    对话步骤响应（关键模式）。

    改动原因：前端需要基于 session_state 决定是否展示"生成计划"按钮与提示。
    包含 assistant 的回复文本和会话状态信息。
    """
    assistant_message: str = Field(..., description="助手回复文本")
    session_state: "SessionState" = Field(..., description="会话状态信息")


class SessionState(BaseModel):
    """
    会话状态信息。

    改动原因：前端需要根据这些字段决定 UI 展示逻辑。
    """
    plan_mode: str = Field("unknown", description="当前判断的计划模式")
    ready_to_finalize: bool = Field(False, description="是否准备好生成计划")
    next_questions: list[str] = Field(default_factory=list, description="还需要追问的问题")
    goal_summary: str | None = Field(None, description="提取的目标摘要")
    allow_quiet_hours: bool | None = Field(None, description="是否建议允许夜间安排")
    # 改动原因：同一时间不能有多个计划，检测到冲突时提醒用户
    conflict_warning: str | None = Field(None, description="计划冲突警告（如有进行中的计划）")


class ChatFinalizeResponse(BaseModel):
    """
    定稿生成计划的响应体。

    改动原因：前端需要接收生成的目标和任务，以及跳转提示。
    """
    goal_id: int = Field(..., description="生成的目标 ID")
    goal_type: str = Field(..., description="目标类型：daily / long_term")
    goal_content: str = Field(..., description="目标内容")
    roadmap_summary: str | None = Field(None, description="路线图摘要（长期计划专用）")
    tasks_count: int = Field(..., description="生成的任务数量")
    redirect_hint: str = Field(..., description="前端跳转提示文案")
    time_adjusted: bool = Field(False, description="是否有任务时间窗被自动调整")
    adjusted_reason: str = Field("", description="时间调整原因")


class DispatchMoreRequest(BaseModel):
    """
    加餐任务请求体。

    改动原因：用户当天任务很快完成时，系统主动询问是否生成新任务。
    """
    goal_id: int = Field(..., description="目标 ID")
    date: str | None = Field(None, description="目标日期（YYYY-MM-DD），默认今天")
    user_feedback: str | None = Field(None, description="用户反馈（可选）")


class DispatchMoreResponse(BaseModel):
    """加餐任务响应体。"""
    tasks: list["DispatchMoreTaskItem"] = Field(..., description="新增的加餐任务列表")
    time_adjusted: bool = Field(False, description="是否有任务时间窗被自动调整")
    adjusted_reason: str = Field("", description="时间调整原因")


class DispatchMoreTaskItem(BaseModel):
    """加餐任务项。"""
    id: int = Field(..., description="任务 ID")
    description: str = Field(..., description="任务描述")
    criteria: str = Field(..., description="完成标准")
    planned_start_at: str | None = Field(None, description="计划开始时间")
    planned_end_at: str | None = Field(None, description="计划截止时间")
    status: str = Field("pending", description="任务状态")

    model_config = {"from_attributes": True}
