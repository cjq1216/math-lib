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
  Progress,
  useToast,
} from "@/components/ui";
import { MathText } from "@/components/MathText";
import {
  DIFFICULTY_LABEL,
  QUESTION_TYPE_LABEL,
  type StudentOverview,
  type WeakPoint,
} from "@/lib/types";

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

  // 一键转为针对性作业
  const [creatingHw, setCreatingHw] = React.useState(false);
  const [createdHw, setCreatedHw] = React.useState<{ homework_id: number; title: string } | null>(
    null
  );

  const reload = React.useCallback(() => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      http.get<StudentOverview>(`/api/v1/analytics/students/${id}/overview`),
      http.get<WeakPoint[]>(`/api/v1/analytics/students/${id}/weak-points?top_n=10`),
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
    setCreatedHw(null);
    try {
      const r = await http.post<{ questions: PracticeQuestion[]; total: number }>(
        `/api/v1/analytics/students/${id}/targeted-practice`,
        { count, difficulty_min: dMin, difficulty_max: dMax }
      );
      setPractice(r.questions ?? []);
      if ((r.total ?? 0) === 0)
        show("没有匹配的题目，试试放宽难度范围或先导入更多题目", "info");
    } catch (e) {
      show(e instanceof Error ? e.message : "生成失败", "error");
    } finally {
      setGenerating(false);
    }
  }

  async function handleCreateTargetedHomework() {
    if (!practice.length || !id) return;
    setCreatingHw(true);
    try {
      const defaultTitle = `${ov?.name ?? "学生"} - 薄弱点针对性练习 (${new Date().toLocaleDateString()})`;
      const res = await http.post<{ homework_id: number; paper_id: number; title: string }>(
        `/api/v1/analytics/students/${id}/create-targeted-homework`,
        {
          title: defaultTitle,
          question_ids: practice.map((q) => q.id),
          score_per_question: 5.0,
        }
      );
      setCreatedHw({ homework_id: res.homework_id, title: res.title });
      show(`已成功生成针对性巩固作业 #${res.homework_id}！`, "success");
    } catch (e) {
      show(e instanceof Error ? e.message : "生成作业失败", "error");
    } finally {
      setCreatingHw(false);
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!ov) return null;

  const activeWeak = weak.filter((w) => !w.is_resolved);
  const resolvedWeak = weak.filter((w) => w.is_resolved);

  return (
    <div className="space-y-4">
      {/* 顶部标题与操作 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{ov.name} 的学情档案</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            累计作业 {ov.total_homework ?? 0} 次 · 覆盖知识点 {ov.knowledge_points_practiced ?? 0} 个
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={recompute} disabled={recomputing}>
            {recomputing ? "重算中..." : "手动刷新学情"}
          </Button>
        </div>
      </div>

      {/* 核心指标卡片 */}
      <div className="grid gap-3 md:grid-cols-3">
        <Card className="p-4">
          <div className="text-xs text-muted-foreground">综合平均分</div>
          <div className="mt-1 text-2xl font-bold">
            {ov.average_score != null ? `${Number(ov.average_score).toFixed(1)} 分` : "-"}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-muted-foreground">待攻克薄弱知识点</div>
          <div className="mt-1 text-2xl font-bold text-amber-600 dark:text-amber-500">
            {activeWeak.length} 个
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-muted-foreground">已攻克薄弱知识点</div>
          <div className="mt-1 text-2xl font-bold text-emerald-600 dark:text-emerald-500">
            {resolvedWeak.length} 个
          </div>
        </Card>
      </div>

      {/* 主体两栏：薄弱知识点列表 vs 针对性出题 */}
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>待攻克薄弱点 (正确率 &lt; 60%)</CardTitle>
                <span className="text-xs text-muted-foreground">按正确率升序</span>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {activeWeak.length === 0 ? (
                <Empty text="目前暂无未攻克的薄弱点，保持得很好！" />
              ) : (
                activeWeak.map((w) => (
                  <div key={w.kp_id} className="space-y-1.5 rounded-lg border border-border p-3">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">
                          {w.kp_name ?? `知识点 #${w.kp_id}`}
                        </span>
                        {w.kp_code && (
                          <span className="text-xs font-mono text-muted-foreground">
                            {w.kp_code}
                          </span>
                        )}
                        <Badge tone={w.severity === "high" ? "danger" : "warning"}>
                          {w.severity === "high" ? "高风险" : "中度薄弱"}
                        </Badge>
                        {w.trend && (
                          <Badge
                            tone={
                              w.trend === "up"
                                ? "success"
                                : w.trend === "down"
                                ? "danger"
                                : "default"
                            }
                          >
                            {w.trend === "up" ? "上升 ↑" : w.trend === "down" ? "下降 ↓" : "平稳 →"}
                          </Badge>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        累计正确率:{" "}
                        <span className="font-semibold text-foreground">
                          {Math.round(w.accuracy * 100)}%
                        </span>{" "}
                        ({w.attempts} 次作答)
                        {w.recent_5_accuracy != null && (
                          <span className="ml-2">
                            最近5次:{" "}
                            <span className="font-semibold text-foreground">
                              {Math.round(w.recent_5_accuracy * 100)}%
                            </span>
                          </span>
                        )}
                      </div>
                    </div>
                    <Progress value={w.accuracy * 100} />
                    {w.recommended_practice_count != null && (
                      <div className="text-xs text-muted-foreground">
                        建议专项强化练习 {w.recommended_practice_count} 道题目
                      </div>
                    )}
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {/* 已攻克历史 */}
          {resolvedWeak.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  已攻克的薄弱点历史（正确率已恢复 &gt;= 60%）
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {resolvedWeak.map((w) => (
                  <div
                    key={w.kp_id}
                    className="flex items-center justify-between text-xs py-1.5 px-2.5 rounded bg-muted/40"
                  >
                    <div className="flex items-center gap-2">
                      <Badge tone="success">已攻克 ✓</Badge>
                      <span className="font-medium">{w.kp_name ?? `知识点 #${w.kp_id}`}</span>
                    </div>
                    <span className="text-muted-foreground">
                      当前正确率: {Math.round(w.accuracy * 100)}% ({w.attempts} 次)
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        {/* 右侧：针对性出题配置 */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>智能针对性选题</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label>目标题数</Label>
                <Input
                  type="number"
                  min={1}
                  max={30}
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                />
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
                系统将从该生的未攻克薄弱点中抽取题目，自动排除最近已做过的题，确保针对性强化。
              </p>
              <Button className="w-full" onClick={generatePractice} disabled={generating}>
                {generating ? "选题计算中..." : "生成针对性练习"}
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* 练习题目列表与一键转为作业卡片 */}
      {practice.length > 0 && (
        <Card className="border-primary/50 shadow-sm">
          <CardHeader className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle>针对性练习题目（已精选 {practice.length} 题）</CardTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                已自动剔除该生曾做过的所有题目，命中薄弱知识点率 &gt; 80%
              </p>
            </div>
            <div className="flex items-center gap-2">
              {createdHw ? (
                <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
                  <span>已生成作业！</span>
                  <Link href={`/homework/${createdHw.homework_id}`}>
                    <Button size="sm" variant="outline">
                      前往查看作业 #{createdHw.homework_id}
                    </Button>
                  </Link>
                </div>
              ) : (
                <Button
                  size="sm"
                  onClick={handleCreateTargetedHomework}
                  disabled={creatingHw}
                >
                  {creatingHw ? "生成中..." : "一键下发为新作业"}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {practice.map((q, i) => (
              <div
                key={q.id}
                className="rounded border border-border p-3 space-y-2 bg-background/50"
              >
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-foreground">第 {i + 1} 题</span>
                    <Badge>
                      {QUESTION_TYPE_LABEL[q.question_type as keyof typeof QUESTION_TYPE_LABEL] ??
                        q.question_type}
                    </Badge>
                    <Badge
                      tone={
                        q.difficulty >= 4
                          ? "danger"
                          : q.difficulty <= 2
                          ? "success"
                          : "warning"
                      }
                    >
                      难度 {q.difficulty}
                    </Badge>
                  </div>
                  <span className="text-[11px] font-mono">ID: #{q.id}</span>
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
