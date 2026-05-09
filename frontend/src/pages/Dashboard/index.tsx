/**
 * Dashboard 页面 — Trello 风格三列看板（暗色主题）
 *
 * 增量升级说明：
 * - 长期模式展示：Roadmap 摘要卡片
 * - 每日自动派发：加载时检查 long_term goal 并自动 dispatch
 * - Quiet Hours 设置入口
 * - time_adjusted 提示（toast）
 * 改动原因：长期目标仍以"今天"执行为中心，用户每天打开就有任务。
 */

import { useState, useEffect, useRef, useMemo } from "react";
import {
  DndContext,
  DragOverlay,
  closestCorners,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import type {
  ActiveLongTermResponse,
  CreateTaskRequest,
  GeneratePlanResponse,
  Task,
  UserPreferences,
} from "../../types/api";
import {
  ApiError,
  clearToken,
  cancelLongTermGoal,
  completeTask,
  continueLongTermGoal,
  createTask,
  dispatchMoreTasks,
  getActiveLongTerm,
  getLatestPlan,
  getPlanById,
  getUserPreferences,
  uncompleteTask,
  updateUserPreferences,
} from "../../services/api";
import TaskCard from "../../components/business/TaskCard";
import PreferencesModal from "../../components/business/PreferencesModal";
import { ThemeToggle } from "../../components/business/ThemeProvider";
import type { User } from "../../types/api";

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

interface DashboardProps {
  user: User;
  onLogout: () => void;
  onNavigateReview: () => void;
  onNavigateHistory: () => void;
  onNavigateChat: (msg?: string) => void;
  /** 从 History 页面传入的目标 ID，用于查看历史任务看板 */
  goalId?: number | null;
  /** goalId 消费后回调，通知父组件清空 */
  onGoalIdConsumed?: () => void;
}

/** 前端扩展的列类型 */
type KanbanColumn = "todo" | "in_progress" | "done";

type DoneSection = { dateKey: string; label: string; tasks: Task[] };

/** 可放置的看板列组件 */
function DroppableColumn({
  column,
  planData,
  onUpdateTask,
  onDeleteTask,
  onOpenAddTask,
  doneSections,
  expandedDoneDates,
  onToggleDoneDate,
}: {
  column: { id: KanbanColumn; title: string; color: string; glowColor: string; tasks: Task[]; colId: string };
  planData: GeneratePlanResponse | null;
  onUpdateTask: (taskId: number, updatedTask: Task) => void;
  onDeleteTask?: (taskId: number) => void;
  onOpenAddTask?: () => void;
  doneSections?: DoneSection[];
  expandedDoneDates?: Set<string>;
  onToggleDoneDate?: (dateKey: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column.colId });
  const isDoneGrouped = column.id === "done" && !!doneSections && !!expandedDoneDates && !!onToggleDoneDate;
  const visibleDoneTasks = isDoneGrouped
    ? doneSections.flatMap((s) => (expandedDoneDates.has(s.dateKey) ? s.tasks : []))
    : [];

  return (
    <div
      ref={setNodeRef}
      id={column.colId}
      className={`flex flex-col rounded-xl border overflow-hidden transition-colors duration-200 ${
        isOver ? "bg-bg-secondary border-accent-blue/30" : "bg-bg-secondary/50 border-border-subtle"
      }`}
    >
      <div className="px-4 py-3 flex items-center justify-between border-b border-border-subtle">
        <div className="flex items-center gap-2.5">
          <div className={`w-2 h-2 rounded-full ${column.glowColor} ${column.id === "in_progress" ? "animate-pulse" : ""}`} />
          <h3 className={`text-base font-bold ${column.color}`}>{column.title}</h3>
          <span className="text-xs font-mono text-text-tertiary bg-bg-tertiary px-1.5 py-0.5 rounded">
            {column.tasks.length}
          </span>
        </div>
        {column.id === "todo" && onOpenAddTask && (
          <button
            type="button"
            onClick={onOpenAddTask}
            className="text-xs px-2.5 py-1 rounded-lg bg-accent-blue/10 text-accent-blue hover:bg-accent-blue/20 transition-all cursor-pointer border border-accent-blue/20"
            title="手动新增任务"
          >
            + 新任务
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto kanban-column p-3 space-y-2.5">
        {isDoneGrouped ? (
          doneSections.length === 0 ? (
            <div className={`flex items-center justify-center h-24 rounded-lg border border-dashed text-xs transition-colors ${
              isOver ? "border-accent-blue/40 text-accent-blue/60" : "border-border-subtle text-text-tertiary/40"
            }`}>
              {isOver ? "松开放置到此处" : "暂无已完成任务"}
            </div>
          ) : (
            <>
              <SortableContext
                items={visibleDoneTasks.map((t) => t.id)}
                strategy={verticalListSortingStrategy}
              >
                {doneSections.map((section) => {
                  const expanded = expandedDoneDates.has(section.dateKey);
                  return (
                    <div key={section.dateKey} className="rounded-xl border border-border-subtle bg-bg-tertiary/20 overflow-hidden">
                      <button
                        type="button"
                        onClick={() => onToggleDoneDate(section.dateKey)}
                        className="w-full px-3 py-2 flex items-center justify-between hover:bg-bg-tertiary/40 transition-colors cursor-pointer"
                      >
                        <div className="flex items-center gap-2">
                          <div className={`w-1.5 h-1.5 rounded-full ${column.glowColor}`} />
                          <span className="text-xs font-semibold text-text-secondary">{section.label}</span>
                          <span className="text-[11px] font-mono text-text-tertiary bg-bg-tertiary px-1.5 py-0.5 rounded">
                            {section.tasks.length}
                          </span>
                        </div>
                        <svg
                          className={`w-4 h-4 text-text-tertiary transition-transform ${expanded ? "rotate-180" : "rotate-0"}`}
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>

                      <div className={`overflow-hidden transition-all duration-300 ${
                        expanded ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0"
                      }`}>
                        <div className="p-3 space-y-2.5">
                          {expanded && section.tasks.map((task) => (
                            <TaskCard
                              key={task.id}
                              task={task}
                              index={planData ? planData.tasks.findIndex((t) => t.id === task.id) + 1 : 0}
                              onUpdateTask={onUpdateTask}
                            />
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </SortableContext>

              {isOver && (
                <div className="flex items-center justify-center h-16 rounded-lg border border-dashed border-accent-blue/40 text-xs text-accent-blue/60">
                  松开放置到此处
                </div>
              )}
            </>
          )
        ) : (
          <>
            <SortableContext
              items={column.tasks.map((t) => t.id)}
              strategy={verticalListSortingStrategy}
            >
              {column.tasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  index={planData ? planData.tasks.findIndex((t) => t.id === task.id) + 1 : 0}
                  onUpdateTask={onUpdateTask}
                  onDeleteTask={column.id === "todo" ? onDeleteTask : undefined}
                />
              ))}
            </SortableContext>
          </>
        )}

        {!isDoneGrouped && column.tasks.length === 0 && (
          <div className={`flex items-center justify-center h-24 rounded-lg border border-dashed text-xs transition-colors ${
            isOver ? "border-accent-blue/40 text-accent-blue/60" : "border-border-subtle text-text-tertiary/40"
          }`}>
            {isOver ? "松开放置到此处" : "拖拽卡片到此处"}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Dashboard({ user, onLogout, onNavigateReview, onNavigateHistory, onNavigateChat, goalId, onGoalIdConsumed }: DashboardProps) {
  const [isLoading] = useState(false);
  const [isRestoring, setIsRestoring] = useState(true);
  const [planData, setPlanData] = useState<GeneratePlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 前端本地「进行中」任务 ID 集合
  const [inProgressIds, setInProgressIds] = useState<Set<number>>(new Set());

  // 日期时钟
  const [currentTime, setCurrentTime] = useState(new Date());
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 偏好设置弹窗
  const [showPrefs, setShowPrefs] = useState(false);
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);

  // Toast 提示
  const [toast, setToast] = useState<string | null>(null);

  // 长期任务刷新引导弹窗
  // 改动原因：刷新任务看板时需要检测是否存在进行中的长期任务，并给出继续/取消/重新规划选项，避免重复生成与状态不一致
  const [activeLongTerm, setActiveLongTerm] = useState<ActiveLongTermResponse | null>(null);
  const [showLongTermPrompt, setShowLongTermPrompt] = useState(false);
  const [longTermFeedback, setLongTermFeedback] = useState("");
  const [longTermError, setLongTermError] = useState<string | null>(null);
  const [showLongTermResult, setShowLongTermResult] = useState(false);
  const [longTermResult, setLongTermResult] = useState<{ title: string; message: string } | null>(null);
  const [isContinuingLongTerm, setIsContinuingLongTerm] = useState(false);
  const [isCancellingLongTerm, setIsCancellingLongTerm] = useState(false);
  const [showCancelLongTermConfirm, setShowCancelLongTermConfirm] = useState(false);

  // 手动新增任务弹窗
  // 改动原因：支持在「待办」列表手动补充任务，而不只依赖 AI 自动生成
  const [showCreateTask, setShowCreateTask] = useState(false);
  const [newDesc, setNewDesc] = useState("");
  const [newCriteria, setNewCriteria] = useState("");
  const [newStartAt, setNewStartAt] = useState("");
  const [newEndAt, setNewEndAt] = useState("");
  const [isCreatingTask, setIsCreatingTask] = useState(false);
  const [createTaskError, setCreateTaskError] = useState<string | null>(null);

  // 加餐任务相关状态
  // 改动原因：用户当天任务快速完成时，系统主动询问是否生成新任务
  const [showBonusPrompt, setShowBonusPrompt] = useState(false);
  const [bonusFeedback, setBonusFeedback] = useState("");
  const [isDispatchingMore, setIsDispatchingMore] = useState(false);
  const [bonusDismissed, setBonusDismissed] = useState(false);

  useEffect(() => {
    clockRef.current = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => { if (clockRef.current) clearInterval(clockRef.current); };
  }, []);

  // Toast 自动消失
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const dateStr = `${currentTime.getFullYear()}.${String(currentTime.getMonth() + 1).padStart(2, "0")}.${String(currentTime.getDate()).padStart(2, "0")}`;
  const weekDay = WEEKDAYS[currentTime.getDay()];
  const timeStr = `${String(currentTime.getHours()).padStart(2, "0")}:${String(currentTime.getMinutes()).padStart(2, "0")}`;

  const inProgressStorageKey = (gid: number) => `aicoach_in_progress_ids_${user.user_id}_${gid}`;

  const restoreInProgressIds = (gid: number, tasks: Task[]) => {
    const raw = localStorage.getItem(inProgressStorageKey(gid));
    let ids: number[] = [];
    try {
      const parsed = raw ? (JSON.parse(raw) as unknown) : [];
      if (Array.isArray(parsed)) ids = parsed.map((v) => Number(v)).filter((n) => Number.isFinite(n));
    } catch {
      ids = [];
    }

    const pendingTaskIds = new Set(tasks.filter((t) => t.status === "pending").map((t) => t.id));
    const cleaned = ids.filter((id) => pendingTaskIds.has(id));
    localStorage.setItem(inProgressStorageKey(gid), JSON.stringify(cleaned));
    return new Set(cleaned);
  };

  useEffect(() => {
    const gid = planData?.goal.id;
    if (!gid) return;
    localStorage.setItem(inProgressStorageKey(gid), JSON.stringify(Array.from(inProgressIds)));
  }, [inProgressIds, planData?.goal.id]);

  // 恢复历史数据 + 刷新检测长期任务
  useEffect(() => {
    const restorePlan = async () => {
      try {
        // 如果有 goalId，加载指定计划；否则加载最新计划
        const data = goalId ? await getPlanById(goalId) : await getLatestPlan();
        setPlanData(data);
        setInProgressIds(restoreInProgressIds(data.goal.id, data.tasks));
        // 消费 goalId，防止重复加载
        if (goalId) onGoalIdConsumed?.();
        if (!goalId) {
          try {
            const active = await getActiveLongTerm();
            setActiveLongTerm(active);
            if (active) {
              const key = `aicoach_long_term_prompt_shown_${user.user_id}_${active.goal.id}`;
              const now = new Date();
              const todayKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
              const emptyKey = `aicoach_long_term_empty_prompt_shown_${user.user_id}_${active.goal.id}_${todayKey}`;
              const isTodayEmpty = active.today_tasks.length === 0;
              if (isTodayEmpty && !sessionStorage.getItem(emptyKey)) {
                sessionStorage.setItem(emptyKey, "1");
                setShowLongTermPrompt(true);
              } else if (!isTodayEmpty && !sessionStorage.getItem(key)) {
                sessionStorage.setItem(key, "1");
                setShowLongTermPrompt(true);
              }
            }
          } catch (e) {
            const msg = e instanceof ApiError ? e.message : "长期任务检测失败";
            console.info("[AICoach] active_long_term_failed", { message: msg });
            setToast(msg);
            setLongTermResult({ title: "长期任务检测失败", message: msg });
            setShowLongTermResult(true);
            setActiveLongTerm(null);
          }
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) { /* 静默 */ }
        else console.error("恢复历史计划失败:", err);
      } finally { setIsRestoring(false); }
    };
    restorePlan();
  }, [goalId]);

  const handleTaskUpdate = (taskId: number, updatedTask: Task) => {
    if (!planData) return;
    setPlanData({
      ...planData,
      tasks: planData.tasks.map((t) => (t.id === taskId ? updatedTask : t)),
    });
    if (updatedTask.status === "completed") {
      setInProgressIds((prev) => {
        const next = new Set(prev);
        next.delete(taskId);
        return next;
      });
    }
  };

  const handleTaskDeleteLocal = (taskId: number) => {
    if (!planData) return;
    setPlanData({
      ...planData,
      tasks: planData.tasks.filter((t) => t.id !== taskId),
    });
    setInProgressIds((prev) => {
      const next = new Set(prev);
      next.delete(taskId);
      return next;
    });
  };

  const handleLogout = () => { clearToken(); onLogout(); };

  const handleOpenCreateTask = () => {
    setCreateTaskError(null);
    setNewDesc("");
    setNewCriteria("");
    setNewStartAt("");
    setNewEndAt("");
    setShowCreateTask(true);
  };

  const handleConfirmCreateTask = async () => {
    if (!planData || isCreatingTask) return;
    if (!newDesc.trim() || !newCriteria.trim()) {
      setCreateTaskError("请填写任务描述和完成标准");
      return;
    }

    setIsCreatingTask(true);
    setCreateTaskError(null);

    try {
      const baseDate = new Date();
      const body: CreateTaskRequest = {
        goal_id: planData.goal.id,
        description: newDesc.trim(),
        criteria: newCriteria.trim(),
      };

      if (newStartAt) {
        const [h, m] = newStartAt.split(":").map(Number);
        const dt = new Date(baseDate);
        dt.setHours(h, m, 0, 0);
        body.planned_start_at = dt.toISOString();
      }
      if (newEndAt) {
        const [h, m] = newEndAt.split(":").map(Number);
        const dt = new Date(baseDate);
        dt.setHours(h, m, 0, 0);
        body.planned_end_at = dt.toISOString();
      }

      const created = await createTask(body);
      setPlanData({
        ...planData,
        tasks: [...planData.tasks, created],
      });
      setShowCreateTask(false);
    } catch (err) {
      setCreateTaskError(err instanceof ApiError ? err.message : "新增任务失败");
    } finally {
      setIsCreatingTask(false);
    }
  };

  const handleContinueLongTerm = async () => {
    if (!activeLongTerm || isContinuingLongTerm) return;
    setIsContinuingLongTerm(true);
    setLongTermError(null);
    try {
      const startedAt = performance.now();
      const feedback = longTermFeedback.trim();
      const result = await continueLongTermGoal(activeLongTerm.goal.id, feedback ? feedback : undefined);
      const full = await getPlanById(result.goal.id);
      setPlanData(full);
      setInProgressIds(restoreInProgressIds(full.goal.id, full.tasks));
      setShowLongTermPrompt(false);
      setShowCancelLongTermConfirm(false);
      if (result.time_adjusted && result.adjusted_reason) {
        setLongTermResult({
          title: result.generated_new ? "已生成今天任务" : "今天任务已存在（未重复生成）",
          message: `共 ${result.tasks.length} 条任务。系统已自动调整部分时间窗：${result.adjusted_reason}`,
        });
      } else {
        setLongTermResult({
          title: result.generated_new ? "已生成今天任务" : "今天任务已存在（未重复生成）",
          message: result.generated_new ? `已生成 ${result.created_count} 条任务。` : `共 ${result.tasks.length} 条任务。`,
        });
      }
      setShowLongTermResult(true);

      console.info("[AICoach] continue_long_term_ok", {
        goal_id: result.goal.id,
        tasks: result.tasks.length,
        generated_new: result.generated_new,
        created_count: result.created_count,
        cost_ms: Math.round(performance.now() - startedAt),
      });

      setActiveLongTerm((prev) => (prev ? { ...prev, today_tasks: result.tasks } : prev));
      setLongTermFeedback("");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "继续长期任务失败";
      setLongTermError(msg);
      setLongTermResult({ title: "继续任务失败", message: msg });
      setShowLongTermResult(true);
      console.info("[AICoach] continue_long_term_failed", { message: msg });
    } finally {
      setIsContinuingLongTerm(false);
    }
  };

  const handleCancelLongTerm = async () => {
    if (!activeLongTerm || isCancellingLongTerm) return;
    setIsCancellingLongTerm(true);
    setLongTermError(null);
    try {
      const res = await cancelLongTermGoal(activeLongTerm.goal.id);
      setToast(res.message);
      setActiveLongTerm(null);
      setShowLongTermPrompt(false);
      setShowCancelLongTermConfirm(false);
      if (planData?.goal.id === res.goal_id && planData.goal.goal_type === "long_term") {
        setPlanData(null);
        setInProgressIds(new Set());
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "取消长期任务失败";
      setLongTermError(msg);
      setToast(msg);
    } finally {
      setIsCancellingLongTerm(false);
    }
  };

  const handleReplanLongTerm = () => {
    if (!activeLongTerm) return;
    setShowLongTermPrompt(false);
    setShowCancelLongTermConfirm(false);
    onNavigateChat(`我想重新规划长期计划：${activeLongTerm.goal.content}。请帮我重新制定路线图和今天的任务安排。`);
  };

  // 偏好设置
  const handleOpenPrefs = async () => {
    try {
      const data = await getUserPreferences();
      setPrefs(data);
      setShowPrefs(true);
    } catch (err) {
      console.error("获取偏好失败:", err);
    }
  };

  const handleSavePrefs = async (newPrefs: Partial<UserPreferences>) => {
    try {
      const updated = await updateUserPreferences(newPrefs);
      setPrefs(updated);
      setShowPrefs(false);
    } catch (err) {
      console.error("更新偏好失败:", err);
    }
  };

  // 加餐任务处理
  // 改动原因：基于复盘报告生成增量任务，追加到当前计划
  const handleDispatchMore = async () => {
    if (!planData || isDispatchingMore) return;
    setIsDispatchingMore(true);
    try {
      const result = await dispatchMoreTasks(
        planData.goal.id,
        undefined,
        bonusFeedback || undefined,
      );
      // 将新任务追加到 planData
      const newTasks: Task[] = result.tasks.map((t) => ({
        id: t.id,
        goal_id: planData.goal.id,
        description: t.description,
        criteria: t.criteria,
        status: "pending" as const,
        planned_start_at: t.planned_start_at,
        planned_end_at: t.planned_end_at,
        completed_at: null,
        completion_reason: null,
        is_late: false,
        created_at: new Date().toISOString(),
        scheduled_date: t.planned_start_at?.split("T")[0] || null,
      }));
      setPlanData({
        ...planData,
        tasks: [...planData.tasks, ...newTasks],
      });
      setShowBonusPrompt(false);
      if (result.time_adjusted && result.adjusted_reason) {
        setToast(result.adjusted_reason);
      }
    } catch (err) {
      console.error("生成加餐任务失败:", err);
    } finally {
      setIsDispatchingMore(false);
    }
  };

  // ===== 看板列数据 =====
  const todoTasks = useMemo(() => {
    const tasks = planData?.tasks.filter((t) => t.status === "pending" && !inProgressIds.has(t.id)) ?? [];
    const getTs = (t: Task) => {
      if (t.planned_start_at) return new Date(t.planned_start_at).getTime();
      if (t.planned_end_at) return new Date(t.planned_end_at).getTime();
      return Number.POSITIVE_INFINITY;
    };
    return tasks.slice().sort((a, b) => {
      const diff = getTs(a) - getTs(b);
      if (diff !== 0) return diff;
      return a.id - b.id;
    });
  }, [planData, inProgressIds]);

  const inProgressTasks = useMemo(() => {
    const tasks = planData?.tasks.filter((t) => t.status === "pending" && inProgressIds.has(t.id)) ?? [];
    const getTs = (t: Task) => {
      if (t.planned_start_at) return new Date(t.planned_start_at).getTime();
      if (t.planned_end_at) return new Date(t.planned_end_at).getTime();
      return Number.POSITIVE_INFINITY;
    };
    return tasks.slice().sort((a, b) => {
      const diff = getTs(a) - getTs(b);
      if (diff !== 0) return diff;
      return a.id - b.id;
    });
  }, [planData, inProgressIds]);

  const doneTasks = useMemo(() =>
    planData?.tasks.filter((t) => t.status === "completed") ?? [],
    [planData]
  );

  const [expandedDoneDates, setExpandedDoneDates] = useState<Set<string>>(() => {
    const d = new Date();
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return new Set([key]);
  });

  const todayKey = useMemo(() => dateStr.replaceAll(".", "-"), [dateStr]);

  const doneSections = useMemo((): DoneSection[] => {
    const formatKeyFromIso = (iso: string) => {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return null;
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    };

    const getDoneKey = (t: Task) => {
      if (t.completed_at) return formatKeyFromIso(t.completed_at);
      if (t.scheduled_date) return t.scheduled_date;
      if (t.planned_end_at) return formatKeyFromIso(t.planned_end_at);
      if (t.planned_start_at) return formatKeyFromIso(t.planned_start_at);
      return null;
    };

    const groups = new Map<string, Task[]>();
    for (const t of doneTasks) {
      const key = getDoneKey(t);
      if (!key) continue;
      const list = groups.get(key) ?? [];
      list.push(t);
      groups.set(key, list);
    }

    const keys = Array.from(groups.keys()).sort((a, b) => {
      if (a === todayKey && b !== todayKey) return -1;
      if (b === todayKey && a !== todayKey) return 1;
      return b.localeCompare(a);
    });

    return keys.map((key) => {
      const tasks = (groups.get(key) ?? []).slice().sort((a, b) => {
        const ta = a.completed_at ? new Date(a.completed_at).getTime() : 0;
        const tb = b.completed_at ? new Date(b.completed_at).getTime() : 0;
        if (tb !== ta) return tb - ta;
        return b.id - a.id;
      });
      return { dateKey: key, label: key === todayKey ? "今天" : key.replaceAll("-", "."), tasks };
    });
  }, [doneTasks, todayKey]);

  const handleToggleDoneDate = (dateKey: string) => {
    setExpandedDoneDates((prev) => {
      const next = new Set(prev);
      if (next.has(dateKey)) next.delete(dateKey);
      else next.add(dateKey);
      return next;
    });
  };

  const completedCount = doneTasks.length;
  const totalCount = planData?.tasks.length ?? 0;
  const completionRate = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  // ===== 拖拽 =====
  const [activeId, setActiveId] = useState<number | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as number);
  };

  const handleDragOver = () => {};

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);
    if (!over || !planData) return;

    const taskId = active.id as number;
    const overIdStr = String(over.id);

    let targetColumn: KanbanColumn | null = null;

    if (overIdStr === "col-todo") targetColumn = "todo";
    else if (overIdStr === "col-in_progress") targetColumn = "in_progress";
    else if (overIdStr === "col-done") targetColumn = "done";
    else {
      const task = planData.tasks.find((t) => String(t.id) === overIdStr);
      if (task) {
        if (task.status === "completed") targetColumn = "done";
        else if (inProgressIds.has(task.id)) targetColumn = "in_progress";
        else targetColumn = "todo";
      }
    }

    if (!targetColumn) return;

    const currentTask = planData.tasks.find((t) => t.id === taskId);
    if (!currentTask) return;

    if (targetColumn === "done" && currentTask.status !== "completed") {
      try {
        const result = await completeTask(taskId);
        handleTaskUpdate(taskId, result.task);
      } catch (err) {
        console.error("完成任务失败:", err);
      }
    } else if (targetColumn !== "done" && currentTask.status === "completed") {
      try {
        const updated = await uncompleteTask(taskId);
        handleTaskUpdate(taskId, updated);
        if (targetColumn === "in_progress") {
          setInProgressIds((prev) => new Set(prev).add(taskId));
        } else {
          setInProgressIds((prev) => {
            const next = new Set(prev);
            next.delete(taskId);
            return next;
          });
        }
      } catch (err) {
        console.error("取消完成失败:", err);
      }
    } else if (targetColumn === "in_progress" && !inProgressIds.has(taskId)) {
      setInProgressIds((prev) => new Set(prev).add(taskId));
    } else if (targetColumn === "todo" && inProgressIds.has(taskId)) {
      setInProgressIds((prev) => {
        const next = new Set(prev);
        next.delete(taskId);
        return next;
      });
    }
  };

  const activeTask = activeId ? planData?.tasks.find((t) => t.id === activeId) : null;

  const isLongTerm = planData?.goal.goal_type === "long_term";
  const showLongTermNudge = !!activeLongTerm && activeLongTerm.today_tasks.length === 0;

  // ===== 列定义 =====
  const columns: { id: KanbanColumn; title: string; color: string; glowColor: string; tasks: Task[]; colId: string }[] = [
    { id: "todo", title: "待办", color: "text-accent-blue", glowColor: "bg-accent-blue", tasks: todoTasks, colId: "col-todo" },
    { id: "in_progress", title: "进行中", color: "text-accent-amber", glowColor: "bg-accent-amber", tasks: inProgressTasks, colId: "col-in_progress" },
    { id: "done", title: "已完成", color: "text-accent-green", glowColor: "bg-accent-green", tasks: doneTasks, colId: "col-done" },
  ];

  return (
    <div className="min-h-screen bg-bg-primary flex flex-col">
      {/* ===== 顶部导航栏 ===== */}
      <header className="glass-strong sticky top-0 z-30">
        <div className="px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-bold text-text-primary tracking-tight">
              <span className="text-accent-blue">AI</span>Coach
            </h1>
            <span className="text-xs text-text-tertiary hidden sm:inline">Hi, {user.username}</span>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-3 px-4 py-1.5 rounded-lg bg-bg-tertiary/50 border border-border-subtle">
              <span className="text-xs text-text-secondary">{dateStr} {weekDay}</span>
              <span className="w-px h-4 bg-border-default" />
              <span className="text-sm font-mono font-medium text-accent-blue tabular-nums">{timeStr}</span>
            </div>

            {planData && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-bg-tertiary/50 border border-border-subtle">
                <div className="w-16 h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${completionRate === 100 ? "bg-accent-green" : "bg-accent-blue"}`}
                    style={{ width: `${completionRate}%` }}
                  />
                </div>
                <span className={`text-xs font-mono font-bold ${completionRate === 100 ? "text-accent-green" : "text-accent-blue"}`}>
                  {completionRate}%
                </span>
                <span className="text-[11px] text-text-tertiary">{completedCount}/{totalCount}</span>
              </div>
            )}

            {/* 增量：快速完成按钮 */}
            {/* 改动原因：用户可以主动触发加餐，不依赖自动检测 */}
            {planData && completionRate === 100 && planData.tasks.length >= 3 && !showBonusPrompt && !bonusDismissed && (
              <button
                type="button"
                onClick={() => setShowBonusPrompt(true)}
                className="text-xs px-3 py-1.5 rounded-lg bg-accent-green/10 text-accent-green hover:bg-accent-green/20 transition-all cursor-pointer border border-accent-green/20"
              >
                加餐任务
              </button>
            )}

            <ThemeToggle />
            <button
              type="button"
              onClick={() => onNavigateChat()}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer border border-border-subtle"
            >
              AI 对话
            </button>
            <button
              type="button"
              className="text-xs px-3 py-1.5 rounded-lg bg-accent-blue/10 text-accent-blue border border-accent-blue/20 cursor-default"
            >
              任务看板
            </button>
            <button
              type="button"
              onClick={onNavigateHistory}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer border border-border-subtle"
            >
              历史
            </button>
            <button
              type="button"
              onClick={onNavigateReview}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer border border-border-subtle"
            >
              复盘
            </button>
            {/* 增量：偏好设置按钮 */}
            {/* 改动原因：用户需要入口来调整 Quiet Hours 偏好 */}
            <button
              type="button"
              onClick={handleOpenPrefs}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer border border-border-subtle"
              title="个性设置"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-tertiary hover:text-accent-red hover:bg-accent-red/10 transition-all cursor-pointer border border-border-subtle"
            >
              退出
            </button>
          </div>
        </div>
      </header>
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* 空状态提示 - 无计划时显示 */}
        {!planData && !isLoading && !isRestoring && (
          <div className="px-6 pt-4 pb-2">
            <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-bg-secondary border border-border-subtle">
              <svg className="w-5 h-5 text-text-tertiary shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <p className="text-sm text-text-secondary">暂无任务计划</p>
              <button
                type="button"
                onClick={() => onNavigateChat()}
                className="ml-auto text-xs px-3 py-1.5 rounded-lg bg-accent-blue text-white hover:bg-accent-blue/90 transition-all cursor-pointer"
              >
                去生成计划
              </button>
            </div>
          </div>
        )}

        {/* 错误提示 */}
        {error && (
          <div className="mx-6 mb-3 p-3 bg-accent-red/10 border border-accent-red/20 rounded-xl animate-fade-in-up">
            <p className="text-sm text-accent-red">{error}</p>
            <button type="button" onClick={() => setError(null)} className="mt-1 text-xs text-accent-red/60 hover:text-accent-red cursor-pointer">关闭</button>
          </div>
        )}

        {/* Toast 提示（时间调整） */}
        {/* 改动原因：避免用户困惑"为什么时间变了" */}
        {toast && (
          <div className="mx-6 mb-3 p-3 bg-accent-amber/10 border border-accent-amber/20 rounded-xl animate-fade-in-up flex items-center gap-2">
            <svg className="w-4 h-4 text-accent-amber shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm text-accent-amber">{toast}</p>
            <button type="button" onClick={() => setToast(null)} className="ml-auto text-xs text-accent-amber/60 hover:text-accent-amber cursor-pointer">✕</button>
          </div>
        )}

        {/* 恢复中 */}
        {isRestoring && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="relative w-10 h-10 mx-auto mb-3">
                <div className="absolute inset-0 rounded-full border-2 border-accent-blue/20" />
                <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-accent-blue animate-spin" />
              </div>
              <p className="text-sm text-text-tertiary">正在恢复上次的计划...</p>
            </div>
          </div>
        )}

        {/* 加载骨架 */}
        {isLoading && (
          <div className="flex-1 px-6 pb-6 grid grid-cols-3 gap-4">
            {[0, 1, 2].map((col) => (
              <div key={col} className="space-y-3">
                <div className="h-8 bg-bg-card rounded-lg animate-pulse" />
                {[0, 1, 2].map((i) => (
                  <div key={i} className="bg-bg-card rounded-xl p-4 border border-border-subtle animate-shimmer">
                    <div className="flex gap-2 mb-3">
                      <div className="w-4 h-4 bg-bg-tertiary rounded" />
                      <div className="h-3 bg-bg-tertiary rounded w-12" />
                    </div>
                    <div className="h-4 bg-bg-tertiary rounded w-3/4 mb-2" />
                    <div className="h-12 bg-bg-tertiary/50 rounded-lg" />
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* 看板主体 */}
        {!isLoading && !isRestoring && (
          <div className="flex-1 px-6 pb-6 overflow-hidden">
            {/* 目标展示条 - 有计划时显示 */}
            {planData && (
            <>
            <div className={`mb-5 px-5 py-3.5 rounded-xl flex items-center gap-3 border ${
              isLongTerm
                ? "bg-accent-purple/5 border-accent-purple/15"
                : "bg-accent-blue/5 border-accent-blue/15"
            }`}>
              <span className={`text-sm font-bold tracking-wide shrink-0 ${
                isLongTerm ? "text-accent-purple" : "text-accent-blue"
              }`}>
                {isLongTerm ? "🎯 长期计划" : "🎯 今日目标"}
              </span>
              <span className={`w-px h-5 ${isLongTerm ? "bg-accent-purple/20" : "bg-accent-blue/20"}`} />
              <p className="text-base font-medium text-text-primary truncate leading-snug">{planData.goal.content}</p>
              {isLongTerm && planData.goal.target_duration_days && (
                <span className="text-xs font-mono text-accent-purple/60 bg-accent-purple/10 px-2 py-0.5 rounded shrink-0">
                  {planData.goal.target_duration_days}天
                </span>
              )}
            </div>

            {/* 增量：长期计划摘要卡片 */}
            {/* 改动原因：用户需要看到路线图概览，了解整体进度 */}
            {isLongTerm && planData.goal.roadmap_summary && (
              <div className="mb-4 px-4 py-3 rounded-xl bg-gradient-to-r from-accent-purple/5 to-accent-blue/5 border border-accent-purple/10">
                <div className="flex items-center gap-2 mb-2">
                  <svg className="w-4 h-4 text-accent-purple" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                  </svg>
                  <span className="text-xs font-semibold text-accent-purple">学习路线图</span>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed">{planData.goal.roadmap_summary}</p>
              </div>
            )}
            </>
            )}

            {/* 长期计划：今日任务为空时的常驻引导条（不依赖 sessionStorage 一次性弹窗） */}
            {showLongTermNudge && (
              <div className="mb-4 px-4 py-3 rounded-xl bg-accent-purple/5 border border-accent-purple/15 flex items-start gap-3 animate-fade-in-up">
                <svg className="w-5 h-5 text-accent-purple shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M12 18a6 6 0 100-12 6 6 0 000 12z" />
                </svg>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-text-primary font-medium">今天还没有生成长期计划任务</p>
                  <p className="text-xs text-text-secondary mt-0.5">
                    目标：{activeLongTerm.goal.content}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => setShowLongTermPrompt(true)}
                    className="px-4 py-2 bg-bg-tertiary text-text-secondary rounded-lg text-sm font-medium hover:bg-border-strong transition-colors cursor-pointer border border-border-subtle"
                  >
                    打开引导
                  </button>
                  <button
                    type="button"
                    onClick={handleContinueLongTerm}
                    disabled={isContinuingLongTerm}
                    className={`px-4 py-2 rounded-lg font-medium text-sm transition-all cursor-pointer ${
                      isContinuingLongTerm ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed" : "bg-accent-purple text-white hover:bg-accent-purple/90"
                    }`}
                  >
                    {isContinuingLongTerm ? "处理中..." : "继续任务"}
                  </button>
                </div>
              </div>
            )}

            <DndContext
              sensors={sensors}
              collisionDetection={closestCorners}
              onDragStart={handleDragStart}
              onDragOver={handleDragOver}
              onDragEnd={handleDragEnd}
            >
              <div className="grid grid-cols-3 gap-4 h-full">
                {columns.map((column) => (
                  <DroppableColumn
                    key={column.id}
                    column={column}
                    planData={planData}
                    onUpdateTask={handleTaskUpdate}
                    onDeleteTask={column.id === "todo" ? handleTaskDeleteLocal : undefined}
                    onOpenAddTask={column.id === "todo" ? handleOpenCreateTask : undefined}
                    doneSections={column.id === "done" ? doneSections : undefined}
                    expandedDoneDates={column.id === "done" ? expandedDoneDates : undefined}
                    onToggleDoneDate={column.id === "done" ? handleToggleDoneDate : undefined}
                  />
                ))}
              </div>

              <DragOverlay>
                {activeTask && (
                  <div className="drag-overlay rounded-xl p-4 bg-bg-card border border-accent-blue/30 w-72">
                    <h3 className="text-sm font-medium text-text-primary mb-1.5">{activeTask.description}</h3>
                    <p className="text-xs text-text-secondary line-clamp-2">{activeTask.criteria}</p>
                  </div>
                )}
              </DragOverlay>
            </DndContext>
          </div>
        )}

        {/* 空状态：输入框已居中展示，无需额外提示 */}
      </main>

      {/* 刷新检测：长期任务引导弹窗 */}
      {showLongTermPrompt && activeLongTerm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-overlay backdrop-blur-sm">
          <div className="glass-strong rounded-2xl shadow-2xl p-6 mx-4 max-w-md w-full animate-scale-in">
            <div className="flex items-start justify-between gap-3">
            <h3 className="text-base font-semibold text-text-primary mb-1">检测到进行中的长期计划</h3>
              <button
                type="button"
                onClick={() => {
                  setShowLongTermPrompt(false);
                  setShowCancelLongTermConfirm(false);
                  setLongTermError(null);
                  setLongTermFeedback("");
                }}
                className="shrink-0 w-8 h-8 rounded-lg bg-bg-tertiary/60 hover:bg-bg-tertiary text-text-tertiary hover:text-text-secondary transition-colors cursor-pointer border border-border-subtle flex items-center justify-center"
                aria-label="关闭"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="text-sm text-text-secondary mb-4">你可以继续推进、取消当前计划，或回到 AI 对话重新规划。</p>

            <div className="p-3 rounded-xl bg-bg-tertiary/40 border border-border-subtle">
              <p className="text-sm font-medium text-text-primary line-clamp-2">{activeLongTerm.goal.content}</p>
              <div className="flex items-center gap-2 mt-2">
                <div className={`flex-1 h-1.5 rounded-full bg-bg-tertiary overflow-hidden ${isContinuingLongTerm ? "animate-pulse" : ""}`}>
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${activeLongTerm.progress.completion_rate === 100 ? "bg-accent-green" : "bg-accent-blue"} ${isContinuingLongTerm ? "opacity-70" : ""}`}
                    style={{ width: `${activeLongTerm.progress.completion_rate}%` }}
                  />
                </div>
                <span className={`text-xs font-mono font-bold ${activeLongTerm.progress.completion_rate === 100 ? "text-accent-green" : "text-accent-blue"}`}>
                  {activeLongTerm.progress.completion_rate}%
                </span>
                <span className="text-[11px] text-text-tertiary">{activeLongTerm.progress.completed}/{activeLongTerm.progress.total}</span>
              </div>
              <p className="text-xs text-text-tertiary mt-2">
                今天已有 {activeLongTerm.today_tasks.length} 条任务。点击“继续任务”会幂等补齐/返回今天任务，避免重复生成。
              </p>
            </div>

            <div className="mt-3">
              <label className="block text-xs font-medium text-text-tertiary mb-1 uppercase tracking-wider">可选反馈（用于滚动调整）</label>
              <textarea
                value={longTermFeedback}
                onChange={(e) => setLongTermFeedback(e.target.value)}
                rows={2}
                placeholder={'例如："今天精力一般，任务别太多"'}
                className="w-full resize-none rounded-lg bg-bg-secondary border border-border-subtle px-3 py-2 text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-blue/50"
              />
            </div>

            {isContinuingLongTerm && (
              <div className="mt-3 p-2 rounded-lg bg-accent-blue/10 border border-accent-blue/20">
                <p className="text-xs text-accent-blue">正在生成/同步今天任务…</p>
              </div>
            )}

            {longTermError && (
              <div className="mt-3 p-2 rounded-lg bg-accent-red/10 border border-accent-red/20">
                <p className="text-xs text-accent-red">{longTermError}</p>
              </div>
            )}

            {showCancelLongTermConfirm ? (
              <div className="mt-4">
                <div className="p-3 rounded-xl bg-accent-red/10 border border-accent-red/20">
                  <p className="text-sm text-text-primary font-medium mb-1">确认取消当前长期计划？</p>
                  <p className="text-xs text-text-secondary">将清理所有未完成任务（已完成记录保留）。该操作不可恢复。</p>
                </div>
                <div className="flex gap-2 mt-3 justify-end">
                  <button
                    type="button"
                    onClick={() => setShowCancelLongTermConfirm(false)}
                    disabled={isCancellingLongTerm}
                    className="px-4 py-2 bg-bg-tertiary text-text-secondary rounded-lg text-sm font-medium hover:bg-border-strong transition-colors cursor-pointer"
                  >
                    返回
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelLongTerm}
                    disabled={isCancellingLongTerm}
                    className={`px-5 py-2 rounded-lg font-medium text-sm transition-all cursor-pointer ${
                      isCancellingLongTerm ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed" : "bg-accent-red text-white hover:bg-accent-red/90"
                    }`}
                  >
                    {isCancellingLongTerm ? "取消中..." : "确认取消"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2 mt-4">
                <button
                  type="button"
                  onClick={handleContinueLongTerm}
                  disabled={isContinuingLongTerm}
                  className={`flex-1 py-2 rounded-lg font-medium text-sm transition-all cursor-pointer ${
                    isContinuingLongTerm ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed" : "bg-accent-blue text-white hover:bg-accent-blue/90"
                  }`}
                >
                  {isContinuingLongTerm ? "处理中..." : "继续任务"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCancelLongTermConfirm(true)}
                  disabled={isContinuingLongTerm}
                  className="px-4 py-2 bg-accent-red/10 text-accent-red rounded-lg text-sm font-medium hover:bg-accent-red/20 transition-colors cursor-pointer border border-accent-red/20"
                >
                  取消任务
                </button>
                <button
                  type="button"
                  onClick={handleReplanLongTerm}
                  disabled={isContinuingLongTerm}
                  className="px-4 py-2 bg-bg-tertiary text-text-secondary rounded-lg text-sm font-medium hover:bg-border-strong transition-colors cursor-pointer"
                >
                  重新规划
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 继续任务结果弹窗（比 toast 更显眼） */}
      {showLongTermResult && longTermResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-overlay backdrop-blur-sm">
          <div className="glass-strong rounded-2xl shadow-2xl p-6 mx-4 max-w-md w-full animate-scale-in">
            <h3 className="text-base font-semibold text-text-primary mb-1">{longTermResult.title}</h3>
            <p className="text-sm text-text-secondary mb-4 whitespace-pre-line">{longTermResult.message}</p>

            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => {
                  setShowLongTermResult(false);
                  window.setTimeout(
                    () => document.getElementById("col-todo")?.scrollIntoView({ behavior: "smooth", block: "start" }),
                    50,
                  );
                }}
                className="px-4 py-2 rounded-lg font-medium text-sm bg-accent-blue text-white hover:bg-accent-blue/90 transition-all cursor-pointer"
              >
                查看待办
              </button>
              <button
                type="button"
                onClick={() => setShowLongTermResult(false)}
                className="px-4 py-2 bg-bg-tertiary text-text-secondary rounded-lg text-sm font-medium hover:bg-border-strong transition-colors cursor-pointer"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 手动新增任务弹窗 */}
      {showCreateTask && planData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-overlay backdrop-blur-sm">
          <div className="glass-strong rounded-2xl shadow-2xl p-6 mx-4 max-w-md w-full animate-scale-in">
            <h3 className="text-base font-semibold text-text-primary mb-1">新增待办任务</h3>
            <p className="text-sm text-text-secondary mb-4">手动补充任务会进入「待办」列表</p>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-tertiary mb-1 uppercase tracking-wider">任务描述</label>
                <input
                  type="text"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary placeholder-text-tertiary focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all"
                  placeholder="例如：复习第6章：风险管理..."
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-tertiary mb-1 uppercase tracking-wider">完成标准</label>
                <textarea
                  value={newCriteria}
                  onChange={(e) => setNewCriteria(e.target.value)}
                  rows={3}
                  className="w-full px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary placeholder-text-tertiary focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all resize-none"
                  placeholder="例如：完成5道真题，正确率80%以上"
                />
              </div>
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-text-tertiary mb-1 uppercase tracking-wider">开始（可选）</label>
                  <input
                    type="time"
                    value={newStartAt}
                    onChange={(e) => setNewStartAt(e.target.value)}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary font-mono focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all"
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-xs font-medium text-text-tertiary mb-1 uppercase tracking-wider">截止（可选）</label>
                  <input
                    type="time"
                    value={newEndAt}
                    onChange={(e) => setNewEndAt(e.target.value)}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary font-mono focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all"
                  />
                </div>
              </div>
            </div>

            {createTaskError && (
              <div className="mt-3 p-2 bg-accent-red/10 border border-accent-red/20 rounded-lg">
                <p className="text-xs text-accent-red">{createTaskError}</p>
              </div>
            )}

            <div className="flex gap-2 mt-4">
              <button
                type="button"
                onClick={handleConfirmCreateTask}
                disabled={isCreatingTask}
                className={`flex-1 py-2 rounded-lg font-medium text-sm transition-all cursor-pointer ${
                  isCreatingTask ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed" : "bg-accent-blue text-white hover:bg-accent-blue/90"
                }`}
              >
                {isCreatingTask ? "保存中..." : "保存"}
              </button>
              <button
                type="button"
                onClick={() => setShowCreateTask(false)}
                disabled={isCreatingTask}
                className="px-4 py-2 bg-bg-tertiary text-text-secondary rounded-lg text-sm font-medium hover:bg-border-strong transition-colors cursor-pointer"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 加餐任务提示弹窗 */}
      {/* 改动原因：实现"教练主动介入"，新任务依据复盘而不是随机加任务 */}
      {showBonusPrompt && planData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-bg-card border border-border-subtle rounded-2xl p-6 max-w-sm mx-4 animate-scale-in shadow-2xl">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-xl bg-accent-green/10 flex items-center justify-center">
                <svg className="w-5 h-5 text-accent-green" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-semibold text-text-primary">太棒了！全部完成 🎉</h3>
                <p className="text-xs text-text-secondary">是否生成新的加餐任务？</p>
              </div>
            </div>
            <p className="text-sm text-text-secondary mb-3">
              将基于你的复盘报告自动调整，生成 2-3 条增量任务。
            </p>
            <textarea
              value={bonusFeedback}
              onChange={(e) => setBonusFeedback(e.target.value)}
              placeholder={'可选：告诉 AI 你的状态（如"今天状态很好，想多做一点"）'}
              rows={2}
              className="w-full resize-none rounded-lg bg-bg-secondary border border-border-subtle px-3 py-2 text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-blue/50 mb-4"
            />
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => { setShowBonusPrompt(false); setBonusDismissed(true); }}
                className="flex-1 px-4 py-2 rounded-lg bg-bg-tertiary text-text-secondary hover:text-text-primary transition-all cursor-pointer border border-border-subtle text-sm"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleDispatchMore}
                disabled={isDispatchingMore}
                className="flex-1 px-4 py-2 rounded-lg bg-accent-green text-white hover:bg-accent-green/80 transition-all cursor-pointer text-sm font-medium disabled:opacity-50"
              >
                {isDispatchingMore ? "生成中..." : "生成加餐"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 偏好设置弹窗 */}
      {showPrefs && prefs && (
        <PreferencesModal
          preferences={prefs}
          onSave={handleSavePrefs}
          onClose={() => setShowPrefs(false)}
        />
      )}
    </div>
  );
}
