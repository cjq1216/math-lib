import Link from "next/link";

const QUICK = [
  { href: "/questions/new", title: "录题", desc: "LaTeX 题干 + 实时预览 + 知识点关联" },
  { href: "/knowledge", title: "知识点", desc: "树形体系 + JSON 批量导入" },
  { href: "/papers/generate", title: "智能组卷", desc: "题型 / 难度 / 知识点约束" },
  { href: "/classes", title: "班级学生", desc: "建班 + Excel 导入学生" },
  { href: "/homework", title: "作业成绩", desc: "下发 + 单条/Excel 录入" },
  { href: "/analytics", title: "学情分析", desc: "薄弱点定位 + 针对性出题" },
];

const FLOW = [
  { step: 1, title: "导入知识点体系", href: "/knowledge", desc: "组卷和学情分析的地基，建议先做" },
  { step: 2, title: "录入第一批题", href: "/questions/new", desc: "先录 50 道跑通闭环，可用 AI 自动打标" },
  { step: 3, title: "智能组卷", href: "/papers/generate", desc: "配置题型与难度分布，一键生成" },
  { step: 4, title: "建班并下发作业", href: "/classes", desc: "关联班级，下发试卷作为作业" },
  { step: 5, title: "录入成绩", href: "/homework", desc: "单条录入或 Excel 批量，然后重算学情" },
  { step: 6, title: "看薄弱点", href: "/analytics", desc: "定位薄弱知识点，生成针对性练习" },
];

export default function Home() {
  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-3xl font-bold">数学题库与学情分析</h1>
        <p className="mt-2 text-muted-foreground">
          面向培训机构的初中数学教研工具：录题 → 组卷 → 下发 → 录分 → 定位薄弱点 → 针对性练习
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">快捷入口</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {QUICK.map((q) => (
            <Link
              key={q.href}
              href={q.href}
              className="rounded-lg border border-border p-4 transition hover:border-primary"
            >
              <div className="font-semibold">{q.title}</div>
              <div className="mt-1 text-sm text-muted-foreground">{q.desc}</div>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">首次使用流程</h2>
        <ol className="space-y-2">
          {FLOW.map((f) => (
            <li key={f.step} className="flex items-start gap-3">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium">
                {f.step}
              </span>
              <div>
                <Link href={f.href} className="font-medium hover:underline">
                  {f.title}
                </Link>
                <div className="text-sm text-muted-foreground">{f.desc}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
