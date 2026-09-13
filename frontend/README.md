# 前端开发说明

Next.js 前端，提供题库、知识点、组卷、班级学生、作业成绩和学情分析界面。

> 当前状态：R1 会话恢复、401 自动刷新、业务页面守护和 ESLint 已完成；完整题目聚合编辑、每题成绩、真实导出等后续闭环仍待 R2-R4 实现。

## 技术栈

- Next.js 15 App Router
- React 19
- TypeScript strict mode
- Tailwind CSS 3
- KaTeX
- 原生 Fetch 封装

依赖中包含但当前未使用：

- `@tanstack/react-query`
- `zustand`

修复期不引入第二套状态管理模式。若继续使用当前页面级状态，应删除未使用依赖；若决定引入 React Query，应统一迁移数据请求和缓存，不保留两套并行约定。

## 目录结构

```text
frontend/
├── src/
│   ├── app/
│   │   ├── login/                   # 登录
│   │   ├── questions/               # 题库和题目编辑
│   │   ├── knowledge/               # 知识点树
│   │   ├── papers/                  # 试卷和智能组卷
│   │   ├── classes/                 # 班级学生
│   │   ├── homework/                # 作业和成绩录入
│   │   └── analytics/               # 学情分析
│   ├── components/
│   │   ├── AppShell.tsx             # 全局导航
│   │   ├── QuestionEditor.tsx       # 题目编辑器
│   │   ├── MathText.tsx             # KaTeX 渲染
│   │   └── ui.tsx                   # 轻量 UI 组件
│   └── lib/
│       ├── api.ts                   # API 客户端
│       └── types.ts                 # 共享前端类型
├── next.config.ts
├── package.json
├── tailwind.config.ts
└── Dockerfile
```

## 页面路由

| 页面 | 路径 | 当前能力 |
|---|---|---|
| 首页 | `/` | 使用引导 |
| 登录 | `/login` | 用户名密码登录 |
| 题库列表 | `/questions` | 关键词、题型、难度、知识点筛选 |
| 新建题目 | `/questions/new` | 题干、公式预览、选项、答案、知识点、小问 |
| 编辑题目 | `/questions/[id]/edit` | 加载并编辑题目 |
| 知识点 | `/knowledge` | 树展示、创建、JSON 导入 |
| 试卷列表 | `/papers` | 列出试卷 |
| 智能组卷 | `/papers/generate` | 题型、难度和知识点约束 |
| 试卷详情 | `/papers/[id]` | 预览、发布、导出入口 |
| 班级 | `/classes` | 列表和创建 |
| 班级详情 | `/classes/[id]` | 学生关联和 Excel 导入 |
| 作业 | `/homework` | 作业列表 |
| 新建作业 | `/homework/new` | 从试卷下发 |
| 作业详情 | `/homework/[id]` | 总分录入和 Excel 导入 |
| 学情入口 | `/analytics` | 学生入口 |
| 学生学情 | `/analytics/students/[id]` | 薄弱点和针对性练习 |

## 安装与运行

```bash
npm install
npm run dev
```

默认地址：`http://localhost:3000`。

生产构建：

```bash
npm run type-check
npm run lint
npm run build
npm start
```

当前验证结果：

- `npm run type-check`：通过；
- `npm run lint`：通过；
- `npm run build`：通过，生成 14 个页面；
- 实际浏览器登录、受保护页面和刷新后会话恢复：通过，控制台无异常。

## 环境变量

复制模板：

Windows：

```bash
copy .env.example .env.local
```

Linux/macOS：

```bash
cp .env.example .env.local
```

变量：

| 变量 | 说明 |
|---|---|
| `NEXT_PUBLIC_API_BASE` | 浏览器直连后端地址；留空时使用同源代理 |
| `API_PROXY_TARGET` | Next.js 服务端代理目标 |

推荐本地配置：

```dotenv
API_PROXY_TARGET=http://localhost:8000
```

容器内应使用服务名：

```dotenv
API_PROXY_TARGET=http://backend:8000
```

浏览器请求统一使用 `/api/v1/*` 相对路径，优先走同源代理。生产环境不要把 `NEXT_PUBLIC_API_BASE` 配置为 `http://localhost:8000`。

## API 客户端

`src/lib/api.ts` 提供：

- `http.get`
- `http.post`
- `http.patch`
- `http.put`
- `http.del`
- `http.upload`
- `http.download`
- `qs`

access token 仅保存在页面进程内存中，refresh token 由后端写入 HttpOnly cookie。并发 401 共用一次 refresh 请求，成功后原请求只重试一次；刷新失败才清理会话并跳转登录。上传和下载也走同一恢复逻辑。

