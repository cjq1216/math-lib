"use client";

import * as React from "react";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorBox,
  Label,
  Loading,
  useToast,
} from "@/components/ui";
import { http } from "@/lib/api";
import type { ImportSummary } from "@/lib/types";

export default function StudentImportPage() {
  const { show, node } = useToast();
  const [file, setFile] = React.useState<File | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [result, setResult] = React.useState<ImportSummary | null>(null);
  const [error, setError] = React.useState("");

  async function upload() {
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const r = await http.upload<ImportSummary>("/api/v1/students/import", file);
      setResult(r);
      show(`导入完成：新增 ${r.created}，更新 ${r.updated}，错误 ${r.errors.length}`, r.errors.length ? "error" : "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : "导入失败");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-bold">批量导入学生</h1>

      <Card>
          <CardHeader>
            <CardTitle>操作</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              下载模板，按列填写后上传。表头至少需包含：学号 / 姓名 / 年级。
              本页导入不会自动加入任何班级，导入后可到班级详情页把学生加入。
            </p>
            <div>
              <Button
                variant="outline"
                onClick={() => http.download("/api/v1/students/template", "students_template.xlsx")}
              >
                下载学生模板
              </Button>
            </div>
            <div className="space-y-2">
              <Label htmlFor="xlsx">选择 .xlsx 文件</Label>
              <input
                id="xlsx"
                type="file"
                accept=".xlsx,.xls"
                className="w-full text-sm"
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null;
                  setFile(f);
                  setResult(null);
                  setError("");
                }}
              />
              {file && <p className="text-xs text-muted-foreground">已选择：{file.name}</p>}
            </div>
            <div className="flex gap-2">
              <Button onClick={upload} disabled={!file || uploading}>
                {uploading ? "上传中..." : "上传"}
              </Button>
              {result && (
                <Button variant="outline" onClick={() => { setFile(null); setResult(null); setError(""); }}>
                  清空
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

      {error && <ErrorBox message={error} />}

      {uploading && <Loading />}

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>导入结果</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-4 text-sm">
              <span className="text-emerald-600">新增 {result.created}</span>
              <span className="text-blue-600">更新 {result.updated}</span>
              <span className={result.errors.length ? "text-red-600" : "text-muted-foreground"}>
                错误 {result.errors.length}
              </span>
            </div>
            {result.errors.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="py-2">行</th>
                      <th className="py-2">列</th>
                      <th className="py-2">错误码</th>
                      <th className="py-2">说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.errors.map((err, i) => (
                      <tr key={i} className="border-b border-border last:border-0">
                        <td className="py-2">{err.row ?? "—"}</td>
                        <td className="py-2">{err.column ?? "—"}</td>
                        <td className="py-2 font-mono text-xs">{err.code}</td>
                        <td className="py-2">{err.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {node}
    </div>
  );
}