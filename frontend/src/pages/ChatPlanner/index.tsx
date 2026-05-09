/**
 * ChatPlanner 页面 — ChatGPT 风格对话式计划生成
 *
 * 改动原因：
 * 把"选择长短计划"隐到对话中，让体验更自然。
 * 通过多轮对话判断短期/长期，对话完成后一键生成计划并跳转到看板页面。
 */

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  ChatSessionListItem,
  ChatMessageItem,
  ChatStepResponse,
  SessionState,
  UserPreferences,
} from "../../types/api";
import {
  createChatSession,
  getChatSessions,
  getChatSession,
  sendChatMessage,
  deleteChatSession,
  renameChatSession,
  finalizeChatSession,
  getUserPreferences,
  updateUserPreferences,
} from "../../services/api";
import { clearToken } from "../../services/api";
import { ThemeToggle } from "../../components/business/ThemeProvider";

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

interface ChatPlannerProps {
  user: { user_id: number; username: string };
  onNavigateDashboard: () => void;
  onLogout: () => void;
  onNavigateReview: () => void;
  onNavigateHistory: () => void;
  /** 从 Dashboard 携带的初始消息，自动创建会话并发送 */
  initialMessage?: string | null;
  /** 初始消息处理完成后回调，通知父组件清空 initialMessage */
  onInitialMessageConsumed?: () => void;
}

