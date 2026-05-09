/**
 * API 服务层
 *
 * 增量升级说明：
 * - 新增 getUserPreferences / updateUserPreferences
 * - 新增 dispatchDailyTasks
 * - mapPlanFromApi / mapPlanWithTasksFromApi 适配新字段
 * - generatePlan 返回 time_adjusted / adjusted_reason
 * 改动原因：前端需要调用新增的后端接口。
 */

import type {
  ActiveLongTermResponse,
  ChatFinalizeResponse,
  ChatSessionDetail,
  ChatSessionListItem,
  ChatStepResponse,
  CompleteTaskResponse,
  ContinueLongTermResponse,
  CreateTaskRequest,
  CancelLongTermResponse,
  DispatchMoreResponse,
  DispatchResponse,
  GeneratePlanResponse,
  LoginResponse,
  PlanWithTasks,
  ReviewReport,
  Task,
  UpdateTaskRequest,
  User,
  UserPreferences,
} from "../types/api";

// ===== 通用错误类 =====

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function redactSensitive(text: string): string {
  return text.replace(/sk-[A-Za-z0-9_-]{8,}/g, "sk-***");
}

// ===== Token 管理 =====

const TOKEN_KEY = "aicoach_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ===== 通用请求 =====

async function request<T>(
  url: string,
  options?: RequestInit & { skipAuth?: boolean; timeoutMs?: number },
): Promise<T> {
  const { skipAuth, timeoutMs, ...fetchOptions } = options || {};
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };
  if (!skipAuth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let timeoutId: number | null = null;
  const timeoutController = !fetchOptions.signal && timeoutMs ? new AbortController() : null;
  const signal = fetchOptions.signal ?? timeoutController?.signal;
  if (timeoutController && timeoutMs) {
    timeoutId = window.setTimeout(() => timeoutController.abort(), timeoutMs);
  }

  let response: Response;
  try {
    response = await fetch(url, { ...fetchOptions, headers, signal });
  } catch (err) {
    if (timeoutId) window.clearTimeout(timeoutId);
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "请求超时，请检查网络后重试");
    }
    throw new ApiError(0, "网络异常，请检查网络连接后重试");
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
  if (!response.ok) {
    let detail = `请求失败 (${response.status})`;
    try {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const body = await response.json();
        if (typeof body?.detail === "string" && body.detail.trim()) detail = body.detail;
        else if (typeof body?.message === "string" && body.message.trim()) detail = body.message;
      } else {
        const text = (await response.text()).trim();
        if (text && !text.toLowerCase().startsWith("<!doctype")) detail = text.slice(0, 300);
      }
    } catch {
      // ignore
    }
    if (response.status === 401) clearToken();
    if (detail === `请求失败 (${response.status})` && response.status >= 500) {
      detail = `服务端内部错误 (${response.status})，请查看后端日志`;
    }
    throw new ApiError(response.status, redactSensitive(detail));
  }
  return response.json() as Promise<T>;
}

// ===== 字段映射 =====

function mapTaskFromApi(raw: Record<string, unknown>): Task {
  return {
    id: raw.id as number,
    goal_id: raw.goal_id as number,
    description: raw.description as string,
    criteria: raw.criteria as string,
    status: raw.status as Task["status"],
    planned_start_at: (raw.planned_start_at as string) || null,
    planned_end_at: (raw.planned_end_at as string) || null,
    completed_at: (raw.completed_at as string) || null,
    completion_reason: (raw.completion_reason as string) || null,
    is_late: (raw.is_late as boolean) || false,
    created_at: raw.created_at as string,
    scheduled_date: (raw.scheduled_date as string) || null,
  };
}

function mapGoalFromApi(raw: Record<string, unknown>) {
  return {
    id: raw.id as number,
    user_id: (raw.user_id as number) || 0,
    content: raw.content as string,
    created_at: raw.created_at as string,
    goal_type: (raw.goal_type as "daily" | "long_term") || "daily",
    roadmap_summary: (raw.roadmap_summary as string) || null,
    target_duration_days: (raw.target_duration_days as number) || null,
    start_date: (raw.start_date as string) || null,
  };
}

function mapPlanFromApi(raw: Record<string, unknown>): GeneratePlanResponse {
  const goal = mapGoalFromApi(raw.goal as Record<string, unknown>);
  const tasks = (raw.tasks as Record<string, unknown>[]).map(mapTaskFromApi);
  return {
    goal,
    tasks,
    time_adjusted: (raw.time_adjusted as boolean) || false,
    adjusted_reason: (raw.adjusted_reason as string) || "",
  };
}

