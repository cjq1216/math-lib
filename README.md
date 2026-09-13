# 数学题库与学情分析系统

面向培训机构数学教研组的本地化题库、智能组卷与学情分析系统。

> 当前状态：R0 本地运行基线已完成，下一阶段为 R1 认证、授权与 API 契约。用户本地没有 Docker，项目默认使用后端 venv + Uvicorn 和前端 Next.js 运行；Docker 配置仅作为未来部署能力，不阻塞迭代。

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
- 智能组卷、LLM 任务和学情聚合的初步实现。

尚未达到最终 MVP 验收状态：

- JWT 已签发，但业务接口认证授权和对象级数据隔离尚待 R1；
- 每题成绩模型和学情分析闭环尚待 R2；
- 智能组卷尚不能保证全部硬约束；
- Markdown/Word 导出仍是占位；
- 媒体资源尚未与题目形成完整关联；
- Docker 实际构建未验证，但不影响本地开发和 R1 推进；
- PRD 完整验收集尚未执行。

完整证据和修复顺序：

- [项目接管调研报告](docs/AUDIT_REPORT.md)
- [优化修复迭代计划](docs/REMEDIATION_PLAN.md)

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+、FastAPI、SQLModel、Alembic |
| 数据库 | SQLite；向量能力规划使用 sqlite-vec |
| 认证 | JWT，后续完成对象级授权和 refresh 策略 |
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
npm run build
```

当前结果：

- Alembic 空库升级通过；
- 后端回归测试 2 项通过；
- 后端实际服务和核心 API smoke 通过；
- development 模式空库自动迁移通过；
- 前端类型检查和生产构建通过。

已知验证缺口：

- Docker 镜像和 Compose 尚未实际构建；该项为未来部署验证，不阻塞本地迭代；
- `npm run lint` 尚不可用于 CI；
- PRD 完整业务验收尚未执行。

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
