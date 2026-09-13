"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
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
  useToast,
} from "@/components/ui";
import type {
  HomeworkResultItem,
  ImportErrorItem,
  PaperDetail,
  StudentItem,
} from "@/lib/types";

interface HomeworkDetail {
  id: number;
  title: string;
  type: string;
  status: string;
  paper_id: number;
  class_ids?: number[] | null;
  due_at?: string | null;
  results: HomeworkResultItem[];
}

export default function HomeworkDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const { show, node } = useToast();

  const [hw, setHw] = React.useState<HomeworkDetail | null>(null);
  const [paper, setPaper] = React.useState<PaperDetail | null>(null);
  const [students, setStudents] = React.useState<StudentItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  // student_id -> { score, time }
  const [inputs, setInputs] = React.useState<Record<number, { score: string; time: string }>>({});
  const [savingId, setSavingId] = React.useState<number | null>(null);
  const [recomputing, setRecomputing] = React.useState(false);

  const reload = React.useCallback(() => {
    if (!id) return;
    setLoading(true);
    http
      .get<HomeworkDetail>(`/api/v1/homework/${id}`)
      .then(async (h) => {
        setHw(h);
        const p = await http.get<PaperDetail>(`/api/v1/papers/${h.paper_id}`).catch(() => null);
        setPaper(p);

        // 拉取班级学生
        const cids = h.class_ids ?? [];
        const lists = await Promise.all(
          cids.map((c) =>
            http.get<StudentItem[]>(`/api/v1/classes/${c}/students`).catch(() => [] as StudentItem[]),
          ),
        );
        const merged: StudentItem[] = [];
        lists.flat().forEach((s) => {
          if (!merged.some((m) => m.student_id === s.student_id)) merged.push(s);
        });
        setStudents(merged);

        // 回填已有成绩
        const init: Record<number, { score: string; time: string }> = {};
        merged.forEach((s) => {
          const r = (h.results ?? []).find((x) => x.student_id === s.student_id);
          init[s.student_id] = {
            score: r?.total_score != null ? String(r.total_score) : "",
            time: r?.time_spent_minutes != null ? String(r.time_spent_minutes) : "",
          };
        });
        setInputs(init);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  React.useEffect(reload, [reload]);

  async function saveOne(studentId: number) {
    const v = inputs[studentId];
    if (!v || v.score === "") return show("请先填写得分", "error");
    setSavingId(studentId);
    try {
      await http.post(`/api/v1/homework/${id}/results`, {
        student_id: studentId,
        total_score: Number(v.score),
        max_score: paper?.total_score ?? 100,
        time_spent_minutes: v.time ? Number(v.time) : null,
      });
      show("已保存", "success");
    } catch (e) {
      show(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSavingId(null);
    }
  }

  async function saveAll() {
    const rows = students.filter((s) => inputs[s.student_id]?.score !== "");
    if (rows.length === 0) return show("没有填写任何得分", "error");
    setSavingId(-1);
    let ok = 0;
    for (const s of rows) {
      try {
        await http.post(`/api/v1/homework/${id}/results`, {
          student_id: s.student_id,
          total_score: Number(inputs[s.student_id].score),
          max_score: paper?.total_score ?? 100,
          time_spent_minutes: inputs[s.student_id].time ? Number(inputs[s.student_id].time) : null,
        });
        ok++;
      } catch {
        /* 单条失败不中断 */
      }
    }
    setSavingId(null);
    show(`已保存 ${ok}/${rows.length} 条`, ok === rows.length ? "success" : "error");
  }

  async function recomputeAll() {
    setRecomputing(true);
    let n = 0;
    for (const s of students) {
      try {
        await http.post(`/api/v1/analytics/students/${s.student_id}/recompute`, {});
        n++;
      } catch {
        /* ignore */
      }
    }
    setRecomputing(false);
    show(`已重算 ${n} 名学生的学情`, "success");
  }

  async function importResults(file: File) {
    try {
      const r = await http.upload<{
        created: number;
        updated: number;
        errors: ImportErrorItem[];
      }>(
        `/api/v1/homework/${id}/import-results`,
        file,
      );
      if (r.errors.length) {
        show(`导入：新增 ${r.created} 更新 ${r.updated}，${r.errors.length} 行有错`, "error");
        console.warn(r.errors);
      } else {
        show(`导入成功：新增 ${r.created} 更新 ${r.updated}`, "success");
      }
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "导入失败", "error");
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!hw) return null;

  const filled = students.filter((s) => inputs[s.student_id]?.score !== "").length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{hw.title}</h1>
          <p className="text-sm text-muted-foreground">
            试卷：{paper?.title ?? `#${hw.paper_id}`} · 满分 {paper?.total_score ?? 100} ·{" "}
            已录入 {filled}/{students.length}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              http.download(`/api/v1/homework/${id}/template`, `homework_${id}_template.xlsx`)
            }
          >
            下载成绩模板
          </Button>
          <Button variant="outline" size="sm" onClick={recomputeAll} disabled={recomputing}>
            {recomputing ? "重算中..." : "重算学情"}
          </Button>
          <Button size="sm" onClick={saveAll} disabled={savingId === -1}>
            {savingId === -1 ? "保存中..." : "一键保存全部"}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="flex items-center justify-between">
          <CardTitle>成绩录入</CardTitle>
          <div className="flex items-center gap-2">
            <Label className="mb-0">Excel 批量导入</Label>
            <input
              type="file"
              accept=".xlsx,.xls"
              className="text-sm"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importResults(f);
                e.target.value = "";
              }}
            />
          </div>
        </CardHeader>
        <CardContent>
          {students.length === 0 ? (
            <Empty text="该作业未关联到有学生的班级" />
          ) : (
            <div className="max-h-[560px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-background">
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="py-2">学号</th>
                    <th className="py-2">姓名</th>
                    <th className="w-32 py-2">得分</th>
                    <th className="w-32 py-2">用时(分钟)</th>
                    <th className="py-2 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((s) => (
                    <tr key={s.student_id} className="border-b border-border last:border-0">
                      <td className="py-2">{s.student_no ?? "-"}</td>
                      <td className="py-2 font-medium">
                        <Link
                          href={`/analytics/students/${s.student_id}`}
                          className="hover:underline"
                        >
                          {s.name}
                        </Link>
                      </td>
                      <td className="py-2">
                        <Input
                          type="number"
                          step="0.5"
                          value={inputs[s.student_id]?.score ?? ""}
                          onChange={(e) =>
                            setInputs((prev) => ({
                              ...prev,
                              [s.student_id]: {
                                score: e.target.value,
                                time: prev[s.student_id]?.time ?? "",
                              },
                            }))
                          }
                        />
                      </td>
                      <td className="py-2">
                        <Input
                          type="number"
                          value={inputs[s.student_id]?.time ?? ""}
                          onChange={(e) =>
                            setInputs((prev) => ({
                              ...prev,
                              [s.student_id]: {
                                score: prev[s.student_id]?.score ?? "",
                                time: e.target.value,
                              },
                            }))
                          }
                        />
                      </td>
                      <td className="py-2 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {inputs[s.student_id]?.score !== "" && (
                            <Badge tone="success">已录</Badge>
                          )}
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => saveOne(s.student_id)}
                            disabled={savingId === s.student_id}
                          >
                            {savingId === s.student_id ? "…" : "保存"}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {node}
    </div>
  );
}
