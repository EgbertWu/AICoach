/**
 * Login 页面 — 暗色主题版
 */

import { useState } from "react";
import { ApiError, login } from "../../services/api";
import { ThemeToggle } from "../../components/business/ThemeProvider";

interface LoginPageProps {
  onLoginSuccess: () => void;
  onSwitchToRegister: () => void;
}

export default function LoginPage({ onLoginSuccess, onSwitchToRegister }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError("请输入用户名和密码");
      return;
    }
    setIsLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await login(username.trim(), password.trim());
      setSuccessMsg("登录成功");
      setTimeout(() => { onLoginSuccess(); }, 600);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败，请稍后重试");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center px-4 relative">
      {/* 主题切换 - 右上角 */}
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-sm animate-fade-in-up">
        {/* Logo */}
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold text-text-primary mb-2 tracking-tight">
            <span className="text-accent-blue">AI</span>Coach
          </h1>
          <p className="text-sm text-text-tertiary">AI 执行力教练</p>
        </div>

        {/* 表单 */}
        <div className="glass-strong rounded-2xl p-8">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="username" className="block text-xs font-medium text-text-tertiary mb-1.5 uppercase tracking-wider">
                用户名
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="请输入用户名"
                className="w-full px-4 py-2.5 rounded-xl bg-bg-tertiary border border-border-default text-sm text-text-primary placeholder-text-tertiary focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all"
                disabled={isLoading}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-medium text-text-tertiary mb-1.5 uppercase tracking-wider">
                密码
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                className="w-full px-4 py-2.5 rounded-xl bg-bg-tertiary border border-border-default text-sm text-text-primary placeholder-text-tertiary focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all"
                disabled={isLoading}
              />
            </div>

            {error && (
              <div className="p-3 bg-accent-red/10 border border-accent-red/20 rounded-xl">
                <p className="text-xs text-accent-red">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className={`w-full py-2.5 rounded-xl font-medium text-sm transition-all duration-200 cursor-pointer ${
                isLoading
                  ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed"
                  : "bg-accent-blue text-white hover:bg-accent-blue/90 active:scale-[0.98] shadow-lg shadow-accent-blue/20"
              }`}
            >
              {isLoading ? "登录中..." : "登 录"}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-sm text-text-tertiary">
              还没有账号？
              <button
                type="button"
                onClick={onSwitchToRegister}
                className="text-accent-blue hover:text-accent-blue/80 font-medium ml-1 cursor-pointer"
              >
                立即注册
              </button>
            </p>
          </div>
        </div>
      </div>

      {/* 成功弹窗 */}
      {successMsg && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-overlay backdrop-blur-sm">
          <div className="glass-strong rounded-2xl shadow-2xl p-8 mx-4 max-w-sm w-full text-center animate-scale-in">
            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-accent-green/10 flex items-center justify-center">
              <svg className="w-6 h-6 text-accent-green" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-base font-semibold text-text-primary">{successMsg}</p>
          </div>
        </div>
      )}
    </div>
  );
}
