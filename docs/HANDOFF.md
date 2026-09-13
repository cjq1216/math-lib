# 项目 Handoff

> 项目：初中数学题库与学情分析系统  
> 交接日期：2026-09-12  
> 当前阶段：R1 已完成，下一阶段 R2
> 默认运行方式：Windows 本地开发环境，不以 Docker 作为迭代阻塞条件

---

## 1. 当前结论

R0“恢复可运行基线”和 R1“认证、授权与 API 契约”已经完成并通过本地实际运行验证。后端可以从空数据库迁移到 `0004_auth_and_class_access`，完成首个管理员初始化、登录、HttpOnly refresh cookie 轮换、Bearer access token 校验、当前用户查询、管理员用户管理，以及班级/学生对象级权限隔离。业务 API 已统一要求登录，可信操作者由服务端注入。

前端已移除 localStorage token，改为内存 access token + HttpOnly refresh cookie；启动时通过服务端恢复会话，业务页面具备路由守护。TypeScript、ESLint flat config 和生产构建均已通过。

当前项目仍不是最终 MVP。下一优先级是 R2：成绩明细与学情闭环。组卷、媒体和导出问题继续按 `REMEDIATION_PLAN.md` 顺序处理。

本地没有 Docker Engine。Dockerfile 和 Compose 配置保留为未来部署能力，但 Docker 实际构建不作为本地迭代前置条件。

---

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

现有非阻断警告：

- 多个模型仍使用 `datetime.utcnow()`，Python 3.14 提示弃用（建议在后续代码现代化阶段统一为 `datetime.now(timezone.utc)`）；
- Starlette TestClient 使用 AnyIO 的弃用别名。

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

## 8. 当前已知风险

### P0：下一步必须处理

- `homework_results.result_detail` 仍不能可靠表示每题成绩，知识点统计缺少可信输入；
- 作业班级和学生名单仍保存在 JSON 字段中，尚未形成历史名单快照；
- Excel 成绩导入尚未绑定 `paper_question_id`，对错版与得分版尚未完成同等校验；
- 学情聚合尚未实现近期趋势、薄弱点自动解除和规范化班级统计。

### 后续业务风险

- 智能组卷不保证所有硬约束；
- Word/Markdown 导出尚未实现，接口现明确返回 501，前端按钮已禁用；
- 媒体上传没有题目关联闭环，`/static` 资源仍是公开静态地址；
- LLM provider 没有真实失败兜底，进程重启仍会丢失执行中任务；
- R2/R3 尚需补齐其他关键关联表的组合唯一约束；
- Python 3.14 下现有 `datetime.utcnow()` 与 Starlette TestClient 仍产生弃用警告。

详细证据见 `AUDIT_REPORT.md`。

---

## 9. R1 完成证据与下一迭代

### R1 已完成

- access token 使用 OAuth2 Bearer，refresh token 使用同源 HttpOnly cookie；
- `auth_sessions` 支持 refresh 轮换、重放拒绝和 logout 撤销；
- `/auth/me` 返回数据库当前用户，禁用用户的现有会话立即失效；
- 仅空库允许公开初始化第一个管理员，后续用户只能由管理员创建；
- 业务路由统一认证，用户管理为管理员专用；
- `ClassTeacher` 与对象权限依赖限制教师只能访问任教班级、在班学生及对应作业；
- `created_by`、`recorded_by`、媒体上传者和任务创建者均由服务端注入；
- 主要 API 已使用严格 Pydantic schema，PATCH 不再接受任意字段；
- 登录、用户、题目、班级、学生、试卷、作业、导入及后台失败写入审计；
- 前端不再使用 localStorage，刷新浏览器可通过 HttpOnly refresh cookie 恢复会话；
- ESLint flat config、类型检查和生产构建通过。

验证结果：

```text
Alembic: 0004_auth_and_class_access (head)
pytest: 18 passed
Ruff 基础规则: passed
frontend type-check: passed
frontend lint: passed
frontend build: passed（14 个页面）
实际浏览器: 登录、受保护页面、刷新后会话恢复通过；控制台无异常
```

### 下一迭代：R2

按 `REMEDIATION_PLAN.md` 第 5 节实施“成绩明细与学情闭环”：

1. 新增正规每题成绩明细和作业名单关联表；
2. 从试卷快照计算满分并生成稳定模板；
3. 完成得分版/对错版 Excel 幂等导入与结构化错误；
4. 由每题结果自动聚合学生和班级学情；
5. 完成薄弱点生成、恢复解除和针对性练习闭环；
6. 用一个学生、三个知识点、五次作业的真实场景验收。

---

## 10. 交接后的第一条命令

```bat
cd backend
.venv\Scripts\pytest.exe -q
```

确认 R0/R1 回归仍通过后，直接开始 R2 的成绩明细模型与迁移，不再等待 Docker。
