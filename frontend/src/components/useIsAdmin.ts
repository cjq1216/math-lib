"use client";

import { useAuth } from "./AuthProvider";

/** 当前用户是否为管理员。权限校验永远以后端为准，此 hook 仅作 UI 入口/页面级 UX 守卫。 */
export function useIsAdmin(): boolean {
  return useAuth().isAdmin;
}