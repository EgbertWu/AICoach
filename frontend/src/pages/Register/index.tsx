/**
 * Register 页面 — 暗色主题版
 */

import { useState } from "react";
import { ApiError, register } from "../../services/api";
import { ThemeToggle } from "../../components/business/ThemeProvider";

interface RegisterPageProps {
  onRegisterSuccess: () => void;
  onSwitchToLogin: () => void;
}

export default function RegisterPage({ onRegisterSuccess, onSwitchToLogin }: RegisterPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!username.trim() || !password.trim()) {
      setError("请输入用户名和密码");
      return;
    }
    if (username.trim().length < 3) {
      setError("用户名至少 3 个字符");
      return;
    }
    if (password.length < 6) {
      setError("密码至少 6 个字符");
      return;
    }
    if (password !== confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }
    setIsLoading(true);
    setSuccessMsg(null);
    try {
      await register(username.trim(), password);
      setSuccessMsg("注册成功！请使用刚注册的账号登录");
      // 2 秒后自动跳转到登录页
      setTimeout(() => { onRegisterSuccess(); }, 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "注册失败，请稍后重试");
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
          <p className="text-sm text-text-tertiary">创建你的账号</p>
        </div>

        {/* 表单 */}
        <div className="glass-strong rounded-2xl p-8">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="reg-username" className="block text-xs font-medium text-text-tertiary mb-1.5 uppercase tracking-wider">
                用户名
              </label>
              <input
                id="reg-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="至少 3 个字符"
                className="w-full px-4 py-2.5 rounded-xl bg-bg-tertiary border border-border-default text-sm text-text-primary placeholder-text-tertiary focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all"
                disabled={isLoading}
              />
            </div>

            <div>
              <label htmlFor="reg-password" className="block text-xs font-medium text-text-tertiary mb-1.5 uppercase tracking-wider">
                密码
              </label>
              <input
                id="reg-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 6 个字符"
                className="w-full px-4 py-2.5 rounded-xl bg-bg-tertiary border border-border-default text-sm text-text-primary placeholder-text-tertiary focus:border-accent-blue focus:ring-1 focus:ring-accent-blue/20 outline-none transition-all"
                disabled={isLoading}
              />
            </div>

            <div>
              <label htmlFor="reg-confirm" className="block text-xs font-medium text-text-tertiary mb-1.5 uppercase tracking-wider">
                确认密码
              </label>
              <input
                id="reg-confirm"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="再次输入密码"
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
              {isLoading ? "注册中..." : "注 册"}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-sm text-text-tertiary">
              已有账号？
              <button
                type="button"
                onClick={onSwitchToLogin}
                className="text-accent-blue hover:text-accent-blue/80 font-medium ml-1 cursor-pointer"
              >
                返回登录
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
            <p className="text-base font-semibold text-text-primary mb-2">{successMsg}</p>
            <button
              type="button"
              onClick={onRegisterSuccess}
              className="mt-4 w-full py-2.5 bg-accent-blue text-white rounded-xl font-medium text-sm hover:bg-accent-blue/90 active:scale-[0.98] transition-all cursor-pointer"
            >
              前往登录
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
