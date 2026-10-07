# 数学题库与学情分析系统

面向培训机构数学教研组的本地化题库、智能组卷与学情分析系统。

> 当前状态：**R0 至 R6 全量迭代修复已全部完成并通过端到端验收**，系统具备完整题库、智能组卷、作业下发、成绩导入、学情分析、Word/PDF 提取切题、纯线上向量检索、SQLite 安全热备份、分层健康探针与灾难恢复能力，进入生产运维就绪状态。
## 项目目标

系统围绕以下业务闭环建设：

```text
题目入库
  → 知识点与难度标注
  → 智能组卷
  → 下发班级作业
  → 录入每题成绩
  → 分析学生/班级学情
  → 根据薄弱知识点生成练习
```

目标用户：

- 机构管理员：管理教师、系统配置和全局数据；
- 教师：维护题库、班级、作业和学情；
- 学生：MVP 不登录，由教师维护信息和作答结果。

## 当前接管结论

已经具备：

- FastAPI、SQLModel、Alembic 后端结构；
- Next.js 15、React 19、Tailwind CSS 前端；
- 题目、知识点、试卷、班级、作业和学情领域模型；
- 主要前端页面和 API 路由骨架；
- KaTeX 公式渲染；
- 智能组卷、LLM 任务和学情聚合的初步实现；
- OAuth2 Bearer access token、HttpOnly refresh cookie 轮换与可撤销会话；
- 管理员/教师角色授权、班级教师关联以及班级/学生对象级隔离；
- 主要 API 的显式 Pydantic 契约、可信操作者注入和审计日志；
- 前端服务端会话验证、受保护页面守护和 401 自动刷新。

已完成全链路闭环能力：

- **R0（运行基线）**：统一同步 SQLModel 会话、解耦 sqlite-vec、平滑 Alembic 迁移、健全目录与启动机制；
- **R1（认证与授权）**：首管理员保护、双轨 Token 会话与轮换、后端对象级数据隔离、AuditLog 审计追踪；
- **R2（成绩与学情）**：正规每题成绩明细 (`homework_question_results`)、名单快照、双版本 Excel 导入与错误定位、加权选题与薄弱点闭环；
- **R3（题库与媒体）**：题目/小问/多空答案聚合写入、Checksum 防重、知识点层级与无环校验、媒体 MD5 去重与引用计数；
- **R4（组卷与导出）**：组卷四步拆分引擎 (`plan`→`generate`→`validate`→`persist`)、硬约束 100% 达标、Markdown 与 Word 快照级完整导出；
- **R5（LLM 与向量）**：Word/矢量 PDF 提取解析引擎、纯线上 LLM/向量架构、任务自愈状态机、双栏切题校对工作台 (`/questions/import`)；
- **R6（运维与灾备）**：SQLite 原生安全热备份 (`sqlite3.backup`)、媒体同步归档、保留策略、原子灾难恢复演练通过、分层健康探针 (`/health/live`, `/health/ready`)、全链路 Request-ID 追踪与敏感数据脱敏过滤器。
完整证据和修复顺序：

- [项目接管调研报告](docs/AUDIT_REPORT.md)
- [优化修复迭代计划](docs/REMEDIATION_PLAN.md)

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+、FastAPI、SQLModel、Alembic |
| 数据库 | SQLite；向量能力规划使用 sqlite-vec |
| 认证 | OAuth2 Bearer access token、HttpOnly refresh cookie、可撤销会话与对象级授权 |
| LLM | MiniMax、Ollama |
| 前端 | Next.js 15、React 19、TypeScript、Tailwind CSS |
| 数学公式 | KaTeX |
| Excel | openpyxl |
| 部署 | Docker Compose |

## 目录结构

```text
math-lib/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/            # HTTP 路由
│   │   ├── core/              # 配置、数据库、安全
│   │   ├── models/            # SQLModel 数据模型
│   │   ├── schemas/           # Pydantic 请求/响应模型
│   │   └── services/          # 组卷、学情、LLM、任务服务
│   ├── alembic/               # 数据库迁移
│   ├── pyproject.toml
│   └── README.md
├── frontend/                   # Next.js 前端
│   ├── src/app/               # App Router 页面
│   ├── src/components/        # 共享组件
│   ├── src/lib/               # API 客户端和共享类型
│   └── README.md
├── docs/
│   ├── PRD.md                 # 产品需求
│   ├── ARCHITECTURE.md        # 原架构设计
│   ├── ROADMAP.md             # 原功能路线图
│   ├── AUDIT_REPORT.md        # 接管调研结论
│   └── REMEDIATION_PLAN.md     # 当前修复执行计划
├── docker-compose.yml
├── start.bat
└── start.sh
```

