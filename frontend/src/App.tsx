/**
 * AICoach 根组件
 *
 * 页面路由：Login / Register / Dashboard / Review / History
 * 使用简单状态管理，不引入 React Router。
 * 自动检测 localStorage 中的 JWT Token 进行认证守卫。
 * 集成 ThemeProvider 支持明亮/暗黑主题切换。
 */

import { useState, useEffect } from "react";
import type { User } from "./types/api";
import { getToken, getMe } from "./services/api";
import { ThemeProvider } from "./components/business/ThemeProvider";
import LoginPage from "./pages/Login";
import RegisterPage from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import ReviewPage from "./pages/Review";
import HistoryPage from "./pages/History";
import ChatPlanner from "./pages/ChatPlanner";

type Page = "login" | "register" | "dashboard" | "review" | "history" | "chat";

function parseStoredPage(value: string | null): Page | null {
  if (value === "login" || value === "register" || value === "dashboard" || value === "review" || value === "history" || value === "chat") {
    return value;
  }
  return null;
}

function App() {
  const [page, setPage] = useState<Page>(() => parseStoredPage(localStorage.getItem("aicoach_last_page")) ?? "login");
  const [user, setUser] = useState<User | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  /** 从 Dashboard 携带到 ChatPlanner 的初始消息 */
  const [chatInitialMessage, setChatInitialMessage] = useState<string | null>(() => localStorage.getItem("aicoach_chat_initial_message"));
  /** 从 History 页面携带到 Dashboard 的目标 ID，用于查看历史任务看板 */
  const [selectedGoalId, setSelectedGoalId] = useState<number | null>(() => {
    const raw = localStorage.getItem("aicoach_selected_goal_id");
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  });

  useEffect(() => {
    localStorage.setItem("aicoach_last_page", page);
  }, [page]);

  useEffect(() => {
    if (chatInitialMessage) localStorage.setItem("aicoach_chat_initial_message", chatInitialMessage);
    else localStorage.removeItem("aicoach_chat_initial_message");
  }, [chatInitialMessage]);

  useEffect(() => {
    if (selectedGoalId != null) localStorage.setItem("aicoach_selected_goal_id", String(selectedGoalId));
    else localStorage.removeItem("aicoach_selected_goal_id");
  }, [selectedGoalId]);

  useEffect(() => {
    const checkAuth = async () => {
      const token = getToken();
      if (!token) {
        setIsCheckingAuth(false);
        return;
      }
      try {
        const userData = await getMe();
        setUser(userData);
        const restored = parseStoredPage(localStorage.getItem("aicoach_last_page"));
        const target = restored && restored !== "login" && restored !== "register" ? restored : "chat";
        setPage(target);
      } catch {
        localStorage.removeItem("aicoach_token");
      } finally {
        setIsCheckingAuth(false);
      }
    };
    checkAuth();
  }, []);

  const handleLoginSuccess = () => {
    getMe()
      .then((userData) => {
        setUser(userData);
        const restored = parseStoredPage(localStorage.getItem("aicoach_last_page"));
        const target = restored && restored !== "login" && restored !== "register" ? restored : "chat";
        setPage(target);
      })
      .catch(() => {
        console.error("获取用户信息失败");
      });
  };

  const handleRegisterSuccess = () => {
    setPage("login");
  };

  const handleLogout = () => {
    setUser(null);
    setPage("login");
    localStorage.setItem("aicoach_last_page", "login");
    localStorage.removeItem("aicoach_selected_goal_id");
    localStorage.removeItem("aicoach_chat_initial_message");
  };

  // ===== 认证检查中 Loading =====
  if (isCheckingAuth) {
    return (
      <div className="min-h-screen bg-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="relative w-12 h-12 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-2 border-accent-blue/20" />
            <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-accent-blue animate-spin" />
          </div>
          <p className="text-sm text-text-tertiary">正在加载...</p>
        </div>
      </div>
    );
  }

  // ===== 页面路由（包裹 ThemeProvider） =====
  return (
    <ThemeProvider>
      <AppRouter
        page={page}
        user={user}
        setPage={setPage}
        setUser={setUser}
        onLoginSuccess={handleLoginSuccess}
        onRegisterSuccess={handleRegisterSuccess}
        onLogout={handleLogout}
        chatInitialMessage={chatInitialMessage}
        setChatInitialMessage={setChatInitialMessage}
        selectedGoalId={selectedGoalId}
        setSelectedGoalId={setSelectedGoalId}
      />
    </ThemeProvider>
  );
}

/** 页面路由子组件（ThemeProvider 内部） */
function AppRouter({
  page, user, setPage, onLoginSuccess, onRegisterSuccess, onLogout,
  chatInitialMessage, setChatInitialMessage, selectedGoalId, setSelectedGoalId,
}: {
  page: Page;
  user: User | null;
  setPage: (p: Page) => void;
  setUser: (u: User) => void;
  onLoginSuccess: () => void;
  onRegisterSuccess: () => void;
  onLogout: () => void;
  chatInitialMessage: string | null;
  setChatInitialMessage: (msg: string | null) => void;
  selectedGoalId: number | null;
  setSelectedGoalId: (id: number | null) => void;
}) {
  switch (page) {
    case "register":
      return (
        <RegisterPage
          onRegisterSuccess={onRegisterSuccess}
          onSwitchToLogin={() => setPage("login")}
        />
      );
    case "dashboard":
      return user ? (
        <Dashboard
          user={user}
          onLogout={onLogout}
          onNavigateReview={() => setPage("review")}
          onNavigateHistory={() => setPage("history")}
          onNavigateChat={(msg) => { setChatInitialMessage(msg || null); setPage("chat"); }}
          goalId={selectedGoalId}
          onGoalIdConsumed={() => setSelectedGoalId(null)}
        />
      ) : (
        <LoginPage
          onLoginSuccess={onLoginSuccess}
          onSwitchToRegister={() => setPage("register")}
        />
      );
    case "review":
      return user ? (
        <ReviewPage
          user={user}
          onNavigateChat={() => setPage("chat")}
          onNavigateDashboard={() => setPage("dashboard")}
          onNavigateHistory={() => setPage("history")}
          onLogout={onLogout}
        />
      ) : (
        <LoginPage
          onLoginSuccess={onLoginSuccess}
          onSwitchToRegister={() => setPage("register")}
        />
      );
    case "history":
      return user ? (
        <HistoryPage
          user={user}
          onNavigateChat={() => setPage("chat")}
          onNavigateDashboard={(goalId) => { setSelectedGoalId(goalId); setPage("dashboard"); }}
          onNavigateReview={() => setPage("review")}
          onLogout={onLogout}
        />
      ) : (
        <LoginPage
          onLoginSuccess={onLoginSuccess}
          onSwitchToRegister={() => setPage("register")}
        />
      );
    case "chat":
      return user ? (
        <ChatPlanner
          user={user}
          onNavigateDashboard={() => { setChatInitialMessage(null); setPage("dashboard"); }}
          onLogout={onLogout}
          onNavigateReview={() => setPage("review")}
          onNavigateHistory={() => setPage("history")}
          initialMessage={chatInitialMessage}
          onInitialMessageConsumed={() => setChatInitialMessage(null)}
        />
      ) : (
        <LoginPage
          onLoginSuccess={onLoginSuccess}
          onSwitchToRegister={() => setPage("register")}
        />
      );
    case "login":
    default:
      return (
        <LoginPage
          onLoginSuccess={onLoginSuccess}
          onSwitchToRegister={() => setPage("register")}
        />
      );
  }
}

export default App;
