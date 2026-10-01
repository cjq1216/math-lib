"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [realName, setRealName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { user, login, register, needsBootstrapSignup } = useAuth();

  const isRegister = needsBootstrapSignup && user === null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (isRegister) {
        await register({
          username: username.trim(),
          password,
          real_name: realName.trim(),
          email: email.trim() || undefined,
        });
      } else {
        await login(username, password);
      }
      const requested = new URLSearchParams(window.location.search).get("next");
      const destination =
        requested?.startsWith("/") && !requested.startsWith("//") ? requested : "/";
      router.replace(destination);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "操作失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
        <h1 className="text-2xl font-bold text-center">
          {isRegister ? "注册首个管理员" : "登录"}
        </h1>
        <input
          type="text"
          placeholder="用户名"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full px-3 py-2 border rounded"
          required
        />
        <input
          type="password"
          placeholder="密码（至少 8 个字符）"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={8}
          className="w-full px-3 py-2 border rounded"
          required
        />
        {isRegister && (
          <>
            <input
              type="text"
              placeholder="姓名"
              value={realName}
              onChange={(e) => setRealName(e.target.value)}
              className="w-full px-3 py-2 border rounded"
              required
            />
            <input
              type="email"
              placeholder="邮箱（可选）"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border rounded"
            />
          </>
        )}
        {error && <div className="text-red-500 text-sm">{error}</div>}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-primary text-primary-foreground rounded disabled:opacity-50"
        >
          {loading
            ? isRegister
              ? "注册中..."
              : "登录中..."
            : isRegister
              ? "创建管理员账号"
              : "登录"}
        </button>
        <p className="text-xs text-muted-foreground text-center">
          {isRegister
            ? "首管理员只允许注册一次；后续用户请由管理员在「用户管理」中创建。"
            : "如忘记管理员账号，请联系系统运维重置数据库。"}
        </p>
      </form>
    </main>
  );
}