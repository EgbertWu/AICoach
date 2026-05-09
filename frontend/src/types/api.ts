/**
 * AICoach TypeScript 类型定义
 *
 * 增量升级说明：
 * - UserGoal 新增 goal_type / roadmap_summary / target_duration_days / start_date
 * - Task 新增 scheduled_date
 * - 新增 UserPreferences 类型
 * - GeneratePlanResponse 新增 time_adjusted / adjusted_reason
 * - 新增 DispatchResponse 类型
 * 改动原因：前端需要适配后端新增的长期目标和偏好功能。
 */

export type TaskStatus = "pending" | "completed";

export interface User {
  user_id: number;
  username: string;
}

export interface UserGoal {
  id: number;
  user_id: number;
  content: string;
  created_at: string;
  goal_type: "daily" | "long_term";
  roadmap_summary: string | null;
  target_duration_days: number | null;
  start_date: string | null;
}

/**
 * 用户偏好设置。
 * 改动原因：前端需要展示和编辑 Quiet Hours 偏好。
 */
export interface UserPreferences {
  quiet_hours_start: string;
  quiet_hours_end: string;
  allow_quiet_hours: boolean;
  timezone: string;
}

/**
 * 任务卡片。
 * 增量字段：scheduled_date（长期计划按天派发归属日期）。
 */
export interface Task {
  id: number;
  goal_id: number;
  description: string;
  criteria: string;
  status: TaskStatus;
  planned_start_at: string | null;
  planned_end_at: string | null;
  completed_at: string | null;
  completion_reason: string | null;
  is_late: boolean;
  created_at: string;
  scheduled_date: string | null;
}

export interface ReviewReport {
  id: number;
  goal_id: number | null;
  period_type: "daily" | "weekly" | "monthly";
  period_label: string;
  completion_rate: number;
  analysis: string;
  suggestions: string;
  created_at: string;
}

/**
 * 计划生成响应。
 * 增量字段：time_adjusted / adjusted_reason（时间窗调整提示）。
 */
export interface GeneratePlanResponse {
  goal: UserGoal;
  tasks: Task[];
  time_adjusted: boolean;
  adjusted_reason: string;
}

/**
 * 每日派发响应。
 * 改动原因：前端需要处理 dispatch 接口返回。
 */
export interface DispatchResponse {
  goal: UserGoal;
  tasks: Task[];
  time_adjusted: boolean;
  adjusted_reason: string;
}

/**
 * 刷新检测：活跃长期任务响应。
 * 改动原因：页面刷新时需要检测进行中的长期计划并展示引导弹窗。
 */
export interface ActiveLongTermResponse {
  goal: UserGoal;
  progress: { total: number; completed: number; completion_rate: number };
  today_tasks: Task[];
}

/**
 * 继续长期任务响应（幂等生成今天任务）。
 * 改动原因：支持“继续任务”按钮基于进度补齐当天子任务，并避免重复生成。
 */
export interface ContinueLongTermResponse {
  goal: UserGoal;
  tasks: Task[];
  time_adjusted: boolean;
  adjusted_reason: string;
  generated_new: boolean;
  created_count: number;
}

/**
 * 取消长期任务响应。
 * 改动原因：支持“取消任务”终止长期计划并清理未完成任务。
 */
export interface CancelLongTermResponse {
  goal_id: number;
  deleted_pending_tasks: number;
  message: string;
}

export interface UpdateTaskRequest {
  description?: string;
  criteria?: string;
  planned_start_at?: string | null;
  planned_end_at?: string | null;
}

export interface CreateTaskRequest {
  goal_id: number;
  description: string;
  criteria: string;
  planned_start_at?: string | null;
  planned_end_at?: string | null;
  scheduled_date?: string | null;
}

export interface CompleteTaskResponse {
  task: Task;
  is_late: boolean;
  reason_required: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  username: string;
}

export interface PlanWithTasks {
  id: number;
  user_id: number;
  content: string;
  created_at: string;
  goal_type: "daily" | "long_term";
  roadmap_summary: string | null;
  target_duration_days: number | null;
  start_date: string | null;
  tasks: Task[];
}

// ===== 聊天会话类型 =====
// 改动原因：ChatGPT 风格的对话式计划生成需要前端类型定义

/**
 * 聊天会话列表项（左侧栏展示）。
 * 改动原因：前端需要展示历史对话列表。
 */
export interface ChatSessionListItem {
  id: number;
  title: string | null;
  status: "active" | "finalized";
  plan_mode: "unknown" | "daily" | "long_term";
  created_at: string;
  updated_at: string;
}

/**
 * 聊天消息。
 * 改动原因：消息流渲染需要消息类型定义。
 */
export interface ChatMessageItem {
  id: number;
  session_id: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

/**
 * 会话详情（含消息列表）。
 * 改动原因：打开历史会话时需要加载完整对话。
 */
export interface ChatSessionDetail {
  id: number;
  title: string | null;
  status: "active" | "finalized";
  plan_mode: "unknown" | "daily" | "long_term";
  linked_goal_id: number | null;
  created_at: string;
  updated_at: string;
  messages: ChatMessageItem[];
}

/**
 * 会话状态信息。
 * 改动原因：前端需要根据这些字段决定 UI 展示逻辑（如是否显示"生成计划"按钮）。
 */
export interface SessionState {
  plan_mode: "unknown" | "daily" | "long_term";
  ready_to_finalize: boolean;
  next_questions: string[];
  goal_summary: string | null;
  allow_quiet_hours: boolean | null;
  /** 计划冲突警告（如有进行中的计划） */
  conflict_warning: string | null;
}

/**
 * 对话步骤响应。
 * 改动原因：每次发送消息后返回助手回复和会话状态。
 */
export interface ChatStepResponse {
  assistant_message: string;
  session_state: SessionState;
}

/**
 * 定稿生成计划的响应。
 * 改动原因：前端需要接收生成结果并跳转到 Dashboard。
 */
export interface ChatFinalizeResponse {
  goal_id: number;
  goal_type: "daily" | "long_term";
  goal_content: string;
  roadmap_summary: string | null;
  tasks_count: number;
  redirect_hint: string;
  time_adjusted: boolean;
  adjusted_reason: string;
}

/**
 * 加餐任务项。
 * 改动原因：快速完成后生成的增量任务需要类型定义。
 */
export interface DispatchMoreTaskItem {
  id: number;
  description: string;
  criteria: string;
  planned_start_at: string | null;
  planned_end_at: string | null;
  status: "pending" | "completed";
}

/**
 * 加餐任务响应。
 * 改动原因：dispatch-more 接口返回类型。
 */
export interface DispatchMoreResponse {
  tasks: DispatchMoreTaskItem[];
  time_adjusted: boolean;
  adjusted_reason: string;
}
