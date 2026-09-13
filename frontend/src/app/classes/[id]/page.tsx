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
  Select,
  useToast,
} from "@/components/ui";
import type {
  ClassItem,
  ClassOverview,
  ImportErrorItem,
  RankRow,
  StudentItem,
} from "@/lib/types";

interface StudentRow {
  id: number;
  student_no?: string | null;
  name: string;
  gender?: string | null;
  grade: number;
  phone?: string | null;
  average_score?: number | null;
}

export default function ClassDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const { show, node } = useToast();

  const [cls, setCls] = React.useState<ClassItem | null>(null);
  const [students, setStudents] = React.useState<StudentItem[]>([]);
  const [overview, setOverview] = React.useState<ClassOverview | null>(null);
  const [ranking, setRanking] = React.useState<RankRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const [allStudents, setAllStudents] = React.useState<StudentRow[]>([]);
  const [addId, setAddId] = React.useState("");
  const [newStudent, setNewStudent] = React.useState({ student_no: "", name: "", gender: "男" });

  const reload = React.useCallback(() => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      http.get<ClassItem[]>(`/api/v1/classes/`),
      http.get<StudentItem[]>(`/api/v1/classes/${id}/students`),
      http.get<ClassOverview>(`/api/v1/analytics/classes/${id}/overview`),
      http.get<RankRow[]>(`/api/v1/analytics/classes/${id}/ranking`),
    ])
      .then(([list, stus, ov, rank]) => {
        setCls(list.find((c) => String(c.id) === String(id)) ?? null);
        setStudents(Array.isArray(stus) ? stus : []);
        setOverview(ov);
        setRanking(Array.isArray(rank) ? rank : []);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  React.useEffect(reload, [reload]);

  React.useEffect(() => {
    if (!cls) return;
    http
      .get<StudentRow[]>(`/api/v1/students/?grade=${cls.grade}&limit=200`)
      .then((d) => setAllStudents(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, [cls]);

  async function addExisting() {
    if (!addId) return show("请选择学生", "error");
    try {
      await http.post(`/api/v1/classes/${id}/students/${addId}`, {});
      show("已加入班级", "success");
      setAddId("");
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "添加失败", "error");
    }
  }

  async function createAndAdd() {
    if (!newStudent.student_no.trim() || !newStudent.name.trim())
      return show("学号和姓名必填", "error");
    try {
      await http.post("/api/v1/students/", {
        student_no: newStudent.student_no.trim(),
        name: newStudent.name.trim(),
        gender: newStudent.gender,
        grade: cls?.grade ?? 7,
        class_id: Number(id),
      });
      show("已新建并加入班级", "success");
      setNewStudent({ student_no: "", name: "", gender: "男" });
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "创建失败", "error");
    }
  }

  async function importExcel(file: File) {
    try {
      const r = await http.upload<{
        created: number;
        updated: number;
        errors: ImportErrorItem[];
      }>(
        `/api/v1/students/import?class_id=${id}`,
        file,
      );
      show(`导入完成：新增 ${r.created}，更新 ${r.updated}，错误 ${r.errors.length}`, r.errors.length ? "error" : "success");
      if (r.errors.length) console.warn(r.errors);
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "导入失败", "error");
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;

  const notInClass = allStudents.filter(
    (s) => !students.some((cs) => String(cs.student_id) === String(s.id)),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{cls?.name ?? `班级 #${id}`}</h1>
          <p className="text-sm text-muted-foreground">
            {cls ? `${cls.grade} 年级 · ${cls.semester}册` : ""} · {students.length} 名学生
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => http.download("/api/v1/students/template", "students_template.xlsx")}
          >
            下载学生模板
          </Button>
        </div>
      </div>

      {/* 学情概览 */}
      {overview && (
        <div className="grid gap-3 md:grid-cols-4">
          <StatCard label="学生数" value={overview.student_count} />
          <StatCard label="作业次数" value={overview.total_homework ?? 0} />
          <StatCard
            label="平均分"
            value={overview.avg_score != null ? overview.avg_score.toFixed(1) : "-"}
          />
          <StatCard
            label="最高 / 最低"
            value={
              overview.max_score != null
                ? `${overview.max_score.toFixed(0)} / ${overview.min_score?.toFixed(0) ?? "-"}`
                : "-"
            }
          />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>学生名单</CardTitle>
            </CardHeader>
            <CardContent>
              {students.length === 0 ? (
                <Empty text="班级还没有学生，从右侧添加或 Excel 导入" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2">学号</th>
                        <th className="py-2">姓名</th>
                        <th className="py-2">性别</th>
                        <th className="py-2">联系电话</th>
                        <th className="py-2 text-right">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {students.map((s) => (
                        <tr key={s.student_id} className="border-b border-border last:border-0">
                          <td className="py-2">{s.student_no ?? "-"}</td>
                          <td className="py-2 font-medium">{s.name}</td>
                          <td className="py-2">{s.gender ?? "-"}</td>
                          <td className="py-2">{s.phone ?? "-"}</td>
                          <td className="py-2 text-right">
                            <Link
                              href={`/analytics/students/${s.student_id}`}
                              className="text-blue-600 hover:underline"
                            >
                              学情
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {ranking.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>班级排行（按累计成绩）</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {ranking.slice(0, 20).map((r) => (
                    <div key={`${r.student_id}-${r.rank}`} className="flex items-center gap-3 rounded px-2 py-1.5 text-sm hover:bg-accent/50">
                      <span className="w-6 text-muted-foreground">{r.rank}</span>
                      <span className="flex-1">{r.name}</span>
                      <span className="text-xs text-muted-foreground">{r.student_no}</span>
                      <Badge tone={r.percentage != null && r.percentage >= 80 ? "success" : r.percentage != null && r.percentage >= 60 ? "warning" : "danger"}>
                        {r.total_score?.toFixed(0) ?? "-"}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>添加已有学生</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Select value={addId} onChange={(e) => setAddId(e.target.value)}>
                <option value="">选择学生（{notInClass.length} 人可选）</option>
                {notInClass.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.student_no} · {s.name}
                  </option>
                ))}
              </Select>
              <Button className="w-full" variant="outline" onClick={addExisting}>
                加入班级
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>新建学生并加入</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Input
                placeholder="学号"
                value={newStudent.student_no}
                onChange={(e) => setNewStudent({ ...newStudent, student_no: e.target.value })}
              />
              <Input
                placeholder="姓名"
                value={newStudent.name}
                onChange={(e) => setNewStudent({ ...newStudent, name: e.target.value })}
              />
              <Select
                value={newStudent.gender}
                onChange={(e) => setNewStudent({ ...newStudent, gender: e.target.value })}
              >
                <option value="男">男</option>
                <option value="女">女</option>
              </Select>
              <Button className="w-full" variant="outline" onClick={createAndAdd}>
                创建并加入
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Excel 批量导入</CardTitle>
            </CardHeader>
            <CardContent>
              <Label>选择 .xlsx（需含 学号 / 姓名 / 年级 列）</Label>
              <input
                type="file"
                accept=".xlsx,.xls"
                className="w-full text-sm"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) importExcel(f);
                  e.target.value = "";
                }}
              />
              <p className="mt-2 text-xs text-muted-foreground">
                导入后需手动把学生加入本班（右侧「添加已有学生」）
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      {node}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
    </Card>
  );
}
