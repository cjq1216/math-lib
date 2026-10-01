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
import { useIsAdmin } from "@/components/useIsAdmin";
import { http } from "@/lib/api";
import type { CurrentUser, UserCreatePayload, UserRole } from "@/lib/types";

export default function NewUserPage() {
  return <NewUserForm />;
}

function NewUserForm() {
  const router = useRouter();
  const isAdmin = useIsAdmin();
  const { show, node } = useToast();
  const [saving, setSaving] = React.useState(false);

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [realName, setRealName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [role, setRole] = React.useState<UserRole>("teacher");
  const [subject, setSubject] = React.useState("");
  const [notes, setNotes] = React.useState("");

  // 非 admin 立即跳走
  React.useEffect(() => {
    if (!isAdmin) router.replace("/");
  }, [isAdmin, router]);

  if (!isAdmin) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || username.trim().length < 3) {
      show("用户名至少 3 个字符", "error");
      return;
    }
    if (password.length < 8) {
      show("密码至少 8 个字符", "error");
      return;
    }
    if (!realName.trim()) {
      show("请填写真实姓名", "error");
      return;
    }

    const payload: UserCreatePayload = {
      username: username.trim(),
      password,
      real_name: realName.trim(),
      email: email.trim() || null,
      phone: phone.trim() || null,
      role,
      subject: subject.trim() || null,
      notes: notes.trim() || null,
    };

    setSaving(true);
    try {
      await http.post<CurrentUser>("/api/v1/users/", payload);
      show("已创建", "success");
      router.push("/users");
    } catch (e) {
      show(e instanceof Error ? e.message : "创建失败", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-2xl font-bold">新建用户</h1>
      <form onSubmit={submit}>
        <Card>
          <CardHeader>
            <CardTitle>账号信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <Label htmlFor="username">用户名</Label>
                <Input
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="3-64 字符"
                  minLength={3}
                  maxLength={64}
                  required
                />
              </div>
              <div>
                <Label htmlFor="password">初始密码</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="至少 8 个字符"
                  minLength={8}
                  required
                />
              </div>
              <div>
                <Label htmlFor="realName">真实姓名</Label>
                <Input
                  id="realName"
                  value={realName}
                  onChange={(e) => setRealName(e.target.value)}
                  maxLength={64}
                  required
                />
              </div>
              <div>
                <Label htmlFor="role">角色</Label>
                <Select
                  id="role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as UserRole)}
                >
                  <option value="teacher">教师</option>
                  <option value="admin">管理员</option>
                </Select>
              </div>
              <div>
                <Label htmlFor="email">邮箱（可选）</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="phone">电话（可选）</Label>
                <Input
                  id="phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  maxLength={20}
                />
              </div>
              <div>
                <Label htmlFor="subject">学科（可选）</Label>
                <Input
                  id="subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  maxLength={64}
                  placeholder="如：数学"
                />
              </div>
            </div>
            <div>
              <Label htmlFor="notes">备注（可选）</Label>
              <Textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="如：负责七年级数学"
              />
            </div>
          </CardContent>
        </Card>

        <div className="mt-4 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.push("/users")}
          >
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