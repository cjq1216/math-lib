"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ApiError, http } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorBox,
  Input,
  Label,
} from "@/components/ui";
import { MathText } from "@/components/MathText";
import {
  QUESTION_TYPE_LABEL,
  type ConstraintUnsatisfiableDetail,
  type KnowledgePoint,
  type PaperConstraint,
} from "@/lib/types";

interface KpPick {
  id: number;
  name: string;
  path: string;
}

function flattenKps(nodes: KnowledgePoint[], prefix = "", out: KpPick[] = []): KpPick[] {
  for (const n of nodes) {
    const path = prefix ? `${prefix} / ${n.name}` : n.name;
    out.push({ id: n.id, name: n.name, path });
    if (n.children?.length) flattenKps(n.children, path, out);
  }
  return out;
}

export default function GeneratePaperPage() {
  const router = useRouter();

  const [title, setTitle] = React.useState("");
  const [totalScore, setTotalScore] = React.useState(100);
  const [duration, setDuration] = React.useState(90);
  const [seedInput, setSeedInput] = React.useState<string>("");

  const [typeDist, setTypeDist] = React.useState<Record<string, number>>({
    choice_single: 8,
    fill: 4,
    solution: 2,
    choice_multi: 0,
    judge: 0,
    proof: 0,
  });

  const [typeScores, setTypeScores] = React.useState<Record<string, number>>({
    choice_single: 3,
    fill: 4,
    solution: 10,
    choice_multi: 4,
    judge: 2,
    proof: 12,
  });
  const [useTypeScores, setUseTypeScores] = React.useState(false);

  const [diffRatio, setDiffRatio] = React.useState<Record<string, number>>({
    "1": 20,
    "2": 30,
    "3": 30,
    "4": 15,
    "5": 5,
  });

  const [kps, setKps] = React.useState<KpPick[]>([]);
  const [requiredKps, setRequiredKps] = React.useState<number[]>([]);
  const [forbiddenKps, setForbiddenKps] = React.useState<number[]>([]);
  const [pickMode, setPickMode] = React.useState<"required" | "forbidden">("required");

  const [generating, setGenerating] = React.useState(false);
  const [error, setError] = React.useState("");
  const [unsatisfiableDetail, setUnsatisfiableDetail] = React.useState<ConstraintUnsatisfiableDetail | null>(null);

  const [preview, setPreview] = React.useState<
    { display_order: number; section?: string; score: number; stem: string }[]
  >([]);
  const [paperId, setPaperId] = React.useState<number | null>(null);
  const [paperTotalScore, setPaperTotalScore] = React.useState<number>(100);

  React.useEffect(() => {
    http
      .get<KnowledgePoint[]>("/api/v1/knowledge/tree")
      .then((tree) => setKps(flattenKps(tree)))
      .catch(() => {});
  }, []);

  const totalCount = Object.values(typeDist).reduce((a, b) => a + (Number(b) || 0), 0);
  const ratioSum = Object.values(diffRatio).reduce((a, b) => a + (Number(b) || 0), 0);

  function toggleKp(id: number) {
    if (pickMode === "required") {
      setRequiredKps((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
    } else {
      setForbiddenKps((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
    }
  }

  async function generate() {
    setError("");
    setUnsatisfiableDetail(null);
    if (!title.trim()) return setError("请填写试卷标题");
    if (ratioSum <= 0) return setError("难度比例之和必须大于 0");
    if (totalCount <= 0) return setError("题目总数必须大于 0");

    const constraint: PaperConstraint = {
      total_score: totalScore,
      duration_minutes: duration,
      type_distribution: Object.fromEntries(
        Object.entries(typeDist).filter(([, v]) => Number(v) > 0),
      ),
      difficulty_ratio: Object.fromEntries(
        Object.entries(diffRatio)
          .filter(([, v]) => Number(v) > 0)
          .map(([k, v]) => [k, Number(v) / ratioSum]),
      ),
      required_kps: requiredKps,
      forbidden_kps: forbiddenKps,
      seed: seedInput.trim() ? Number(seedInput.trim()) : null,
      type_scores: useTypeScores ? typeScores : null,
    };

    setGenerating(true);
    try {
      const r = await http.post<{
        paper_id: number;
        question_count: number;
        total_score: number;
        questions: { display_order: number; section?: string; score: number; stem: string }[];
      }>("/api/v1/papers/generate", { title, constraint });
      setPaperId(r.paper_id);
      setPaperTotalScore(r.total_score);
      setPreview(r.questions ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        try {
          const detail = typeof e.message === "string" ? JSON.parse(e.message) : e.message;
          if (detail && detail.error === "constraint_unsatisfiable") {
            setUnsatisfiableDetail(detail);
            setError(detail.message || "当前题库可用题量无法满足设定的硬约束");
            return;
          }
        } catch {
          // not json detail
        }
      }
      setError(e instanceof Error ? e.message : "组卷失败");
    } finally {
      setGenerating(false);
    }
  }

  async function downloadExport(format: "markdown" | "word") {
    if (!paperId) return;
    const filename = `${title || "试卷"}.${format === "word" ? "docx" : "md"}`;
    await http.download(`/api/v1/papers/${paperId}/export?format=${format}`, filename);
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[450px_1fr]">
      {/* 左侧约束配置面板 */}
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">智能组卷</h1>

        <Card>
          <CardHeader>
            <CardTitle>基本信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>试卷标题</Label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="如：七年级上册期中数学模拟卷"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>总分</Label>
                <Input
                  type="number"
                  value={totalScore}
                  onChange={(e) => setTotalScore(Number(e.target.value))}
                />
              </div>
              <div>
                <Label>时长（分钟）</Label>
                <Input
                  type="number"
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                />
              </div>
            </div>
            <div>
              <Label>随机种子（可选，输入正整数可完全复现选题结果）</Label>
              <Input
                placeholder="留空为随机"
                value={seedInput}
                onChange={(e) => setSeedInput(e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        {/* 题型与分值策略 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <div>
              <CardTitle>题型配比（共 {totalCount} 题）</CardTitle>
              <p className="text-xs text-muted-foreground">设置试卷中各类题型的数量与赋分模式</p>
            </div>
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
              <input
                type="checkbox"
                className="h-3.5 w-3.5"
                checked={useTypeScores}
                onChange={(e) => setUseTypeScores(e.target.checked)}
              />
              按题型定分
            </label>
          </CardHeader>
          <CardContent className="space-y-2 pt-2">
            {Object.entries(QUESTION_TYPE_LABEL).map(([v, l]) => (
              <div key={v} className="flex items-center gap-2">
                <span className="w-24 text-sm font-medium">{l}</span>
                <div className="flex flex-1 items-center gap-2">
                  <Input
                    type="number"
                    min={0}
                    className="w-20"
                    placeholder="题数"
                    value={typeDist[v] ?? 0}
                    onChange={(e) =>
                      setTypeDist({ ...typeDist, [v]: Math.max(0, Number(e.target.value) || 0) })
                    }
                  />
                  <span className="text-xs text-muted-foreground">题</span>
                  {useTypeScores && (
                    <div className="ml-auto flex items-center gap-1">
                      <Input
                        type="number"
                        min={0.5}
                        step={0.5}
                        className="w-16"
                        placeholder="分值"
                        value={typeScores[v] ?? 3}
                        onChange={(e) =>
                          setTypeScores({
                            ...typeScores,
                            [v]: Math.max(0.5, Number(e.target.value) || 1),
                          })
                        }
                      />
                      <span className="text-xs text-muted-foreground">分/题</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* 难度分布比例 */}
        <Card>
          <CardHeader>
            <CardTitle>难度配比（占比和 {ratioSum}%）</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {[1, 2, 3, 4, 5].map((d) => (
              <div key={d} className="flex items-center gap-3">
                <span className="w-16 text-sm">难度 {d}</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  className="flex-1"
                  value={diffRatio[String(d)] ?? 0}
                  onChange={(e) =>
                    setDiffRatio({ ...diffRatio, [String(d)]: Number(e.target.value) })
                  }
                />
                <span className="w-10 text-right text-xs text-muted-foreground">
                  {diffRatio[String(d)] ?? 0}%
                </span>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* 知识点必含 / 禁含约束 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle>知识点约束</CardTitle>
            <div className="flex rounded-md border border-border bg-muted/40 p-0.5 text-xs">
              <button
                className={`rounded px-2 py-0.5 ${pickMode === "required" ? "bg-background font-medium shadow-sm" : ""}`}
                onClick={() => setPickMode("required")}
              >
                必含 ({requiredKps.length})
              </button>
              <button
                className={`rounded px-2 py-0.5 ${pickMode === "forbidden" ? "bg-background font-medium shadow-sm" : ""}`}
                onClick={() => setPickMode("forbidden")}
              >
                禁含 ({forbiddenKps.length})
              </button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-border p-2">
              {kps.map((k) => {
                const isReq = requiredKps.includes(k.id);
                const isForb = forbiddenKps.includes(k.id);
                return (
                  <div
                    key={k.id}
                    className="flex cursor-pointer items-center justify-between rounded px-2 py-1 text-xs hover:bg-accent"
                    onClick={() => toggleKp(k.id)}
                  >
                    <span>{k.path}</span>
                    {isReq && <Badge tone="info">必含</Badge>}
                    {isForb && <Badge tone="danger">禁含</Badge>}
                  </div>
                );
              })}
            </div>
            <div className="text-xs text-muted-foreground">
              已选必含 {requiredKps.length} 个 · 禁含 {forbiddenKps.length} 个
            </div>
          </CardContent>
        </Card>

        <Button className="w-full" size="lg" onClick={generate} disabled={generating}>
          {generating ? "智能组卷计算中..." : "开始智能组卷"}
        </Button>

        {/* 结构化硬约束未满足提示 */}
        {unsatisfiableDetail && (
          <div className="rounded-md border border-red-300 bg-red-50 p-4 text-xs text-red-900 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
            <div className="font-bold text-sm mb-1.5 flex items-center gap-1.5 text-red-800 dark:text-red-400">
              <span>⚠️</span> 组卷硬约束未达标
            </div>
            <p className="mb-2 leading-relaxed">{unsatisfiableDetail.message}</p>
            {unsatisfiableDetail.missing_types && Object.keys(unsatisfiableDetail.missing_types).length > 0 && (
              <div className="space-y-1 mt-2 border-t border-red-200/60 pt-2 dark:border-red-900/40">
                <div className="font-semibold text-red-800 dark:text-red-400">题库题量缺口明细：</div>
                {Object.entries(unsatisfiableDetail.missing_types).map(([qt, info]) => (
                  <div key={qt} className="flex justify-between pl-2">
                    <span>{QUESTION_TYPE_LABEL[qt as keyof typeof QUESTION_TYPE_LABEL] ?? qt}</span>
                    <span>
                      需要 {info.needed} 题，可用 {info.available} 题，<strong>缺少 {info.shortage} 题</strong>
                    </span>
                  </div>
                ))}
              </div>
            )}
            {unsatisfiableDetail.missing_required_kps && unsatisfiableDetail.missing_required_kps.length > 0 && (
              <div className="mt-2 text-red-700 dark:text-red-400">
                必含知识点 ID: {unsatisfiableDetail.missing_required_kps.join(", ")} 当前无可用题目。
              </div>
            )}
          </div>
        )}

        {error && !unsatisfiableDetail && <ErrorBox message={error} />}
      </div>

      {/* 右侧生成结果预览 */}
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xl font-bold">生成结果预览</h2>
          {paperId && (
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => downloadExport("markdown")}>
                下载 Markdown
              </Button>
              <Button variant="outline" size="sm" onClick={() => downloadExport("word")}>
                下载 Word
              </Button>
              <Button size="sm" onClick={() => router.push(`/papers/${paperId}`)}>
                进入试卷详情与微调
              </Button>
            </div>
          )}
        </div>

        {preview.length === 0 ? (
          <Card className="p-12 text-center text-sm text-muted-foreground">
            配置左侧约束条件后点击「开始智能组卷」，试卷结构与快照将在此展示，可直接导出 Word 与 Markdown 文档。
          </Card>
        ) : (
          <Card>
            <CardHeader className="border-b border-border pb-3">
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold">{title}</span>
                <span className="text-muted-foreground">
                  共 {preview.length} 题 · 实际总分 {paperTotalScore} 分 · 时长 {duration} 分钟
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-4 pt-4">
              {preview.map((q) => (
                <div key={q.display_order} className="border-b border-border pb-4 last:border-0 last:pb-0">
                  <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">{q.display_order}.</span>
                    {q.section && <Badge>{q.section}</Badge>}
                    <span className="font-mono text-primary">{q.score} 分</span>
                  </div>
                  <MathText className="text-sm leading-relaxed">{q.stem}</MathText>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