function mapActiveLongTermFromApi(raw: Record<string, unknown>): ActiveLongTermResponse {
  return {
    goal: mapGoalFromApi(raw.goal as Record<string, unknown>),
    progress: raw.progress as ActiveLongTermResponse["progress"],
    today_tasks: ((raw.today_tasks as Record<string, unknown>[]) || []).map(mapTaskFromApi),
  };
}

function mapPlanWithTasksFromApi(raw: Record<string, unknown>): PlanWithTasks {
  const goal = mapGoalFromApi(raw);
  return {
    ...goal,
    tasks: ((raw.tasks as Record<string, unknown>[]) || []).map(mapTaskFromApi),
  };
}

// ===== 认证 API =====

export async function register(username: string, password: string): Promise<{ message: string; user_id: number; username: string }> {
  const formData = new URLSearchParams();
  formData.append("username", username);
  formData.append("password", password);
  return request("/api/auth/register", { method: "POST", body: formData, headers: { "Content-Type": "application/x-www-form-urlencoded" }, skipAuth: true });
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const formData = new URLSearchParams();
  formData.append("username", username);
  formData.append("password", password);
  const data = await request<LoginResponse>("/api/auth/login", { method: "POST", body: formData, headers: { "Content-Type": "application/x-www-form-urlencoded" }, skipAuth: true });
  setToken(data.access_token);
  return data;
}

export async function getMe(): Promise<User> {
  const data = await request<{ user_id: number; username: string; created_at: string }>("/api/auth/me");
  return { user_id: data.user_id, username: data.username };
}

// ===== 业务 API =====

export async function generatePlan(goalContent: string): Promise<GeneratePlanResponse> {
  const data = await request<Record<string, unknown>>("/api/plans/generate", { method: "POST", body: JSON.stringify({ content: goalContent }) });
  return mapPlanFromApi(data);
}

/**
 * 每日派发接口。
 * 改动原因：支持"每天打开自动派发今天任务"。
 */
export async function dispatchDailyTasks(goalId: number, date?: string, userFeedback?: string): Promise<DispatchResponse> {
  const body: Record<string, unknown> = { goal_id: goalId };
  if (date) body.date = date;
  if (userFeedback) body.user_feedback = userFeedback;
  const data = await request<Record<string, unknown>>("/api/plans/dispatch", { method: "POST", body: JSON.stringify(body) });
  const goal = mapGoalFromApi(data.goal as Record<string, unknown>);
  const tasks = (data.tasks as Record<string, unknown>[]).map(mapTaskFromApi);
  return {
    goal,
    tasks,
    time_adjusted: (data.time_adjusted as boolean) || false,
    adjusted_reason: (data.adjusted_reason as string) || "",
  };
}

/**
 * 获取进行中的长期任务（用于刷新检测）。
 * 改动原因：刷新任务看板时需要判断是否存在进行中的长期计划，并显示引导弹窗。
 */
