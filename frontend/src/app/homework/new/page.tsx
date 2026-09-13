"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { http } from "@/lib/api";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorBox,
  Input,
  Label,
  Loading,
  useToast,
} from "@/components/ui";
import type { ClassItem, PaperSummary } from "@/lib/types";

/** useSearchParams 必须在 Suspense 边界内，否则 Next 构建会报错 */
export default function NewHomeworkPage() {
  return (
    <React.Suspense fallback={<Loading />}>
      <NewHomeworkForm />
    </React.Suspense>
  );
}

function NewHomeworkForm() {
  const router = useRouter();
  const sp = useSearchParams();
  const { show, node } = useToast();

  const [papers, setPapers] = React.useState<PaperSummary[]>([]);
  const [classes, setClasses] = React.useState<ClassItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const [title, setTitle] = React.useState("");
  const [paperId, setPaperId] = React.useState(sp?.get("paper_id") ?? "");
  const [hwType, setHwType] = React.useState("homework");
  const [dueAt, setDueAt] = React.useState("");
  const [selectedClasses, setSelectedClasses] = React.useState<number[]>([]);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    Promise.all([
      http.get<PaperSummary[]>("/api/v1/papers/?limit=100"),
      http.get<ClassItem[]>("/api/v1/classes/"),
    ])
      .then(([p, c]) => {
        setPapers(Array.isArray(p) ? p : []);
        setClasses(Array.isArray(c) ? c : []);
        // 预填标题
        const pre = p.find((x) => String(x.id) === String(sp?.get("paper_id")));
        if (pre) setTitle(`${pre.title} · 作业`);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sp]);

  async function submit() {
    if (!title.trim()) return show("请填写作业标题", "error");
    if (!paperId) return show("请选择试卷", "error");
    if (selectedClasses.length === 0) return show("请至少选择一个班级", "error");

    setSaving(true);
    try {
      const r = await http.post<{ id: number }>("/api/v1/homework/", {
        title: title.trim(),
        type: hwType,
        paper_id: Number(paperId),
        class_ids: selectedClasses,
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
      });
      show("作业已下发", "success");
      router.push(`/homework/${r.id}`);
    } catch (e) {
      show(e instanceof Error ? e.message : "下发失败", "error");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Loading />;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-bold">下发作业</h1>
      {error && <ErrorBox message={error} />}

      <Card>
        <CardHeader>
          <CardTitle>作业信息</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>标题</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="如：第九周有理数练习" />
          </div>

          <div>
            <Label>选择试卷</Label>
            <select
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              value={paperId}
              onChange={(e) => setPaperId(e.target.value)}
            >
              <option value="">请选择</option>
              {papers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}（{p.question_count ?? 0} 题 / {p.total_score} 分）
                </option>
              ))}
            </select>
            {papers.length === 0 && (
              <p className="mt-1 text-xs text-muted-foreground">还没有试卷，请先到「组卷」生成</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>类型</Label>
              <select
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                value={hwType}
                onChange={(e) => setHwType(e.target.value)}
              >
                <option value="homework">课后作业</option>
                <option value="quiz">测验</option>
              </select>
            </div>
            <div>
              <Label>截止时间（可选）</Label>
              <Input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} />
            </div>
          </div>

          <div>
            <Label>下发班级</Label>
            <div className="space-y-1 rounded-md border border-border p-3">
              {classes.length === 0 && (
                <p className="text-sm text-muted-foreground">还没有班级，请先到「班级」页创建</p>
              )}
              {classes.map((c) => (
                <label key={c.id} className="flex cursor-pointer items-center gap-2 py-1 text-sm">
                  <input
                    type="checkbox"
                    className="h-4 w-4"
                    checked={selectedClasses.includes(c.id)}
                    onChange={(e) =>
                      setSelectedClasses((prev) =>
                        e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id),
                      )
                    }
                  />
                  {c.name}
                  <span className="text-xs text-muted-foreground">
                    （{c.grade} 年级 {c.semester}册）
                  </span>
                </label>
              ))}
            </div>
          </div>

          <Button className="w-full" size="lg" onClick={submit} disabled={saving}>
            {saving ? "下发中..." : "确认下发"}
          </Button>
        </CardContent>
      </Card>

      {node}
    </div>
  );
}