`src/components/AuthProvider.tsx` 启动时通过 refresh 和 `/auth/me` 建立服务端验证的当前用户；`AppShell` 在验证完成前不渲染业务页面，并按真实用户状态执行路由守护。不要在页面中新增第二套认证处理。

要求：

- 页面不直接拼接后端绝对地址；
- 业务错误显示后端结构化消息；
- 文件上传使用 `http.upload`，不要手工设置 multipart Content-Type；
- 文件下载使用 `http.download`；
- 新响应类型先加入 `src/lib/types.ts` 或生成的 API 类型；
- 不允许用 `any` 绕过后端契约漂移。

## 组件约定

### 数学公式

使用 `MathText` 渲染包含 `$...$` 和 `$$...$$` 的文本：

```tsx
<MathText>{question.stem}</MathText>
```

正文会先进行 HTML 转义，KaTeX 输出再回填。不要在业务页面自行使用 `dangerouslySetInnerHTML`。

### UI

共享基础组件放在 `src/components/ui.tsx`。新增通用组件前先复用现有 Button、Card、Input、Select、Textarea、Badge、Loading、ErrorBox 和 Toast。

### 页面数据

当前页面使用 `useEffect` 和本地 state。修复期遵循：

- 请求状态必须覆盖 loading、error、empty 和 success；
- 异步按钮必须防重复提交；
- 导入错误必须在界面显示，不能只写 `console.warn`；
- 批量保存必须返回逐项失败信息；
- 删除和不可逆操作必须明确确认。

## 当前功能缺口

### 认证

R1 已完成：

- 页面不再使用 localStorage/sessionStorage 保存 token；
- `/auth/me` 是当前用户和角色的真实来源；
- access 过期后通过 HttpOnly refresh cookie 自动恢复；
- 登录页之外的业务页面均由 `AppShell` 守护；
- 顶部导航显示真实用户和管理员/教师角色，退出会撤销后端会话。

### 题目编辑

- 当前是 Textarea + KaTeX，不是富文本编辑器；
- 没有图片上传和题目媒体排序；
- 没有多空答案和等价规则编辑；
- 题目、知识点和小问通过多个请求保存，可能产生部分成功；
- 没有明确“人工校对完成”操作。

### 组卷

- 生成结果不能手动替换、删除、排序和改单题分值；
- 不可满足约束时缺少结构化说明；
- 重新生成会创建新试卷，缺少草稿策略；
- 导出按钮对应的后端仍是占位。

### 作业与学情

- 作业详情只录总分，没有每题成绩；
- Excel 错误只显示数量，详细信息写入控制台；
- 学情重算通过前端逐学生串行调用；
- 针对性练习不能直接转为新作业；
- 缺少趋势、雷达图和试卷质量分析。

## 近期改造边界

按 `../docs/REMEDIATION_PLAN.md` 执行：

1. R0：只配合后端恢复启动和代理链路；
2. R1：统一认证状态、当前用户和页面保护；
3. R2：重写作业详情为每题成绩录入；
4. R3：完善题目聚合编辑和媒体；
5. R4：支持试卷调整和真实导出；
6. R5：增加 Word 导入校对和可靠任务状态。

不要提前开发 PDF、OCR、几何画板、AI 新题或管理看板。

## 代码质量

现有脚本：

```json
{
  "dev": "next dev",
  "build": "next build",
  "start": "next start",
  "lint": "eslint . --max-warnings=0",
  "type-check": "tsc --noEmit"
}
```

R1 已增加 `eslint.config.mjs` 并将 lint 改为非交互式 ESLint CLI。当前 type-check、lint、build 均通过。

后续仍需删除未使用依赖或完成统一迁移，并在 CI 中固定依次运行 type-check、lint 和 build。

## Docker

Dockerfile 已完成以下修复：

- 使用 `npm ci` 和 lockfile 安装依赖；
- 不再复制不存在的 `public/`；
- 构建阶段注入 `API_PROXY_TARGET=http://backend:8000`；
- 运行时继续使用容器服务名访问后端；
- `.dockerignore` 排除本地依赖和构建产物。

前端已使用容器代理参数完成生产构建。用户本地没有 Docker Engine；镜像与 Compose 仅作为未来部署能力保留，不阻塞本地开发。

## 相关文档

- [项目 Handoff](../docs/HANDOFF.md)
- [项目说明](../README.md)
- [产品需求](../docs/PRD.md)
- [接管调研报告](../docs/AUDIT_REPORT.md)
- [优化修复计划](../docs/REMEDIATION_PLAN.md)
