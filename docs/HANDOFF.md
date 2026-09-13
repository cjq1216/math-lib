# 项目 Handoff

> 项目：初中数学题库与学情分析系统  
> 交接日期：2026-09-12  
> 当前阶段：R0 已完成，下一阶段 R1  
> 默认运行方式：Windows 本地开发环境，不以 Docker 作为迭代阻塞条件

---

## 1. 当前结论

R0“恢复可运行基线”已经完成并通过本地实际运行验证。后端可以从空数据库迁移、启动，完成注册、登录、创建题目和读取题目；服务重启后数据仍然存在。前端类型检查和生产构建通过。

当前项目仍不是最终 MVP。下一优先级是 R1：认证、授权与 API 契约。学情、组卷、媒体和导出问题继续按 `REMEDIATION_PLAN.md` 顺序处理。

本地没有 Docker Engine。Dockerfile 和 Compose 配置保留为未来部署能力，但 Docker 实际构建不再作为进入 R1 的前置条件。

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

- 空库迁移通过：`0001_initial → 0002_vec_questions → 0003_background_tasks`；
- `pytest`：2 项通过；
- 基础 Ruff 检查通过；
- `pip check` 通过；
- 实际 Uvicorn 启动通过；
- `/health` 返回 200；
- 注册、登录、题目创建和读取均返回 200；
- 服务重启后题目仍可读取；
- development 模式从空目录自动迁移通过。

现有非阻断警告：

- 多个模型仍使用 `datetime.utcnow()`，Python 3.14 提示弃用；
- Starlette TestClient 使用 AnyIO 的弃用别名。

### 前端

通过：

```bash
cd frontend
npm run type-check
npm run build
```

生产构建生成 14 个页面。

未通过：

```bash
npm run lint
```

原因：项目没有 ESLint flat config，`next lint` 会进入交互式初始化。该项并入 R1 的代码质量收口。

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
| `backend/app/core/config.py` | 环境配置和旧数据库 URL 兼容 |
| `backend/app/core/database.py` | 同步 Engine、Session、SQLite pragma 和开发迁移 |
| `backend/app/main.py` | 目录初始化、生命周期、静态文件和健康检查 |
| `backend/alembic/env.py` | 迁移环境和空目录处理 |
| `backend/alembic/versions/0002_vec_questions.py` | 可移植 Embedding 表迁移 |
| `backend/app/models/question_embedding.py` | Embedding SQLModel |
| `backend/tests/test_smoke.py` | R0 回归测试 |
| `frontend/src/lib/api.ts` | 前端 API 请求、token 和文件操作 |
| `frontend/src/components/AppShell.tsx` | 当前前端登录状态和导航 |
| `docs/REMEDIATION_PLAN.md` | R1-R6 执行计划 |

---

## 7. 不可破坏的当前决策

1. MVP 数据库继续使用 SQLite；
2. 数据库 ORM 使用同步 SQLModel Session；
3. LLM 网络调用和耗时工作保持 async；
4. 基础迁移不得依赖 sqlite-vec；
5. 试卷题目继续使用快照；
6. 学生不登录，由教师维护；
7. 不允许客户端提供可信的 `created_by`、`recorded_by`；
8. 未完成认证授权前，不宣称数据隔离成立；
9. 不以 Docker 可用性阻塞本地开发；
10. 每个迭代必须以实际运行场景验收。

---

## 8. 当前已知风险

### P0：下一步必须处理

- 业务接口没有统一 JWT 认证依赖；
- `/auth/me` 仍返回 501；
- 用户管理没有管理员权限；
- 公开注册在首个管理员之后仍可创建教师；
- 教师可以访问全部班级、学生和学情；
- `created_by` 等审计字段仍由客户端 payload 提交；
- 大部分 API 使用裸 `dict`，PATCH 存在批量赋值风险。

### 后续业务风险

- 成绩明细不能支撑可靠学情分析；
- 智能组卷不保证所有硬约束；
- Word/Markdown 导出仍是占位；
- 媒体上传没有题目关联闭环；
- LLM provider 没有真实失败兜底；
- 关键关联表缺少组合唯一约束；
- 班级移除学生的 `left_at` 过滤存在错误。

详细证据见 `AUDIT_REPORT.md`。

---

## 9. 下一迭代：R1

目标：认证、授权和 API 契约。

### 第一批实施顺序

1. 在 `app/core/security.py` 增加 OAuth2 Bearer token 解析；
2. 新建认证依赖模块，提供：
   - `get_current_user`
   - `require_admin`
   - `require_teacher_or_admin`
3. 实现 `/auth/me`；
4. 首个管理员创建后关闭公开注册；
5. 用户管理路由增加管理员依赖；
6. 所有业务路由要求登录；
7. 删除 payload 中的 `created_by`、`recorded_by` 信任路径；
8. 建立第一批 Pydantic schema，优先认证、用户和题目；
9. 增加 401、403、禁用用户和伪造审计字段回归测试；
10. 增加 ESLint flat config，修复 `npm run lint`。

### R1 验收

- 未登录访问业务接口返回 401；
- 禁用用户 token 不再可用；
- 教师不能访问用户管理；
- `/auth/me` 返回数据库中的当前用户；
- 第二个及后续用户不能公开注册；
- 伪造 `created_by` 不生效；
- OpenAPI 显示 Bearer 认证和明确 schema；
- 后端测试、基础 Ruff、前端 type-check、lint、build 全部通过。

对象级班级/学生权限如果需要新增班级教师关联表，应在 R1 内完成迁移，不使用前端隐藏按钮代替后端授权。

---

## 10. 交接后的第一条命令

```bat
cd backend
.venv\Scripts\pytest.exe -q
```

确认 R0 回归仍通过后，直接开始 R1 的认证依赖和 `/auth/me`，不再等待 Docker。
