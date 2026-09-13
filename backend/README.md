# 后端开发说明

FastAPI 后端，负责认证、题库、知识点、媒体、组卷、班级学生、作业成绩、学情分析和 LLM 任务。

> 当前状态：R0 本地运行基线已完成，下一阶段为 R1。默认使用 `backend/.venv` 和 Uvicorn 本地运行；Docker 配置仅作为未来部署能力，不阻塞开发。

## 技术栈

- Python 3.11+
- FastAPI
- SQLModel / SQLAlchemy
- Alembic
- SQLite 同步 Session
- openpyxl
- python-jose / passlib / bcrypt
- httpx
- loguru

## 目录结构

```text
backend/
├── app/
│   ├── main.py                 # FastAPI 入口和生命周期
│   ├── api/v1/                # API 路由
│   ├── core/
│   │   ├── config.py          # 环境配置
│   │   ├── database.py        # Engine 与 Session
│   │   └── security.py        # JWT 与密码哈希
│   ├── models/                # SQLModel 表模型
│   ├── schemas/               # Pydantic 请求/响应模型
│   └── services/
│       ├── paper_generator.py # 智能组卷
│       ├── analytics_service.py
│       ├── task_service.py
│       ├── llm_client.py
│       └── llm_service.py
├── alembic/
│   ├── env.py
│   └── versions/
├── alembic.ini
├── pyproject.toml
└── Dockerfile
```

## API 模块

| 模块 | 路径 | 当前说明 |
|---|---|---|
| 认证 | `/api/v1/auth` | 登录、注册；当前用户依赖待完成 |
| 用户 | `/api/v1/users` | 管理接口；管理员权限待完成 |
| 题目 | `/api/v1/questions` | CRUD、筛选、知识点、小问 |
| 知识点 | `/api/v1/knowledge` | 平铺列表、树、创建和导入 |
| 媒体 | `/api/v1/media` | 上传、列表、删除；题目关联待完成 |
| 试卷 | `/api/v1/papers` | CRUD、组卷；导出仍为占位 |
| 班级 | `/api/v1/classes` | 班级和学生关联 |
| 学生 | `/api/v1/students` | 基础管理和 Excel 导入 |
| 作业 | `/api/v1/homework` | 下发、成绩录入和模板 |
| 学情 | `/api/v1/analytics` | 学生、班级和针对性练习 |
| LLM | `/api/v1/llm` | 切题、打标、Embedding 任务 |

## 环境配置

配置类位于 `app/core/config.py`，通过环境变量或 `.env` 注入。

主要变量：

| 变量 | 默认值/说明 |
|---|---|
| `APP_ENV` | `development` |
| `APP_DEBUG` | `true` |
| `DATABASE_URL` | `sqlite:///./data/math_bank.db` |
| `JWT_SECRET_KEY` | 生产环境必须替换 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | access token 生命周期 |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | refresh token 生命周期 |
| `MEDIA_ROOT` | `./data/images` |
| `MEDIA_BASE_URL` | 媒体公开地址 |
| `LLM_PROVIDER` | `minimax` 或 `ollama` |
| `MINIMAX_API_KEY` | MiniMax Key |
| `OLLAMA_BASE_URL` | Ollama 服务地址 |
| `EMBEDDING_API_KEY` | Embedding Key |
| `CORS_ORIGINS` | 允许的前端来源 |

`.env.example` 已在 R0 改为可直接复制的纯 dotenv 模板。

## 安装与运行

预期本地开发流程：

```bash
python -m venv .venv
```

Windows：

```bash
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Linux/macOS：

```bash
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

服务地址：

- API：`http://localhost:8000`
- OpenAPI：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

本地启动链路已通过空库迁移、实际服务启动和重启持久化验证。

## 数据库与迁移

### 迁移命令

```bash
alembic current
alembic upgrade head
alembic downgrade -1
```

生成迁移前必须：

1. 导入所有 SQLModel 表模型；
2. 检查生成脚本，不直接接受自动生成结果；
3. 从空数据库执行到 head；
4. 使用已有开发数据执行升级；
5. 验证必要唯一约束、索引和外键。

### R0 状态

已完成：

- 数据库统一为同步 SQLModel Session；
- Alembic 模型导入和空目录迁移修复；
- sqlite-vec 从基础迁移解耦；
- SQLite 外键和 busy timeout 启用；
- production 容器增加启动前迁移；
- 增加空库迁移及核心 API 回归测试。

后续迭代仍需处理：

- 关联表和聚合表的组合唯一约束；
- 认证授权和对象级数据隔离；
- 每题成绩正规化；
- API schema 和事务边界统一。

## 数据模型边界

当前主要聚合：

- 题目：`Question`、`SubQuestion`、`QuestionAnswer`、`QuestionKnowledge`
- 试卷：`Paper`、`PaperQuestion`，试卷题目保存快照
- 班级学生：`Class`、`ClassStudent`、`Student`
- 作业成绩：`Homework`、`HomeworkResult`
- 学情：`StudentKPStats`、`WeakPoint`
- 媒体：`MediaResource`、`QuestionMedia`
- 任务：`BackgroundTask`

R2 将新增正规每题成绩明细，替换依赖 `result_detail JSON` 的核心统计路径。

## 认证与授权要求

最终接口必须使用统一依赖：

```text
get_current_user
require_admin
require_teacher_or_admin
require_class_access
require_student_access
```

禁止：

- 从 payload 接受可信 `created_by` 或 `recorded_by`；
- 仅靠前端隐藏按钮实现权限；
- 公开注册第二个及后续用户；
- 教师访问非所属班级和学生；
- 使用客户端提供的知识点列表直接生成学情统计。

## API 开发约定

- 请求和响应必须使用 Pydantic schema；
- 禁止新接口使用裸 `payload: dict`；
- PATCH 只能更新白名单字段；
- 业务错误返回稳定错误码和字段结构；
- 事务边界由请求级工作单元或 application service 管理；
- service 不应无规则地自行 commit；
- 列表接口必须有分页上限；
- 导入接口返回 `{row, column, code, message}` 结构化错误；
- 所有写接口从认证上下文记录操作者。

## LLM 与后台任务

LLM 网络调用应保持异步，但数据库任务状态使用统一 Session 工厂。

任务状态规划：

```text
pending
running
success
partial_success
failed
cancelled
```

要求：

- 失败不能伪装为 success；
- 分段失败必须保留错误信息；
- MiniMax 到 Ollama 的兜底仅处理可重试错误；
- 输出必须通过 schema 校验；
- 进程重启后遗留任务必须恢复或明确失败；
- Embedding 能力不可阻断基础数据库迁移和启动。

## 验证

当前验证命令：

```bash
ruff check --select E9,F,I,W app tests alembic
pytest
alembic upgrade head
```

以上命令已在本地通过。全量 Ruff 规则和 mypy 将随 R1 的 schema、类型与旧代码清理一起收口。

核心 smoke：

```text
空数据库
  → 迁移
  → 启动
  → 注册管理员
  → 登录
  → 创建题目
  → 查询题目
  → 重启后读取
```

高风险逻辑需要行为级测试：

- 认证与对象权限；
- 组卷硬约束和不可满足诊断；
- 每题成绩汇总；
- 薄弱点生成和解除；
- Excel 得分版/对错版幂等导入；
- 多空答案等价匹配。

## 相关文档

- [项目 Handoff](../docs/HANDOFF.md)
- [产品需求](../docs/PRD.md)
- [架构设计](../docs/ARCHITECTURE.md)
- [接管调研报告](../docs/AUDIT_REPORT.md)
- [优化修复计划](../docs/REMEDIATION_PLAN.md)
