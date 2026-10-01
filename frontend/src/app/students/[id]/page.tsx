"use client";

import * as React from "react";
import Link from "next/link";
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
import type { ClassItem, Student, StudentUpdatePayload } from "@/lib/types";

export default function StudentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const router = useRouter();
  const { show, node } = useToast();

  const [student, setStudent] = React.useState<Student | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const [editing, setEditing] = React.useState(false);
  const [savingEdit, setSavingEdit] = React.useState(false);
  const [toggling, setToggling] = React.useState(false);

  const [form, setForm] = React.useState({
    name: "",
    gender: "男",
    grade: 7,
    enrollment_year: "",
    phone: "",
    parent_phone: "",
    notes: "",
  });

  const [allClasses, setAllClasses] = React.useState<ClassItem[]>([]);
  const [joinedClassIds, setJoinedClassIds] = React.useState<number[]>([]);

  const reload = React.useCallback(() => {
    if (!id) return;
    setLoading(true);
    http
      .get<Student>(`/api/v1/students/${id}`)
      .then((s) => {
        setStudent(s);
        setForm({
          name: s.name,
          gender: s.gender ?? "男",
          grade: s.grade,
          enrollment_year: s.enrollment_year != null ? String(s.enrollment_year) : "",
          phone: s.phone ?? "",
          parent_phone: s.parent_phone ?? "",
          notes: s.notes ?? "",
        });
        setError("");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  }, [id]);

  React.useEffect(reload, [reload]);

  // 加载所有班级与学生在班名单
  React.useEffect(() => {
    http
      .get<ClassItem[]>("/api/v1/classes/?limit=100")
      .then((d) => setAllClasses(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  React.useEffect(() => {
    if (!student || !allClasses.length) return;
    const checks: Promise<number | null>[] = allClasses.map((c) =>
      http
        .get<{ student_id: number }[]>(`/api/v1/classes/${c.id}/students`)
        .then((rows) => (Array.isArray(rows) && rows.some((r) => r.student_id === student.id) ? c.id : null))
        .catch(() => null),
    );
    Promise.all(checks).then((ids) => setJoinedClassIds(ids.filter((x): x is number => x !== null)));
  }, [student, allClasses]);

  async function saveEdit() {
    if (!form.name.trim()) return show("姓名必填", "error");
    setSavingEdit(true);
    try {
      const payload: StudentUpdatePayload = {
        name: form.name.trim(),
        gender: form.gender || null,
        grade: Number(form.grade),
        enrollment_year: form.enrollment_year ? Number(form.enrollment_year) : null,
        phone: form.phone.trim() || null,
        parent_phone: form.parent_phone.trim() || null,
        notes: form.notes.trim() || null,
      };
      await http.patch(`/api/v1/students/${id}`, payload);
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
    if (!student) return;
    const next = !student.is_active;
    if (!confirm(`确定${next ? "启用" : "停用"}学生「${student.name}」？`)) return;
    setToggling(true);
    try {
      if (next) {
        await http.post(`/api/v1/students/${id}/enable`);
      } else {
        await http.del(`/api/v1/students/${id}`);
      }
      show(`已${next ? "启用" : "停用"}`, "success");
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "操作失败", "error");
    } finally {
      setToggling(false);
    }
  }

  if (loading) return <Loading />;
  if (error && !student) return <ErrorBox message={error} />;
  if (!student) return <Empty text="学生不存在或无权访问" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{student.name}</h1>
          <p className="text-sm text-muted-foreground">
            {student.student_no} · {student.grade} 年级
            {student.is_active ? (
              <Badge tone="success" className="ml-2">在用</Badge>
            ) : (
              <Badge tone="danger" className="ml-2">已停用</Badge>
            )}
            {student.average_score != null && (
              <span className="ml-3">平均分：{student.average_score.toFixed(1)}</span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => router.push("/students")}>
            返回列表
          </Button>
          {!editing && (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              编辑资料
            </Button>
          )}
          <Button
            variant={student.is_active ? "destructive" : "default"}
            size="sm"
            disabled={toggling}
            onClick={() => void toggleActive()}
          >
            {student.is_active ? "停用" : "启用"}
          </Button>
          <Link href={`/analytics/students/${student.id}`}>
            <Button variant="outline" size="sm">查看学情</Button>
          </Link>
        </div>
      </div>

      {editing && (
        <Card>
          <CardHeader>
            <CardTitle>编辑学生资料</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <Label>姓名</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>性别</Label>
                  <Select value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
                    <option value="男">男</option>
                    <option value="女">女</option>
                  </Select>
                </div>
                <div>
                  <Label>年级</Label>
                  <Select value={form.grade} onChange={(e) => setForm({ ...form, grade: Number(e.target.value) })}>
                    {[7, 8, 9].map((g) => (
                      <option key={g} value={g}>{g} 年级</option>
                    ))}
                  </Select>
                </div>
              </div>
              <div>
                <Label>入学年份</Label>
                <Input
                  type="number"
                  min={2000}
                  max={2100}
                  value={form.enrollment_year}
                  onChange={(e) => setForm({ ...form, enrollment_year: e.target.value })}
                />
              </div>
              <div>
                <Label>联系电话</Label>
                <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </div>
              <div>
                <Label>家长电话</Label>
                <Input value={form.parent_phone} onChange={(e) => setForm({ ...form, parent_phone: e.target.value })} />
              </div>
            </div>
            <div>
              <Label>备注</Label>
              <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <Button disabled={savingEdit} onClick={saveEdit}>{savingEdit ? "保存中..." : "保存"}</Button>
              <Button variant="outline" onClick={() => setEditing(false)}>取消</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>所属班级（{joinedClassIds.length}）</CardTitle>
        </CardHeader>
        <CardContent>
          {joinedClassIds.length === 0 ? (
            <Empty text="暂未加入任何班级" />
          ) : (
            <div className="flex flex-wrap gap-2">
              {joinedClassIds.map((cid) => {
                const c = allClasses.find((x) => x.id === cid);
                if (!c) return null;
                return (
                  <Link key={cid} href={`/classes/${cid}`}>
                    <Badge tone="info" className="px-3 py-1">
                      {c.grade} 年级 · {c.name}
                    </Badge>
                  </Link>
                );
              })}
            </div>
          )}
          <p className="mt-3 text-xs text-muted-foreground">
            提示：班级调整请在班级详情页的「学生名单」中进行。
          </p>
        </CardContent>
      </Card>

      {node}
    </div>
  );
}