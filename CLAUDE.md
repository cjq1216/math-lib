# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述与当前状态

本项目是面向培训机构数学教研组的本地化数学题库、智能组卷与学情分析系统。
- **当前阶段**：R1（认证、授权与 API 契约）已完成，下一阶段是 R2（成绩明细与学情闭环）。
- **运行方式**：本地无 Docker Engine，默认采用后端 Python 虚拟环境 + Uvicorn、前端 Next.js 的本地开发模式；Docker 配置仅作为未来部署保留，不作为本地开发阻断条件。

---

## 常用开发命令

### 后端 (FastAPI + SQLModel + Alembic)

工作目录：`backend`

- **Python 环境**：要求 Python >= 3.11（当前系统安装路径参考：`C:\Users\chx12\AppData\Local\Programs\Python\Python314\python.exe`）。
- **创建虚拟环境**：`python -m venv .venv`（或使用绝对路径指定 Python 3.14 解释器）
- **激活虚拟环境**：
  - Windows: `.venv\Scripts\activate`（或直接调用 `.venv\Scripts\<command>.exe`）
  - Linux/macOS: `source .venv/bin/activate`
- **安装依赖**：`pip install -e ".[dev]"`
- **环境配置**：`copy .env.example .env`（若已有 `.env` 切勿覆盖）
- **数据库迁移**：
  - 升级到最新：`alembic upgrade head`
  - 查看当前版本：`alembic current`
  - 回滚一级：`alembic downgrade -1`
- **启动开发服务**：`uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
  - *注：`APP_ENV=development` 时应用启动会自动执行 Alembic `upgrade head`。*
  - 健康检查地址：`http://localhost:8000/health`
  - OpenAPI 文档：`http://localhost:8000/docs`
- **运行测试**：
  - 全量测试：`pytest`
  - 单个测试文件：`pytest tests/test_smoke.py`
  - 单个测试用例：`pytest tests/test_smoke.py::test_migrations_upgrade_empty_database`
- **代码规范检查**：
  - 基础检查：`ruff check --select E9,F,I,W app tests alembic`
  - 全量检查：`ruff check .`

### 前端 (Next.js 15 + React 19 + Tailwind CSS)

工作目录：`frontend`

- **安装依赖**：`npm install`
- **环境配置**：`copy .env.example .env.local`
  - 推荐配置：`API_PROXY_TARGET=http://localhost:8000`，保持 `NEXT_PUBLIC_API_BASE` 为空走同源代理
- **启动开发服务**：`npm run dev`（访问 `http://localhost:3000`）
- **类型检查**：`npm run type-check`（执行 `tsc --noEmit`）
- **生产构建**：`npm run build`
- **代码检查**：`npm run lint`（ESLint 9 flat config，零 warning 验收）

---

## 核心架构与设计模式

### 1. 业务核心闭环
```text
题目入库 → 知识点与难度标注 → 智能组卷 → 下发班级作业 → 录入每题成绩 → 分析学生/班级学情 → 根据薄弱知识点生成练习
```

### 2. 角色与权限模型
- **管理员 (admin)**：系统全局配置、用户账号管理与全局数据。
- **教师 (teacher)**：维护题库、试卷、班级、作业与学情数据。
- **学生 (student)**：**MVP 阶段不实现学生端登录**（ADR-007），所有信息和作答数据由教师代为录入维护。
- **安全与审计约定**：服务端通过 JWT 上下文识别用户角色并写入 `created_by`、`recorded_by` 等审计字段，严禁从客户端 payload 中接收信任的操作者标识。

