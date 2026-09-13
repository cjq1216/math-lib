"use client";

import * as React from "react";
import Link from "next/link";
import { http, qs } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorBox,
  Input,
  Loading,
  Select,
} from "@/components/ui";
import { MathText } from "@/components/MathText";
import {
  DIFFICULTY_LABEL,
  QUESTION_TYPE_LABEL,
  type KnowledgePoint,
  type Question,
} from "@/lib/types";

export default function QuestionsPage() {
  const [items, setItems] = React.useState<Question[]>([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const [keyword, setKeyword] = React.useState("");
  const [qtype, setQtype] = React.useState("");
  const [difficulty, setDifficulty] = React.useState("");
  const [kpId, setKpId] = React.useState("");
  const [kps, setKps] = React.useState<KnowledgePoint[]>([]);

  React.useEffect(() => {
    http
      .get<KnowledgePoint[]>("/api/v1/knowledge/")
      .then(setKps)
      .catch(() => {});
  }, []);

  const load = React.useCallback(() => {
    setLoading(true);
    setError("");
    http
      .get<{ items: Question[]; total: number }>(
        `/api/v1/questions/${qs({ keyword, question_type: qtype, difficulty, knowledge_point_id: kpId, limit: 50 })}`,
      )
      .then((d) => {
        setItems(d.items ?? []);
        setTotal(d.total ?? 0);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [keyword, qtype, difficulty, kpId]);

  // 关键词防抖
  React.useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">题库</h1>
        <Link href="/questions/new">
          <Button>+ 录题</Button>
        </Link>
      </div>

      <Card className="p-4">
        <div className="grid gap-3 md:grid-cols-5">
          <Input
            placeholder="题干关键词"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <Select value={qtype} onChange={(e) => setQtype(e.target.value)}>
            <option value="">全部题型</option>
            {Object.entries(QUESTION_TYPE_LABEL).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </Select>
          <Select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
            <option value="">全部难度</option>
            {[1, 2, 3, 4, 5].map((d) => (
              <option key={d} value={d}>
                {DIFFICULTY_LABEL[d]}
              </option>
            ))}
          </Select>
          <Select value={kpId} onChange={(e) => setKpId(e.target.value)}>
            <option value="">全部知识点</option>
            {kps.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </Select>
          <Button variant="outline" onClick={load}>
            刷新（共 {total} 题）
          </Button>
        </div>
      </Card>

      {error && <ErrorBox message={error} />}

      {loading ? (
        <Loading />
      ) : items.length === 0 ? (
        <Empty
          text="没有符合条件的题目"
          action={
            <Link href="/questions/new">
              <Button>录入第一道题</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-3">
          {items.map((q) => (
            <Link key={q.id} href={`/questions/${q.id}/edit`}>
              <Card className="p-4 transition hover:border-primary">
                <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-muted-foreground">#{q.id}</span>
                  <Badge>{QUESTION_TYPE_LABEL[q.question_type] ?? q.question_type}</Badge>
                  <Badge tone={q.difficulty >= 4 ? "danger" : q.difficulty <= 2 ? "success" : "warning"}>
                    难度 {q.difficulty}
                  </Badge>
                  <Badge tone="info">{q.total_score} 分</Badge>
                  {q.is_verified ? (
                    <Badge tone="success">已校对</Badge>
                  ) : (
                    <Badge tone="warning">待校对</Badge>
                  )}
                </div>
                <MathText className="line-clamp-3 text-sm leading-relaxed">{q.stem}</MathText>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
