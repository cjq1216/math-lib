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
  HomeworkDetail,
  HomeworkPaperQuestionItem,
  HomeworkStudentItem,
  ImportErrorItem,
  PaperDetail,
} from "@/lib/types";

interface StudentScoreState {
  totalScore: string;
  timeSpent: string;
  questionScores: Record<number, string>; // paper_question_id -> score
}

export default function HomeworkDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const { show, node } = useToast();

  const [hw, setHw] = React.useState<HomeworkDetail | null>(null);
  const [paper, setPaper] = React.useState<PaperDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  // student_id -> scoring state
  const [scoreMap, setScoreMap] = React.useState<Record<number, StudentScoreState>>({});
  const [expandedStudentId, setExpandedStudentId] = React.useState<number | null>(null);
  const [savingId, setSavingId] = React.useState<number | null>(null);
  const [importErrors, setImportErrors] = React.useState<ImportErrorItem[]>([]);

  const reload = React.useCallback(() => {
    if (!id) return;
    setLoading(true);
    http
      .get<HomeworkDetail>(`/api/v1/homework/${id}`)
      .then(async (h) => {
        setHw(h);
        const p = await http.get<PaperDetail>(`/api/v1/papers/${h.paper_id}`).catch(() => null);
        setPaper(p);

        // 初始化学生输入状态
        const initialMap: Record<number, StudentScoreState> = {};
        const students = h.target_students || [];
        const results = h.results || [];

        students.forEach((s) => {
          const res = results.find((r) => r.student_id === s.student_id);
          const qScores: Record<number, string> = {};
          if (res?.question_results) {
            res.question_results.forEach((qr) => {
              qScores[qr.paper_question_id] = String(qr.score);
            });
          }

          initialMap[s.student_id] = {
            totalScore: res?.total_score != null ? String(res.total_score) : "",
            timeSpent: res?.time_spent_minutes != null ? String(res.time_spent_minutes) : "",
            questionScores: qScores,
          };
        });

        setScoreMap(initialMap);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  React.useEffect(reload, [reload]);

  // 修改单题得分，自动汇总总分
  function handleQuestionScoreChange(
    studentId: number,
    paperQuestionId: number,
    valStr: string,
    pqs: HomeworkPaperQuestionItem[]
  ) {
    setScoreMap((prev) => {
      const current = prev[studentId] || { totalScore: "", timeSpent: "", questionScores: {} };
      const nextQScores = { ...current.questionScores, [paperQuestionId]: valStr };

      // 计算新的总分
      let sum = 0;
      let hasAny = false;
      pqs.forEach((pq) => {
        const v = nextQScores[pq.id];
        if (v !== undefined && v.trim() !== "") {
          const n = Number(v);
          if (!isNaN(n)) {
            sum += n;
            hasAny = true;
          }
        }
      });

      return {
        ...prev,
        [studentId]: {
          ...current,
          questionScores: nextQScores,
          totalScore: hasAny ? String(sum) : current.totalScore,
        },
      };
    });
  }

  async function saveStudentScore(student: HomeworkStudentItem) {
    if (!hw) return;
    const sid = student.student_id;
    const state = scoreMap[sid];
    if (!state) return show("未录入成绩", "error");

    setSavingId(sid);
    try {
      const pqs = hw.paper_questions || [];
      const hasQDetail = Object.keys(state.questionScores).length > 0;

      let payload: Record<string, unknown> = {
        student_id: sid,
        time_spent_minutes: state.timeSpent ? Number(state.timeSpent) : null,
      };

      if (hasQDetail && pqs.length > 0) {
        const qResults = pqs
          .map((pq) => {
            const val = state.questionScores[pq.id];
            if (val === undefined || val.trim() === "") return null;
            return {
              paper_question_id: pq.id,
              score: Number(val),
            };
          })
          .filter(Boolean);

        payload = {
          ...payload,
          question_results: qResults,
        };
      } else {
        if (!state.totalScore) {
          show("请填写得分", "error");
          setSavingId(null);
          return;
        }
        payload = {
          ...payload,
          total_score: Number(state.totalScore),
          max_score: paper?.total_score ?? 100,
        };
      }

      await http.post(`/api/v1/homework/${id}/results`, payload);
      show(`已保存 ${student.name} 的成绩，学情已自动更新`, "success");
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSavingId(null);
    }
  }

  async function importResults(file: File) {
    try {
      setImportErrors([]);
      const r = await http.upload<{
        created: number;
        updated: number;
        errors: ImportErrorItem[];
      }>(`/api/v1/homework/${id}/import-results`, file);

      if (r.errors && r.errors.length > 0) {
        setImportErrors(r.errors);
        show(`导入完成：成功 ${r.created + r.updated} 条，${r.errors.length} 行有错`, "error");
      } else {
        show(`导入成功：新增 ${r.created}，更新 ${r.updated}，学情已自动重算`, "success");
      }
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "导入失败", "error");
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!hw) return null;

  const students = hw.target_students || [];
  const paperQuestions = hw.paper_questions || [];
  const results = hw.results || [];
  const filledCount = results.filter((r) => r.total_score != null).length;

  return (
    <div className="space-y-4">
      {/* 顶部标题与操作 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold">{hw.title}</h1>
            <Badge tone="info">名单快照</Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            试卷：{paper?.title ?? `#${hw.paper_id}`} · 满分 {paper?.total_score ?? 100} 分 · 共{" "}
            {paperQuestions.length} 题 · 已录入 {filledCount}/{students.length} 人
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
            下载成绩录入模板 (带快照名单)
          </Button>
          <Button
            size="sm"
            onClick={async () => {
              setSavingId(-1);
              let okCount = 0;
              for (const s of students) {
                const st = scoreMap[s.student_id];
                if (st && (st.totalScore || Object.keys(st.questionScores).length > 0)) {
                  try {
                    const hasQ = Object.keys(st.questionScores).length > 0;
                    const payload = hasQ
                      ? {
                          student_id: s.student_id,
                          question_results: paperQuestions
                            .map((pq) => {
                              const val = st.questionScores[pq.id];
                              if (val === undefined || val.trim() === "") return null;
                              return { paper_question_id: pq.id, score: Number(val) };
                            })
                            .filter(Boolean),
                          time_spent_minutes: st.timeSpent ? Number(st.timeSpent) : null,
                        }
                      : {
                          student_id: s.student_id,
                          total_score: Number(st.totalScore),
                          max_score: paper?.total_score ?? 100,
                          time_spent_minutes: st.timeSpent ? Number(st.timeSpent) : null,
                        };
                    await http.post(`/api/v1/homework/${id}/results`, payload);
                    okCount++;
                  } catch {
                    /* 继续保存其他行 */
                  }
                }
              }
              setSavingId(null);
              show(`已保存 ${okCount} 名学生的成绩并自动重算学情`, "success");
              reload();
            }}
            disabled={savingId === -1}
          >
            {savingId === -1 ? "保存中..." : "一键保存全部"}
          </Button>
        </div>
      </div>

      {/* Excel 导入卡片 */}
      <Card>
        <CardHeader className="flex items-center justify-between">
          <div>
            <CardTitle>Excel 成绩导入</CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">
              支持按试卷题目填报分值，同时支持对错符号（如 √、×、对、错）。导入后自动为所有学生重算学情。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Label className="mb-0 text-sm">选择文件：</Label>
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

        {importErrors.length > 0 && (
          <CardContent className="border-t border-destructive/20 bg-destructive/5 pt-4">
            <div className="text-sm font-medium text-destructive mb-2">
              导入错误提示（共 {importErrors.length} 处）：
            </div>
            <div className="max-h-40 overflow-y-auto space-y-1 text-xs text-destructive">
              {importErrors.map((err, i) => (
                <div key={i} className="flex gap-2">
                  <span className="font-semibold">第 {err.row} 行</span>
                  {err.column && <span>[{err.column}]</span>}
                  <span>{err.message}</span>
                </div>
              ))}
            </div>
          </CardContent>
        )}
      </Card>

      {/* 成绩录入主表格 */}
      <Card>
        <CardHeader>
          <CardTitle>学生成绩花名册（下发名单快照）</CardTitle>
        </CardHeader>
        <CardContent>
          {students.length === 0 ? (
            <Empty text="该作业下发名单中暂无学生" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="py-2.5 px-2">学号</th>
                    <th className="py-2.5 px-2">姓名</th>
                    <th className="py-2.5 px-2">下发时班级</th>
                    <th className="w-32 py-2.5 px-2">总分 / 满分</th>
                    <th className="w-24 py-2.5 px-2">百分比</th>
                    <th className="w-28 py-2.5 px-2">用时(分)</th>
                    <th className="py-2.5 px-2 text-right">小题明细 / 操作</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((s) => {
                    const sid = s.student_id;
                    const st = scoreMap[sid] || { totalScore: "", timeSpent: "", questionScores: {} };
                    const isExpanded = expandedStudentId === sid;
                    const res = results.find((r) => r.student_id === sid);
                    const isSaved = res && res.total_score != null;

                    return (
                      <React.Fragment key={sid}>
                        <tr className="border-b border-border hover:bg-muted/30">
                          <td className="py-2 px-2 font-mono text-xs">{s.student_no ?? "-"}</td>
                          <td className="py-2 px-2 font-medium">
                            <Link
                              href={`/analytics/students/${sid}`}
                              className="text-primary hover:underline"
                            >
                              {s.name}
                            </Link>
                          </td>
                          <td className="py-2 px-2 text-xs text-muted-foreground">
                            {s.class_name ?? "未指定"}
                          </td>
                          <td className="py-2 px-2">
                            <Input
                              type="number"
                              step="0.5"
                              value={st.totalScore}
                              placeholder="0"
                              className="h-8 text-sm"
                              onChange={(e) =>
                                setScoreMap((prev) => ({
                                  ...prev,
                                  [sid]: { ...prev[sid], totalScore: e.target.value },
                                }))
                              }
                            />
                          </td>
                          <td className="py-2 px-2 text-xs font-semibold">
                            {res?.percentage != null ? `${Math.round(res.percentage)}%` : "-"}
                          </td>
                          <td className="py-2 px-2">
                            <Input
                              type="number"
                              value={st.timeSpent}
                              placeholder="可选"
                              className="h-8 text-sm"
                              onChange={(e) =>
                                setScoreMap((prev) => ({
                                  ...prev,
                                  [sid]: { ...prev[sid], timeSpent: e.target.value },
                                }))
                              }
                            />
                          </td>
                          <td className="py-2 px-2 text-right space-x-2">
                            {paperQuestions.length > 0 && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-8 px-2 text-xs"
                                onClick={() => setExpandedStudentId(isExpanded ? null : sid)}
                              >
                                {isExpanded ? "收起小题" : "按题录入"}
                              </Button>
                            )}
                            <Button
                              size="sm"
                              className="h-8 px-3 text-xs"
                              disabled={savingId === sid}
                              onClick={() => saveStudentScore(s)}
                            >
                              {savingId === sid ? "保存中" : isSaved ? "更新" : "保存"}
                            </Button>
                          </td>
                        </tr>

                        {/* 展开的按题录入面板 */}
                        {isExpanded && paperQuestions.length > 0 && (
                          <tr className="bg-muted/20">
                            <td colSpan={7} className="p-3 border-b border-border">
                              <div className="space-y-2">
                                <div className="flex items-center justify-between text-xs font-medium">
                                  <span>{s.name} 的小题得分明细（填入后自动汇算总分）：</span>
                                  <span className="text-muted-foreground">
                                    共 {paperQuestions.length} 道题
                                  </span>
                                </div>
                                <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2 pt-1">
                                  {paperQuestions.map((pq) => {
                                    const val = st.questionScores[pq.id] ?? "";
                                    return (
                                      <div
                                        key={pq.id}
                                        className="rounded border border-border bg-background p-2 text-xs space-y-1"
                                      >
                                        <div className="flex justify-between text-muted-foreground">
                                          <span>第 {pq.display_order} 题</span>
                                          <span>{pq.score}分</span>
                                        </div>
                                        <Input
                                          type="number"
                                          step="0.5"
                                          min={0}
                                          max={pq.score}
                                          placeholder={`0-${pq.score}`}
                                          className="h-7 text-xs px-1.5"
                                          value={val}
                                          onChange={(e) =>
                                            handleQuestionScoreChange(
                                              sid,
                                              pq.id,
                                              e.target.value,
                                              paperQuestions
                                            )
                                          }
                                        />
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
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
