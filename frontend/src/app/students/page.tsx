"use client";

import * as React from "react";
import Link from "next/link";
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
} from "@/components/ui";
import type { Student } from "@/lib/types";

type StatusFilter = "all" | "active" | "disabled";

export default function StudentsPage() {
  const [items, setItems] = React.useState<Student[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const [keyword, setKeyword] = React.useState("");
  const [grade, setGrade] = React.useState<string>("");
  const [status, setStatus] = React.useState<StatusFilter>("active");

  const load = React.useCallback(() => {
    setLoading(true);
    setError("");
    const params: Record<string, string | number> = { limit: 100 };
    if (keyword.trim()) params.keyword = keyword.trim();
    if (grade) params.grade = Number(grade);
    if (status !== "all") params.is_active = status === "active" ? "true" : "false";
    http
      .get<Student[]>(`/api/v1/students/${qs(params)}`)
      .then((d) => setItems(Array.isArray(d) ? d : []))
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  }, [keyword, grade, status]);

  // 防抖刷新（关键词）
  React.useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">学生</h1>
        <div className="flex gap-2">
          <Link href="/students/import">
            <Button variant="outline">批量导入</Button>
          </Link>
          <Link href="/students/new">
            <Button>+ 新建学生</Button>
          </Link>
        </div>
      </div>

      <Card className="p-4">
        <div className="grid gap-3 md:grid-cols-4">
          <Input
            placeholder="搜索姓名 / 学号"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <Select value={grade} onChange={(e) => setGrade(e.target.value)}>
            <option value="">全部年级</option>
            {[7, 8, 9].map((g) => (
              <option key={g} value={g}>{g} 年级</option>
            ))}
          </Select>
          <Select value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
            <option value="active">在用</option>
            <option value="disabled">已停用</option>
            <option value="all">全部状态</option>
          </Select>
          <Button variant="outline" onClick={load}>刷新</Button>
        </div>
      </Card>

      {error && <ErrorBox message={error} />}

      {loading ? (
        <Loading />
      ) : items.length === 0 ? (
        <Empty
          text="没有符合条件的学生"
          action={
            <Link href="/students/new">
              <Button>新建学生</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-3">
          {items.map((s) => (
            <Link key={s.id} href={`/students/${s.id}`}>
              <Card className="p-4 transition hover:border-primary">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-muted-foreground">#{s.id}</span>
                  <span className="font-medium">{s.name}</span>
                  <span className="text-muted-foreground">{s.student_no}</span>
                  <Badge>{s.grade} 年级</Badge>
                  {s.is_active ? (
                    <Badge tone="success">在用</Badge>
                  ) : (
                    <Badge tone="danger">已停用</Badge>
                  )}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  性别：{s.gender ?? "—"} · 联系电话：{s.phone ?? "—"} · 家长电话：{s.parent_phone ?? "—"}
                  {s.average_score != null && (
                    <span> · 平均分：{s.average_score.toFixed(1)}</span>
                  )}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}