/**
 * TaskCard 组件 — 看板卡片版（暗色主题）
 *
 * 设计方向：
 * - 紧凑卡片，适配看板列宽
 * - 暗色玻璃拟态背景
 * - 状态标签使用霓虹色
 * - 拖拽手柄 + 悬停微动效
 * - 保留：完成/编辑/重新生成/超时弹窗
 */

import { useState } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { Task, UpdateTaskRequest } from "../../types/api";
import { ApiError, completeTask, deleteTask, regenerateTask, uncompleteTask, updateCompletionReason, updateTask } from "../../services/api";

interface TaskCardProps {
  task: Task;
  index: number;
  onUpdateTask?: (taskId: number, updatedTask: Task) => void;
  onDeleteTask?: (taskId: number) => void;
}

function formatTime(isoStr: string | null): string {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
  } catch {
    return "";
  }
}

function formatTimeWithSec(isoStr: string | null): string {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
  } catch {
    return "";
  }
}

// 用于 time input 的格式化（HH:MM，不带秒）
function formatTimeForInput(isoStr: string | null): string {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  } catch {
    return "";
  }
}

export default function TaskCard({ task, index, onUpdateTask, onDeleteTask }: TaskCardProps) {
  const isCompleted = task.status === "completed";

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  // 编辑模式
  const [isEditing, setIsEditing] = useState(false);
  const [editDesc, setEditDesc] = useState(task.description);
  const [editCriteria, setEditCriteria] = useState(task.criteria);
  const [editStartAt, setEditStartAt] = useState(formatTime(task.planned_start_at));
  const [editEndAt, setEditEndAt] = useState(formatTime(task.planned_end_at));

  // 重新生成弹窗
  const [showRegenModal, setShowRegenModal] = useState(false);
  const [regenFeedback, setRegenFeedback] = useState("");
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);

  // 超时完成弹窗
  const [showOverdueModal, setShowOverdueModal] = useState(false);
  const [overdueReason, setOverdueReason] = useState("");
  const [pendingCompleteTask, setPendingCompleteTask] = useState<Task | null>(null);

  // 删除确认弹窗
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // ===== 完成操作 =====
  const handleComplete = async () => {
    try {
      const result = await completeTask(task.id);
      onUpdateTask?.(task.id, result.task);
      if (result.is_late && result.reason_required) {
        setPendingCompleteTask(result.task);
        setShowOverdueModal(true);
      }
    } catch (err) {
      console.error("完成任务失败:", err);
    }
  };

  const handleOverdueConfirm = async () => {
    if (pendingCompleteTask && overdueReason.trim()) {
      try {
        const updated = await updateCompletionReason(pendingCompleteTask.id, overdueReason.trim());
        onUpdateTask?.(pendingCompleteTask.id, updated);
      } catch (err) {
        console.error("更新原因失败:", err);
      }
    }
    setShowOverdueModal(false);
    setOverdueReason("");
    setPendingCompleteTask(null);
  };

  const handleOverdueSkip = () => {
    setShowOverdueModal(false);
    setOverdueReason("");
    setPendingCompleteTask(null);
  };

  // ===== 取消完成 =====
  const handleUncomplete = async () => {
    if (!isCompleted) return;
    try {
      const updated = await uncompleteTask(task.id);
      onUpdateTask?.(task.id, updated);
    } catch (err) {
      console.error("取消完成失败:", err);
    }
  };

  // ===== 编辑模式 =====
  const handleStartEdit = () => {
    setEditDesc(task.description);
    setEditCriteria(task.criteria);
    setEditStartAt(formatTimeForInput(task.planned_start_at));
    setEditEndAt(formatTimeForInput(task.planned_end_at));
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    const updates: UpdateTaskRequest = {};
    if (editDesc.trim() !== task.description) updates.description = editDesc.trim();
    if (editCriteria.trim() !== task.criteria) updates.criteria = editCriteria.trim();

    // 使用原任务的日期，只修改时间部分
    const baseDate = task.planned_start_at ? new Date(task.planned_start_at) : new Date();

    if (editStartAt && editStartAt !== "--:--") {
      const [h, m, s = 0] = editStartAt.split(":").map(Number);
      const dt = new Date(baseDate);
      dt.setHours(h, m, s, 0);
      updates.planned_start_at = dt.toISOString();
    } else if (editStartAt === "" || editStartAt === "--:--") {
      updates.planned_start_at = null;
    }

    if (editEndAt && editEndAt !== "--:--") {
      const [h, m, s = 0] = editEndAt.split(":").map(Number);
      const dt = new Date(baseDate);
      dt.setHours(h, m, s, 0);
      updates.planned_end_at = dt.toISOString();
    } else if (editEndAt === "" || editEndAt === "--:--") {
      updates.planned_end_at = null;
    }

    // 如果没有时间变化，不发送时间字段
    if (updates.planned_start_at === task.planned_start_at) {
      delete (updates as Record<string, unknown>).planned_start_at;
    }
    if (updates.planned_end_at === task.planned_end_at) {
      delete (updates as Record<string, unknown>).planned_end_at;
    }

    try {
      const updated = await updateTask(task.id, updates);
      onUpdateTask?.(task.id, updated);
      setIsEditing(false);
    } catch (err) {
      console.error("保存编辑失败:", err);
    }
  };

  // ===== 删除任务 =====
  const handleConfirmDelete = async () => {
    if (isCompleted || isDeleting) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteTask(task.id);
      onDeleteTask?.(task.id);
      setShowDeleteModal(false);
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "删除失败");
    } finally {
      setIsDeleting(false);
    }
  };

  // ===== 重新生成 =====
  const handleRegenerate = async () => {
    setIsRegenerating(true);
    setRegenError(null);
    try {
      const updated = await regenerateTask(task.id, regenFeedback.trim() || undefined);
      onUpdateTask?.(task.id, updated);
      setShowRegenModal(false);
      setRegenFeedback("");
    } catch (err) {
      setRegenError(err instanceof ApiError ? err.message : "重新生成失败");
    } finally {
      setIsRegenerating(false);
    }
  };

  // ===== 渲染 =====
  return (
    <>
      <div
        ref={setNodeRef}
        style={style}
        className={`
          group rounded-xl p-4 transition-all duration-200 cursor-default
          ${isCompleted
            ? "bg-bg-card/60 border border-accent-green/20"
            : task.is_late
              ? "bg-bg-card border border-accent-amber/20"
              : "bg-bg-card border border-border-default hover:border-border-strong hover:bg-bg-card-hover"
          }
          ${isDragging ? "shadow-lg shadow-black/20" : ""}
        `}
      >
        {/* 头部：拖拽手柄 + 序号 + 时间 + 操作 */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {/* 拖拽手柄 */}
            <button
              type="button"
              className="cursor-grab active:cursor-grabbing text-text-tertiary hover:text-text-secondary transition-colors p-0.5"
              {...attributes}
              {...listeners}
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
                <circle cx="5" cy="3" r="1.5" />
                <circle cx="11" cy="3" r="1.5" />
                <circle cx="5" cy="8" r="1.5" />
                <circle cx="11" cy="8" r="1.5" />
                <circle cx="5" cy="13" r="1.5" />
                <circle cx="11" cy="13" r="1.5" />
              </svg>
            </button>

            {/* 完成勾选 */}
            <button
              type="button"
              onClick={isCompleted ? handleUncomplete : handleComplete}
              className={`
                w-4.5 h-4.5 rounded flex items-center justify-center transition-all cursor-pointer shrink-0
                ${isCompleted
                  ? "bg-accent-green text-white"
                  : "border border-border-strong hover:border-accent-blue"
                }
              `}
              aria-label={isCompleted ? "取消完成" : "标记完成"}
            >
              {isCompleted && (
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </button>

            <span className="text-xs font-mono text-text-tertiary">#{index}</span>

            {/* 时间窗口 */}
            {(task.planned_start_at || task.planned_end_at) && (
              <span className={`text-xs font-mono px-1.5 py-0.5 rounded whitespace-nowrap ${
                task.is_late ? "text-accent-amber bg-accent-amber/10" : "text-text-tertiary bg-bg-tertiary"
              }`}>
                {formatTime(task.planned_start_at)}–{formatTime(task.planned_end_at)}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
            {/* 状态标签 */}
            {task.is_late && !isCompleted && (
              <span className="text-xs font-medium px-1.5 py-0.5 rounded-full bg-accent-amber/15 text-accent-amber">超时</span>
            )}
            {isCompleted && (
              <span className="text-xs font-medium px-1.5 py-0.5 rounded-full bg-accent-green/15 text-accent-green">完成</span>
            )}

            {/* 操作按钮 */}
            {!isEditing && !isCompleted && (
              <>
                <button
                  type="button"
                  onClick={() => setShowRegenModal(true)}
                  className="p-1 text-text-tertiary hover:text-accent-purple transition-colors cursor-pointer rounded"
                  title="重新生成"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={handleStartEdit}
                  className="p-1 text-text-tertiary hover:text-accent-blue transition-colors cursor-pointer rounded"
                  title="编辑"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                {onDeleteTask && (
                  <button
                    type="button"
                    onClick={() => { setShowDeleteModal(true); setDeleteError(null); }}
                    className="p-1 text-text-tertiary hover:text-accent-red transition-colors cursor-pointer rounded"
                    title="删除"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3m4 0H5" />
                    </svg>
                  </button>
                )}
              </>
            )}
          </div>
        </div>

        {/* 编辑模式 */}
        {isEditing ? (
          <div className="space-y-2.5">
            <div>
              <label className="block text-xs font-medium text-text-tertiary mb-1 uppercase tracking-wider">任务描述</label>
              <input
                type="text"
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
                className="w-full px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary placeholder-text-tertiary focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-text-tertiary mb-1 uppercase tracking-wider">完成标准</label>
              <textarea
                value={editCriteria}
                onChange={(e) => setEditCriteria(e.target.value)}
                rows={2}
                className="w-full px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary placeholder-text-tertiary focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all resize-none"
              />
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <label className="block text-xs font-medium text-text-tertiary mb-1 uppercase tracking-wider">开始</label>
                <input
                  type="time"
                  value={editStartAt}
                  onChange={(e) => setEditStartAt(e.target.value)}
                  className="w-full px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary font-mono focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all"
                />
              </div>
              <div className="flex-1">
                <label className="block text-xs font-medium text-text-tertiary mb-1 uppercase tracking-wider">截止</label>
                <input
                  type="time"
                  value={editEndAt}
                  onChange={(e) => setEditEndAt(e.target.value)}
                  className="w-full px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary font-mono focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all"
                />
              </div>
            </div>
            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={handleSaveEdit}
                className="px-3 py-1 bg-accent-blue text-white text-xs font-medium rounded-lg hover:bg-accent-blue/90 transition-colors cursor-pointer"
              >
                保存
              </button>
              <button
                type="button"
                onClick={() => setIsEditing(false)}
                className="px-3 py-1 bg-bg-tertiary text-text-secondary text-xs font-medium rounded-lg hover:bg-border-strong transition-colors cursor-pointer"
              >
                取消
              </button>
            </div>
          </div>
        ) : (
          <>
            <h3 className={`text-base font-medium mb-2 leading-snug ${
              isCompleted ? "text-text-tertiary line-through" : "text-text-primary"
            }`}>
              {task.description}
            </h3>
            <div className="bg-bg-tertiary/60 rounded-lg px-3 py-2.5 mb-2">
              <p className={`text-sm leading-relaxed ${
                isCompleted ? "text-text-tertiary line-through" : "text-text-secondary"
              }`}>
                {task.criteria}
              </p>
            </div>
            {isCompleted && task.completed_at && (
              <p className="text-[11px] font-mono text-accent-green/70">
                ✓ 完成于 {formatTimeWithSec(task.completed_at)}
              </p>
            )}
          </>
        )}
      </div>

      {/* 重新生成弹窗 */}
      {showRegenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-overlay backdrop-blur-sm">
          <div className="glass-strong rounded-2xl shadow-2xl p-6 mx-4 max-w-sm w-full animate-scale-in">
            <h3 className="text-base font-semibold text-text-primary mb-1">重新生成任务</h3>
            <p className="text-sm text-text-secondary mb-4">AI 将根据目标上下文改写这条任务</p>
            <div className="mb-4">
              <label className="block text-xs font-medium text-text-tertiary mb-1 uppercase tracking-wider">反馈（可选）</label>
              <textarea
                value={regenFeedback}
                onChange={(e) => setRegenFeedback(e.target.value)}
                placeholder="例如：太难了拆小一点..."
                rows={3}
                className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary placeholder-text-tertiary focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/20 outline-none transition-all resize-none"
              />
            </div>
            {regenError && (
              <div className="mb-3 p-2 bg-accent-red/10 border border-accent-red/20 rounded-lg">
                <p className="text-xs text-accent-red">{regenError}</p>
              </div>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleRegenerate}
                disabled={isRegenerating}
                className={`flex-1 py-2 rounded-lg font-medium text-sm transition-all cursor-pointer ${
                  isRegenerating
                    ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed"
                    : "bg-accent-purple text-white hover:bg-accent-purple/90"
                }`}
              >
                {isRegenerating ? "AI 改写中..." : "确认改写"}
              </button>
              <button
                type="button"
                onClick={() => { setShowRegenModal(false); setRegenFeedback(""); setRegenError(null); }}
                disabled={isRegenerating}
                className="px-4 py-2 bg-bg-tertiary text-text-secondary rounded-lg text-sm font-medium hover:bg-border-strong transition-colors cursor-pointer"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 超时完成弹窗 */}
      {showOverdueModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-overlay backdrop-blur-sm">
          <div className="glass-strong rounded-2xl shadow-2xl p-6 mx-4 max-w-sm w-full animate-scale-in">
            <div className="text-3xl mb-2">⏰</div>
            <h3 className="text-base font-semibold text-text-primary mb-1">任务已超时</h3>
            <p className="text-sm text-text-secondary mb-4">可以简单说明超时原因（也可跳过，AI 复盘时会分析）</p>
            <div className="mb-4">
              <textarea
                value={overdueReason}
                onChange={(e) => setOverdueReason(e.target.value)}
                placeholder="例如：被其他事情打断了..."
                rows={2}
                className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary placeholder-text-tertiary focus:border-accent-amber focus:ring-1 focus:ring-accent-amber/20 outline-none transition-all resize-none"
              />
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleOverdueConfirm}
                className="flex-1 py-2 bg-accent-green text-white rounded-lg font-medium text-sm hover:bg-accent-green/90 transition-colors cursor-pointer"
              >
                确认完成
              </button>
              <button
                type="button"
                onClick={handleOverdueSkip}
                className="px-4 py-2 bg-bg-tertiary text-text-secondary rounded-lg text-sm font-medium hover:bg-border-strong transition-colors cursor-pointer"
              >
                跳过
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除确认弹窗 */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-overlay backdrop-blur-sm">
          <div className="glass-strong rounded-2xl shadow-2xl p-6 mx-4 max-w-sm w-full animate-scale-in">
            <h3 className="text-base font-semibold text-text-primary mb-1">删除任务</h3>
            <p className="text-sm text-text-secondary mb-4">确定要删除这条待办任务吗？此操作不可恢复。</p>
            {deleteError && (
              <div className="mb-3 p-2 bg-accent-red/10 border border-accent-red/20 rounded-lg">
                <p className="text-xs text-accent-red">{deleteError}</p>
              </div>
            )}
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className={`px-5 py-2 rounded-lg font-medium text-sm transition-all cursor-pointer ${
                  isDeleting ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed" : "bg-accent-red text-white hover:bg-accent-red/90"
                }`}
              >
                {isDeleting ? "删除中..." : "确认删除"}
              </button>
              <button
                type="button"
                onClick={() => setShowDeleteModal(false)}
                disabled={isDeleting}
                className="px-4 py-2 bg-bg-tertiary text-text-secondary rounded-lg text-sm font-medium hover:bg-border-strong transition-colors cursor-pointer"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
