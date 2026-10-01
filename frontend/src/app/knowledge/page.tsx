"use client";

import * as React from "react";
import { http } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Loading,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import type { KnowledgePoint } from "@/lib/types";

export default function KnowledgePage() {
  const { show, node } = useToast();
  const [tree, setTree] = React.useState<KnowledgePoint[]>([]);
  const [flat, setFlat] = React.useState<KnowledgePoint[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [selected, setSelected] = React.useState<KnowledgePoint | null>(null);
  const [selectedGrade, setSelectedGrade] = React.useState<number | null>(null);

  // 新建表单
  const [form, setForm] = React.useState({
    code: "",
    name: "",
    grade: 7,
    semester: "",
    chapter: "",
    section: "",
    parent_id: "" as string,
    display_order: 0,
  });

  // 编辑表单
  const [editForm, setEditForm] = React.useState<{
    name: string;
    code: string;
    grade: number;
    semester: string;
    chapter: string;
    section: string;
    parent_id: string;
    display_order: number;
  } | null>(null);
  const [migrationTargetId, setMigrationTargetId] = React.useState<string>("");
  const [deleting, setDeleting] = React.useState(false);

  const [importText, setImportText] = React.useState("");
  const [importing, setImporting] = React.useState(false);

  const reload = React.useCallback(() => {
    setLoading(true);
    const treeParams = selectedGrade ? `?grade=${selectedGrade}` : "";
    Promise.all([
      http.get<KnowledgePoint[]>(`/api/v1/knowledge/tree${treeParams}`),
      http.get<KnowledgePoint[]>("/api/v1/knowledge/?include_inactive=true"),
    ])
      .then(([t, f]) => {
        setTree(t);
        setFlat(f);
        if (selected) {
          const fresh = f.find((k) => k.id === selected.id);
          if (fresh) setSelected(fresh);
        }
      })
      .catch((e) => show(e.message, "error"))
      .finally(() => setLoading(false));
  }, [show, selectedGrade, selected]);

  React.useEffect(reload, [reload]);

  // 当选择节点变化时，填充编辑表单
  React.useEffect(() => {
    if (selected) {
      setEditForm({
        name: selected.name,
        code: selected.code || "",
        grade: selected.grade || 7,
        semester: selected.semester || "",
        chapter: selected.chapter || "",
        section: selected.section || "",
        parent_id: selected.parent_id ? String(selected.parent_id) : "",
        display_order: selected.display_order || 0,
      });
      setMigrationTargetId("");
    } else {
      setEditForm(null);
    }
  }, [selected]);

  async function create() {
    if (!form.code.trim() || !form.name.trim()) return show("编码和名称必填", "error");
    try {
      await http.post("/api/v1/knowledge/", {
        code: form.code.trim(),
        name: form.name.trim(),
        grade: Number(form.grade),
        semester: form.semester || null,
        chapter: form.chapter || null,
        section: form.section || null,
        parent_id: form.parent_id ? Number(form.parent_id) : null,
        display_order: Number(form.display_order) || 0,
      });
      show("已创建知识点", "success");
      setForm({
        code: "",
        name: "",
        grade: form.grade,
        semester: "",
        chapter: "",
        section: "",
        parent_id: "",
        display_order: 0,
      });
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "创建失败", "error");
    }
  }

  async function saveEdit() {
    if (!selected || !editForm) return;
    try {
      await http.patch(`/api/v1/knowledge/${selected.id}`, {
        name: editForm.name.trim(),
        code: editForm.code.trim(),
        grade: Number(editForm.grade),
        semester: editForm.semester || null,
        chapter: editForm.chapter || null,
        section: editForm.section || null,
        parent_id: editForm.parent_id ? Number(editForm.parent_id) : null,
        display_order: Number(editForm.display_order) || 0,
      });
      show("知识点更新成功", "success");
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "更新失败", "error");
    }
  }

  async function deleteKp() {
    if (!selected) return;
    setDeleting(true);
    try {
      const url = migrationTargetId
        ? `/api/v1/knowledge/${selected.id}?target_kp_id=${migrationTargetId}`
        : `/api/v1/knowledge/${selected.id}`;
      await http.del(url);
      show(migrationTargetId ? "知识点已迁移关联并删除" : "知识点已软删", "success");
      setSelected(null);
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "删除失败", "error");
    } finally {
      setDeleting(false);
    }
  }

  async function restoreKp() {
    if (!selected) return;
    try {
      await http.post(`/api/v1/knowledge/${selected.id}/restore`);
      show("知识点已恢复", "success");
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "恢复失败", "error");
    }
  }

  async function exportJson() {
    try {
      const data = await http.get<unknown[]>("/api/v1/knowledge/export");
      const jsonStr = JSON.stringify(data, null, 2);
      const blob = new Blob([jsonStr], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `knowledge_points_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      show("知识点体系导出成功", "success");
    } catch (e) {
      show(e instanceof Error ? e.message : "导出失败", "error");
    }
  }

  async function doImport() {
    let items: Record<string, unknown>[];
    try {
      const parsed = JSON.parse(importText);
      items = Array.isArray(parsed) ? parsed : [parsed];
    } catch {
      return show("JSON 解析失败，请检查格式", "error");
    }
    if (items.length === 0) return show("没有可导入的数据", "error");

    setImporting(true);
    try {
      const formatted = items.map((it) => ({
        code: String(it.code),
        name: String(it.name),
        grade: it.grade ? Number(it.grade) : null,
        semester: it.semester ? String(it.semester) : null,
        chapter: it.chapter ? String(it.chapter) : null,
        section: it.section ? String(it.section) : null,
        parent_code: it.parent_code ? String(it.parent_code) : null,
        parent_id: it.parent_id ? Number(it.parent_id) : null,
        display_order: it.display_order ? Number(it.display_order) : 0,
      }));
      const res = await http.post<{ count: number }>("/api/v1/knowledge/import", { items: formatted });
      show(`成功导入 ${res.count} 个知识点，自动建立层级关联`, "success");
      setImportText("");
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "导入失败", "error");
    } finally {
      setImporting(false);
    }
  }

  // 可供选择的父节点（排除自身，避免前端直接选择自身）
  const candidateParents = flat.filter((k) => k.is_active && (!selected || k.id !== selected.id));

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">知识点管理</h1>
            <div className="flex rounded-md border border-border bg-muted/40 p-0.5 text-xs">
              <button
                className={`rounded px-2.5 py-1 ${selectedGrade === null ? "bg-background font-medium shadow-sm" : "hover:text-foreground text-muted-foreground"}`}
                onClick={() => setSelectedGrade(null)}
              >
                全部年级
              </button>
              {[7, 8, 9].map((g) => (
                <button
                  key={g}
                  className={`rounded px-2.5 py-1 ${selectedGrade === g ? "bg-background font-medium shadow-sm" : "hover:text-foreground text-muted-foreground"}`}
                  onClick={() => setSelectedGrade(g)}
                >
                  {g} 年级
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={exportJson}>
              导出 JSON
            </Button>
            <Button variant="outline" size="sm" onClick={reload}>
              刷新
            </Button>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>
              知识点树结构（共 {flat.filter((k) => k.is_active).length} 个活跃节点）
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Loading />
            ) : tree.length === 0 ? (
              <div className="py-8 text-center">
                <p className="mb-3 text-sm text-muted-foreground">
                  当前筛选条件下无知识点。知识点体系是组卷与学情分析的地基，建议先录入或批量导入。
                </p>
              </div>
            ) : (
              <div className="space-y-1">
                {tree.map((n) => (
                  <KpNode key={n.id} node={n} depth={0} selected={selected} onSelect={setSelected} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 右侧面板：选中节点操作、新建与导入 */}
      <div className="space-y-4">
        {selected && editForm ? (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div className="flex items-center gap-2">
                <CardTitle>编辑知识点 #{selected.id}</CardTitle>
                <Badge tone={selected.is_active ? "success" : "danger"}>
                  {selected.is_active ? "正常" : "已停用"}
                </Badge>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>
                关闭
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>编码</Label>
                  <Input
                    value={editForm.code}
                    onChange={(e) => setEditForm({ ...editForm, code: e.target.value })}
                  />
                </div>
                <div>
                  <Label>名称</Label>
                  <Input
                    value={editForm.name}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>年级</Label>
                  <Select
                    value={editForm.grade}
                    onChange={(e) => setEditForm({ ...editForm, grade: Number(e.target.value) })}
                  >
                    {[7, 8, 9].map((g) => (
                      <option key={g} value={g}>
                        {g} 年级
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <Label>学期</Label>
                  <Select
                    value={editForm.semester}
                    onChange={(e) => setEditForm({ ...editForm, semester: e.target.value })}
                  >
                    <option value="">未指定</option>
                    <option value="上">上册</option>
                    <option value="下">下册</option>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>章</Label>
                  <Input
                    placeholder="如：第一章"
                    value={editForm.chapter}
                    onChange={(e) => setEditForm({ ...editForm, chapter: e.target.value })}
                  />
                </div>
                <div>
                  <Label>排序权重</Label>
                  <Input
                    type="number"
                    value={editForm.display_order}
                    onChange={(e) => setEditForm({ ...editForm, display_order: Number(e.target.value) || 0 })}
                  />
                </div>
              </div>

              <div>
                <Label>父知识点（留空为顶级）</Label>
                <Select
                  value={editForm.parent_id}
                  onChange={(e) => setEditForm({ ...editForm, parent_id: e.target.value })}
                >
                  <option value="">（顶级）</option>
                  {candidateParents.map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.code ? `[${k.code}] ` : ""}{k.name}
                    </option>
                  ))}
                </Select>
              </div>

              <div className="flex gap-2 pt-2">
                <Button className="flex-1" onClick={saveEdit}>
                  保存修改
                </Button>
                {!selected.is_active && (
                  <Button variant="outline" onClick={restoreKp}>
                    恢复节点
                  </Button>
                )}
              </div>

              {/* 删除与迁移保护区块 */}
              {selected.is_active && (
                <div className="rounded-md border border-red-200 bg-red-50/50 p-3 text-xs dark:border-red-900/50 dark:bg-red-950/20">
                  <div className="font-medium text-red-800 dark:text-red-400">删除保护与引用迁移</div>
                  <p className="mt-1 text-muted-foreground">
                    若该知识点仍被题目使用，直接删除将被拒绝。您可在下方指定目标知识点将关联迁移后再软删：
                  </p>
                  <div className="mt-2 space-y-2">
                    <Select
                      value={migrationTargetId}
                      onChange={(e) => setMigrationTargetId(e.target.value)}
                    >
                      <option value="">不迁移（若被题目引用将直接报错拦截）</option>
                      {candidateParents.map((k) => (
                        <option key={k.id} value={k.id}>
                          迁移题目至: {k.name} ({k.code})
                        </option>
                      ))}
                    </Select>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full text-red-600 hover:bg-red-100 hover:text-red-700"
                      disabled={deleting}
                      onClick={deleteKp}
                    >
                      {deleting ? "处理中..." : migrationTargetId ? "迁移题目关联并软删" : "确认软删知识点"}
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>新增知识点</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>编码</Label>
                  <Input
                    value={form.code}
                    onChange={(e) => setForm({ ...form, code: e.target.value })}
                    placeholder="G7-S1-01"
                  />
                </div>
                <div>
                  <Label>名称</Label>
                  <Input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="有理数运算"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>年级</Label>
                  <Select
                    value={form.grade}
                    onChange={(e) => setForm({ ...form, grade: Number(e.target.value) })}
                  >
                    {[7, 8, 9].map((g) => (
                      <option key={g} value={g}>
                        {g} 年级
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <Label>学期</Label>
                  <Select
                    value={form.semester}
                    onChange={(e) => setForm({ ...form, semester: e.target.value })}
                  >
                    <option value="">未指定</option>
                    <option value="上">上册</option>
                    <option value="下">下册</option>
                  </Select>
                </div>
              </div>
              <div>
                <Label>父知识点（留空为顶级）</Label>
                <Select
                  value={form.parent_id}
                  onChange={(e) => setForm({ ...form, parent_id: e.target.value })}
                >
                  <option value="">（顶级）</option>
                  {candidateParents.map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.code ? `[${k.code}] ` : ""}{k.name}
                    </option>
                  ))}
                </Select>
              </div>
              <Button className="w-full" onClick={create}>
                创建知识点
              </Button>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>批量导入（JSON）</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-muted-foreground">
              格式：<code>{'[{"code":"G7-S1-01","name":"有理数","grade":7,"parent_code":"G7-S1"}]'}</code>
              <br />
              支持 <code>parent_code</code> 跨环境自动建立父子层级，一次请求全量校验入库。
            </p>
            <Textarea
              className="min-h-[140px] font-mono text-xs"
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder='[{"code":"G7-S1","name":"有理数","grade":7}]'
            />
            <Button
              className="w-full"
              onClick={doImport}
              disabled={importing || !importText.trim()}
            >
              {importing ? "导入中..." : "开始批量导入"}
            </Button>
          </CardContent>
        </Card>
      </div>

      {node}
    </div>
  );
}

function KpNode({
  node,
  depth,
  selected,
  onSelect,
}: {
  node: KnowledgePoint;
  depth: number;
  selected: KnowledgePoint | null;
  onSelect: (k: KnowledgePoint) => void;
}) {
  const [open, setOpen] = React.useState(depth < 1);
  const hasChildren = Boolean(node.children?.length);
  const active = selected?.id === node.id;

  return (
    <div>
      <div
        className={
          "flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm transition hover:bg-accent/60 " +
          (active ? "bg-accent font-medium text-accent-foreground" : "")
        }
        style={{ paddingLeft: depth * 16 + 8 }}
        onClick={() => {
          onSelect(node);
          if (hasChildren) setOpen((v) => !v);
        }}
      >
        <span className="w-4 text-xs text-muted-foreground">
          {hasChildren ? (open ? "▾" : "▸") : "·"}
        </span>
        <span className="flex-1 truncate">{node.name}</span>
        {node.code && (
          <span className="font-mono text-xs text-muted-foreground">{node.code}</span>
        )}
        {!node.is_active && (
          <span className="rounded bg-red-100 px-1 text-[10px] text-red-600 dark:bg-red-950 dark:text-red-400">
            已停用
          </span>
        )}
      </div>
      {open &&
        node.children?.map((c) => (
          <KpNode key={c.id} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} />
        ))}
    </div>
  );
}
