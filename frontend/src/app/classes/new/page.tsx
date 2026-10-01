"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import { useIsAdmin } from "@/components/useIsAdmin";
import { http } from "@/lib/api";
import type { ClassCreatePayload, CurrentUser } from "@/lib/types";

export default function NewClassPage() {
  return <NewClassForm />;
}

function NewClassForm() {
  const router = useRouter();
  const isAdmin = useIsAdmin();
  const { show, node } = useToast();

  const [name, setName] = React.useState("");
  const [grade, setGrade] = React.useState(7);
  const [semester, setSemester] = React.useState("上");
  const [notes, setNotes] = React.useState("");
  const [headTeacherId, setHeadTeacherId] = React.useState<string>("");
  const [teachers, setTeachers] = React.useState<{ id: number; real_name: string; username: string }[]>([]);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (!isAdmin) return;
    http
      .get<CurrentUser[]>("/api/v1/users/?limit=100")
      .then((d) => setTeachers(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, [isAdmin]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return show("请填写班级名称", "error");
    const payload: ClassCreatePayload = {
      name: name.trim(),
      grade,
      semester,
      notes: notes.trim() || null,
    };
    if (isAdmin && headTeacherId) {
      payload.head_teacher_id = Number(headTeacherId);
    }
    setSaving(true);
    try {
      const r = await http.post<{ id: number }>("/api/v1/classes/", payload);
      show("班级已创建", "success");
      router.push(`/classes/${r.id}`);
    } catch (err) {
      show(err instanceof Error ? err.message : "创建失败", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-2xl font-bold">新建班级</h1>
      <form onSubmit={submit}>
        <Card>
          <CardHeader>
            <CardTitle>班级信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <Label htmlFor="cls-name">班级名称</Label>
                <Input
                  id="cls-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="如：七(1)班"
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="cls-grade">年级</Label>
                  <Select id="cls-grade" value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
                    {[7, 8, 9].map((g) => (
                      <option key={g} value={g}>{g} 年级</option>
                    ))}
                  </Select>
                </div>
                <div>
                  <Label htmlFor="cls-sem">学期</Label>
                  <Select id="cls-sem" value={semester} onChange={(e) => setSemester(e.target.value)}>
                    <option value="上">上册</option>
                    <option value="下">下册</option>
                  </Select>
                </div>
              </div>
            </div>
            {isAdmin && (
              <div>
                <Label htmlFor="cls-head">班主任（可选）</Label>
                <Select id="cls-head" value={headTeacherId} onChange={(e) => setHeadTeacherId(e.target.value)}>
                  <option value="">稍后再指定</option>
                  {teachers.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.real_name}（@{t.username}）
                    </option>
                  ))}
                </Select>
              </div>
            )}
            <div>
              <Label htmlFor="cls-notes">备注（可选）</Label>
              <Textarea
                id="cls-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="如：2026 秋季新初一"
              />
            </div>
          </CardContent>
        </Card>
        <div className="mt-4 flex items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => router.push("/classes")}>
            取消
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "创建中..." : "创建"}
          </Button>
        </div>
      </form>
      {node}
    </div>
  );
}