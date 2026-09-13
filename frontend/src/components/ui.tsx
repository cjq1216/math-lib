/**
 * 轻量 UI 组件（Tailwind 手写，不依赖 shadcn/radix，安装即跑）
 */
"use client";

import * as React from "react";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

// ===== Button =====
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "outline" | "ghost" | "destructive" | "secondary";
  size?: "sm" | "md" | "lg";
};

export function Button({ variant = "default", size = "md", className, ...props }: ButtonProps) {
  const variants: Record<string, string> = {
    default: "bg-primary text-primary-foreground hover:opacity-90",
    secondary: "bg-muted text-foreground hover:opacity-80",
    outline: "border border-border bg-transparent hover:bg-accent",
    ghost: "bg-transparent hover:bg-accent",
    destructive: "bg-destructive text-destructive-foreground hover:opacity-90",
  };
  const sizes: Record<string, string> = {
    sm: "h-8 px-3 text-xs",
    md: "h-9 px-4 text-sm",
    lg: "h-11 px-6 text-base",
  };
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition disabled:opacity-50 disabled:pointer-events-none",
        variants[variant],
        sizes[size],
        className,
      )}
    />
  );
}

// ===== Card =====
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("rounded-lg border border-border bg-background", className)} />;
}
export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("p-4 border-b border-border", className)} />;
}
export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 {...props} className={cx("text-base font-semibold", className)} />;
}
export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("p-4", className)} />;
}

// ===== Input / Textarea / Select =====
export const inputCls =
  "w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} {...props} className={cx(inputCls, className)} />;
  },
);

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return <textarea ref={ref} {...props} className={cx(inputCls, "min-h-[90px] font-mono", className)} />;
  },
);

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, ...props }, ref) {
    return <select ref={ref} {...props} className={cx(inputCls, "cursor-pointer", className)} />;
  },
);

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label {...props} className={cx("block text-sm font-medium mb-1.5", className)} />;
}

// ===== Badge =====
export function Badge({
  children,
  tone = "default",
  className,
}: {
  children: React.ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "info";
  className?: string;
}) {
  const tones: Record<string, string> = {
    default: "bg-muted text-foreground",
    success: "bg-emerald-100 text-emerald-700",
    warning: "bg-amber-100 text-amber-700",
    danger: "bg-red-100 text-red-700",
    info: "bg-blue-100 text-blue-700",
  };
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

// ===== 空态 / 加载 / 错误 =====
export function Loading({ text = "加载中..." }: { text?: string }) {
  return <div className="py-12 text-center text-sm text-muted-foreground">{text}</div>;
}

export function Empty({ text = "暂无数据", action }: { text?: string; action?: React.ReactNode }) {
  return (
    <div className="py-12 text-center">
      <div className="text-sm text-muted-foreground mb-3">{text}</div>
      {action}
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
      {message}
    </div>
  );
}

// ===== Toast（极简） =====
export function Toast({ message, tone = "info" }: { message: string; tone?: "info" | "success" | "error" }) {
  const tones: Record<string, string> = {
    info: "bg-blue-600",
    success: "bg-emerald-600",
    error: "bg-red-600",
  };
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
      <div className={cx("rounded-md px-4 py-2 text-sm text-white shadow-lg", tones[tone])}>{message}</div>
    </div>
  );
}

/** useToast：轻量消息提示 */
export function useToast() {
  const [msg, setMsg] = React.useState<{ text: string; tone: "info" | "success" | "error" } | null>(null);
  const show = React.useCallback((text: string, tone: "info" | "success" | "error" = "info") => {
    setMsg({ text, tone });
    window.setTimeout(() => setMsg(null), 2800);
  }, []);
  const node = msg ? <Toast message={msg.text} tone={msg.tone} /> : null;
  return { show, node };
}

// ===== 进度条 =====
export function Progress({ value }: { value: number }) {
  return (
    <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
      <div
        className="h-full bg-blue-600 transition-all"
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}