export async function getActiveLongTerm(): Promise<ActiveLongTermResponse | null> {
  try {
    const data = await request<Record<string, unknown>>("/api/long-term/active", { timeoutMs: 8000 });
    return mapActiveLongTermFromApi(data);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

/**
 * 继续长期任务：幂等生成今天任务（若已存在则直接返回）。
 * 改动原因：支持“继续任务”基于进度补齐当天子任务，并避免重复生成。
 */
export async function continueLongTermGoal(goalId: number, userFeedback?: string): Promise<ContinueLongTermResponse> {
  const body: Record<string, unknown> = {};
  if (userFeedback) body.user_feedback = userFeedback;
  const data = await request<Record<string, unknown>>(`/api/long-term/${goalId}/continue`, {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: 60000,
  });
  return {
    goal: mapGoalFromApi(data.goal as Record<string, unknown>),
    tasks: (data.tasks as Record<string, unknown>[]).map(mapTaskFromApi),
    time_adjusted: (data.time_adjusted as boolean) || false,
    adjusted_reason: (data.adjusted_reason as string) || "",
    generated_new: (data.generated_new as boolean) || false,
    created_count: (data.created_count as number) || 0,
  };
}

/**
 * 取消长期任务并清理未完成任务。
 * 改动原因：支持“取消任务”终止长期计划并清理相关数据，避免刷新后状态不一致。
 */
export async function cancelLongTermGoal(goalId: number): Promise<CancelLongTermResponse> {
  return request<CancelLongTermResponse>(`/api/long-term/${goalId}/cancel`, { method: "POST", body: JSON.stringify({}) });
}

/**
 * 获取用户偏好设置。
 * 改动原因：前端需要读取偏好来展示 Quiet Hours 设置。
 */
export async function getUserPreferences(): Promise<UserPreferences> {
  return request<UserPreferences>("/api/users/preferences");
}

/**
 * 更新用户偏好设置。
 * 改动原因：前端需要写入偏好来持久化 Quiet Hours 设置。
 */
export async function updateUserPreferences(prefs: Partial<UserPreferences>): Promise<UserPreferences> {
  return request<UserPreferences>("/api/users/preferences", { method: "PATCH", body: JSON.stringify(prefs) });
}

/**
 * 完成任务。
 */
export async function completeTask(taskId: number, completionReason?: string): Promise<CompleteTaskResponse> {
  const data = await request<Record<string, unknown>>(`/api/tasks/${taskId}/complete`, {
    method: "POST",
    body: JSON.stringify({ completion_reason: completionReason || null }),
  });
  return {
    task: mapTaskFromApi(data.task as Record<string, unknown>),
    is_late: data.is_late as boolean,
    reason_required: data.reason_required as boolean,
  };
}

export async function uncompleteTask(taskId: number): Promise<Task> {
  const data = await request<Record<string, unknown>>(`/api/tasks/${taskId}/uncomplete`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTaskFromApi(data);
}

/**
 * 补填超时完成原因。
 */
export async function updateCompletionReason(taskId: number, reason: string): Promise<Task> {
  const data = await request<Record<string, unknown>>(`/api/tasks/${taskId}/completion-reason`, {
    method: "PATCH",
    body: JSON.stringify({ completion_reason: reason }),
  });
  return mapTaskFromApi(data);
}

/**
 * 手动编辑任务。
 */
export async function updateTask(taskId: number, updates: UpdateTaskRequest): Promise<Task> {
  const data = await request<Record<string, unknown>>(`/api/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(updates) });
  return mapTaskFromApi(data);
}

/**
 * 手动新增任务。
 * 改动原因：任务看板的待办列表需要支持用户手动添加任务，而不仅依赖 AI 自动生成。
 */
export async function createTask(body: CreateTaskRequest): Promise<Task> {
  const data = await request<Record<string, unknown>>("/api/tasks", { method: "POST", body: JSON.stringify(body) });
  return mapTaskFromApi(data);
}

/**
 * 删除任务。
 * 改动原因：任务看板的待办列表需要支持清理无效/不需要的任务。
 */
export async function deleteTask(taskId: number): Promise<{ message: string; task_id: number }> {
  return request<{ message: string; task_id: number }>(`/api/tasks/${taskId}`, { method: "DELETE" });
}

export async function getLatestPlan(): Promise<GeneratePlanResponse> {
  const data = await request<Record<string, unknown>>("/api/plans/latest");
  return mapPlanFromApi(data);
}

/**
 * 获取指定 ID 的计划及其任务列表。
 */
export async function getPlanById(goalId: number): Promise<GeneratePlanResponse> {
  const data = await request<Record<string, unknown>>(`/api/plans/${goalId}`);
  return mapPlanFromApi(data);
}

export async function getPlanHistory(): Promise<PlanWithTasks[]> {
  const data = await request<Record<string, unknown>[]>("/api/plans/history");
  return data.map(mapPlanWithTasksFromApi);
}

export async function regenerateTask(taskId: number, userFeedback?: string): Promise<Task> {
  const data = await request<Record<string, unknown>>(`/api/tasks/${taskId}/regenerate`, { method: "POST", body: JSON.stringify({ user_feedback: userFeedback || null }) });
  return mapTaskFromApi(data);
}

export async function generateReview(goalId: number): Promise<ReviewReport> {
  const data = await request<Record<string, unknown>>("/api/reviews/generate", { method: "POST", body: JSON.stringify({ goal_id: goalId }) });
  const review = data.review as Record<string, unknown>;
  return mapReviewFromApi(review);
}

export async function generatePeriodReview(periodType: "weekly" | "monthly", startDate: string, endDate: string): Promise<ReviewReport> {
  const data = await request<Record<string, unknown>>("/api/reviews/generate-period", {
    method: "POST",
    body: JSON.stringify({ period_type: periodType, start_date: startDate, end_date: endDate }),
  });
  const review = data.review as Record<string, unknown>;
  return mapReviewFromApi(review);
}

export async function getReviewHistory(): Promise<ReviewReport[]> {
  const data = await request<Record<string, unknown>[]>("/api/reviews/history");
  return data.map(mapReviewFromApi);
}

export async function getPeriodReviewHistory(periodType?: "weekly" | "monthly"): Promise<ReviewReport[]> {
  const params = periodType ? `?period_type=${periodType}` : "";
  const data = await request<Record<string, unknown>[]>(`/api/reviews/period-history${params}`);
  return data.map(mapReviewFromApi);
}

// ===== 字段映射辅助 =====

function mapReviewFromApi(raw: Record<string, unknown>): ReviewReport {
  return {
    id: raw.id as number,
    goal_id: (raw.goal_id as number) ?? null,
    period_type: (raw.period_type as "daily" | "weekly" | "monthly") || "daily",
    period_label: (raw.period_label as string) || "",
    completion_rate: raw.completion_rate as number,
    analysis: raw.analysis as string,
    suggestions: raw.suggestions as string,
    created_at: raw.created_at as string,
  };
}

// ===== 聊天 API =====
// 改动原因：ChatGPT 风格的对话式计划生成需要调用后端聊天接口

/**
 * 创建新的聊天会话。
 * 改动原因：用户开始新对话时需要创建会话记录。
 */
export async function createChatSession(title?: string): Promise<ChatSessionListItem> {
  const body: Record<string, unknown> = {};
  if (title) body.title = title;
  return request<ChatSessionListItem>("/api/chat/sessions", { method: "POST", body: JSON.stringify(body) });
}

/**
 * 获取当前用户的会话列表。
 * 改动原因：左侧历史对话列表需要展示所有会话。
 */
export async function getChatSessions(): Promise<ChatSessionListItem[]> {
  return request<ChatSessionListItem[]>("/api/chat/sessions");
}

/**
 * 获取指定会话的详情（含消息列表）。
 * 改动原因：打开历史会话时需要加载完整对话上下文。
 */
export async function getChatSession(sessionId: number): Promise<ChatSessionDetail> {
  return request<ChatSessionDetail>(`/api/chat/sessions/${sessionId}`);
}

/**
 * 删除会话及其所有消息。
 */
export async function deleteChatSession(sessionId: number): Promise<void> {
  return request<void>(`/api/chat/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

/**
 * 重命名会话标题。
 */
export async function renameChatSession(sessionId: number, title: string): Promise<{ message: string; title: string }> {
  return request<{ message: string; title: string }>(`/api/chat/sessions/${sessionId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

/**
 * 发送消息并获取助手回复。
 * 改动原因：核心对话交互——发送用户消息，返回助手回复和会话状态。
 */
export async function sendChatMessage(sessionId: number, content: string): Promise<ChatStepResponse> {
  return request<ChatStepResponse>(`/api/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

/**
 * 定稿会话并生成计划。
 * 改动原因：对话确认后，调用此接口生成实际的任务计划。
 */
export async function finalizeChatSession(sessionId: number): Promise<ChatFinalizeResponse> {
  return request<ChatFinalizeResponse>(`/api/chat/sessions/${sessionId}/finalize`, { method: "POST" });
}

/**
 * 生成加餐任务（基于复盘调整）。
 * 改动原因：用户当天任务快速完成时，基于复盘报告生成增量任务。
 */
export async function dispatchMoreTasks(goalId: number, date?: string, userFeedback?: string): Promise<DispatchMoreResponse> {
  const body: Record<string, unknown> = { goal_id: goalId };
  if (date) body.date = date;
  if (userFeedback) body.user_feedback = userFeedback;
  const data = await request<Record<string, unknown>>("/api/plans/dispatch-more", {
    method: "POST",
    body: JSON.stringify(body),
  });
  const tasks = ((data.tasks as Record<string, unknown>[]) || []).map((t: Record<string, unknown>) => ({
    id: t.id as number,
    description: t.description as string,
    criteria: t.criteria as string,
    planned_start_at: (t.planned_start_at as string) || null,
    planned_end_at: (t.planned_end_at as string) || null,
    status: (t.status as "pending" | "completed") || "pending",
  }));
  return {
    tasks,
    time_adjusted: (data.time_adjusted as boolean) || false,
    adjusted_reason: (data.adjusted_reason as string) || "",
  };
}
