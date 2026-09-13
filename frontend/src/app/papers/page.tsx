"use client";

import * as React from "react";
import Link from "next/link";
import { http } from "@/lib/api";
import { Badge, Button, Card, Empty, ErrorBox, Loading } from "@/components/ui";
import type { PaperSummary } from "@/lib/types";

export default function PapersPage() {
  const [items, setItems] = React.useState<PaperSummary[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const load = React.useCallback(() => {
    setLoading(true);
    http
      .get<PaperSummary[]>("/api/v1/papers/?limit=50")
      .then((d) => setItems(Array.isArray(d) ? d : []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(load, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">试卷</h1>
        <Link href="/papers/generate">
          <Button>+ 智能组卷</Button>
        </Link>
      </div>

      {error && <ErrorBox message={error} />}
      {loading ? (
        <Loading />
      ) : items.length === 0 ? (
        <Empty
          text="还没有试卷"
          action={
            <Link href="/papers/generate">
              <Button>去组卷</Button>
            </Link>
          }
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {items.map((p) => (
            <Link key={p.id} href={`/papers/${p.id}`}>
              <Card className="p-4 transition hover:border-primary">
                <div className="mb-2 flex items-center gap-2">
                  <span className="font-medium">{p.title}</span>
                  <Badge tone={p.status === "published" ? "success" : "default"}>
                    {p.status === "published" ? "已发布" : "草稿"}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground">
                  {p.question_count ?? 0} 题 · {p.total_score} 分 · {p.duration_minutes} 分钟
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
