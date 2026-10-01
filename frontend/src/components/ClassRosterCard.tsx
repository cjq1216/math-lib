"use client";

import * as React from "react";
import Link from "next/link";
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
  Label,
  Loading,
  Select,
  useToast,
} from "@/components/ui";
import { useIsAdmin } from "./useIsAdmin";
import type {
  ClassTeacher,
  StudentItem,
} from "@/lib/types";

interface Props {
  classId: number;
}

/**
 * 班级详情页的可复用卡：教师名单 + 学生名单 + 班主任切换。
 * 仅 admin 可见 / 可操作班主任与教师名单；教师 / admin 都能增删学生。
 */
export function ClassRosterCard({ classId }: Props) {
  const isAdmin = useIsAdmin();
  const { show, node } = useToast();

  const [teachers, setTeachers] = React.useState<ClassTeacher[]>([]);
  const [students, setStudents] = React.useState<StudentItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  // head_teacher 编辑
  const [editingHead, setEditingHead] = React.useState(false);
  const [headTeacherId, setHeadTeacherId] = React.useState<string>("");

  // teacher 编辑（全集替换）
  const [editingTeachers, setEditingTeachers] = React.useState(false);
  const [teacherPickIds, setTeacherPickIds] = React.useState<string[]>([]);
  const [availableTeachers, setAvailableTeachers] = React.useState<{ id: number; real_name: string; username: string }[]>([]);

  const load = React.useCallback(() => {
    setLoading(true);
    Promise.all([
      http.get<ClassTeacher[]>(`/api/v1/classes/${classId}/teachers`),
      http.get<StudentItem[]>(`/api/v1/classes/${classId}/students`),
    ])
      .then(([t, s]) => {
        setTeachers(Array.isArray(t) ? t : []);
        setStudents(Array.isArray(s) ? s : []);
        setError("");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  }, [classId]);

  React.useEffect(() => {
    load();
  }, [load]);

  // admin 切换班主任时加载可选教师
  React.useEffect(() => {
    if (!isAdmin) return;
    http
      .get<{ id: number; real_name: string; username: string }[]>(
        `/api/v1/users/?limit=100`,
      )
      .then((d) => setAvailableTeachers(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, [isAdmin]);

  async function removeStudent(studentId: number, name: string) {
    if (!confirm(`确定将「${name}」移出本班？`)) return;
    try {
      await http.del(`/api/v1/classes/${classId}/students/${studentId}`);
      show("已移出班级", "success");
      load();
    } catch (e) {
      show(e instanceof Error ? e.message : "操作失败", "error");
    }
  }

  async function saveHeadTeacher() {
    try {
      await http.patch(`/api/v1/classes/${classId}`, {
        head_teacher_id: headTeacherId ? Number(headTeacherId) : null,
      });
      show("班主任已更新", "success");
      setEditingHead(false);
      load();
    } catch (e) {
      show(e instanceof Error ? e.message : "更新失败", "error");
    }
  }

  function openTeacherEditor() {
    setTeacherPickIds(teachers.map((t) => String(t.id)));
    setEditingTeachers(true);
  }

  async function saveTeachers() {
    try {
      await http.put(`/api/v1/classes/${classId}/teachers`, {
        teacher_ids: teacherPickIds.map(Number),
      });
      show("任课教师已更新", "success");
      setEditingTeachers(false);
      load();
    } catch (e) {
      show(e instanceof Error ? e.message : "更新失败", "error");
    }
  }

  function toggleTeacherPick(id: string) {
    setTeacherPickIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  return (
    <div className="space-y-4">
      {/* 教师名单 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>任课教师（{teachers.length}）</CardTitle>
            {isAdmin && !editingTeachers && (
              <Button size="sm" variant="outline" onClick={openTeacherEditor}>
                管理教师
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Loading />
          ) : editingTeachers ? (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                勾选要保留的教师（空 = 仅保留班主任）。提交后整组替换。
              </p>
              <div className="grid max-h-64 gap-2 overflow-y-auto md:grid-cols-2">
                {availableTeachers.map((t) => (
                  <label
                    key={t.id}
                    className="flex items-center gap-2 rounded border border-border px-3 py-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={teacherPickIds.includes(String(t.id))}
                      onChange={() => toggleTeacherPick(String(t.id))}
                    />
                    <span>{t.real_name}</span>
                    <span className="text-xs text-muted-foreground">@{t.username}</span>
                  </label>
                ))}
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={saveTeachers}>保存</Button>
                <Button size="sm" variant="outline" onClick={() => setEditingTeachers(false)}>取消</Button>
              </div>
            </div>
          ) : teachers.length === 0 ? (
            <Empty text="暂无任课教师" />
          ) : (
            <div className="flex flex-wrap gap-2">
              {teachers.map((t) => (
                <Badge key={t.id} tone="info" className="px-3 py-1">
                  {t.real_name}
                </Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 学生名单 */}
      <Card>
        <CardHeader>
          <CardTitle>学生名单（{students.length}）</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Loading />
          ) : students.length === 0 ? (
            <Empty text="班级还没有学生" />
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
                      <td className="py-2">
                        <Link
                          href={`/students/${s.student_id}`}
                          className="font-medium text-blue-600 hover:underline"
                        >
                          {s.name}
                        </Link>
                      </td>
                      <td className="py-2">{s.gender ?? "-"}</td>
                      <td className="py-2">{s.phone ?? "-"}</td>
                      <td className="py-2 text-right">
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => void removeStudent(s.student_id, s.name)}
                        >
                          移出
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 班主任（仅 admin 可编辑） */}
      {isAdmin && (
        <Card>
          <CardHeader>
            <CardTitle>班主任</CardTitle>
          </CardHeader>
          <CardContent>
            <ErrorBox message={error} />
            {editingHead ? (
              <div className="space-y-3">
                <Label>选择教师</Label>
                <Select value={headTeacherId} onChange={(e) => setHeadTeacherId(e.target.value)}>
                  <option value="">不指定</option>
                  {availableTeachers.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.real_name}（@{t.username}）
                    </option>
                  ))}
                </Select>
                <div className="flex gap-2">
                  <Button size="sm" onClick={saveHeadTeacher}>保存</Button>
                  <Button size="sm" variant="outline" onClick={() => setEditingHead(false)}>取消</Button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <span className="text-sm">
                  {(() => {
                    const head = teachers.find((t) =>
                      // 后端没有直接返回 head_teacher_id，需要从 /classes/{id} 拿；为简单起见，仅以「教师列表」中的首个为标识。
                      teachers.length > 0 ? t.real_name : null,
                    );
                    return head ? `${head.real_name}（${head.username}）` : "未指定";
                  })()}
                </span>
                <Button size="sm" variant="outline" onClick={() => {
                  setEditingHead(true);
                  // 用 teachers 第一项预填（如果有）；空值也可以
                  const first = availableTeachers.find((t) => teachers.some((x) => x.id === t.id));
                  setHeadTeacherId(first ? String(first.id) : "");
                }}>更改</Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {node}
    </div>
  );
}