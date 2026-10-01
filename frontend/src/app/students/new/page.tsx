"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import { http } from "@/lib/api";
import type { ClassItem, StudentCreatePayload } from "@/lib/types";

export default function NewStudentPage() {
  return <NewStudentForm />;
}

function NewStudentForm() {
  const router = useRouter();
  const { show, node } = useToast();

  const [studentNo, setStudentNo] = React.useState("");
  const [name, setName] = React.useState("");
  const [gender, setGender] = React.useState("男");
  const [grade, setGrade] = React.useState(7);
  const [enrollmentYear, setEnrollmentYear] = React.useState<string>(String(new Date().getFullYear()));
  const [phone, setPhone] = React.useState("");
  const [parentPhone, setParentPhone] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [classId, setClassId] = React.useState<string>("");

  const [classes, setClasses] = React.useState<ClassItem[]>([]);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    http
      .get<ClassItem[]>("/api/v1/classes/?is_active=true&limit=100")
      .then((d) => setClasses(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!studentNo.trim()) return show("学号必填", "error");
    if (!name.trim()) return show("姓名必填", "error");
    const payload: StudentCreatePayload = {
      student_no: studentNo.trim(),
      name: name.trim(),
      gender: gender || null,
      grade,
      enrollment_year: enrollmentYear ? Number(enrollmentYear) : null,
      phone: phone.trim() || null,
      parent_phone: parentPhone.trim() || null,
      notes: notes.trim() || null,
      class_id: classId ? Number(classId) : null,
    };
    setSaving(true);
    try {
      const r = await http.post<{ id: number }>("/api/v1/students/", payload);
      show("学生已创建", "success");
      router.push(`/students/${r.id}`);
    } catch (err) {
      show(err instanceof Error ? err.message : "创建失败", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-2xl font-bold">新建学生</h1>
      <form onSubmit={submit}>
        <Card>
          <CardHeader>
            <CardTitle>学生信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <Label htmlFor="stu-no">学号</Label>
                <Input
                  id="stu-no"
                  value={studentNo}
                  onChange={(e) => setStudentNo(e.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor="stu-name">姓名</Label>
                <Input
                  id="stu-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor="stu-gender">性别</Label>
                <Select id="stu-gender" value={gender} onChange={(e) => setGender(e.target.value)}>
                  <option value="男">男</option>
                  <option value="女">女</option>
                </Select>
              </div>
              <div>
                <Label htmlFor="stu-grade">年级</Label>
                <Select id="stu-grade" value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
                  {[7, 8, 9].map((g) => (
                    <option key={g} value={g}>{g} 年级</option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="stu-year">入学年份（可选）</Label>
                <Input
                  id="stu-year"
                  type="number"
                  min={2000}
                  max={2100}
                  value={enrollmentYear}
                  onChange={(e) => setEnrollmentYear(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="stu-class">加入班级（可选）</Label>
                <Select id="stu-class" value={classId} onChange={(e) => setClassId(e.target.value)}>
                  <option value="">暂不加入</option>
                  {classes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.grade} 年级 · {c.name}（{c.semester}册）
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="stu-phone">联系电话（可选）</Label>
                <Input
                  id="stu-phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="stu-parent">家长电话（可选）</Label>
                <Input
                  id="stu-parent"
                  value={parentPhone}
                  onChange={(e) => setParentPhone(e.target.value)}
                />
              </div>
            </div>
            <div>
              <Label htmlFor="stu-notes">备注（可选）</Label>
              <Textarea
                id="stu-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>
          </CardContent>
        </Card>
        <div className="mt-4 flex items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => router.push("/students")}>
            取消
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "创建中..." : "创建"}
          </Button>
        </div>
      </form>
      {node}
    </div>
  );
}