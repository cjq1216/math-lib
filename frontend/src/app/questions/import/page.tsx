"use client";

import * as React from "react";
import Link from "next/link";
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
  Progress,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import { MathText } from "@/components/MathText";
import {
  DIFFICULTY_LABEL,
  QUESTION_TYPE_LABEL,
  type LlmTaskStatus,
  type QuestionType,
  type SplitDraftQuestion,
  type SplitTaskResult,
} from "@/lib/types";

function sleep(ms: number): Promise<void> {
  const { promise, resolve } = Promise.withResolvers<void>();
  setTimeout(resolve, ms);
  return promise;
}

export default function QuestionImportPage() {
  const router = useRouter();
  const { show, node } = useToast();

  const [rawText, setRawText] = React.useState("");
  const [drafts, setDrafts] = React.useState<SplitDraftQuestion[]>([]);
  const [task, setTask] = React.useState<LlmTaskStatus | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [committing, setCommitting] = React.useState(false);
  const [error, setError] = React.useState("");

  // 手动粘贴切题输入框显示切换
  const [showPasteModal, setShowPasteModal] = React.useState(false);
  const [pasteText, setPasteText] = React.useState("");

  async function pollTask(taskId: number): Promise<SplitTaskResult> {
    for (let i = 0; i < 150; i++) {
      const s = await http.get<LlmTaskStatus>(`/api/v1/llm/tasks/${taskId}`);
      setTask(s);
      if (s.status === "success" || s.status === "partial_success") {
        return (s.result as SplitTaskResult) || { questions: [], total: 0 };
      }
      if (s.status === "failed" || s.status === "cancelled") {
        throw new Error(s.error_message || "切题任务执行失败");
      }
      await sleep(1500);
    }
    throw new Error("切题任务超时，请稍后刷新任务列表重试");
  }

  // 上传试卷文件切题
  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setError("");
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);

    try {
      show(`正在解析文档: ${file.name}...`, "info");
      // 先调用上传接口触发切题
      const res = await http.upload<{ task_id: number; message: string }>("/api/v1/llm/split-doc", file);
      show("切题任务已启动，正在分段调用大模型分析试题...", "info");

      const result = await pollTask(res.task_id);
      setDrafts(result.questions || []);
      show(`切题完成！共识别 ${result.questions?.length ?? 0} 道题目，请校对后确认入库`, "success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "切题解析失败");
      show(err instanceof Error ? err.message : "切题解析失败", "error");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  // 纯文本切题
  async function handlePasteSplit() {
    if (!pasteText.trim()) return;
    setError("");
    setUploading(true);
    setShowPasteModal(false);
    setRawText(pasteText);

    try {
      const res = await http.post<{ task_id: number }>("/api/v1/llm/split", { text: pasteText });
      show("纯文本切题任务已启动...", "info");
      const result = await pollTask(res.task_id);
      setDrafts(result.questions || []);
      show(`切题完成！共识别 ${result.questions?.length ?? 0} 道题目`, "success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "切题失败");
    } finally {
      setUploading(false);
    }
  }

  // 批量确认入库
  async function commitAllDrafts() {
    if (drafts.length === 0) return;
    setCommitting(true);
    try {
      const res = await http.post<{ created_count: number; question_ids: number[] }>(
        "/api/v1/llm/commit-drafts",
        { questions: drafts },
      );
      show(`成功将 ${res.created_count} 道题目正式存入题库！`, "success");
      router.push("/questions");
    } catch (err) {
      show(err instanceof Error ? err.message : "入库失败", "error");
    } finally {
      setCommitting(false);
    }
  }

  function updateDraft(index: number, patch: Partial<SplitDraftQuestion>) {
    setDrafts((prev) => {
      const n = [...prev];
      n[index] = { ...n[index], ...patch };
      return n;
    });
  }

  function removeDraft(index: number) {
    setDrafts((prev) => prev.filter((_, idx) => idx !== index));
  }

  const totalScoreEstimate = drafts.reduce((acc, q) => acc + (Number(q.total_score) || 0), 0);

  return (
    <div className="space-y-4">
      {/* 顶部标题与操作栏 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">试卷切题与智能校对工作台</h1>
          <p className="text-sm text-muted-foreground mt-1">
            支持 Word (.docx)、PDF (.pdf) 与纯文本试卷智能切分；左侧查看原始试卷，右侧实时校对微调后一键聚合入库。
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="cursor-pointer">
            <span className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow hover:bg-primary/90">
              {uploading ? "正在解析切题..." : "+ 上传试卷文件 (.docx / .pdf)"}
            </span>
            <input
              type="file"
              className="hidden"
              accept=".docx,.pdf,.txt,.md"
              disabled={uploading}
              onChange={handleFileUpload}
            />
          </label>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowPasteModal(true)}
            disabled={uploading}
          >
            粘贴纯文本切题
          </Button>
          <Link href="/questions">
            <Button variant="ghost" size="sm">
              返回题库
            </Button>
          </Link>
        </div>
      </div>

      {/* 任务进度条 */}
      {task && uploading && (
        <Card className="border-primary/50 bg-primary/5">
          <CardContent className="space-y-2 py-3 text-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge tone={task.status === "failed" ? "danger" : "info"}>
                  {task.status === "running" ? "AI 分析切题中" : "任务排队中"}
                </Badge>
                <span className="text-xs text-muted-foreground">{task.progress_message}</span>
              </div>
              <span className="font-mono text-xs font-semibold">{task.progress}%</span>
            </div>
            <Progress value={task.progress} />
          </CardContent>
        </Card>
      )}

      {error && <ErrorBox message={error} />}

      {/* 粘贴文本模态浮层 */}
      {showPasteModal && (
        <div className="rounded-md border border-border bg-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <Label className="font-semibold">粘贴试卷纯文本（含 LaTeX 公式）：</Label>
            <Button variant="ghost" size="sm" onClick={() => setShowPasteModal(false)}>
              取消
            </Button>
          </div>
          <Textarea
            className="min-h-[160px] font-mono text-xs"
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder="例如：\n1. 已知 x^2 - 4 = 0，求 x 的值。\nA. 2  B. -2  C. ±2  D. 4"
          />
          <Button size="sm" onClick={handlePasteSplit} disabled={!pasteText.trim()}>
            开始切题
          </Button>
        </div>
      )}

      {/* 双栏校对主工作区 */}
      <div className="grid gap-6 lg:grid-cols-[400px_1fr]">
        {/* 左栏：原始试卷内容 */}
        <div className="space-y-3">
          <Card className="h-[calc(100vh-240px)] flex flex-col">
            <CardHeader className="border-b border-border pb-3">
              <CardTitle className="text-sm">原始试卷内容对照</CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-y-auto p-3 text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap font-mono">
              {rawText.trim() ? (
                rawText
              ) : (
                <div className="py-20 text-center text-muted-foreground/60">
                  上传 Word/PDF 或粘贴试卷后，原文内容将在此实时展示，供右侧题目校对时逐题比对。
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* 右栏：AI 识别题目卡片列表 */}
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">待校对题目列表</span>
              <Badge tone="info">{drafts.length} 题</Badge>
              <span className="text-xs text-muted-foreground">总分预估：{totalScoreEstimate} 分</span>
            </div>

            {drafts.length > 0 && (
              <Button size="sm" onClick={commitAllDrafts} disabled={committing}>
                {committing ? "入库中..." : "✓ 确认并一键批量入库"}
              </Button>
            )}
          </div>

          {drafts.length === 0 ? (
            <Card className="p-16 text-center text-sm text-muted-foreground">
              暂无待校对题目。请在上方点击「上传试卷文件」或「粘贴纯文本切题」，大模型将自动提取每题题干、选项、答案与解析。
            </Card>
          ) : (
            <div className="space-y-4 max-h-[calc(100vh-280px)] overflow-y-auto pr-1">
              {drafts.map((d, idx) => (
                <Card key={idx} className="border-border">
                  <CardHeader className="flex flex-row items-center justify-between border-b border-border bg-muted/20 py-2.5 px-4">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-semibold text-foreground">
                        第 {d.number || idx + 1} 题
                      </span>
                      <Select
                        className="h-7 text-xs"
                        value={d.question_type}
                        onChange={(e) =>
                          updateDraft(idx, { question_type: e.target.value as QuestionType })
                        }
                      >
                        {Object.entries(QUESTION_TYPE_LABEL).map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </Select>
                      <Select
                        className="h-7 text-xs"
                        value={d.difficulty}
                        onChange={(e) => updateDraft(idx, { difficulty: Number(e.target.value) || 3 })}
                      >
                        {[1, 2, 3, 4, 5].map((level) => (
                          <option key={level} value={level}>
                            {DIFFICULTY_LABEL[level]}
                          </option>
                        ))}
                      </Select>
                      <div className="flex items-center gap-1">
                        <Input
                          type="number"
                          step={0.5}
                          className="h-7 w-16 px-1.5 text-xs font-mono"
                          value={d.total_score}
                          onChange={(e) =>
                            updateDraft(idx, { total_score: Number(e.target.value) || 5 })
                          }
                        />
                        <span className="text-muted-foreground">分</span>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-xs text-red-600 hover:bg-red-50 hover:text-red-700"
                      onClick={() => removeDraft(idx)}
                    >
                      删除
                    </Button>
                  </CardHeader>
                  <CardContent className="space-y-3 p-4 text-xs">
                    {/* 题干输入与预览 */}
                    <div>
                      <Label className="text-[11px] text-muted-foreground">题干（含 LaTeX）</Label>
                      <Textarea
                        className="mt-1 min-h-[60px]"
                        value={d.stem}
                        onChange={(e) => updateDraft(idx, { stem: e.target.value })}
                      />
                      {d.stem && (
                        <div className="mt-1.5 rounded bg-muted/30 p-2 text-xs">
                          <MathText className="leading-relaxed">{d.stem}</MathText>
                        </div>
                      )}
                    </div>

                    {/* 选择题选项 */}
                    {(d.question_type === "choice_single" || d.question_type === "choice_multi") && (
                      <div>
                        <Label className="text-[11px] text-muted-foreground">选项（每行一个选项）</Label>
                        <Textarea
                          className="mt-1 min-h-[50px] font-mono"
                          value={(d.options || []).join("\n")}
                          onChange={(e) =>
                            updateDraft(idx, {
                              options: e.target.value.split("\n").filter((l) => l.trim()),
                            })
                          }
                          placeholder="A. ...\nB. ...\nC. ...\nD. ..."
                        />
                      </div>
                    )}

                    {/* 答案与解析 */}
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-[11px] text-muted-foreground">参考答案</Label>
                        <Input
                          className="mt-1 h-7 text-xs"
                          value={d.answer || ""}
                          onChange={(e) => updateDraft(idx, { answer: e.target.value })}
                        />
                      </div>
                      <div>
                        <Label className="text-[11px] text-muted-foreground">
                          知识点标签（逗号分隔）
                        </Label>
                        <Input
                          className="mt-1 h-7 text-xs"
                          value={(d.knowledge_points || []).join(", ")}
                          onChange={(e) =>
                            updateDraft(idx, {
                              knowledge_points: e.target.value
                                .split(/[,，]/)
                                .map((s) => s.trim())
                                .filter(Boolean),
                            })
                          }
                        />
                      </div>
                    </div>

                    <div>
                      <Label className="text-[11px] text-muted-foreground">试题解析</Label>
                      <Textarea
                        className="mt-1 min-h-[40px]"
                        value={d.analysis || ""}
                        onChange={(e) => updateDraft(idx, { analysis: e.target.value })}
                      />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>

      {node}
    </div>
  );
}
