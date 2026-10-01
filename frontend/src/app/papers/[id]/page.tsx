"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { http } from "@/lib/api";
import { Badge, Button, Card, CardContent, ErrorBox, Input, Loading, useToast } from "@/components/ui";
import { MathText } from "@/components/MathText";
import type { PaperDetail, PaperQuestionItem } from "@/lib/types";

export default function PaperDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const router = useRouter();
  const { show, node } = useToast();

  const [data, setData] = React.useState<PaperDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [showAnswer, setShowAnswer] = React.useState(false);

  // 单题分值编辑状态
  const [editingScoreId, setEditingScoreId] = React.useState<number | null>(null);
  const [newScoreVal, setNewScoreVal] = React.useState<string>("");

  // 操作加载状态
  const [actionLoading, setActionLoading] = React.useState(false);
  const [exporting, setExporting] = React.useState(false);

  const loadData = React.useCallback(() => {
    if (!id) return;
    setLoading(true);
    http
      .get<PaperDetail>(`/api/v1/papers/${id}`)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  async function publish() {
    if (!id) return;
    try {
      await http.post(`/api/v1/papers/${id}/publish`);
      show("试卷已发布", "success");
      loadData();
    } catch (e) {
      show(e instanceof Error ? e.message : "发布失败", "error");
    }
  }

  async function handleExport(format: "word" | "markdown") {
    if (!id || !data) return;
    setExporting(true);
    try {
      const ext = format === "word" ? "docx" : "md";
      const filename = `${data.title || "试卷"}.${ext}`;
      await http.download(`/api/v1/papers/${id}/export?format=${format}`, filename);
      show(`试卷已导出为 ${format === "word" ? "Word (.docx)" : "Markdown (.md)"}`, "success");
    } catch (e) {
      show(e instanceof Error ? e.message : "导出失败", "error");
    } finally {
      setExporting(false);
    }
  }

  async function saveScore(pq: PaperQuestionItem) {
    if (!id) return;
    const scoreNum = parseFloat(newScoreVal);
    if (isNaN(scoreNum) || scoreNum <= 0) {
      return show("请输入有效的分值", "error");
    }
    setActionLoading(true);
    try {
      await http.put(`/api/v1/papers/${id}/questions/${pq.id}`, { score: scoreNum });
      show("题目分值已更新", "success");
      setEditingScoreId(null);
      loadData();
    } catch (e) {
      show(e instanceof Error ? e.message : "分值更新失败", "error");
    } finally {
      setActionLoading(false);
    }
  }

  async function replaceQuestion(pq: PaperQuestionItem) {
    if (!id) return;
    if (!confirm(`确定要在题库中寻找同题型、相近难度的题目替换第 ${pq.display_order} 题吗？`)) {
      return;
    }
    setActionLoading(true);
    try {
      await http.post(`/api/v1/papers/${id}/questions/${pq.id}/replace`, {});
      show("题目替换成功，已同步更新快照", "success");
      loadData();
    } catch (e) {
      show(e instanceof Error ? e.message : "替换失败", "error");
    } finally {
      setActionLoading(false);
    }
  }

  async function deleteQuestion(pq: PaperQuestionItem) {
    if (!id) return;
    if (!confirm(`确定要从试卷中删除第 ${pq.display_order} 题吗？后续题号将自动顺延。`)) {
      return;
    }
    setActionLoading(true);
    try {
      await http.del(`/api/v1/papers/${id}/questions/${pq.id}`);
      show("题目已删除，题号与总分已自动重算", "success");
      loadData();
    } catch (e) {
      show(e instanceof Error ? e.message : "删除失败", "error");
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      {/* 顶部标题与工具栏 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{data.title}</h1>
            <Badge tone={data.status === "published" ? "success" : "warning"}>
              {data.status === "published" ? "已发布" : "草稿"}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            共 {data.questions.length} 题 · 满分 {data.total_score} 分 · 时长 {data.duration_minutes} 分钟
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowAnswer((v) => !v)}>
            {showAnswer ? "隐藏答案与解析" : "显示答案与解析"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleExport("word")}
            disabled={exporting}
          >
            {exporting ? "导出中..." : "导出 Word"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleExport("markdown")}
            disabled={exporting}
          >
            {exporting ? "导出中..." : "导出 Markdown"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => router.push(`/homework/new?paper_id=${id}`)}>
            下发为作业
          </Button>
          {data.status !== "published" && (
            <Button size="sm" onClick={publish} disabled={actionLoading}>
              发布试卷
            </Button>
          )}
        </div>
      </div>

      {/* 试题列表与题目微调 */}
      <Card>
        <CardContent className="space-y-5 pt-6">
          {data.questions.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">该试卷暂无题目</p>
          )}
          {data.questions.map((q) => (
            <div key={q.id} className="border-b border-border pb-5 last:border-0 last:pb-0">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-semibold text-foreground text-sm">{q.display_order}.</span>
                  {q.section && <Badge>{q.section}</Badge>}
                  {editingScoreId === q.id ? (
                    <div className="flex items-center gap-1">
                      <Input
                        type="number"
                        step={0.5}
                        min={0.5}
                        className="h-6 w-16 px-1.5 text-xs font-mono"
                        value={newScoreVal}
                        onChange={(e) => setNewScoreVal(e.target.value)}
                      />
                      <span className="text-muted-foreground">分</span>
                      <Button
                        size="sm"
                        className="h-6 px-2 text-xs"
                        onClick={() => saveScore(q)}
                        disabled={actionLoading}
                      >
                        保存
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-1.5 text-xs"
                        onClick={() => setEditingScoreId(null)}
                      >
                        取消
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-primary font-medium">{q.score} 分</span>
                      <button
                        type="button"
                        className="text-[11px] text-muted-foreground hover:text-foreground hover:underline"
                        onClick={() => {
                          setEditingScoreId(q.id);
                          setNewScoreVal(String(q.score));
                        }}
                      >
                        [改分]
                      </button>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => replaceQuestion(q)}
                    disabled={actionLoading}
                  >
                    替换题目
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs text-red-600 hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-950/30"
                    onClick={() => deleteQuestion(q)}
                    disabled={actionLoading}
                  >
                    删除
                  </Button>
                </div>
              </div>

              {/* 题干快照展示 */}
              <MathText className="text-sm leading-relaxed">{q.stem}</MathText>

              {/* 选项快照展示 */}
              {q.options && Array.isArray(q.options) && q.options.length > 0 && (
                <div className="mt-2.5 grid gap-1.5 sm:grid-cols-2 text-sm text-foreground/90">
                  {q.options.map((opt, optIdx) => (
                    <div key={optIdx} className="rounded bg-muted/30 px-2 py-1">
                      <MathText className="inline">{opt}</MathText>
                    </div>
                  ))}
                </div>
              )}

              {/* 答案与解析折叠区 */}
              {showAnswer && (
                <div className="mt-3 space-y-2 rounded-md bg-muted/40 p-3 text-xs">
                  {q.answer && (
                    <div className="flex items-baseline gap-1.5">
                      <span className="font-semibold text-muted-foreground">【参考答案】</span>
                      <MathText className="inline font-mono">{q.answer}</MathText>
                    </div>
                  )}
                  {q.analysis && (
                    <div className="space-y-1">
                      <span className="font-semibold text-muted-foreground">【试题解析】</span>
                      <MathText className="leading-relaxed text-muted-foreground/90">{q.analysis}</MathText>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      <Link href="/papers" className="inline-block text-sm text-muted-foreground hover:underline">
        ← 返回试卷列表
      </Link>

      {node}
    </div>
  );
}
