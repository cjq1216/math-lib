# 项目 Handoff

> 项目：初中数学题库与学情分析系统  
> 交接日期：2026-10-07  
> 当前阶段：R0-R6 全部完成（系统里程碑最终验收通过，生产运维就绪）
> 默认运行方式：Windows 本地开发环境 + Linux/Docker 生产部署模式

---

## 1. 当前结论

R0“恢复可运行基线”、R1“认证、授权与 API 契约”、R2“成绩明细与学情闭环”、R3“题库、知识点与媒体完整性”、R4“智能组卷与导出”、R5“LLM、文档导入与向量检索能力”以及 R6“运维、可观测性与灾备收口”已经全部完成，并通过全量自动化测试、端到端全业务闭环测试以及生产构建验收。

R6 落地并验证了工业级本地化系统的运维自愈与数据安全防线：
- **SQLite 原生安全热备份 (`backup_service.py`)**：采用 `sqlite3.Connection.backup()` 在线热导出 API，并发读写时不产生锁冲突或撕裂，严禁直接 cp 规避损坏风险；
- **媒体目录强一致同步归档**：将本地媒体图片与数据库热快照整合归档进单一 ZIP 包，并写入包含 SHA256 校验和与媒体清单的 `manifest.json`；
- **保留策略与自动巡检**：支持保留天数 (`BACKUP_RETENTION_DAYS`) 与最大备份数 (`BACKUP_MAX_COUNT`)，自动巡检清理历史备份，始终保底保留最新 1 个备份；
- **灾难恢复演练通过**：提供 CLI 命令行 (`python -m app.cli.backup`) 与管理端 API；在单元测试中完成真实数据篡改与媒体删除后的无损原子还原演练，并自动生成恢复前快照 `pre_restore_backup` 兜底；
- **分层健康探针**：存活探针 `/health/live`（极轻量进程自检）与就绪探针 `/health/ready`（检查数据库连接、数据/媒体/日志/备份目录可写状态与延迟，故障时返回 503）；保持 `/health` 综合兼容；
- **全链路追踪与耗时**：挂载 `RequestLoggingMiddleware`，透传或生成 `X-Request-ID`，并在响应头返回 `X-Response-Time-Ms` 毫秒耗时；
- **敏感隐私脱敏**：实现 `sanitize_sensitive_data` 过滤器，严格脱敏 Authorization、Token、Cookie、密码及学生身份证等隐私字段。

后端全量 77 项测试全部通过（0 失败，0 警告），Ruff 规范检查零错误；前端 TypeScript 类型检查通过、ESLint 零警告，Next.js 生产构建（21 个页面全部成功）。
系统全阶段 R0-R6 修复与构建任务全部交付收口，具备完整生产部署手册 (`DEPLOYMENT.md`) 与灾备手册 (`BACKUP_RESTORE.md`)。

## 2. 文档优先级

发生冲突时按以下顺序执行：

1. [HANDOFF.md](HANDOFF.md) — 当前交接状态和下一步；
2. [REMEDIATION_PLAN.md](REMEDIATION_PLAN.md) — 修复顺序与验收；
3. [AUDIT_REPORT.md](AUDIT_REPORT.md) — 接管时发现的问题；
4. [PRD.md](PRD.md) — 产品需求；
5. [ARCHITECTURE.md](ARCHITECTURE.md) — 架构决策；
6. [ROADMAP.md](ROADMAP.md) — 原功能规划，仅用于需求追溯。

开发入口：

- [根目录 README](../README.md)
- [后端 README](../backend/README.md)
- [前端 README](../frontend/README.md)

---

## 3. R0 已完成内容

### 3.1 数据库会话

- `backend/app/core/database.py` 已统一为同步 SQLModel Session；
- 普通数据库路由已改为同步 `def`，由 FastAPI 线程池执行；
- 文件上传和 LLM 工作函数保留异步；
- SQLite 连接启用 `foreign_keys=ON` 和 5 秒 busy timeout；
- 旧环境中的 `sqlite+aiosqlite://` URL 会由配置兼容转换为同步 URL。

### 3.2 Alembic

- `backend/alembic/env.py` 不再导入不存在的模型模块；
- 迁移通过 `app.models` 注册完整 metadata；
- SQLite 数据目录不存在时会自动创建；
- `alembic.ini` 已改为兼容 Windows locale 的 ASCII 配置；
- development 模式启动时自动执行 `upgrade head`；
- production 容器启动命令在 Uvicorn 前执行迁移。

### 3.3 Embedding

