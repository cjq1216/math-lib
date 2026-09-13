"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { http } from "@/lib/api";
import { Badge, Button, Card, CardContent, ErrorBox, Loading, useToast } from "@/components/ui";
import { MathText } from "@/components/MathText";
import type { PaperDetail } from "@/lib/types";

export default function PaperDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const router = useRouter();
  const { show, node } = useToast();

  const [data, setData] = React.useState<PaperDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [showAnswer, setShowAnswer] = React.useState(false);

  React.useEffect(() => {
    if (!id) return;
    http
      .get<PaperDetail>(`/api/v1/papers/${id}`)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  async function publish() {
    try {
      await http.post(`/api/v1/papers/${id}/publish`, {});
      show("已发布", "success");
      setData((d) => (d ? { ...d, status: "published" } : d));
    } catch (e) {
      show(e instanceof Error ? e.message : "发布失败", "error");
    }
  }

  async function exportPaper(format: "word" | "markdown" | "pdf") {
    try {
      const r = await http.post<{ message: string }>(
        `/api/v1/papers/${id}/export?format=${format}`,
        {},
      );
      show(r.message ?? "导出任务已提交", "info");
    } catch (e) {
      show(e instanceof Error ? e.message : "导出失败", "error");
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{data.title}</h1>
          <p className="text-sm text-muted-foreground">
            {data.questions.length} 题 · {data.total_score} 分 · {data.duration_minutes} 分钟
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowAnswer((v) => !v)}>
            {showAnswer ? "隐藏答案" : "显示答案"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => exportPaper("word")}>
            导出 Word
          </Button>
          <Button variant="outline" size="sm" onClick={() => exportPaper("markdown")}>
            导出 Markdown
          </Button>
          <Button variant="outline" size="sm" onClick={() => router.push(`/homework/new?paper_id=${id}`)}>
            下发为作业
          </Button>
          {data.status !== "published" && (
            <Button size="sm" onClick={publish}>
              发布
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardContent className="space-y-5">
          {data.questions.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">该试卷暂无题目</p>
          )}
          {data.questions.map((q) => (
            <div key={q.id} className="border-b border-border pb-5 last:border-0 last:pb-0">
              <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{q.display_order}.</span>
                {q.section && <Badge>{q.section}</Badge>}
                <span>{q.score} 分</span>
              </div>
              <MathText className="text-sm leading-relaxed">{q.stem}</MathText>

              {showAnswer && (
                <div className="mt-3 space-y-2 rounded-md bg-muted/50 p-3 text-sm">
                  {q.answer && (
                    <div>
                      <span className="font-medium">答案：</span>
                      <MathText className="inline">{q.answer}</MathText>
                    </div>
                  )}
                  {q.analysis && (
                    <div>
                      <span className="font-medium">解析：</span>
                      <MathText className="inline">{q.analysis}</MathText>
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
