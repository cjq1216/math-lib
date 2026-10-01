"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { http } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Empty,
  ErrorBox,
  Input,
  Label,
  Loading,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import { useIsAdmin } from "@/components/useIsAdmin";
import { ClassRosterCard } from "@/components/ClassRosterCard";
import type {
  ClassItem,
  ClassOverview,
  RankRow,
} from "@/lib/types";

export default function ClassDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const router = useRouter();
  const isAdmin = useIsAdmin();
  const { show, node } = useToast();

  const [cls, setCls] = React.useState<ClassItem | null>(null);
  const [overview, setOverview] = React.useState<ClassOverview | null>(null);
  const [ranking, setRanking] = React.useState<RankRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const [editing, setEditing] = React.useState(false);
  const [editForm, setEditForm] = React.useState({ name: "", grade: 7, semester: "上", notes: "" });
  const [savingEdit, setSavingEdit] = React.useState(false);

  const [toggling, setToggling] = React.useState(false);

  const reload = React.useCallback(() => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      http.get<ClassItem>(`/api/v1/classes/${id}`),
      http.get<ClassOverview>(`/api/v1/analytics/classes/${id}/overview`),
      http.get<RankRow[]>(`/api/v1/analytics/classes/${id}/ranking`),
    ])
      .then(([c, ov, rank]) => {
        setCls(c);
        setOverview(ov);
        setRanking(Array.isArray(rank) ? rank : []);
        setEditForm({
          name: c.name,
          grade: c.grade,
          semester: c.semester,
          notes: c.notes ?? "",
        });
        setError("");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  }, [id]);

  React.useEffect(reload, [reload]);

  async function saveEdit() {
    if (!editForm.name.trim()) return show("班级名称必填", "error");
    setSavingEdit(true);
    try {
      await http.patch(`/api/v1/classes/${id}`, {
        name: editForm.name.trim(),
        grade: Number(editForm.grade),
        semester: editForm.semester,
        notes: editForm.notes.trim() || null,
      });
      show("已更新", "success");
      setEditing(false);
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "更新失败", "error");
    } finally {
      setSavingEdit(false);
    }
  }

  async function toggleActive() {
    if (!cls) return;
    const next = !cls.is_active;
    const verb = next ? "启用" : "停用";
    if (!confirm(`确定${verb}班级「${cls.name}」？`)) return;
    setToggling(true);
    try {
      await http.post(`/api/v1/classes/${id}/${next ? "enable" : "disable"}`);
      show(`已${verb}`, "success");
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : `${verb}失败`, "error");
    } finally {
      setToggling(false);
    }
  }

  if (loading) return <Loading />;
  if (error && !cls) return <ErrorBox message={error} />;
  if (!cls) return <Empty text="班级不存在或无权访问" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{cls.name}</h1>
          <p className="text-sm text-muted-foreground">
            {cls.grade} 年级 · {cls.semester} 学期
            {cls.is_active ? (
              <Badge tone="success" className="ml-2">在用</Badge>
            ) : (
              <Badge tone="danger" className="ml-2">已停用</Badge>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => router.push("/classes")}>
            返回班级列表
          </Button>
          {isAdmin && !editing && (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              编辑资料
            </Button>
          )}
          {isAdmin && (
            <Button
              variant={cls.is_active ? "destructive" : "default"}
              size="sm"
              disabled={toggling}
              onClick={() => void toggleActive()}
            >
              {cls.is_active ? "停用" : "启用"}
            </Button>
          )}
        </div>
      </div>

      {/* 编辑资料表单 */}
      {editing && (
        <Card>
          <CardHeader>
            <CardTitle>编辑班级资料</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <Label>班级名称</Label>
                <Input
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>年级</Label>
                  <Select
                    value={editForm.grade}
                    onChange={(e) => setEditForm({ ...editForm, grade: Number(e.target.value) })}
                  >
                    {[7, 8, 9].map((g) => (
                      <option key={g} value={g}>{g} 年级</option>
                    ))}
                  </Select>
                </div>
                <div>
                  <Label>学期</Label>
                  <Select
                    value={editForm.semester}
                    onChange={(e) => setEditForm({ ...editForm, semester: e.target.value })}
                  >
                    <option value="上">上册</option>
                    <option value="下">下册</option>
                  </Select>
                </div>
              </div>
            </div>
            <div>
              <Label>备注</Label>
              <Textarea
                value={editForm.notes}
                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
              />
            </div>
            <div className="flex gap-2">
              <Button disabled={savingEdit} onClick={saveEdit}>
                {savingEdit ? "保存中..." : "保存"}
              </Button>
              <Button variant="outline" onClick={() => setEditing(false)}>
                取消
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 概览 stats */}
      {overview && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard label="学生数" value={overview.student_count} />
          <StatCard label="累计作业" value={overview.total_homework} />
          <StatCard label="平均分" value={overview.avg_score?.toFixed(1) ?? "—"} />
          <StatCard label="最高 / 最低" value={`${overview.max_score?.toFixed(0) ?? "—"} / ${overview.min_score?.toFixed(0) ?? "—"}`} />
        </div>
      )}

      {/* 名单区 */}
      <ClassRosterCard classId={cls.id} />

      {/* 排行 */}
      {ranking.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>班级排行（按累计成绩）</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {ranking.slice(0, 20).map((r) => (
                <div
                  key={`${r.student_id}-${r.rank}`}
                  className="flex items-center gap-3 rounded px-2 py-1.5 text-sm hover:bg-accent/50"
                >
                  <span className="w-6 text-muted-foreground">{r.rank}</span>
                  <span className="flex-1">{r.name}</span>
                  <span className="text-xs text-muted-foreground">{r.student_no}</span>
                  <Badge
                    tone={
                      r.percentage != null && r.percentage >= 80
                        ? "success"
                        : r.percentage != null && r.percentage >= 60
                          ? "warning"
                          : "danger"
                    }
                  >
                    {r.total_score?.toFixed(0) ?? "-"}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {node}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
    </Card>
  );
}