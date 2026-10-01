"use client";

import * as React from "react";
import {
  api,
  clearAccessToken,
  http,
  refreshAccessToken,
  setAccessToken,
} from "@/lib/api";
import type { AuthResponse, CurrentUser } from "@/lib/types";

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  bootstrapLoading: boolean;
  needsBootstrapSignup: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<CurrentUser>;
  register: (payload: {
    username: string;
    password: string;
    real_name: string;
    email?: string;
  }) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  reloadUser: () => Promise<CurrentUser | null>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<CurrentUser | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [bootstrapLoading, setBootstrapLoading] = React.useState(false);
  const [needsBootstrapSignup, setNeedsBootstrapSignup] = React.useState(false);

  const reloadUser = React.useCallback(async () => {
    try {
      const current = await http.get<CurrentUser>("/api/v1/auth/me");
      setUser(current);
      return current;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  React.useEffect(() => {
    let active = true;
    void (async () => {
      const token = await refreshAccessToken();
      const me = token && active ? await reloadUser() : null;
      if (active) setLoading(false);

      // 仅在尚未登录时探测是否需要首管理员注册；避免已登录用户短暂闪烁注册表单。
      if (active && !me) {
        setBootstrapLoading(true);
        try {
          const status = await api<{ has_users: boolean }>(
            "/api/v1/auth/bootstrap-status",
          );
          if (active) setNeedsBootstrapSignup(status.has_users === false);
        } catch {
          // 探测失败保守默认 false，避免在网络层故障时把用户推到注册流程。
          if (active) setNeedsBootstrapSignup(false);
        } finally {
          if (active) setBootstrapLoading(false);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [reloadUser]);

  const login = React.useCallback(async (username: string, password: string) => {
    const data = await api<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      body: new URLSearchParams({ username, password }),
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    setAccessToken(data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  const register = React.useCallback(
    async (payload: {
      username: string;
      password: string;
      real_name: string;
      email?: string;
    }) => {
      const data = await api<AuthResponse>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setAccessToken(data.access_token);
      setUser(data.user);
      // 首管理员注册成功后立即翻转标记，登录页会回到登录表单
      setNeedsBootstrapSignup(false);
      return data.user;
    },
    [],
  );

  const logout = React.useCallback(async () => {
    await http.post("/api/v1/auth/logout");
    clearAccessToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        bootstrapLoading,
        needsBootstrapSignup,
        isAdmin: user?.role === "admin",
        login,
        register,
        logout,
        reloadUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  if (!context) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return context;
}