## 页面与 API

主要前端页面：

| 页面 | 路径 |
|---|---|
| 登录 | `/login` |
| 题库 | `/questions` |
| 新建/编辑题目 | `/questions/new`、`/questions/[id]/edit` |
| 知识点 | `/knowledge` |
| 试卷与智能组卷 | `/papers`、`/papers/generate` |
| 班级与学生 | `/classes`、`/classes/[id]` |
| 作业 | `/homework`、`/homework/[id]` |
| 学情分析 | `/analytics`、`/analytics/students/[id]` |

主要 API 前缀：

| 模块 | 前缀 |
|---|---|
| 认证 | `/api/v1/auth` |
| 用户 | `/api/v1/users` |
| 题目 | `/api/v1/questions` |
| 知识点 | `/api/v1/knowledge` |
| 媒体 | `/api/v1/media` |
| 试卷 | `/api/v1/papers` |
| 班级 | `/api/v1/classes` |
| 学生 | `/api/v1/students` |
| 作业 | `/api/v1/homework` |
| 学情 | `/api/v1/analytics` |
| LLM 任务 | `/api/v1/llm` |

## 本地开发

### 前端

当前前端可以独立完成类型检查和生产构建：

```bash
cd frontend
npm install
npm run type-check
npm run build
npm run dev
```

默认访问：`http://localhost:3000`。

### 后端

后端依赖 Python 3.11+。预期开发命令如下：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Linux/macOS 激活虚拟环境：

```bash
source .venv/bin/activate
```

默认访问：

- API：`http://localhost:8000`
- OpenAPI：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

本地后端已通过空库迁移、实际启动、注册、登录、题目创建/读取和重启持久化验证。

## Docker

规划启动方式：

```bash
docker compose up --build
```

Dockerfile 和 Compose 配置已完成修正。用户本地没有 Docker Engine，因此 Docker 作为可选部署方式保留，不作为开发或迭代验收门槛。

未来在具备 Docker 的部署环境中，应验证：

```text
空数据卷
  → 数据库迁移
  → 后端健康检查
  → 前端启动
  → 注册管理员
  → 登录
  → 创建并读取题目
  → 重启后数据仍存在
```

## 验证状态

已验证：

```bash
cd backend
alembic upgrade head
pytest

cd ../frontend
npm run type-check
npm run lint
npm run build
```

当前结果：

- Alembic 迁移执行到 head（`0006_question_knowledge_unique_and_media_integrity`）；
- 后端测试全量通过：`pytest` 77 项测试 100% 通过（0 失败，0 警告），覆盖全链路业务端到端 (`test_e2e_full_cycle.py`) 与灾备运维演练 (`test_r6_operations_and_backup.py`)；
- 代码规范检查：Ruff 基础检查通过（0 错误）；
- 前端质量：TypeScript 类型检查通过（0 错误）、ESLint 检查通过（0 警告）、生产构建全部 21 个页面成功；
- 生产运维手册：已交付 [部署与运维手册](docs/DEPLOYMENT.md) 与 [备份、保留与灾难恢复手册](docs/BACKUP_RESTORE.md)。
## 文档优先级

发生冲突时按以下顺序执行：

1. [项目 Handoff](docs/HANDOFF.md)
2. [优化修复迭代计划](docs/REMEDIATION_PLAN.md)
3. [项目接管调研报告](docs/AUDIT_REPORT.md)
4. [产品需求文档](docs/PRD.md)
5. [架构设计文档](docs/ARCHITECTURE.md)
6. [原 Roadmap](docs/ROADMAP.md)

Roadmap 中已勾选的项目目前只表示“已有实现痕迹”，必须通过修复计划定义的验收后才视为真正完成。

## 开发原则

- 正确性和数据完整性优先于功能数量；
- 先打通真实业务闭环，再增加 AI、OCR 和看板；
- 不保留占位接口、假成功消息和误导性按钮；
- 数据库变更必须有 Alembic 迁移；
- 认证用户、审计字段和统计字段由服务端产生；
- 每个迭代必须以实际运行场景作为完成证据；
- 题目与已生成试卷继续使用快照隔离历史内容。

## License

MIT