- 基础迁移不再依赖 sqlite-vec/`vec0`；
- 新增 `backend/app/models/question_embedding.py`；
- `0002_vec_questions` 迁移现在创建 `question_embeddings`；
- 保存向量、维度、模型和更新时间；
- 写入前校验向量维度；
- sqlite-vec 或 pgvector 索引推迟到 R5。

### 3.4 应用启动

- 数据、媒体、日志和导出目录在 `StaticFiles` 挂载前创建；
- 媒体目录使用 `MEDIA_ROOT` 配置，而不是固定路径；
- `.env.example` 已改为可直接复制的纯 dotenv 文件；
- `email-validator` 已加入依赖，认证 schema 可以正常加载。

### 3.5 容器配置

虽然本地不使用 Docker，以下配置已经修正并保留：

- 后端镜像复制应用和 Alembic 后再安装项目；
- 后端容器启动前迁移；
- 前端使用 `npm ci`；
- 前端不再复制不存在的 `public/`；
- 构建阶段注入 `API_PROXY_TARGET=http://backend:8000`；
- Compose 使用 `backend/.env`；
- Compose 健康检查使用 Python 标准库；
- 前后端均有 `.dockerignore`。

这些配置只做过静态/YAML/前端构建验证，没有 Docker Engine 实际构建证据。

### 3.6 回归验证

新增 `backend/tests/test_smoke.py`：

1. 空数据库执行全部 Alembic 迁移；
2. 注册首个管理员；
3. 登录并获得 token；
4. 创建题目；
5. 读取题目。

---

## 4. 已执行验证

### 后端

通过：

```bash
cd backend
.venv\Scripts\alembic.exe -c alembic.ini upgrade head
.venv\Scripts\pytest.exe -q
.venv\Scripts\ruff.exe check --select E9,F,I,W app tests alembic
```

结果：

- 迁移通过：`0001_initial → 0002_vec_questions → 0003_background_tasks → 0004_auth_and_class_access`（当前 head）；
- `pytest`：18 项测试全部通过（涵盖迁移回填、无鉴权 401、首个管理员初始化与二次注册关闭、登录与 `/auth/me`、refresh 轮换与重放防御、禁用用户会话立即失效、管理员专用用户管理、班级/学生/作业对象级权限隔离、伪造操作者字段拒绝、审计日志与 OpenAPI Bearer 契约声明）；
- 基础 Ruff 检查通过（零错误）；
- 实际 Uvicorn 启动通过，`/health` 返回 200；
- 首个管理员注册、二次注册 403 拒绝、登录、刷新轮换及各业务接口鉴权拦截均实际运行验证通过；
- development 模式空库自动迁移通过。

现有警告状态：

- 统一迁移为 `app.core.datetime_utils.utc_now`，Python 3.14 下 1981 项 `datetime.utcnow()` 弃用警告已彻底清零；
- 全量测试套件执行 0 警告、0 失败。
### 前端

通过：

```bash
cd frontend
npm run type-check
npm run lint
npm run build
```

结果：

- `type-check`：通过；
- `lint`：通过（ESLint 9 Flat Config，`--max-warnings=0` 零警告）；
- `build`：生产构建生成 14 个页面全部通过；
- 实际 Chrome 自动化驱动验证：通过（登录表单提交、跳转主页、受保护页面守护拦截、页面刷新后通过 HttpOnly refresh cookie 自动恢复会话，控制台零异常）。

### Docker

未执行。原因是本地没有 Docker Engine，不是当前迭代阻塞项。

---

## 5. 本地启动方式

### 5.1 后端环境

后端已有虚拟环境：

```text
backend/.venv
```

当前检测到的解释器为 Python 3.14.5，满足项目 `>=3.11` 要求。

首次或依赖更新后：

```bat
cd backend
.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env
```

不要覆盖已有 `.env`。如果 `.env` 已经存在，只补充缺失配置。

### 5.2 启动后端

```bat
cd backend
.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```

开发模式会自动执行 Alembic 迁移。

验证：

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

### 5.3 启动前端

另开终端：

