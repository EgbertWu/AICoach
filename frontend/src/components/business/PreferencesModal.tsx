/**
 * PreferencesModal 组件 — Quiet Hours 偏好设置弹窗
 *
 * 增量升级说明：
 * 新增组件，用于设置 Quiet Hours 偏好。
 * 改动原因：偏好必须可调整；默认保护睡眠。
 */

import { useState } from "react";
import type { UserPreferences } from "../../types/api";

interface PreferencesModalProps {
  preferences: UserPreferences;
  onSave: (prefs: Partial<UserPreferences>) => void;
  onClose: () => void;
}

export default function PreferencesModal({ preferences, onSave, onClose }: PreferencesModalProps) {
  const [quietStart, setQuietStart] = useState(preferences.quiet_hours_start);
  const [quietEnd, setQuietEnd] = useState(preferences.quiet_hours_end);
  const [allowQuiet, setAllowQuiet] = useState(preferences.allow_quiet_hours);
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSave({
        quiet_hours_start: quietStart,
        quiet_hours_end: quietEnd,
        allow_quiet_hours: allowQuiet,
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-overlay backdrop-blur-sm">
      <div className="glass-strong rounded-2xl shadow-2xl p-6 mx-4 max-w-md w-full animate-scale-in">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-accent-purple" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
            <h3 className="text-base font-semibold text-text-primary">偏好设置</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-text-tertiary hover:text-text-primary transition-colors cursor-pointer p-1"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-4">
          {/* Quiet Hours 说明 */}
          <div className="p-3 rounded-xl bg-bg-tertiary/50 border border-border-subtle">
            <p className="text-xs text-text-secondary leading-relaxed">
              休息时间（Quiet Hours）内，系统不会安排任务。默认 23:00–06:00 保护你的睡眠时间。
            </p>
          </div>

          {/* 时间设置 */}
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-text-tertiary mb-1.5 uppercase tracking-wider">
                休息开始
              </label>
              <input
                type="time"
                value={quietStart}
                onChange={(e) => setQuietStart(e.target.value)}
                disabled={allowQuiet}
                className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary font-mono focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/20 outline-none transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              />
            </div>
            <div className="flex items-end pb-2 text-text-tertiary">—</div>
            <div className="flex-1">
              <label className="block text-xs font-medium text-text-tertiary mb-1.5 uppercase tracking-wider">
                休息结束
              </label>
              <input
                type="time"
                value={quietEnd}
                onChange={(e) => setQuietEnd(e.target.value)}
                disabled={allowQuiet}
                className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-border-default text-sm text-text-primary font-mono focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/20 outline-none transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              />
            </div>
          </div>

          {/* 允许夜间安排开关 */}
          <div className="flex items-center justify-between px-3 py-2.5 rounded-xl bg-bg-tertiary/30 border border-border-subtle">
            <div>
              <p className="text-sm text-text-primary">允许夜间安排</p>
              <p className="text-[11px] text-text-tertiary mt-0.5">开启后可在休息时间安排任务</p>
            </div>
            <button
              type="button"
              onClick={() => setAllowQuiet(!allowQuiet)}
              className={`relative w-10 h-5.5 rounded-full transition-colors duration-200 cursor-pointer ${
                allowQuiet ? "bg-accent-purple" : "bg-bg-tertiary"
              }`}
            >
              <span
                className={`absolute top-0.5 w-4.5 h-4.5 rounded-full bg-white shadow transition-transform duration-200 ${
                  allowQuiet ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>

          {/* 时区显示 */}
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-tertiary/20">
            <svg className="w-3.5 h-3.5 text-text-tertiary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-xs text-text-tertiary">时区：{preferences.timezone}</span>
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-2 mt-5">
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className={`flex-1 py-2 rounded-lg font-medium text-sm transition-all cursor-pointer ${
              isSaving
                ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed"
                : "bg-accent-purple text-white hover:bg-accent-purple/90"
            }`}
          >
            {isSaving ? "保存中..." : "保存设置"}
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={isSaving}
            className="px-4 py-2 bg-bg-tertiary text-text-secondary rounded-lg text-sm font-medium hover:bg-border-strong transition-colors cursor-pointer"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
