"use client";

import * as React from "react";
import Link from "next/link";
import { http } from "@/lib/api";
import { Badge, Card, Empty, ErrorBox, Loading } from "@/components/ui";
import type { ClassItem, ClassOverview } from "@/lib/types";

interface Row extends ClassItem {
  overview?: ClassOverview | null;
}

export default function AnalyticsPage() {
  const [rows, setRows] = React.useState<Row[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let alive = true;
    http
      .get<ClassItem[]>("/api/v1/classes/")
      .then(async (list) => {
        const classes = Array.isArray(list) ? list : [];
        const withOv: Row[] = await Promise.all(
          classes.map(async (c) => {
            const ov = await http
              .get<ClassOverview>(`/api/v1/analytics/classes/${c.id}/overview`)
              .catch(() => null);
            return { ...c, overview: ov };
          }),
        );
        if (alive) setRows(withOv);
      })
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">学情分析</h1>
      <p className="text-sm text-muted-foreground">
        按班级查看整体学情，进入班级后可点学生姓名查看个人薄弱点与针对性练习。
      </p>

      {error && <ErrorBox message={error} />}
      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <Empty text="还没有班级，请先到「班级」页创建" />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {rows.map((c) => (
            <Link key={c.id} href={`/classes/${c.id}`}>
              <Card className="p-4 transition hover:border-primary">
                <div className="mb-2 flex items-center gap-2">
                  <span className="font-medium">{c.name}</span>
                  <Badge>{c.grade} 年级</Badge>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <Stat label="学生" value={c.overview?.student_count ?? 0} />
                  <Stat label="作业数" value={c.overview?.total_homework ?? 0} />
                  <Stat
                    label="平均分"
                    value={c.overview?.avg_score != null ? c.overview.avg_score.toFixed(1) : "-"}
                  />
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md bg-muted/50 p-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-bold">{value}</div>
    </div>
  );
}
