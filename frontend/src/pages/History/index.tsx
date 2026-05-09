/**
 * HistoryPage — 历史计划页面（增强版）
 *
 * 功能：
 * - 展示所有历史计划列表
 * - 展开计划可查看任务列表 + 复盘报告
 * - 有复盘报告：直接在展开区域显示
 * - 无复盘报告：显示"生成复盘"按钮，点击跳转到复盘页面
 */

import { useState, useEffect, useCallback, useRef } from "react";
import type { PlanWithTasks, ReviewReport } from "../../types/api";
import { getPlanHistory, getReviewHistory, generateReview } from "../../services/api";
import ReviewCard from "../../components/business/ReviewCard";
import { ThemeToggle } from "../../components/business/ThemeProvider";
import type { User } from "../../types/api";

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

interface HistoryPageProps {
  user: User;
  onNavigateChat: () => void;
  onNavigateDashboard: (goalId: number | null) => void;
  onNavigateReview: () => void;
  onLogout: () => void;
}

export default function HistoryPage({
  user,
  onNavigateChat,
  onNavigateDashboard,
  onNavigateReview,
  onLogout,
}: HistoryPageProps) {
  const [history, setHistory] = useState<PlanWithTasks[]>([]);
  const [reviewsMap, setReviewsMap] = useState<Map<number, ReviewReport>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // 日期时钟
  const [currentTime, setCurrentTime] = useState(new Date());
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    clockRef.current = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => { if (clockRef.current) clearInterval(clockRef.current); };
  }, []);
  const dateStr = `${currentTime.getFullYear()}.${String(currentTime.getMonth() + 1).padStart(2, "0")}.${String(currentTime.getDate()).padStart(2, "0")}`;
  const weekDay = WEEKDAYS[currentTime.getDay()];
  const timeStr = `${String(currentTime.getHours()).padStart(2, "0")}:${String(currentTime.getMinutes()).padStart(2, "0")}`;

  // 正在生成复盘的 goalId
  const [generatingReviewFor, setGeneratingReviewFor] = useState<number | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [planData, reviewData] = await Promise.all([
          getPlanHistory(),
          getReviewHistory(),
        ]);
        setHistory(planData);
        // 构建 goal_id -> ReviewReport 的映射（只取单日复盘）
        const map = new Map<number, ReviewReport>();
        for (const r of reviewData) {
          if (r.goal_id != null) {
            if (!map.has(r.goal_id)) map.set(r.goal_id, r);
          }
        }
        setReviewsMap(map);
      } catch {
        setError("加载历史计划失败");
      } finally {
        setIsLoading(false);
      }
    };
    loadData();
  }, []);

  // 在历史页直接生成复盘（不跳转）
  const handleGenerateReview = useCallback(async (goalId: number) => {
    setGeneratingReviewFor(goalId);
    try {
      const review = await generateReview(goalId);
      setReviewsMap((prev) => new Map(prev).set(goalId, review));
    } catch (err) {
      console.error("生成复盘失败:", err);
    } finally {
      setGeneratingReviewFor(null);
    }
  }, []);

  return (
    <div className="min-h-screen bg-bg-primary">
      {/* 顶部导航 */}
      <header className="glass-strong sticky top-0 z-30">
        <div className="px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-bold text-text-primary tracking-tight">
              <span className="text-accent-blue">AI</span>Coach
            </h1>
            <span className="text-xs text-text-tertiary hidden sm:inline">Hi, {user.username}</span>
          </div>
          <div className="flex items-center gap-2 md:gap-3">
            <div className="hidden md:flex items-center gap-3 px-4 py-1.5 rounded-lg bg-bg-tertiary/50 border border-border-subtle">
              <span className="text-xs text-text-secondary">{dateStr} {weekDay}</span>
              <span className="w-px h-4 bg-border-default" />
              <span className="text-sm font-mono font-medium text-accent-blue tabular-nums">{timeStr}</span>
            </div>
            <ThemeToggle />
            <button
              type="button"
              onClick={onNavigateChat}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer border border-border-subtle"
            >
              AI 对话
            </button>
            <button
              type="button"
              onClick={() => onNavigateDashboard(null)}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer border border-border-subtle"
            >
              任务看板
            </button>
            <button
              type="button"
              className="text-xs px-3 py-1.5 rounded-lg bg-accent-blue/10 text-accent-blue border border-accent-blue/20 cursor-default"
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
            <button
              type="button"
              onClick={onLogout}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-tertiary hover:text-accent-red hover:bg-accent-red/10 transition-all cursor-pointer border border-border-subtle"
            >
              退出
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8">
        {isLoading && (
          <div className="text-center py-20">
            <div className="relative w-10 h-10 mx-auto mb-3">
              <div className="absolute inset-0 rounded-full border-2 border-accent-amber/20" />
              <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-accent-amber animate-spin" />
            </div>
            <p className="text-sm text-text-tertiary">加载历史计划...</p>
          </div>
        )}

        {error && (
          <div className="text-center py-20">
            <p className="text-text-secondary">{error}</p>
          </div>
        )}

        {!isLoading && !error && history.length === 0 && (
          <div className="text-center py-20 animate-fade-in-up">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-bg-secondary border border-border-subtle flex items-center justify-center">
              <svg className="w-8 h-8 text-text-tertiary/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-text-secondary mb-1">暂无历史计划</p>
            <p className="text-sm text-text-tertiary">完成第一个计划后，它会出现在这里</p>
          </div>
        )}

        {!isLoading && !error && history.length > 0 && (
          <div className="space-y-3">
            {history.map((plan, idx) => {
              const done = plan.tasks.filter((t) => t.status === "completed").length;
              const total = plan.tasks.length;
              const rate = total > 0 ? Math.round((done / total) * 100) : 0;
              const isExpanded = expandedId === plan.id;
              const review = reviewsMap.get(plan.id);
              const isGenerating = generatingReviewFor === plan.id;

              return (
                <div
                  key={plan.id}
                  className="rounded-xl bg-bg-secondary border border-border-subtle overflow-hidden animate-fade-in-up"
                  style={{ animationDelay: `${idx * 50}ms` }}
                >
                  {/* 计划头部 */}
                  <button
                    type="button"
                    onClick={() => setExpandedId(isExpanded ? null : plan.id)}
                    className="w-full p-4 flex items-center justify-between cursor-pointer hover:bg-bg-card-hover transition-colors"
                  >
                    <div className="flex items-center gap-3 flex-1 text-left min-w-0">
                      {/* 序号 */}
                      <span className="shrink-0 w-6 h-6 rounded-lg bg-bg-tertiary flex items-center justify-center text-[11px] font-mono font-bold text-text-tertiary">
                        {idx + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-text-primary truncate">{plan.content}</p>
                          {review && (
                            <span className="shrink-0 text-[11px] px-1.5 py-0.5 rounded-full bg-accent-purple/15 text-accent-purple font-medium">
                              已复盘
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-text-tertiary mt-1">
                          {new Date(plan.created_at).toLocaleString("zh-CN")}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 ml-4 shrink-0">
                      <div className="flex items-center gap-2">
                        <div className="w-12 h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${rate === 100 ? "bg-accent-green" : rate >= 50 ? "bg-accent-blue" : "bg-accent-amber"}`}
                            style={{ width: `${rate}%` }}
                          />
                        </div>
                        <span className={`text-xs font-mono font-bold ${rate === 100 ? "text-accent-green" : "text-text-secondary"}`}>
                          {rate}%
                        </span>
                      </div>
                      <svg
                        className={`w-4 h-4 text-text-tertiary transition-transform ${isExpanded ? "rotate-180" : ""}`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                      </svg>
                    </div>
                  </button>

                  {/* 展开内容 */}
                  {isExpanded && (
                    <div className="border-t border-border-subtle">
                      {/* 任务列表 */}
                      <div className="p-4 space-y-2">
                        <p className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-2">
                          任务列表 ({done}/{total})
                        </p>
                        {plan.tasks.map((task) => (
                          <div
                            key={task.id}
                            className={`flex items-center gap-3 px-3 py-2 rounded-lg ${
                              task.status === "completed" ? "bg-accent-green/5" : "bg-bg-tertiary/30"
                            }`}
                          >
                            <div className={`w-3 h-3 rounded-full shrink-0 ${
                              task.status === "completed" ? "bg-accent-green" : "bg-border-strong"
                            }`} />
                            <span className={`text-xs flex-1 ${
                              task.status === "completed" ? "text-text-tertiary line-through" : "text-text-secondary"
                            }`}>
                              {task.description}
                            </span>
                            {task.is_late && task.status !== "completed" && (
                              <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-accent-amber/15 text-accent-amber">超时</span>
                            )}
                          </div>
                        ))}
                      </div>

                      {/* 操作按钮区 */}
                      <div className="border-t border-border-subtle p-4 flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => onNavigateDashboard(plan.id)}
                          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-accent-blue text-white hover:bg-accent-blue/90 transition-all cursor-pointer shadow-lg shadow-accent-blue/20"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                          </svg>
                          任务看板详情
                        </button>
                      </div>

                      {/* 复盘报告区域 */}
                      <div className="border-t border-border-subtle p-4">
                        <p className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-3">
                          AI 复盘报告
                        </p>

                        {review ? (
                          <div>
                            <ReviewCard review={review} />
                            <div className="mt-3 flex items-center gap-2 justify-end">
                              <button
                                type="button"
                                onClick={() => handleGenerateReview(plan.id)}
                                disabled={isGenerating}
                                className={`px-4 py-2 rounded-lg font-medium text-xs transition-all cursor-pointer ${
                                  isGenerating
                                    ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed"
                                    : "bg-accent-purple/10 text-accent-purple hover:bg-accent-purple/20 border border-accent-purple/20"
                                }`}
                              >
                                {isGenerating ? "重新复盘中..." : "重新复盘"}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex flex-col items-center py-6">
                            <div className="w-12 h-12 rounded-xl bg-bg-tertiary/50 border border-border-subtle flex items-center justify-center mb-3">
                              <svg className="w-6 h-6 text-text-tertiary/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z" />
                              </svg>
                            </div>
                            <p className="text-xs text-text-tertiary mb-3">该计划尚未生成复盘报告</p>
                            <button
                              type="button"
                              onClick={() => handleGenerateReview(plan.id)}
                              disabled={isGenerating}
                              className={`px-5 py-2 rounded-lg font-medium text-xs transition-all cursor-pointer ${
                                isGenerating
                                  ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed"
                                  : "bg-accent-purple text-white hover:bg-accent-purple/90 shadow-lg shadow-accent-purple/20"
                              }`}
                            >
                              {isGenerating ? (
                                <span className="flex items-center gap-2">
                                  <svg className="animate-spin h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                  </svg>
                                  AI 正在分析...
                                </span>
                              ) : (
                                "生成复盘报告"
                              )}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
