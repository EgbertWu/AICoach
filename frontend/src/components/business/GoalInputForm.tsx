/**
 * GoalInputForm 组件 — 居中聚焦式
 *
 * 两种模式：
 * 1. 空状态（无计划）：输入框居中占据页面中央，大 placeholder，聚焦展开
 * 2. 有计划：收缩为顶部紧凑输入条（可展开编辑）
 */

import { useState, useRef, useEffect, type FormEvent, type KeyboardEvent } from "react";

interface GoalInputFormProps {
  onSubmit: (goalContent: string) => void;
  isLoading: boolean;
  /** 是否已有计划（控制显示模式） */
  hasPlan?: boolean;
}

const MAX_CONTENT_LENGTH = 2000;

export default function GoalInputForm({ onSubmit, isLoading, hasPlan = false }: GoalInputFormProps) {
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const [isExpanded, setIsExpanded] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 有计划时默认折叠，无计划时默认展开
  useEffect(() => {
    if (!hasPlan) {
      setIsExpanded(true);
    }
  }, [hasPlan]);

  // 自动调整高度
  const adjustHeight = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxHeight = isExpanded ? 200 : 120;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  };

  useEffect(() => {
    adjustHeight();
  }, [content, isExpanded]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError("");
    const trimmed = content.trim();
    if (!trimmed) {
      setError("请输入你的目标");
      return;
    }
    if (trimmed.length > MAX_CONTENT_LENGTH) {
      setError(`目标内容不能超过 ${MAX_CONTENT_LENGTH} 个字符`);
      return;
    }
    onSubmit(trimmed);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Ctrl/Cmd + Enter 提交
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  // ===== 空状态：居中大输入框 =====
  if (!hasPlan) {
    return (
      <form onSubmit={handleSubmit} className="w-full max-w-2xl mx-auto">
        <div
          className={`
            rounded-2xl border transition-all duration-300 overflow-hidden
            ${error
              ? "border-accent-red/30 bg-bg-card shadow-lg shadow-accent-red/5"
              : "border-border-default bg-bg-secondary shadow-lg shadow-black/[0.03] hover:border-border-strong hover:shadow-xl focus-within:border-accent-blue/40 focus-within:shadow-xl focus-within:shadow-accent-blue/5"
            }
          `}
        >
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => {
              setContent(e.target.value);
              if (error) setError("");
            }}
            onKeyDown={handleKeyDown}
            placeholder="不积跬步无以至千里！您的目标是？我来帮您拆解成可执行任务..."
            disabled={isLoading}
            rows={4}
            maxLength={MAX_CONTENT_LENGTH}
            className={`
              w-full px-5 pt-5 pb-2 text-base text-text-primary leading-relaxed
              placeholder-text-tertiary/60 resize-none
              focus:outline-none bg-transparent
              disabled:cursor-not-allowed
            `}
          />
          {/* 底部工具栏 */}
          <div className="flex items-center justify-between px-4 pb-3">
            <div className="flex items-center gap-3">
              {error && (
                <span className="text-xs text-accent-red">{error}</span>
              )}
              {!error && content.length > 0 && (
                <span className="text-[10px] text-text-tertiary/50 font-mono">
                  {content.length}/{MAX_CONTENT_LENGTH}
                </span>
              )}
              {!error && content.length === 0 && (
                <span className="text-[11px] text-text-tertiary/40">
                  Ctrl + Enter 发送
                </span>
              )}
            </div>
            <button
              type="submit"
              disabled={isLoading || !content.trim()}
              className={`
                px-5 py-2 rounded-xl font-medium text-sm
                transition-all duration-200 cursor-pointer
                ${isLoading || !content.trim()
                  ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed"
                  : "bg-accent-blue text-white hover:bg-accent-blue/90 active:scale-[0.98] shadow-md shadow-accent-blue/20"
                }
              `}
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  发送中...
                </span>
              ) : (
                "发送"
              )}
            </button>
          </div>
        </div>
      </form>
    );
  }

  // ===== 有计划：顶部紧凑条，可展开 =====
  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div
        className={`
          rounded-xl border overflow-hidden transition-all duration-300
          ${isExpanded ? "border-border-default bg-bg-secondary shadow-md" : "border-border-subtle bg-bg-secondary/50"}
        `}
      >
        {isExpanded ? (
          <>
            <textarea
              ref={textareaRef}
              value={content}
              onChange={(e) => {
                setContent(e.target.value);
                if (error) setError("");
              }}
              onKeyDown={handleKeyDown}
              placeholder="输入新目标，重新生成计划..."
              disabled={isLoading}
              rows={2}
              maxLength={MAX_CONTENT_LENGTH}
              className={`
                w-full px-4 pt-3 pb-1 text-sm text-text-primary
                placeholder-text-tertiary/60 resize-none
                focus:outline-none bg-transparent
                disabled:cursor-not-allowed
              `}
            />
            <div className="flex items-center justify-between px-3 pb-2.5">
              <div className="flex items-center gap-2">
                {error && <span className="text-xs text-accent-red">{error}</span>}
                {!error && content.length > 0 && (
                  <span className="text-[10px] text-text-tertiary/50 font-mono">{content.length}/{MAX_CONTENT_LENGTH}</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => { setIsExpanded(false); setContent(""); setError(""); }}
                  className="px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary rounded-lg hover:bg-bg-tertiary transition-colors cursor-pointer"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isLoading || !content.trim()}
                  className={`
                    px-4 py-1.5 rounded-lg font-medium text-xs
                    transition-all duration-200 cursor-pointer
                    ${isLoading || !content.trim()
                      ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed"
                      : "bg-accent-blue text-white hover:bg-accent-blue/90 active:scale-[0.98]"
                    }
                  `}
                >
                  {isLoading ? "发送中..." : "发送"}
                </button>
              </div>
            </div>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setIsExpanded(true)}
            className="w-full px-4 py-2.5 text-left text-sm text-text-tertiary hover:text-text-secondary hover:bg-bg-tertiary/30 transition-colors cursor-pointer flex items-center gap-2"
          >
            <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            <span>输入新目标，重新生成计划...</span>
          </button>
        )}
      </div>
    </form>
  );
}
