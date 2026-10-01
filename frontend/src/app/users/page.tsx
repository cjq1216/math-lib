"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { http, qs } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorBox,
  Input,
  Loading,
  Select,
  useToast,
} from "@/components/ui";
import { useAuth } from "@/components/AuthProvider";
import { useIsAdmin } from "@/components/useIsAdmin";
import type { CurrentUser, UserRole } from "@/lib/types";

type StatusFilter = "all" | "active" | "disabled";
type RoleFilter = "all" | UserRole;

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "管理员",
  teacher: "教师",
};

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

export default function UsersPage() {
  const router = useRouter();
  const isAdmin = useIsAdmin();
  const { user: currentUser } = useAuth();
  const { show, node } = useToast();

  const [items, setItems] = React.useState<CurrentUser[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const [keyword, setKeyword] = React.useState("");
  const [role, setRole] = React.useState<RoleFilter>("all");
  const [status, setStatus] = React.useState<StatusFilter>("all");
  const [disablingId, setDisablingId] = React.useState<number | null>(null);

  // 非 admin 立即跳走，避免展示 403 给普通教师造成困惑
  React.useEffect(() => {
    if (!isAdmin) router.replace("/");
  }, [isAdmin, router]);

  const load = React.useCallback(() => {
    setLoading(true);
    setError("");
    http
      .get<CurrentUser[]>(
        `/api/v1/users/${qs({ skip: 0, limit: 50 })}`,
      )
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  // 前端粗筛：服务端只支持 skip/limit，过滤在客户端做
  const filtered = React.useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return items.filter((u) => {
      if (role !== "all" && u.role !== role) return false;
      if (status === "active" && !u.is_active) return false;
      if (status === "disabled" && u.is_active) return false;
      if (!kw) return true;
      return (
        u.username.toLowerCase().includes(kw) ||
        u.real_name.toLowerCase().includes(kw) ||
        (u.email ?? "").toLowerCase().includes(kw)
      );
    });
  }, [items, keyword, role, status]);

  async function disableUser(u: CurrentUser) {
    if (u.id === currentUser?.id) {
      show("不能禁用当前管理员", "error");
      return;
    }
    if (!confirm(`确定禁用用户「${u.real_name}（${u.username}）」？该用户的全部会话将立即失效。`)) return;
    setDisablingId(u.id);
    try {
      await http.post(`/api/v1/users/${u.id}/disable`);
      show("已禁用", "success");
      load();
    } catch (e) {
      show(e instanceof Error ? e.message : "禁用失败", "error");
    } finally {
      setDisablingId(null);
    }
  }

  if (!isAdmin) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">用户管理</h1>
        <Link href="/users/new">
          <Button>+ 新建用户</Button>
        </Link>
      </div>

      <Card className="p-4">
        <div className="grid gap-3 md:grid-cols-4">
          <Input
            placeholder="搜索用户名 / 姓名 / 邮箱"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <Select value={role} onChange={(e) => setRole(e.target.value as RoleFilter)}>
            <option value="all">全部角色</option>
            <option value="admin">管理员</option>
            <option value="teacher">教师</option>
          </Select>
          <Select value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
            <option value="all">全部状态</option>
            <option value="active">在用</option>
            <option value="disabled">已禁用</option>
          </Select>
          <Button variant="outline" onClick={load}>刷新</Button>
        </div>
      </Card>

      {error && <ErrorBox message={error} />}

      {loading ? (
        <Loading />
      ) : filtered.length === 0 ? (
        <Empty
          text={items.length === 0 ? "还没有用户" : "没有符合条件的用户"}
          action={
            <Link href="/users/new">
              <Button>新建用户</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((u) => {
            const isSelf = u.id === currentUser?.id;
            return (
              <Card key={u.id} className="p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="text-muted-foreground">#{u.id}</span>
                      <span className="font-medium">{u.real_name}</span>
                      <span className="text-muted-foreground">@{u.username}</span>
                      <Badge tone={u.role === "admin" ? "info" : "default"}>
                        {ROLE_LABEL[u.role]}
                      </Badge>
                      {u.is_active ? (
                        <Badge tone="success">在用</Badge>
                      ) : (
                        <Badge tone="danger">已禁用</Badge>
                      )}
                      {isSelf && <Badge tone="warning">当前账号</Badge>}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      邮箱：{u.email ?? "—"} · 学科：{u.subject ?? "—"}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      创建：{formatDateTime(u.created_at)} · 最近登录：{formatDateTime(u.last_login_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={isSelf || !u.is_active || disablingId === u.id}
                      title={isSelf ? "不能禁用当前管理员" : !u.is_active ? "用户已禁用" : "禁用用户"}
                      onClick={() => void disableUser(u)}
                    >
                      {disablingId === u.id ? "处理中..." : "禁用"}
                    </Button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {node}
    </div>
  );
}