### 3. 后端架构要点 (`backend/app/`)
- **同步 Session 规范**：数据库 ORM 统一使用同步 SQLModel `SessionLocal`（`app/core/database.py`）。SQLite 数据库连接开启 `PRAGMA foreign_keys=ON` 和 5000ms `busy_timeout`。数据库常规路由使用同步函数 `def`（FastAPI 自动交由线程池执行），避免混用异步 ORM 会话；仅外部 LLM HTTP 请求和异步文件 I/O 采用 `async def`。
- **R1 会话模型**：短期 access token 通过 OAuth2 Bearer 传递；refresh token 只在同源 HttpOnly cookie 中。`AuthSession` 保存当前 refresh `jti`，刷新时轮换，旧 token 重放、logout、禁用用户都会撤销会话。权限角色始终读取数据库当前用户，不信任 JWT 中的角色快照。
- **对象权限**：`app/core/dependencies.py` 统一提供用户、角色、班级、学生和作业权限。题库/知识点/试卷是机构内共享；教师只能访问 `ClassTeacher` 关联班级、仍在班的学生及对应作业，管理员可访问全部。
- **API 契约与审计**：请求体使用 `app/schemas/` 的严格 Pydantic schema，PATCH 只更新白名单字段。写操作从当前用户注入审计字段，并通过 `audit_service.add_audit_event` 与业务修改在同一事务提交。
- **题目-试卷快照隔离 (ADR-002)**：`PaperQuestion` 表中保留 `stem_snapshot`、`answer_snapshot`、`analysis_snapshot` 字段。原题库修改绝不影响已生成的历史试卷。
- **Embedding 存储设计 (ADR-006)**：基础迁移使用独立的 `question_embeddings` 表持久化向量数组、模型及维度，解耦 sqlite-vec 引擎强依赖，保障标准 SQLite 空库平滑迁移。
- **本地媒体管理 (ADR-004)**：静态文件存放在 `MEDIA_ROOT` 本地目录，采用 MD5 去重机制与多对多题目关联。
- **异步后台任务 (ADR-005)**：切题、打标、Embedding 等长耗时任务使用 FastAPI `BackgroundTasks` 处理，状态写入 `background_tasks` 表，前端轮询 `/api/v1/llm/tasks/{id}` 获取进度。

### 4. 前端架构要点 (`frontend/src/`)
- **同源反向代理**：`next.config.ts` 通过 `rewrites` 将 `/api/v1/:path*` 和 `/static/:path*` 代理到后端的 `API_PROXY_TARGET`，浏览器请求均使用相对路径，规避 CORS 复杂配置。
- **数学公式渲染**：全局使用 `MathText` 组件渲染 LaTeX 公式（支持 `$...$` 与 `$$...$$`），内部对正文进行 HTML 转义后回填 KaTeX 输出，严禁在业务页面直接使用 `dangerouslySetInnerHTML`。
- **API 请求客户端**：统一使用 `src/lib/api.ts` 的封装（`http.get/post/patch/del/upload/download`）。access token 仅存在模块内存；并发 401 共用一次 refresh 请求并最多重试一次。`AuthProvider` 通过 refresh + `/auth/me` 建立真实会话，`AppShell` 在完成校验前不渲染业务页。禁止 localStorage token 和页面内第二套认证处理。

---

## 开发约定与执行规则

### 文档优先级 (发生冲突时按此顺序执行)
1. `docs/HANDOFF.md` —— 最新交接状态与当前迭代重点
2. `docs/REMEDIATION_PLAN.md` —— 修复顺序与各阶段验收要求（R0 ~ R6）
3. `docs/AUDIT_REPORT.md` —— 接管审查发现的历史问题与证据
4. `docs/PRD.md` —— 产品原始需求与功能边界
5. `docs/ARCHITECTURE.md` —— 原始架构设计文档
6. `docs/ROADMAP.md` —— 原路线图（仅作追溯，已勾选仅代表有代码痕迹）

### 不可违反的约束
1. **真实实现优先**：严禁提交占位接口、假成功提示（Mock）或不可点击的误导性按钮。
2. **数据完整性**：所有数据库模型变更必须生成对应的 Alembic 迁移脚本，并验证可从空库平滑升级。
3. **严格以实际场景验收**：每个开发任务完成后，必须通过可复现的运行场景或测试用例作为验收证据。
