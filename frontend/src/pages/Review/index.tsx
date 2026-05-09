/**
 * ReviewPage — 周报/月报复盘页面
 *
 * 功能：
 * - Tab 切换：周报 | 月报
 * - 自动计算当前周/月时间范围，可切换上一周/上一月
 * - 卡片列表展示已有复盘报告（有序号 + 时间标签）
 * - 无复盘时显示"生成复盘"按钮
 * - 生成后自动刷新列表
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import type { ReviewReport } from "../../types/api";
import { generatePeriodReview, getPeriodReviewHistory } from "../../services/api";
import ReviewCard from "../../components/business/ReviewCard";
import { ThemeToggle } from "../../components/business/ThemeProvider";
import type { User } from "../../types/api";

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

type PeriodTab = "weekly" | "monthly";

interface ReviewPageProps {
  user: User;
  onNavigateChat: () => void;
  onNavigateDashboard: () => void;
  onNavigateHistory: () => void;
  onLogout: () => void;
}

/** 日期格式化工具 */
function formatDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** 获取本周一 */
function getMonday(date: Date): Date {
  const d = new Date(date);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  d.setDate(diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

/** 获取本周日 */
function getSunday(date: Date): Date {
  const d = new Date(date);
  const day = d.getDay();
  const diff = d.getDate() + (day === 0 ? 0 : 7 - day);
  d.setDate(diff);
  d.setHours(23, 59, 59, 999);
  return d;
}

/** 获取本月第一天 */
function getMonthStart(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

/** 获取本月最后一天 */
function getMonthEnd(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0, 23, 59, 59, 999);
}

/** 生成周期标签 */
function buildPeriodLabel(tab: PeriodTab, startDate: Date, endDate: Date): string {
  if (tab === "weekly") {
    return `${startDate.getFullYear()}年${startDate.getMonth() + 1}月${startDate.getDate()}日-${endDate.getMonth() + 1}月${endDate.getDate()}日 周报`;
  } else {
    return `${startDate.getFullYear()}年${startDate.getMonth() + 1}月 月报`;
  }
}

export default function ReviewPage({
  user,
  onNavigateChat,
  onNavigateDashboard,
  onNavigateHistory,
  onLogout,
}: ReviewPageProps) {
  const [activeTab, setActiveTab] = useState<PeriodTab>("weekly");

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

  // 时间偏移（0=当前，-1=上一个）
  const [weekOffset, setWeekOffset] = useState(0);
  const [monthOffset, setMonthOffset] = useState(0);

  // 数据
  const [reviews, setReviews] = useState<ReviewReport[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  const [expandedReviewIds, setExpandedReviewIds] = useState<Set<number>>(new Set());

  // 计算当前时间范围
  const dateRange = useMemo(() => {
    const now = new Date();
    if (activeTab === "weekly") {
      const ref = new Date(now);
      ref.setDate(ref.getDate() + weekOffset * 7);
      const start = getMonday(ref);
      const end = getSunday(ref);
      return { start, end, startStr: formatDate(start), endStr: formatDate(end) };
    } else {
      const ref = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1);
      const start = getMonthStart(ref);
      const end = getMonthEnd(ref);
      return { start, end, startStr: formatDate(start), endStr: formatDate(end) };
    }
  }, [activeTab, weekOffset, monthOffset]);

  const periodLabel = useMemo(
    () => buildPeriodLabel(activeTab, dateRange.start, dateRange.end),
    [activeTab, dateRange.start, dateRange.end]
  );

  // 加载复盘历史
  const loadReviews = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getPeriodReviewHistory(activeTab);
      setReviews(data);
    } catch {
      setError("加载复盘历史失败");
    } finally {
      setIsLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    void loadReviews();
  }, [loadReviews]);

  const toggleReviewExpanded = (id: number) => {
    setExpandedReviewIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // 检查当前时间段是否已有复盘
  const currentReview = useMemo(() => {
    return reviews.find((r) => r.period_label === periodLabel);
  }, [reviews, periodLabel]);

  // 切换 Tab 时重置偏移
  const handleTabChange = (tab: PeriodTab) => {
    setActiveTab(tab);
    if (tab === "weekly") setWeekOffset(0);
    else setMonthOffset(0);
  };

  // 生成复盘
  const handleGenerate = async () => {
    setIsGenerating(true);
    setError(null);
    try {
      await generatePeriodReview(activeTab, dateRange.startStr, dateRange.endStr);
      await loadReviews();
    } catch (err) {
      setError(err instanceof Error ? err.message : "复盘生成失败");
    } finally {
      setIsGenerating(false);
    }
  };

  // 上一个/下一个
  const handlePrev = () => {
    if (activeTab === "weekly") setWeekOffset((v) => v - 1);
    else setMonthOffset((v) => v - 1);
  };
  const handleNext = () => {
    if (activeTab === "weekly") setWeekOffset((v) => v + 1);
    else setMonthOffset((v) => v + 1);
  };

  // 当前是否是最新周期
  const isCurrentPeriod = activeTab === "weekly" ? weekOffset === 0 : monthOffset === 0;

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
              onClick={onNavigateDashboard}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer border border-border-subtle"
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
              className="text-xs px-3 py-1.5 rounded-lg bg-accent-blue/10 text-accent-blue border border-accent-blue/20 cursor-default"
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
        {/* Tab 切换 */}
        <div className="flex gap-1 p-1 rounded-xl bg-bg-secondary border border-border-subtle mb-6">
          <button
            type="button"
            onClick={() => handleTabChange("weekly")}
            className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all cursor-pointer ${
              activeTab === "weekly"
                ? "bg-accent-blue text-white shadow-lg shadow-accent-blue/20"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            周报
          </button>
          <button
            type="button"
            onClick={() => handleTabChange("monthly")}
            className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all cursor-pointer ${
              activeTab === "monthly"
                ? "bg-accent-purple text-white shadow-lg shadow-accent-purple/20"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            月报
          </button>
        </div>

        {/* 时间范围选择器 */}
        <div className="flex items-center justify-between mb-6 px-4 py-3 rounded-xl bg-bg-secondary border border-border-subtle">
          <button
            type="button"
            onClick={handlePrev}
            className="p-1.5 rounded-lg text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="text-center">
            <p className="text-sm font-semibold text-text-primary">{periodLabel}</p>
            <p className="text-[11px] text-text-tertiary mt-0.5">
              {dateRange.startStr} ~ {dateRange.endStr}
            </p>
          </div>
          <button
            type="button"
            onClick={handleNext}
            disabled={isCurrentPeriod}
            className={`p-1.5 rounded-lg transition-all cursor-pointer ${
              isCurrentPeriod
                ? "text-text-tertiary/30 cursor-not-allowed"
                : "text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary"
            }`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        {/* 当前周期：生成或展示 */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-3">
            <div className={`w-2 h-2 rounded-full ${isCurrentPeriod ? "bg-accent-blue animate-pulse" : "bg-border-strong"}`} />
            <p className="text-xs font-medium text-text-tertiary uppercase tracking-wider">
              {isCurrentPeriod ? "当前周期" : "历史周期"}
            </p>
          </div>

          {currentReview ? (
            <ReviewCard review={currentReview} />
          ) : (
            <div className="rounded-xl bg-bg-secondary border border-border-subtle p-6 text-center">
              <div className="w-12 h-12 mx-auto mb-3 rounded-xl bg-bg-tertiary/50 border border-border-subtle flex items-center justify-center">
                <svg className="w-6 h-6 text-text-tertiary/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z" />
                </svg>
              </div>
              <p className="text-sm text-text-secondary mb-1">该周期尚未生成复盘报告</p>
              <p className="text-xs text-text-tertiary mb-4">AI 将分析该时间段内所有任务的执行情况</p>
              <button
                type="button"
                onClick={handleGenerate}
                disabled={isGenerating}
                className={`px-6 py-2.5 rounded-xl font-medium text-sm transition-all cursor-pointer ${
                  isGenerating
                    ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed"
                    : `shadow-lg ${
                        activeTab === "weekly"
                          ? "bg-accent-blue text-white hover:bg-accent-blue/90 shadow-accent-blue/20"
                          : "bg-accent-purple text-white hover:bg-accent-purple/90 shadow-accent-purple/20"
                      }`
                }`}
              >
                {isGenerating ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    AI 正在分析...
                  </span>
                ) : (
                  `生成${activeTab === "weekly" ? "周报" : "月报"}复盘`
                )}
              </button>
            </div>
          )}
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="mb-4 p-3 bg-accent-red/10 border border-accent-red/20 rounded-xl">
            <p className="text-sm text-accent-red">{error}</p>
          </div>
        )}

        {/* 历史复盘卡片列表 */}
        <div>
          <p className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-3">
            历史复盘记录
          </p>

          {isLoading && (
            <div className="text-center py-10">
              <div className="relative w-8 h-8 mx-auto mb-2">
                <div className="absolute inset-0 rounded-full border-2 border-accent-purple/20" />
                <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-accent-purple animate-spin" />
              </div>
              <p className="text-xs text-text-tertiary">加载中...</p>
            </div>
          )}

          {!isLoading && reviews.length === 0 && (
            <div className="text-center py-10">
              <p className="text-sm text-text-tertiary">暂无{activeTab === "weekly" ? "周报" : "月报"}复盘记录</p>
            </div>
          )}

          {!isLoading && reviews.length > 0 && (
            <div className="space-y-3">
              {reviews.map((review, idx) => {
                const expanded = expandedReviewIds.has(review.id);
                return (
                  <div
                    key={review.id}
                    className="rounded-xl bg-bg-secondary border border-border-subtle overflow-hidden animate-fade-in-up"
                    style={{ animationDelay: `${idx * 50}ms` }}
                  >
                    <button
                      type="button"
                      onClick={() => toggleReviewExpanded(review.id)}
                      className="w-full px-4 py-3 flex items-center justify-between border-b border-border-subtle hover:bg-bg-tertiary/30 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center gap-3">
                        <span className="shrink-0 w-6 h-6 rounded-lg bg-bg-tertiary flex items-center justify-center text-[11px] font-mono font-bold text-text-tertiary">
                          {idx + 1}
                        </span>
                        <div>
                          <p className="text-sm font-medium text-text-primary">{review.period_label}</p>
                          <p className="text-[11px] text-text-tertiary">
                            {new Date(review.created_at).toLocaleString("zh-CN")}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-mono font-bold ${
                          review.completion_rate >= 80 ? "text-accent-green" : review.completion_rate >= 50 ? "text-accent-blue" : "text-accent-amber"
                        }`}>
                          {Math.round(review.completion_rate)}%
                        </span>
                        <svg
                          className={`w-4 h-4 text-text-tertiary transition-transform ${expanded ? "rotate-180" : "rotate-0"}`}
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                    </button>

                    <div className={`overflow-hidden transition-all duration-300 ${
                      expanded ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0"
                    }`}>
                      {expanded && (
                        <div className="p-4">
                          <ReviewCard review={review} />
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
