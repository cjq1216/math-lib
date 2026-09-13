import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/AppShell";
import { AuthProvider } from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "数学题库系统",
  description: "初中数学题库与学情分析系统",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
