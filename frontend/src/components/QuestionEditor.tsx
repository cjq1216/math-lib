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
  type KnowledgePoint,
  type LlmTaskStatus,
  type QuestionDetail,
  type QuestionType,
} from "@/lib/types";

interface Props {
  initial?: QuestionDetail | null;
}

interface KpPick {
  id: number;
  name: string;
  path: string;
}

/** 把知识点树拍平成带路径的列表 */
function flattenKps(nodes: KnowledgePoint[], prefix = "", out: KpPick[] = []): KpPick[] {
  for (const n of nodes) {
    const path = prefix ? `${prefix} / ${n.name}` : n.name;
    out.push({ id: n.id, name: n.name, path });
    if (n.children?.length) flattenKps(n.children, path, out);
  }
  return out;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function QuestionEditor({ initial }: Props) {
  const router = useRouter();
  const { show, node } = useToast();

  const isEdit = Boolean(initial?.id);

  const [stem, setStem] = React.useState(initial?.stem ?? "");
  const [qtype, setQtype] = React.useState<QuestionType>(initial?.question_type ?? "choice_single");
  const [difficulty, setDifficulty] = React.useState(initial?.difficulty ?? 3);
  const [totalScore, setTotalScore] = React.useState(initial?.total_score ?? 10);
  const [options, setOptions] = React.useState<string[]>(
    initial?.options?.length ? initial.options : ["", "", "", ""],
  );
  const [answer, setAnswer] = React.useState(initial?.answer ?? "");
  const [analysis, setAnalysis] = React.useState(initial?.analysis ?? "");
  const [tagsText, setTagsText] = React.useState((initial?.tags ?? []).join(", "));

  const [subs, setSubs] = React.useState<{ label: string; stem: string; score: number; answer: string }[]>(
    initial?.sub_questions?.length
      ? initial.sub_questions.map((s) => ({
          label: s.label,
          stem: s.stem ?? "",
          score: s.score,
          answer: s.answer ?? "",
        }))
      : [],
  );

  const [kpList, setKpList] = React.useState<KpPick[]>([]);
  const [kpKeyword, setKpKeyword] = React.useState("");
  const [selectedKps, setSelectedKps] = React.useState<number[]>(
    initial?.knowledge_points?.map((k) => k.kp_id) ?? [],
  );
  const [primaryKp, setPrimaryKp] = React.useState<number | null>(
    initial?.knowledge_points?.find((k) => k.is_primary)?.kp_id ?? null,
  );

  const [saving, setSaving] = React.useState(false);
  const [task, setTask] = React.useState<LlmTaskStatus | null>(null);

  // 加载知识点树
  React.useEffect(() => {
    http
      .get<KnowledgePoint[]>("/api/v1/knowledge/tree")
      .then((tree) => setKpList(flattenKps(tree)))
      .catch(() => show("知识点加载失败，请确认已导入知识点", "error"));
  }, [show]);

  const filteredKps = React.useMemo(() => {
    const kw = kpKeyword.trim();
    return kw ? kpList.filter((k) => k.path.includes(kw)) : kpList;
  }, [kpList, kpKeyword]);

  const needOptions = qtype === "choice_single" || qtype === "choice_multi";

  async function pollTask(taskId: number): Promise<LlmTaskStatus> {
    for (let i = 0; i < 120; i++) {
      const s = await http.get<LlmTaskStatus>(`/api/v1/llm/tasks/${taskId}`);
      setTask(s);
      if (s.status === "success" || s.status === "failed") return s;
      await sleep(1200);
    }
    throw new Error("任务超时");
  }

  async function onAutoTag() {
    if (!stem.trim()) return show("请先填写题干", "error");
    try {
      const r = await http.post<{ task_id: number }>("/api/v1/llm/tag", {
        stem,
        options: needOptions ? options.filter(Boolean) : null,
        answer,
        question_id: initial?.id ?? null,
      });
      show("AI 打标任务已提交", "info");
      const s = await pollTask(r.task_id);
      if (s.status === "failed") {
        show(s.error_message || "打标失败", "error");
        return;
      }
      const res = (s.result ?? {}) as Record<string, unknown>;
      const t = res.question_type as QuestionType | undefined;
      const d = res.difficulty as number | string | undefined;
      if (t && t in QUESTION_TYPE_LABEL) setQtype(t);
      if (d !== undefined) setDifficulty(Number(d));
      show("AI 打标完成，请人工确认后保存", "success");
    } catch (e) {
      show(e instanceof Error ? e.message : "打标失败", "error");
    } finally {
      setTask(null);
    }
  }

  async function save(goList: boolean) {
    if (!stem.trim()) return show("题干不能为空", "error");
    setSaving(true);
    try {
      const payload = {
        stem,
        question_type: qtype,
        difficulty,
        total_score: Number(totalScore),
        options: needOptions ? options.filter((o) => o.trim()) : null,
        answer,
        analysis,
        tags: tagsText
          .split(/[,，]/)
          .map((s) => s.trim())
          .filter(Boolean),
      };

      let qid = initial?.id;
      if (isEdit && qid) {
        await http.patch(`/api/v1/questions/${qid}`, payload);
      } else {
        const r = await http.post<{ id: number }>("/api/v1/questions/", payload);
        qid = r.id;
      }

      // 知识点关联
      await http.put(`/api/v1/questions/${qid}/knowledge`, {
        items: selectedKps.map((id) => ({ kp_id: id, is_primary: id === primaryKp })),
      });
      // 小问
      await http.put(`/api/v1/questions/${qid}/sub-questions`, { items: subs });

      show("保存成功", "success");
      if (goList) router.push("/questions");
      else if (!isEdit) router.push(`/questions/${qid}/edit`);
    } catch (e) {
      show(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      {/* 左侧：题面 */}
      <div className="space-y-4">
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>{isEdit ? `编辑题目 #${initial?.id}` : "新建题目"}</CardTitle>
            <Button variant="outline" size="sm" onClick={onAutoTag}>
              AI 自动打标
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>题干（支持 LaTeX：$x^2$ 行内，$$...$$ 独立成行）</Label>
              <Textarea
                value={stem}
                onChange={(e) => setStem(e.target.value)}
                placeholder="例如：已知 $x^2 - 5x + 6 = 0$，求 $x$ 的值。"
              />
            </div>

            <div className="rounded-md border border-border bg-muted/40 p-3">
              <div className="mb-1 text-xs text-muted-foreground">实时预览</div>
              <MathText className="text-sm leading-relaxed" >{stem}</MathText>
            </div>

            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <div>
                <Label>题型</Label>
                <Select value={qtype} onChange={(e) => setQtype(e.target.value as QuestionType)}>
                  {Object.entries(QUESTION_TYPE_LABEL).map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label>难度</Label>
                <Select value={difficulty} onChange={(e) => setDifficulty(Number(e.target.value))}>
                  {[1, 2, 3, 4, 5].map((d) => (
                    <option key={d} value={d}>
                      {DIFFICULTY_LABEL[d]}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label>总分</Label>
                <Input
                  type="number"
                  step="0.5"
                  value={totalScore}
                  onChange={(e) => setTotalScore(Number(e.target.value))}
                />
              </div>
              <div>
                <Label>标签（逗号分隔）</Label>
                <Input value={tagsText} onChange={(e) => setTagsText(e.target.value)} placeholder="期中,易错" />
              </div>
            </div>

            {needOptions && (
              <div>
                <Label>选项</Label>
                <div className="space-y-2">
                  {options.map((o, i) => (
                    <div key={i} className="flex gap-2">
                      <span className="w-8 pt-2 text-sm text-muted-foreground">
                        {String.fromCharCode(65 + i)}.
                      </span>
                      <Input
                        value={o}
                        onChange={(e) => {
                          const next = [...options];
                          next[i] = e.target.value;
                          setOptions(next);
                        }}
                        placeholder={`选项 ${String.fromCharCode(65 + i)}`}
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setOptions(options.filter((_, idx) => idx !== i))}
                      >
                        删
                      </Button>
                    </div>
                  ))}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-2"
                  onClick={() => setOptions([...options, ""])}
                >
                  + 加选项
                </Button>
              </div>
            )}

            <div>
              <Label>答案</Label>
              <Textarea value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="如：$x=2$ 或 $x=3$" />
            </div>

            <div>
              <Label>解析</Label>
              <Textarea value={analysis} onChange={(e) => setAnalysis(e.target.value)} />
            </div>
          </CardContent>
        </Card>

        {/* 小问 */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>小问（复合题可拆，用于独立给分与学情聚合）</CardTitle>
            <Button variant="outline" size="sm" onClick={() => setSubs([...subs, { label: `(${subs.length + 1})`, stem: "", score: 0, answer: "" }])}>
              + 加小问
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {subs.length === 0 && (
              <p className="text-sm text-muted-foreground">无小问。单道题可留空。</p>
            )}
            {subs.map((s, i) => (
              <div key={i} className="grid gap-2 rounded-md border border-border p-3 md:grid-cols-[80px_1fr_90px_1fr_auto]">
                <Input value={s.label} onChange={(e) => {
                  const n = [...subs]; n[i] = { ...s, label: e.target.value }; setSubs(n);
                }} />
                <Input placeholder="小问题干" value={s.stem} onChange={(e) => {
                  const n = [...subs]; n[i] = { ...s, stem: e.target.value }; setSubs(n);
                }} />
                <Input type="number" step="0.5" placeholder="分值" value={s.score} onChange={(e) => {
                  const n = [...subs]; n[i] = { ...s, score: Number(e.target.value) }; setSubs(n);
                }} />
                <Input placeholder="小问答案" value={s.answer} onChange={(e) => {
                  const n = [...subs]; n[i] = { ...s, answer: e.target.value }; setSubs(n);
                }} />
                <Button variant="ghost" size="sm" onClick={() => setSubs(subs.filter((_, idx) => idx !== i))}>
                  删
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* 右侧：知识点 + 保存 */}
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>知识点关联</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              value={kpKeyword}
              onChange={(e) => setKpKeyword(e.target.value)}
              placeholder="搜索知识点"
            />
            <div className="max-h-80 space-y-1 overflow-y-auto rounded-md border border-border p-2">
              {filteredKps.length === 0 && (
                <p className="p-2 text-sm text-muted-foreground">未找到知识点，请先到「知识点」页导入</p>
              )}
              {filteredKps.map((k) => {
                const checked = selectedKps.includes(k.id);
                return (
                  <div key={k.id} className="flex items-center gap-2 rounded px-1 py-1 hover:bg-accent/50">
                    <input
                      type="checkbox"
                      className="h-4 w-4 cursor-pointer"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedKps([...selectedKps, k.id]);
                        else {
                          setSelectedKps(selectedKps.filter((x) => x !== k.id));
                          if (primaryKp === k.id) setPrimaryKp(null);
                        }
                      }}
                    />
                    <span className="flex-1 cursor-pointer text-sm" onClick={() => {
                      setSelectedKps(checked ? selectedKps.filter((x) => x !== k.id) : [...selectedKps, k.id]);
                    }}>
                      {k.path}
                    </span>
                    {checked && (
                      <button
                        className={"rounded px-1.5 py-0.5 text-xs " + (primaryKp === k.id ? "bg-blue-600 text-white" : "bg-muted")}
                        onClick={() => setPrimaryKp(primaryKp === k.id ? null : k.id)}
                        title="设为主知识点"
                      >
                        主
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="text-xs text-muted-foreground">
              已选 {selectedKps.length} 个{primaryKp ? " · 已设主知识点" : " · 未设主知识点"}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-2">
            <Button className="w-full" onClick={() => save(false)} disabled={saving}>
              {saving ? "保存中..." : "保存"}
            </Button>
            <Button variant="outline" className="w-full" onClick={() => save(true)} disabled={saving}>
              保存并返回列表
            </Button>
            <Button variant="ghost" className="w-full" onClick={() => router.push("/questions")}>
              取消
            </Button>
          </CardContent>
        </Card>

        {task && (
          <Card>
            <CardContent className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <Badge tone={task.status === "failed" ? "danger" : "info"}>
                  {task.status === "pending" && "排队中"}
                  {task.status === "running" && "处理中"}
                  {task.status === "success" && "已完成"}
                  {task.status === "failed" && "失败"}
                </Badge>
                <span className="text-muted-foreground">{task.progress}%</span>
              </div>
              <Progress value={task.progress} />
              {task.progress_message && (
                <p className="text-xs text-muted-foreground">{task.progress_message}</p>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {node}
    </div>
  );
}
