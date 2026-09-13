"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { Button, Loading } from "./ui";

const NAV = [
  { href: "/questions", label: "题库" },
  { href: "/knowledge", label: "知识点" },
  { href: "/papers", label: "组卷" },
  { href: "/classes", label: "班级" },
  { href: "/homework", label: "作业" },
  { href: "/analytics", label: "学情" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [logoutFailed, setLogoutFailed] = React.useState(false);
  const isLoginPage = pathname === "/login";

  React.useEffect(() => {
    if (loading) return;
    if (!user && !isLoginPage) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    } else if (user && isLoginPage) {
      router.replace("/");
    }
  }, [isLoginPage, loading, pathname, router, user]);

  if (loading || (!user && !isLoginPage) || (user && isLoginPage)) {
    return (
      <main className="flex min-h-screen items-center justify-center p-4">
        <Loading text="正在验证登录状态..." />
      </main>
    );
  }

  if (isLoginPage) return <>{children}</>;

  async function handleLogout() {
    setLogoutFailed(false);
    try {
      await logout();
      router.replace("/login");
    } catch {
      setLogoutFailed(true);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <Link href="/" className="font-semibold whitespace-nowrap">
            数学题库
          </Link>
          <nav className="flex flex-1 items-center gap-1 overflow-x-auto text-sm">
            {NAV.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={
                    "rounded-md px-3 py-1.5 whitespace-nowrap transition " +
                    (active
                      ? "bg-accent font-medium"
                      : "text-muted-foreground hover:bg-accent/60")
                  }
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="hidden text-right text-xs sm:block">
            <div className="font-medium">{user?.real_name}</div>
            <div className="text-muted-foreground">
              {user?.role === "admin" ? "管理员" : "教师"}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={() => void handleLogout()}>
            {logoutFailed ? "退出失败，请重试" : "退出"}
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
