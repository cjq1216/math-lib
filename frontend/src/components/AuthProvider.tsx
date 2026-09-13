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
  login: (username: string, password: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  reloadUser: () => Promise<CurrentUser | null>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<CurrentUser | null>(null);
  const [loading, setLoading] = React.useState(true);

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
      if (token && active) await reloadUser();
      if (active) setLoading(false);
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

  const logout = React.useCallback(async () => {
    await http.post("/api/v1/auth/logout");
    clearAccessToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, reloadUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  if (!context) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return context;
}
