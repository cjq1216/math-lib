"use client";

import * as React from "react";
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
  Progress,
  useToast,
} from "@/components/ui";
import { MathText } from "@/components/MathText";
import { DIFFICULTY_LABEL, QUESTION_TYPE_LABEL, type StudentOverview, type WeakPoint } from "@/lib/types";

interface PracticeQuestion {
  id: number;
  stem: string;
  question_type: string;
  difficulty: number;
}

export default function StudentAnalyticsPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const { show, node } = useToast();

  const [ov, setOv] = React.useState<StudentOverview | null>(null);
  const [weak, setWeak] = React.useState<WeakPoint[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const [count, setCount] = React.useState(5);
  const [dMin, setDMin] = React.useState(1);
  const [dMax, setDMax] = React.useState(3);
  const [practice, setPractice] = React.useState<PracticeQuestion[]>([]);
  const [generating, setGenerating] = React.useState(false);
  const [recomputing, setRecomputing] = React.useState(false);

  const reload = React.useCallback(() => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      http.get<StudentOverview>(`/api/v1/analytics/students/${id}/overview`),
      http.get<WeakPoint[]>(`/api/v1/analytics/students/${id}/weak-points?top_n=8`),
    ])
      .then(([o, w]) => {
        setOv(o);
        setWeak(Array.isArray(w) ? w : []);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  React.useEffect(reload, [reload]);

  async function recompute() {
    setRecomputing(true);
    try {
      await http.post(`/api/v1/analytics/students/${id}/recompute`, {});
      show("学情已重算", "success");
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "重算失败", "error");
    } finally {
      setRecomputing(false);
    }
  }

  async function generatePractice() {
    setGenerating(true);
    try {
      const r = await http.post<{ questions: PracticeQuestion[]; total: number }>(
        `/api/v1/analytics/students/${id}/targeted-practice`,
        { count, difficulty_min: dMin, difficulty_max: dMax },
      );
      setPractice(r.questions ?? []);
      if ((r.total ?? 0) === 0) show("没有匹配的题目，试试放宽难度范围或先导入更多题目", "info");
    } catch (e) {
      show(e instanceof Error ? e.message : "生成失败", "error");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{ov?.name ?? `学生 #${id}`} 的学情</h1>
          <p className="text-sm text-muted-foreground">
            作业 {ov?.total_homework ?? 0} 次 · 覆盖知识点 {ov?.knowledge_points_practiced ?? 0} 个
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={recompute} disabled={recomputing}>
          {recomputing ? "重算中..." : "重算学情"}
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Card className="p-4">
          <div className="text-xs text-muted-foreground">平均得分</div>
          <div className="mt-1 text-2xl font-bold">
            {ov?.average_score != null ? Number(ov.average_score).toFixed(1) : "-"}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-muted-foreground">薄弱知识点</div>
          <div className="mt-1 text-2xl font-bold">{weak.length}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-muted-foreground">作业次数</div>
          <div className="mt-1 text-2xl font-bold">{ov?.total_homework ?? 0}</div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card>
          <CardHeader>
            <CardTitle>薄弱知识点</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {weak.length === 0 ? (
              <Empty text="暂未识别到薄弱点。需要该知识点累计练习 ≥3 次且正确率 <60% 才会标记。" />
            ) : (
              weak.map((w) => (
                <div key={w.kp_id} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">{w.kp_name ?? `知识点 #${w.kp_id}`}</span>
                    <div className="flex items-center gap-2">
                      <Badge tone={w.severity === "high" ? "danger" : "warning"}>
                        {w.severity === "high" ? "严重" : "中等"}
                      </Badge>
                      <span className="text-muted-foreground">
                        {Math.round(w.accuracy * 100)}% · {w.attempts} 次
                      </span>
                    </div>
                  </div>
                  <Progress value={w.accuracy * 100} />
                  {w.recommended_practice_count != null && (
                    <div className="text-xs text-muted-foreground">
                      建议再练 {w.recommended_practice_count} 题
                    </div>
                  )}
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>针对性出题</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label>题数</Label>
                <Input type="number" min={1} max={30} value={count} onChange={(e) => setCount(Number(e.target.value))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>难度下限</Label>
                  <select
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    value={dMin}
                    onChange={(e) => setDMin(Number(e.target.value))}
                  >
                    {[1, 2, 3, 4, 5].map((d) => (
                      <option key={d} value={d}>
                        {DIFFICULTY_LABEL[d]}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label>难度上限</Label>
                  <select
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    value={dMax}
                    onChange={(e) => setDMax(Number(e.target.value))}
                  >
                    {[1, 2, 3, 4, 5].map((d) => (
                      <option key={d} value={d}>
                        {DIFFICULTY_LABEL[d]}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                薄弱点建议先给低难度题建立信心，再逐步提升。
              </p>
              <Button className="w-full" onClick={generatePractice} disabled={generating}>
                {generating ? "生成中..." : "生成练习"}
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      {practice.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>针对性练习（{practice.length} 题）</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {practice.map((q, i) => (
              <div key={q.id} className="border-b border-border pb-4 last:border-0 last:pb-0">
                <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{i + 1}.</span>
                  <Badge>{QUESTION_TYPE_LABEL[q.question_type as keyof typeof QUESTION_TYPE_LABEL] ?? q.question_type}</Badge>
                  <Badge tone={q.difficulty >= 4 ? "danger" : q.difficulty <= 2 ? "success" : "warning"}>
                    难度 {q.difficulty}
                  </Badge>
                </div>
                <MathText className="text-sm leading-relaxed">{q.stem}</MathText>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {node}
    </div>
  );
}
