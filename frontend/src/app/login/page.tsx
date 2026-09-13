"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { login } = useAuth();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      const requested = new URLSearchParams(window.location.search).get("next");
      const destination = requested?.startsWith("/") && !requested.startsWith("//") ? requested : "/";
      router.replace(destination);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "登录失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
        <h1 className="text-2xl font-bold text-center">登录</h1>
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
          placeholder="密码"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full px-3 py-2 border rounded"
          required
        />
        {error && <div className="text-red-500 text-sm">{error}</div>}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-primary text-primary-foreground rounded disabled:opacity-50"
        >
          {loading ? "登录中..." : "登录"}
        </button>
        <p className="text-xs text-muted-foreground text-center">
          首次启动：数据库为空，请先注册第一个管理员账号
        </p>
      </form>
    </main>
  );
}