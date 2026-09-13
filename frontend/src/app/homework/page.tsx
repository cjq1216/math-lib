"use client";

import * as React from "react";
import Link from "next/link";
import { http } from "@/lib/api";
import { Badge, Button, Card, Empty, ErrorBox, Loading } from "@/components/ui";
import type { HomeworkItem } from "@/lib/types";

const TYPE_LABEL: Record<string, string> = {
  homework: "课后作业",
  exam: "考试",
  practice: "练习",
};

export default function HomeworkPage() {
  const [items, setItems] = React.useState<HomeworkItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    http
      .get<HomeworkItem[]>("/api/v1/homework/?limit=50")
      .then((d) => setItems(Array.isArray(d) ? d : []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">作业 / 考试</h1>
        <Link href="/homework/new">
          <Button>+ 下发作业</Button>
        </Link>
      </div>

      {error && <ErrorBox message={error} />}
      {loading ? (
        <Loading />
      ) : items.length === 0 ? (
        <Empty
          text="还没有下发过作业"
          action={
            <Link href="/homework/new">
              <Button>去下发</Button>
            </Link>
          }
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {items.map((h) => (
            <Link key={h.id} href={`/homework/${h.id}`}>
              <Card className="p-4 transition hover:border-primary">
                <div className="mb-1 flex items-center gap-2">
                  <span className="font-medium">{h.title}</span>
                  <Badge>{TYPE_LABEL[h.type] ?? h.type}</Badge>
                  <Badge tone={h.status === "graded" ? "success" : "default"}>
                    {h.status === "graded" ? "已批改" : "已下发"}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground">
                  试卷 #{h.paper_id}
                  {h.due_at ? ` · 截止 ${new Date(h.due_at).toLocaleString("zh-CN")}` : ""}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