export default function ChatPlanner({
  user,
  onNavigateDashboard,
  onLogout,
  onNavigateReview,
  onNavigateHistory,
  initialMessage,
  onInitialMessageConsumed,
}: ChatPlannerProps) {
  // ===== 会话列表 =====
  const [sessions, setSessions] = useState<ChatSessionListItem[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [showSidebar, setShowSidebar] = useState(true);

  // ===== 消息与状态 =====
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [sessionState, setSessionState] = useState<SessionState | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 改动原因：会话列表右键菜单状态
  const [menuSessionId, setMenuSessionId] = useState<number | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  // 改动原因：点击会话列表外部区域时自动关闭菜单
  useEffect(() => {
    if (!menuSessionId) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-session-menu]')) {
        setMenuSessionId(null);
        setIsRenaming(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuSessionId]);
  // 改动原因：ChatGPT 风格首页，空状态时输入框居中，有消息后移到底部
  const hasStartedChat = messages.length > 0 || isLoading || activeSessionId !== null;

  // ===== 日期时钟 =====
  const [currentTime, setCurrentTime] = useState(new Date());
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ===== Quiet Hours 偏好 =====
  const [showPrefs, setShowPrefs] = useState(false);
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);
  const [showQuietHoursConfirm, setShowQuietHoursConfirm] = useState(false);

  // ===== DOM Refs =====
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // ===== StrictMode 防护：防止初始消息重复创建会话 =====
  const initialMessageConsumedRef = useRef<string | null>(null);

  // 时钟更新
  useEffect(() => {
    clockRef.current = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => {
      if (clockRef.current) clearInterval(clockRef.current);
    };
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // 加载会话列表
  useEffect(() => {
    const loadSessions = async () => {
      try {
        const list = await getChatSessions();
        setSessions(list);
      } catch (err) {
        console.error("加载会话列表失败:", err);
      }
    };
    loadSessions();
  }, []);

  const dateStr = `${currentTime.getFullYear()}.${String(currentTime.getMonth() + 1).padStart(2, "0")}.${String(currentTime.getDate()).padStart(2, "0")}`;
  const weekDay = WEEKDAYS[currentTime.getDay()];
  const timeStr = `${String(currentTime.getHours()).padStart(2, "0")}:${String(currentTime.getMinutes()).padStart(2, "0")}`;

  // ===== 删除会话 =====
  const handleDeleteSession = useCallback(async (sessionId: number) => {
    try {
      await deleteChatSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        setMessages([]);
        setSessionState(null);
      }
      setMenuSessionId(null);
    } catch (err) {
      console.error("删除会话失败:", err);
    }
  }, [activeSessionId]);

  // ===== 重命名会话 =====
  const handleRenameSession = useCallback(async (sessionId: number) => {
    if (!renameValue.trim()) return;
    try {
      const result = await renameChatSession(sessionId, renameValue.trim());
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, title: result.title } : s))
      );
      setIsRenaming(false);
      setMenuSessionId(null);
    } catch (err) {
      console.error("重命名会话失败:", err);
    }
  }, [renameValue]);

  // ===== 创建新会话 =====
  const handleNewSession = useCallback(async () => {
    try {
      const newSession = await createChatSession();
      setSessions((prev) => [newSession, ...prev]);
      setActiveSessionId(newSession.id);
      setMessages([]);
      setSessionState(null);
      setError(null);
      setInputValue("");
      return newSession;
    } catch (err) {
      console.error("创建会话失败:", err);
      return null;
    }
  }, []);

  // ===== 空状态时创建会话并发送消息 =====
  const handleNewSessionAndSend = useCallback(async () => {
    const content = inputValue.trim();
    if (!content || isLoading) return;

    setIsLoading(true);
    setError(null);

    try {
      // 1. 创建新会话
      const title = content.slice(0, 30) + (content.length > 30 ? "..." : "");
      const newSession = await createChatSession(title);
      setSessions((prev) => [newSession, ...prev]);
      setActiveSessionId(newSession.id);
      setInputValue("");

      // 2. 添加用户消息到本地
      const userMsg: ChatMessageItem = {
        id: Date.now(),
        session_id: newSession.id,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };
      setMessages([userMsg]);

      // 3. 发送给 LLM
      const result = await sendChatMessage(newSession.id, content);

      const assistantMsg: ChatMessageItem = {
        id: Date.now() + 1,
        session_id: newSession.id,
        role: "assistant",
        content: result.assistant_message,
        created_at: new Date().toISOString(),
      };
      setMessages([userMsg, assistantMsg]);
      setSessionState(result.session_state);

      setSessions((prev) =>
        prev.map((s) =>
          s.id === newSession.id
            ? { ...s, plan_mode: result.session_state.plan_mode, updated_at: new Date().toISOString() }
            : s
        )
      );

      // 检测 quiet hours 建议
      if (result.session_state.allow_quiet_hours === true && prefs && !prefs.allow_quiet_hours) {
        setShowQuietHoursConfirm(true);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "发送失败";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, isLoading, prefs]);

  // ===== 选择会话 =====
  const handleSelectSession = useCallback(async (sessionId: number) => {
    setActiveSessionId(sessionId);
    setError(null);
    setSessionState(null);
    try {
      const detail = await getChatSession(sessionId);
      setMessages(detail.messages);
      // 从会话详情推断状态
      if (detail.status === "finalized") {
        // 已生成计划：不需要显示"生成计划"按钮
        setSessionState({
          plan_mode: detail.plan_mode as SessionState["plan_mode"],
          ready_to_finalize: false,
          next_questions: [],
          goal_summary: null,
          allow_quiet_hours: null,
          conflict_warning: null,
        });
      } else if (detail.plan_mode && detail.plan_mode !== "unknown") {
        // 未定稿但已识别计划模式：保持"生成计划"按钮可见
        setSessionState({
          plan_mode: detail.plan_mode as SessionState["plan_mode"],
          ready_to_finalize: true,
          next_questions: [],
          goal_summary: null,
          allow_quiet_hours: null,
          conflict_warning: null,
        });
      }
      // plan_mode 为 unknown 的会话：sessionState 保持 null，不显示按钮
    } catch (err) {
      console.error("加载会话失败:", err);
    }
  }, []);

  // ===== 发送消息 =====
  const handleSend = useCallback(async () => {
    const content = inputValue.trim();
    if (!content || isLoading || !activeSessionId) return;

    // 添加用户消息到本地
    const userMsg: ChatMessageItem = {
      id: Date.now(),
      session_id: activeSessionId,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInputValue("");
    setIsLoading(true);
    setError(null);

    // 自动调整 textarea 高度
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    try {
      const result: ChatStepResponse = await sendChatMessage(activeSessionId, content);

      // 添加助手消息
      const assistantMsg: ChatMessageItem = {
        id: Date.now() + 1,
        session_id: activeSessionId,
        role: "assistant",
        content: result.assistant_message,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setSessionState(result.session_state);

      // 更新会话列表（标题可能变化）
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId
            ? { ...s, plan_mode: result.session_state.plan_mode, updated_at: new Date().toISOString() }
            : s
        )
      );

      // 检测 quiet hours 建议
      if (result.session_state.allow_quiet_hours === true && prefs && !prefs.allow_quiet_hours) {
        setShowQuietHoursConfirm(true);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "发送失败";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, isLoading, activeSessionId, prefs]);

  // ===== 初始消息处理：从 Dashboard 跳转时自动创建会话并发送 =====
  // 改动原因：用户在首页输入的目标不应丢失，需要自动带入聊天记录
  useEffect(() => {
    // 改动原因：类型保护，防止 initialMessage 为非字符串时调用 .trim() 崩溃
    if (typeof initialMessage !== "string" || !initialMessage.trim()) return;

    let cancelled = false;
    // 改动原因：防止 React StrictMode 双重调用导致重复创建会话
    // 使用局部变量，在 useEffect 执行期间保持状态
    let initialized = false;

    const initAndSend = async () => {
      // 防重入：StrictMode 下第二次调用直接跳过
      if (initialized) return;
      initialized = true;

      // 再次检查：如果已经消费过这个 initialMessage，跳过
      if (initialMessageConsumedRef.current === initialMessage) return;
      initialMessageConsumedRef.current = initialMessage;

      try {
        // 1. 创建新会话，用用户输入作为标题
        const title = initialMessage.trim().slice(0, 30) + (initialMessage.trim().length > 30 ? "..." : "");
        const newSession = await createChatSession(title);
        if (cancelled) return;
        setSessions((prev) => [newSession, ...prev]);
        setActiveSessionId(newSession.id);
        setMessages([]);
        setSessionState(null);
        setError(null);

        // 2. 添加用户消息到本地
        const userMsg: ChatMessageItem = {
          id: Date.now(),
          session_id: newSession.id,
          role: "user",
          content: initialMessage.trim(),
          created_at: new Date().toISOString(),
        };
        setMessages([userMsg]);
        setIsLoading(true);

        // 2.5 通知父组件 initialMessage 已处理
        onInitialMessageConsumed?.();

        // 3. 发送给 LLM
        const result: ChatStepResponse = await sendChatMessage(newSession.id, initialMessage.trim());
        if (cancelled) return;

        const assistantMsg: ChatMessageItem = {
          id: Date.now() + 1,
          session_id: newSession.id,
          role: "assistant",
          content: result.assistant_message,
          created_at: new Date().toISOString(),
        };
        setMessages([userMsg, assistantMsg]);
        setSessionState(result.session_state);

        setSessions((prev) =>
          prev.map((s) =>
            s.id === newSession.id
              ? { ...s, plan_mode: result.session_state.plan_mode, updated_at: new Date().toISOString() }
              : s
          )
        );
      } catch (err) {
        if (!cancelled) {
          console.error("初始消息发送失败:", err);
          setError(err instanceof Error ? err.message : "发送失败");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    initAndSend();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ===== 定稿生成计划 =====
  const handleFinalize = useCallback(async () => {
    if (!activeSessionId || isFinalizing) return;
    setIsFinalizing(true);
    setError(null);

    try {
      await finalizeChatSession(activeSessionId);

      // 更新会话列表状态
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId ? { ...s, status: "finalized" as const } : s
        )
      );

      // 跳转到 Dashboard
      onNavigateDashboard();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "生成计划失败";
      setError(msg);
    } finally {
      setIsFinalizing(false);
    }
  }, [activeSessionId, isFinalizing, onNavigateDashboard]);

  // ===== 键盘事件 =====
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ===== Textarea 自动高度 =====
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  // ===== Quiet Hours 确认 =====
  const handleConfirmQuietHours = async () => {
    try {
      await updateUserPreferences({ allow_quiet_hours: true });
      if (prefs) setPrefs({ ...prefs, allow_quiet_hours: true });
      setShowQuietHoursConfirm(false);
    } catch (err) {
      console.error("更新偏好失败:", err);
    }
  };

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

  const handleLogout = () => {
    clearToken();
    onLogout();
  };

  const readyToFinalize = sessionState?.ready_to_finalize === true;

  return (
    <div className="min-h-screen bg-bg-primary flex flex-col">
      {/* ===== 顶部导航栏 ===== */}
      <header className="glass-strong sticky top-0 z-30">
        <div className="px-4 md:px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {/* 移动端侧边栏切换 */}
            <button
              type="button"
              onClick={() => setShowSidebar(!showSidebar)}
              className="md:hidden text-text-secondary hover:text-text-primary transition-colors cursor-pointer"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
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
              className="text-xs px-3 py-1.5 rounded-lg bg-accent-blue/10 text-accent-blue border border-accent-blue/20 cursor-default"
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
              onClick={onNavigateReview}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer border border-border-subtle"
            >
              复盘
            </button>
            <button
              type="button"
              onClick={handleOpenPrefs}
              className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary/50 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer border border-border-subtle"
              title="偏好设置"
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

      <div className="flex-1 flex overflow-hidden">
        {/* ===== 左侧边栏 ===== */}
        {showSidebar && (
          <aside className="w-72 border-r border-border-subtle bg-bg-secondary/30 flex flex-col shrink-0">
            {/* 新建对话按钮 */}
            <div className="p-3">
              <button
                type="button"
                onClick={handleNewSession}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-accent-blue/10 text-accent-blue hover:bg-accent-blue/20 transition-all cursor-pointer border border-accent-blue/20 text-sm font-medium"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                </svg>
                新建对话
              </button>
            </div>

            {/* 会话列表 */}
            <div className="flex-1 overflow-y-auto px-2 pb-3 space-y-1">
              {sessions.length === 0 && (
                <p className="text-xs text-text-tertiary text-center py-8">暂无对话记录</p>
              )}
              {sessions.map((session) => (
                <div key={session.id} className="relative" data-session-menu>
                  <button
                    type="button"
                    onClick={() => handleSelectSession(session.id)}
                    className={`w-full text-left px-3 py-2.5 rounded-lg transition-all cursor-pointer group ${
                      activeSessionId === session.id
                        ? "bg-accent-blue/10 border border-accent-blue/20"
                        : "hover:bg-bg-tertiary/50 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <svg className={`w-4 h-4 shrink-0 ${activeSessionId === session.id ? "text-accent-blue" : "text-text-tertiary"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm truncate ${activeSessionId === session.id ? "text-text-primary font-medium" : "text-text-secondary"}`}>
                          {session.title || "新对话"}
                        </p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span className={`text-[11px] px-1.5 py-0.5 rounded ${
                            session.plan_mode === "daily"
                              ? "bg-accent-blue/10 text-accent-blue"
                              : session.plan_mode === "long_term"
                              ? "bg-accent-purple/10 text-accent-purple"
                              : "bg-bg-tertiary text-text-tertiary"
                          }`}>
                            {session.plan_mode === "daily" ? "日计划" : session.plan_mode === "long_term" ? "长期" : "待定"}
                          </span>
                          {session.status === "finalized" && (
                            <span className="text-[11px] text-accent-green">✓</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </button>
                  {/* "⋯" 操作按钮 - 仅选中时显示 */}
                  {activeSessionId === session.id && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuSessionId(menuSessionId === session.id ? null : session.id);
                      setIsRenaming(false);
                    }}
                    className="absolute top-2 right-2 w-6 h-6 rounded flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-all cursor-pointer"
                  >
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
                      <circle cx="3" cy="8" r="1.5" />
                      <circle cx="8" cy="8" r="1.5" />
                      <circle cx="13" cy="8" r="1.5" />
                    </svg>
                  </button>
                  )}
                  {/* 下拉菜单 */}
                  {menuSessionId === session.id && (
                    <div className="absolute right-0 top-8 z-50 w-28 bg-bg-primary border border-border-subtle rounded-lg shadow-lg py-1">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setRenameValue(session.title || "");
                          setIsRenaming(true);
                        }}
                        className="w-full text-left px-3 py-2 text-sm text-text-primary hover:bg-bg-tertiary transition-colors cursor-pointer"
                      >
                        重命名
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteSession(session.id);
                        }}
                        className="w-full text-left px-3 py-2 text-sm text-red-500 hover:bg-bg-tertiary transition-colors cursor-pointer"
                      >
                        删除
                      </button>
                    </div>
                  )}
                  {/* 重命名弹窗 */}
                  {menuSessionId === session.id && isRenaming && (
                    <div className="absolute left-0 top-0 right-0 z-50 bg-bg-primary border border-accent-blue/30 rounded-lg p-2 shadow-lg">
                      <input
                        type="text"
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleRenameSession(session.id);
                          if (e.key === "Escape") { setIsRenaming(false); setMenuSessionId(null); }
                        }}
                        autoFocus
                        className="w-full text-sm bg-bg-secondary border border-border-subtle rounded px-2 py-1.5 text-text-primary focus:outline-none focus:border-accent-blue"
                      />
                      <div className="flex gap-2 mt-2">
                        <button
                          type="button"
                          onClick={() => handleRenameSession(session.id)}
                          className="flex-1 text-xs py-1 rounded bg-accent-blue text-white hover:bg-accent-blue/80 transition-colors cursor-pointer"
                        >
                          确定
                        </button>
                        <button
                          type="button"
                          onClick={() => { setIsRenaming(false); setMenuSessionId(null); }}
                          className="flex-1 text-xs py-1 rounded bg-bg-tertiary text-text-secondary hover:bg-bg-tertiary/80 transition-colors cursor-pointer"
                        >
                          取消
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </aside>
        )}

        {/* ===== 主聊天区域 ===== */}
        <main className="flex-1 flex flex-col min-w-0 relative">
          {/* 移动端日期时间 */}
          <div className="md:hidden px-4 py-2 flex items-center justify-center gap-3 border-b border-border-subtle">
            <span className="text-xs text-text-secondary">{dateStr} {weekDay}</span>
            <span className="text-sm font-mono font-medium text-accent-blue tabular-nums">{timeStr}</span>
          </div>

          {/* 消息流 - 空状态时居中显示 Hero + 输入框 */}
          <div className={`flex-1 overflow-y-auto px-4 md:px-8 py-6 ${!hasStartedChat ? 'flex flex-col' : ''}`}>
            {!hasStartedChat && (
              <div className="flex-1 flex flex-col items-center justify-center animate-fade-in-up">
                {/* Hero 区域 */}
                <div className="w-16 h-16 rounded-2xl bg-accent-blue/10 flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-accent-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <h2 className="text-lg font-semibold text-text-primary mb-2">不积跬步，无以至千里。您的计划是？</h2>
                <p className="text-sm text-text-tertiary text-center max-w-md mb-8">
                  我会通过对话了解您的目标，帮您制定最合适的计划。
                  <br />可以是今天的小目标，也可以是长期的学习计划。
                </p>

                {/* 空状态时的居中输入框 */}
                <div className="w-full max-w-2xl">
                  <div className="relative flex items-end gap-3 bg-bg-secondary border border-border-subtle rounded-2xl px-4 py-3 shadow-lg shadow-black/5">
                    <textarea
                      ref={textareaRef}
                      value={inputValue}
                      onChange={handleInputChange}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          if (inputValue.trim() && !isLoading) {
                            // 空状态时先创建会话再发送
                            handleNewSessionAndSend();
                          }
                        }
                      }}
                      placeholder="计划做..."
                      disabled={isLoading}
                      rows={1}
                      className="flex-1 resize-none bg-transparent border-0 text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:ring-0"
                      style={{ maxHeight: "200px", minHeight: "24px" }}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        if (inputValue.trim() && !isLoading) {
                          handleNewSessionAndSend();
                        }
                      }}
                      disabled={!inputValue.trim() || isLoading}
                      className="shrink-0 w-10 h-10 rounded-xl bg-accent-blue text-white flex items-center justify-center hover:bg-accent-blue/80 transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* 消息列表 - 只在有消息时显示 */}
            {hasStartedChat && messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex mb-4 animate-fade-in-up ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.role === "assistant" && (
                  <div className="w-7 h-7 rounded-lg bg-accent-blue/10 flex items-center justify-center mr-3 mt-1 shrink-0">
                    <svg className="w-4 h-4 text-accent-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                    </svg>
                  </div>
                )}
                <div
                  className={`max-w-[75%] md:max-w-[65%] px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                    msg.role === "user"
                      ? "bg-accent-blue text-white rounded-br-md"
                      : "bg-bg-secondary border border-border-subtle text-text-primary rounded-bl-md"
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}

            {/* 加载指示器 - 只在有消息时显示 */}
            {hasStartedChat && isLoading && (
              <div className="flex mb-4 animate-fade-in-up">
                <div className="w-7 h-7 rounded-lg bg-accent-blue/10 flex items-center justify-center mr-3 mt-1 shrink-0">
                  <svg className="w-4 h-4 text-accent-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                  </svg>
                </div>
                <div className="bg-bg-secondary border border-border-subtle px-4 py-3 rounded-2xl rounded-bl-md">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full bg-text-tertiary animate-bounce" style={{ animationDelay: "0ms" }} />
                    <div className="w-2 h-2 rounded-full bg-text-tertiary animate-bounce" style={{ animationDelay: "150ms" }} />
                    <div className="w-2 h-2 rounded-full bg-text-tertiary animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}

            {/* 计划冲突警告 - 只在有消息时显示 */}
            {hasStartedChat && sessionState?.conflict_warning && (
              <div className="flex justify-center mb-4 animate-fade-in-up">
                <div className="max-w-lg px-4 py-3 rounded-xl bg-accent-amber/10 border border-accent-amber/20">
                  <div className="flex items-start gap-2">
                    <svg className="w-5 h-5 text-accent-amber shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                    </svg>
                    <p className="text-sm text-accent-amber">{sessionState.conflict_warning}</p>
                  </div>
                </div>
              </div>
            )}

            {/* 生成计划按钮 - 只在有消息时显示 */}
            {hasStartedChat && readyToFinalize && !isFinalizing && (
              <div className="flex justify-center mb-4 animate-fade-in-up">
                <button
                  type="button"
                  onClick={handleFinalize}
                  className="px-8 py-3 rounded-xl bg-gradient-to-r from-accent-blue to-accent-purple text-white font-semibold text-sm shadow-lg shadow-accent-blue/25 hover:shadow-accent-blue/40 transition-all cursor-pointer hover:scale-105 active:scale-95"
                >
                  ✨ 生成计划
                </button>
              </div>
            )}

            {/* 定稿中 - 只在有消息时显示 */}
            {hasStartedChat && isFinalizing && (
              <div className="flex justify-center mb-4">
                <div className="flex items-center gap-3 px-6 py-3 rounded-xl bg-accent-blue/10 border border-accent-blue/20">
                  <div className="w-4 h-4 border-2 border-accent-blue border-t-transparent rounded-full animate-spin" />
                  <span className="text-sm text-accent-blue font-medium">正在生成计划...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* 错误提示 */}
          {error && (
            <div className="mx-4 md:mx-8 mb-2 p-3 bg-accent-red/10 border border-accent-red/20 rounded-xl animate-fade-in-up">
              <p className="text-sm text-accent-red">{error}</p>
              <button type="button" onClick={() => setError(null)} className="mt-1 text-xs text-accent-red/60 hover:text-accent-red cursor-pointer">关闭</button>
            </div>
          )}

          {/* 输入区域 - 只在有消息时显示在底部 */}
          {hasStartedChat && (
          <div className="px-4 md:px-8 py-4 border-t border-border-subtle">
            <div className="max-w-3xl mx-auto flex items-end gap-3">
              <div className="flex-1 relative">
                <textarea
                  ref={textareaRef}
                  value={inputValue}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder={activeSessionId ? "输入消息... (Enter 发送, Shift+Enter 换行)" : "请先新建对话"}
                  disabled={!activeSessionId || isLoading || isFinalizing}
                  rows={1}
                  className="w-full resize-none rounded-xl bg-bg-secondary border border-border-subtle px-4 py-3 text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-blue/50 focus:ring-1 focus:ring-accent-blue/20 transition-all disabled:opacity-50"
                  style={{ maxHeight: "200px" }}
                />
              </div>
              <button
                type="button"
                onClick={handleSend}
                disabled={!inputValue.trim() || isLoading || !activeSessionId || isFinalizing}
                className="shrink-0 w-10 h-10 rounded-xl bg-accent-blue text-white flex items-center justify-center hover:bg-accent-blue/80 transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                </svg>
              </button>
            </div>
          </div>
          )}
        </main>
      </div>

      {/* ===== Quiet Hours 确认弹窗 ===== */}
      {showQuietHoursConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-bg-card border border-border-subtle rounded-2xl p-6 max-w-sm mx-4 animate-scale-in shadow-2xl">
            <h3 className="text-base font-semibold text-text-primary mb-2">更新作息偏好？</h3>
            <p className="text-sm text-text-secondary mb-4">
              检测到你希望在夜间安排任务，是否更新偏好设置允许在休息时间（23:00-06:00）安排任务？
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setShowQuietHoursConfirm(false)}
                className="flex-1 px-4 py-2 rounded-lg bg-bg-tertiary text-text-secondary hover:text-text-primary transition-all cursor-pointer border border-border-subtle text-sm"
              >
                保持现状
              </button>
              <button
                type="button"
                onClick={handleConfirmQuietHours}
                className="flex-1 px-4 py-2 rounded-lg bg-accent-blue text-white hover:bg-accent-blue/80 transition-all cursor-pointer text-sm font-medium"
              >
                允许夜间安排
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== 偏好设置弹窗 ===== */}
      {showPrefs && prefs && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-bg-card border border-border-subtle rounded-2xl p-6 max-w-md mx-4 animate-scale-in shadow-2xl w-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-text-primary">偏好设置</h3>
              <button type="button" onClick={() => setShowPrefs(false)} className="text-text-tertiary hover:text-text-primary cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-text-secondary mb-1 block">休息开始时间</label>
                <input
                  type="time"
                  value={prefs.quiet_hours_start}
                  onChange={(e) => setPrefs({ ...prefs, quiet_hours_start: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border-subtle text-sm text-text-primary focus:outline-none focus:border-accent-blue/50"
                />
              </div>
              <div>
                <label className="text-xs text-text-secondary mb-1 block">休息结束时间</label>
                <input
                  type="time"
                  value={prefs.quiet_hours_end}
                  onChange={(e) => setPrefs({ ...prefs, quiet_hours_end: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border-subtle text-sm text-text-primary focus:outline-none focus:border-accent-blue/50"
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-primary">允许夜间安排任务</span>
                <button
                  type="button"
                  onClick={() => setPrefs({ ...prefs, allow_quiet_hours: !prefs.allow_quiet_hours })}
                  className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${prefs.allow_quiet_hours ? "bg-accent-blue" : "bg-bg-tertiary"}`}
                >
                  <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${prefs.allow_quiet_hours ? "translate-x-5" : ""}`} />
                </button>
              </div>
              <p className="text-[11px] text-text-tertiary">时区：{prefs.timezone}</p>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                type="button"
                onClick={() => setShowPrefs(false)}
                className="flex-1 px-4 py-2 rounded-lg bg-bg-tertiary text-text-secondary hover:text-text-primary transition-all cursor-pointer border border-border-subtle text-sm"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => handleSavePrefs({ quiet_hours_start: prefs.quiet_hours_start, quiet_hours_end: prefs.quiet_hours_end, allow_quiet_hours: prefs.allow_quiet_hours })}
                className="flex-1 px-4 py-2 rounded-lg bg-accent-blue text-white hover:bg-accent-blue/80 transition-all cursor-pointer text-sm font-medium"
              >
                保存设置
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
