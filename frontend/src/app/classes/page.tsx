"use client";

import * as React from "react";
import Link from "next/link";
import { http } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorBox,
  Input,
  Label,
  Loading,
  Select,
  useToast,
} from "@/components/ui";
import type { ClassItem } from "@/lib/types";

export default function ClassesPage() {
  const { show, node } = useToast();
  const [items, setItems] = React.useState<ClassItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [form, setForm] = React.useState({ name: "", grade: 7, semester: "上" });

  const load = React.useCallback(() => {
    setLoading(true);
    http
      .get<ClassItem[]>("/api/v1/classes/")
      .then((d) => setItems(Array.isArray(d) ? d : []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(load, [load]);

  async function create() {
    if (!form.name.trim()) return show("请输入班级名称", "error");
    try {
      await http.post("/api/v1/classes/", {
        name: form.name.trim(),
        grade: Number(form.grade),
        semester: form.semester,
      });
      show("班级已创建", "success");
      setForm({ ...form, name: "" });
      load();
    } catch (e) {
      show(e instanceof Error ? e.message : "创建失败", "error");
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">班级</h1>

      <Card className="p-4">
        <div className="grid items-end gap-3 md:grid-cols-[1fr_120px_120px_auto]">
          <div>
            <Label>班级名称</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="七(1)班" />
          </div>
          <div>
            <Label>年级</Label>
            <Select value={form.grade} onChange={(e) => setForm({ ...form, grade: Number(e.target.value) })}>
              {[7, 8, 9].map((g) => (
                <option key={g} value={g}>
                  {g} 年级
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>学期</Label>
            <Select value={form.semester} onChange={(e) => setForm({ ...form, semester: e.target.value })}>
              <option value="上">上册</option>
              <option value="下">下册</option>
            </Select>
          </div>
          <Button onClick={create}>+ 建班</Button>
        </div>
      </Card>

      {error && <ErrorBox message={error} />}

      {loading ? (
        <Loading />
      ) : items.length === 0 ? (
        <Empty text="还没有班级" />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {items.map((c) => (
            <Link key={c.id} href={`/classes/${c.id}`}>
              <Card className="p-4 transition hover:border-primary">
                <div className="mb-1 font-medium">{c.name}</div>
                <div className="text-xs text-muted-foreground">
                  <Badge>{c.grade} 年级</Badge> <Badge>{c.semester}册</Badge>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {node}
    </div>
  );
}
