"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Button } from "./ui";

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
  const [authed, setAuthed] = React.useState(false);

  React.useEffect(() => {
    setAuthed(Boolean(localStorage.getItem("token")));
  }, [pathname]);

  // 登录页不套导航
  if (pathname === "/login") return <>{children}</>;

  function logout() {
    localStorage.removeItem("token");
    router.push("/login");
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <Link href="/" className="font-semibold whitespace-nowrap">
            数学题库
          </Link>
          <nav className="flex flex-1 items-center gap-1 overflow-x-auto text-sm">
            {NAV.map((n) => {
              const active = pathname === n.href || pathname.startsWith(n.href + "/");
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  className={
                    "rounded-md px-3 py-1.5 whitespace-nowrap transition " +
                    (active ? "bg-accent font-medium" : "text-muted-foreground hover:bg-accent/60")
                  }
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
          {authed ? (
            <Button variant="ghost" size="sm" onClick={logout}>
              退出
            </Button>
          ) : (
            <Link href="/login">
              <Button size="sm">登录</Button>
            </Link>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
