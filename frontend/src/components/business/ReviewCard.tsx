/**
 * ReviewCard 组件 — 暗色主题版
 *
 * 展示 AI 复盘报告：完成率进度条 + 分析 + 建议
 */

import type { ReviewReport } from "../../types/api";

interface ReviewCardProps {
  review: ReviewReport;
}

function getRateColor(rate: number): string {
  if (rate >= 80) return "bg-accent-green";
  if (rate >= 50) return "bg-accent-blue";
  return "bg-accent-amber";
}

function getRateTextColor(rate: number): string {
  if (rate >= 80) return "text-accent-green";
  if (rate >= 50) return "text-accent-blue";
  return "text-accent-amber";
}

function getRateLabel(rate: number): string {
  if (rate === 100) return "完美达成";
  if (rate >= 80) return "表现出色";
  if (rate >= 50) return "继续加油";
  if (rate > 0) return "有待提高";
  return "尚未开始";
}

export default function ReviewCard({ review }: ReviewCardProps) {
  const rate = Math.round(review.completion_rate);
  const barColor = getRateColor(rate);
  const textColor = getRateTextColor(rate);

  return (
    <div className="rounded-xl border border-border-subtle overflow-hidden animate-fade-in-up">
      {/* 头部 */}
      <div className="bg-gradient-to-r from-accent-purple/20 to-accent-blue/20 px-6 py-5 border-b border-border-subtle">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-text-primary">
            AI 复盘报告
          </h3>
          <span className="text-xs text-text-tertiary font-mono">
            {new Date(review.created_at).toLocaleString("zh-CN")}
          </span>
        </div>

        <div className="flex items-center gap-4">
          <div className={`text-3xl font-bold font-mono ${textColor} bg-bg-primary/50 rounded-xl px-4 py-2 border border-border-subtle`}>
            {rate}%
          </div>
          <div className="flex-1">
            <div className="flex justify-between text-xs text-text-tertiary mb-1.5">
              <span>任务完成率</span>
              <span className={textColor}>{getRateLabel(rate)}</span>
            </div>
            <div className="w-full bg-bg-primary/50 rounded-full h-2 border border-border-subtle">
              <div
                className={`${barColor} h-2 rounded-full transition-all duration-700 ease-out`}
                style={{ width: `${rate}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 内容 */}
      <div className="px-6 py-5 space-y-5 bg-bg-secondary">
        <div>
          <h4 className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">
            执行分析
          </h4>
          <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">
            {review.analysis}
          </p>
        </div>

        <hr className="border-border-subtle" />

        <div>
          <h4 className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">
            改进建议
          </h4>
          <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">
            {review.suggestions}
          </p>
        </div>
      </div>
    </div>
  );
}
