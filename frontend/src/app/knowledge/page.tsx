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

  // 新建表单
  const [form, setForm] = React.useState({
    code: "",
    name: "",
    grade: 7,
    semester: "",
    chapter: "",
    section: "",
    parent_id: "" as string,
  });

  const [importText, setImportText] = React.useState("");
  const [importing, setImporting] = React.useState(false);

  const reload = React.useCallback(() => {
    setLoading(true);
    Promise.all([
      http.get<KnowledgePoint[]>("/api/v1/knowledge/tree"),
      http.get<KnowledgePoint[]>("/api/v1/knowledge/"),
    ])
      .then(([t, f]) => {
        setTree(t);
        setFlat(f);
      })
      .catch((e) => show(e.message, "error"))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(reload, [reload]);

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
      });
      show("已创建", "success");
      setForm({ code: "", name: "", grade: form.grade, semester: "", chapter: "", section: "", parent_id: "" });
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "创建失败", "error");
    }
  }

  /**
   * 批量导入：支持 [{code, name, grade, chapter, parent_code}]
   * 先全部建为根节点，再按 parent_code 回填 parent_id
   */
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
      for (const it of items) {
        await http.post("/api/v1/knowledge/", {
          code: String(it.code),
          name: String(it.name),
          grade: Number(it.grade ?? 7),
          semester: it.semester ?? null,
          chapter: it.chapter ?? null,
          section: it.section ?? null,
          parent_id: null,
        });
      }
      // 回填父子关系
      const all = await http.get<KnowledgePoint[]>("/api/v1/knowledge/");
      const codeToId = new Map(all.map((k) => [k.code, k.id]));
      let linked = 0;
      for (const it of items) {
        const pc = it.parent_code as string | undefined;
        if (!pc) continue;
        const parentId = codeToId.get(pc);
        const selfId = codeToId.get(String(it.code));
        if (parentId && selfId) {
          await http.patch(`/api/v1/knowledge/${selfId}`, { parent_id: parentId });
          linked++;
        }
      }
      show(`导入完成：${items.length} 个知识点，${linked} 个父子关系`, "success");
      setImportText("");
      reload();
    } catch (e) {
      show(e instanceof Error ? e.message : "导入失败", "error");
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">知识点</h1>
          <Button variant="outline" size="sm" onClick={reload}>
            刷新
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>知识点树（共 {flat.length} 个）</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Loading />
            ) : tree.length === 0 ? (
              <div className="py-8 text-center">
                <p className="mb-3 text-sm text-muted-foreground">
                  还没有知识点。知识点体系是组卷与学情分析的地基，建议先导入。
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

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>新增知识点</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>编码</Label>
                <Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="G7-S1-01" />
              </div>
              <div>
                <Label>名称</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="有理数" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
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
                  <option value="">未指定</option>
                  <option value="上">上册</option>
                  <option value="下">下册</option>
                </Select>
              </div>
            </div>
            <div>
              <Label>父知识点（留空为顶级）</Label>
              <Select value={form.parent_id} onChange={(e) => setForm({ ...form, parent_id: e.target.value })}>
                <option value="">（顶级）</option>
                {flat.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.name}
                  </option>
                ))}
              </Select>
            </div>
            <Button className="w-full" onClick={create}>
              创建
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>批量导入（JSON）</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-muted-foreground">
              格式：[{"{"}"code":"G7-S1-01","name":"有理数","grade":7,"parent_code":"G7-S1"{"}"}]
              <br />
              parent_code 留空表示顶级，导入后自动建立父子关系。
            </p>
            <Textarea
              className="min-h-[160px]"
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder='[{"code":"G7-S1","name":"有理数","grade":7}]'
            />
            <Button className="w-full" onClick={doImport} disabled={importing || !importText.trim()}>
              {importing ? "导入中..." : "开始导入"}
            </Button>
          </CardContent>
        </Card>

        {selected && (
          <Card>
            <CardHeader>
              <CardTitle>已选中</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div>
                <Badge>{selected.code}</Badge> {selected.name}
              </div>
              <div className="text-xs text-muted-foreground">
                ID {selected.id} · 年级 {selected.grade ?? "-"} · 父级 {selected.parent_id ?? "顶级"}
              </div>
            </CardContent>
          </Card>
        )}
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
          "flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-accent/60 " +
          (active ? "bg-accent font-medium" : "")
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
        <span className="flex-1">{node.name}</span>
        {node.code && <span className="text-xs text-muted-foreground">{node.code}</span>}
      </div>
      {open &&
        node.children?.map((c) => (
          <KpNode key={c.id} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} />
        ))}
    </div>
  );
}