```bat
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

前端地址：

```text
http://localhost:3000
```

`.env.local` 推荐只配置：

```dotenv
API_PROXY_TARGET=http://localhost:8000
```

保持 `NEXT_PUBLIC_API_BASE` 为空，浏览器通过 Next.js 同源代理访问后端。

---

## 6. 当前关键文件

| 文件 | 作用 |
|---|---|
| `backend/app/core/database.py` | 同步 Engine、Session、SQLite pragma 和开发迁移 |
| `backend/app/core/security.py` | 密码策略及 access/refresh JWT 签发校验 |
| `backend/app/core/dependencies.py` | 当前用户、角色、班级/学生/作业权限依赖 |
| `backend/app/api/v1/auth.py` | 初始化管理员、登录、refresh 轮换、logout、`/me` |
| `backend/app/models/auth_session.py` | 可撤销、可轮换的登录会话 |
| `backend/app/models/class_.py` | 班级、班级教师和班级学生关联 |
| `backend/alembic/versions/0004_auth_and_class_access.py` | R1 会话与班级教师迁移 |
| `backend/app/schemas/` | 各领域显式 Pydantic 请求/响应契约 |
| `backend/app/services/audit_service.py` | 与业务事务共同提交的显式审计事件 |
| `backend/tests/test_r1_auth_and_authorization.py` | R1 认证、授权、审计和 OpenAPI 回归 |
| `frontend/src/lib/api.ts` | 内存 access token、401 refresh 和统一文件请求 |
| `frontend/src/components/AuthProvider.tsx` | 服务端验证的前端会话状态 |
| `frontend/src/components/AppShell.tsx` | 页面守护、导航和退出 |
| `docs/REMEDIATION_PLAN.md` | R0-R6 修复顺序与验收标准 |

---

## 7. 不可破坏的当前决策

1. MVP 数据库继续使用 SQLite；
2. 数据库 ORM 使用同步 SQLModel Session；
3. LLM 网络调用和耗时工作保持 async；
4. 基础迁移不得依赖 sqlite-vec；
5. 试卷题目继续使用快照；
6. 学生不登录，由教师维护；
7. 不允许客户端提供可信的 `created_by`、`recorded_by`；
8. 班级、学生、作业和任务的数据范围必须由后端权限依赖校验，不能依赖前端隐藏；
9. 不以 Docker 可用性阻塞本地开发；
10. 每个迭代必须以实际运行场景验收。

---

## 8. R0-R6 核心闭环与能力矩阵

| 阶段 | 模块 | 核心能力 | 验收状态 |
|---|---|---|---|
| **R0** | 基础架构 | 同步 SQLModel 会话、Alembic 平滑迁移（空库到 head）、可移植 Embedding 持久化、媒体目录保护 | 已通过 |
| **R1** | 认证与契约 | OAuth2 Bearer + HttpOnly Cookie 会话轮换、首管理员保护、对象级权限隔离、严格 Pydantic 契约与 AuditLog | 已通过 |
| **R2** | 成绩与学情 | 正规每题成绩明细 (`homework_question_results`)、名单快照、Excel 双版本导入、掌握度趋势与薄弱点闭环、针对性练习转作业 | 已通过 |
| **R3** | 题库与媒体 | 题目/小问/多空答案聚合事务写入、Checksum 防重、等价匹配规则、知识点树层级与循环校验、媒体 MD5 去重与引用计数 | 已通过 |
| **R4** | 组卷与导出 | 智能组卷四步拆分引擎 (`plan`→`generate`→`validate`→`persist`)、硬约束与必含知识点 100% 达标、题目微调、Word/Markdown 快照级导出 | 已通过 |
| **R5** | LLM与向量 | 试卷文档提取（Word/PDF/纯文本）、MiniMax 客户端重试与 JSON 容错、长任务自愈状态机、余弦相似度检索平滑降级、双栏切题校对工作台 | 已通过 |
| **R6** | 运维与灾备 | SQLite 安全在线热备份、媒体同步归档、保留策略、原子灾难恢复演练、分层健康探针与请求追踪脱敏 | 已通过 |
| **交付** | 文档与手册 | 修订 PRD、更新 ADR-008/009、校准 Roadmap、发布 DEPLOYMENT.md 与 BACKUP_RESTORE.md | 已通过 |

验证结果：

```text
Alembic: 0006_question_knowledge_unique_and_media_integrity (head)
pytest: 77 passed, 0 warnings in 24s
Ruff 基础规则: passed (0 errors)
frontend type-check: passed
frontend lint: passed (0 warnings)
frontend build: passed（21 个页面全部成功）
端到端闭环: tests/test_e2e_full_cycle.py 全流程通过
灾备恢复演练: tests/test_r6_operations_and_backup.py 验证通过
```

## 10. 接手后的第一条命令

```bat
cd backend
E:/work/math-lib/backend/.venv/Scripts/python.exe -m pytest -q
```
前端生产验证：
```bat
cd frontend
npm run type-check && npm run lint && npm run build
```
## 10. 交接后的第一条命令

```bat
cd backend
E:/work/math-lib/backend/.venv/Scripts/python.exe -m pytest -q
```
