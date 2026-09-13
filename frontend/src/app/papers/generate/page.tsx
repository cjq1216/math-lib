"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { http } from "@/lib/api";
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
  Select,
} from "@/components/ui";
import { MathText } from "@/components/MathText";
import { QUESTION_TYPE_LABEL, type KnowledgePoint, type PaperConstraint } from "@/lib/types";

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
  const [typeDist, setTypeDist] = React.useState<Record<string, number>>({
    choice_single: 10,
    fill: 5,
    solution: 3,
  });
  const [diffRatio, setDiffRatio] = React.useState<Record<string, number>>({
    "1": 10, "2": 25, "3": 35, "4": 20, "5": 10,
  });

  const [kps, setKps] = React.useState<KpPick[]>([]);
  const [requiredKps, setRequiredKps] = React.useState<number[]>([]);
  const [forbiddenKps, setForbiddenKps] = React.useState<number[]>([]);
  const [pickMode, setPickMode] = React.useState<"required" | "forbidden">("required");

  const [generating, setGenerating] = React.useState(false);
  const [error, setError] = React.useState("");
  const [preview, setPreview] = React.useState<{ display_order: number; section?: string; score: number; stem: string }[]>([]);
  const [paperId, setPaperId] = React.useState<number | null>(null);

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
    if (!title.trim()) return setError("请填写试卷标题");
    if (ratioSum <= 0) return setError("难度比例之和必须大于 0");

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
    };

    setGenerating(true);
    try {
      const r = await http.post<{
        paper_id: number;
        question_count: number;
        questions: { display_order: number; section?: string; score: number; stem: string }[];
      }>("/api/v1/papers/generate", { title, constraint });
      setPaperId(r.paper_id);
      setPreview(r.questions ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "组卷失败");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[420px_1fr]">
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">智能组卷</h1>

        <Card>
          <CardHeader>
            <CardTitle>基本信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>试卷标题</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="如：八年级上册期中模拟卷 A" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>总分</Label>
                <Input type="number" value={totalScore} onChange={(e) => setTotalScore(Number(e.target.value))} />
              </div>
              <div>
                <Label>时长（分钟）</Label>
                <Input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>题型配比（共 {totalCount} 题）</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(QUESTION_TYPE_LABEL).map(([v, l]) => (
              <div key={v} className="flex items-center gap-3">
                <span className="w-20 text-sm">{l}</span>
                <Input
                  type="number"
                  min={0}
                  className="w-24"
                  value={typeDist[v] ?? 0}
                  onChange={(e) => setTypeDist({ ...typeDist, [v]: Number(e.target.value) })}
                />
                <span className="text-xs text-muted-foreground">题</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>难度分布（和为 {ratioSum}%，自动归一化）</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {[1, 2, 3, 4, 5].map((d) => (
              <div key={d} className="flex items-center gap-3">
                <span className="w-14 text-sm">难度 {d}</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  className="flex-1 accent-blue-600"
                  value={diffRatio[String(d)] ?? 0}
                  onChange={(e) => setDiffRatio({ ...diffRatio, [String(d)]: Number(e.target.value) })}
                />
                <span className="w-24 text-right text-xs text-muted-foreground">
                  {diffRatio[String(d)] ?? 0}% ·{" "}
                  {Math.round((totalCount * (diffRatio[String(d)] ?? 0)) / (ratioSum || 1))} 题
                </span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>知识点约束</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Select value={pickMode} onChange={(e) => setPickMode(e.target.value as "required" | "forbidden")}>
              <option value="required">必含知识点（卷内至少覆盖一次）</option>
              <option value="forbidden">禁含知识点（卷内不得出现）</option>
            </Select>
            <div className="max-h-56 space-y-1 overflow-y-auto rounded-md border border-border p-2">
              {kps.map((k) => {
                const inReq = requiredKps.includes(k.id);
                const inForb = forbiddenKps.includes(k.id);
                return (
                  <div key={k.id} className="flex items-center gap-2 rounded px-1 py-1 hover:bg-accent/50">
                    <input
                      type="checkbox"
                      className="h-4 w-4 cursor-pointer"
                      checked={pickMode === "required" ? inReq : inForb}
                      onChange={() => toggleKp(k.id)}
                    />
                    <span className="flex-1 text-sm">{k.path}</span>
                    {inReq && <Badge tone="success">必含</Badge>}
                    {inForb && <Badge tone="danger">禁含</Badge>}
                  </div>
                );
              })}
              {kps.length === 0 && (
                <p className="p-2 text-sm text-muted-foreground">未加载知识点，请先到「知识点」页导入</p>
              )}
            </div>
            <div className="text-xs text-muted-foreground">
              必含 {requiredKps.length} 个 · 禁含 {forbiddenKps.length} 个
            </div>
          </CardContent>
        </Card>

        <Button className="w-full" size="lg" onClick={generate} disabled={generating}>
          {generating ? "组卷中..." : "开始组卷"}
        </Button>
        {error && <ErrorBox message={error} />}
      </div>

      {/* 右侧预览 */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold">生成结果</h2>
          {paperId && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => router.push(`/papers/${paperId}`)}>
                查看详情
              </Button>
              <Button size="sm" onClick={generate} disabled={generating}>
                重新生成
              </Button>
            </div>
          )}
        </div>

        {preview.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted-foreground">
            配置好约束后点击「开始组卷」，结果会显示在这里
          </Card>
        ) : (
          <Card>
            <CardContent className="space-y-4">
              {preview.map((q) => (
                <div key={q.display_order} className="border-b border-border pb-4 last:border-0 last:pb-0">
                  <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">{q.display_order}.</span>
                    {q.section && <Badge>{q.section}</Badge>}
                    <span>{q.score} 分</span>
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
