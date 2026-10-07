# 架构设计文档

> 项目：初中数学题库与学情分析系统
> 文档版本：v1.2
> 制定日期：2026-09-12（2026-10-07 里程碑收口）
> 状态：✅ 实施与最终验收已完成（R0-R6 全部闭环通过）

---

## 1. 总体架构

### 1.1 系统组件

```
┌────────────────────────────────────────────────────────┐
│                      浏览器 (教师)                       │
│                Next.js 15 + Tailwind + shadcn/ui        │
└──────────────────────┬─────────────────────────────────┘
                       │ HTTPS (Caddy)
                       ▼
┌────────────────────────────────────────────────────────┐
│              FastAPI 后端 (Python 3.11+)                │
│  ┌─────────┬──────────┬───────────┬──────────────┐    │
│  │  API    │ Services │ Background│   Auth/JWT   │    │
│  │ Routes  │ (业务逻辑) │  Tasks    │              │    │
│  └────┬────┴─────┬────┴─────┬─────┴──────┬───────┘    │
│       │          │         │            │             │
└───────┼──────────┼─────────┼────────────┼─────────────┘
        │          │         │            │
        ▼          ▼         ▼            ▼
┌──────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐
│  SQLite  │ │ Media   │ │ MiniMax  │ │ External│
│ +向量数据│ │ Files   │ │ LLM API  │ │ Embed   │
│ 持久化表 │ │ (本地)  │ │ (主)     │ │ API     │
└──────────┘ └─────────┘ └──────────┘ └─────────┘
                              │
                              ▼ (失败兜底)
                       ┌──────────────┐
                       │ Ollama +     │
                       │ Qwen2.5-14B  │
                       │ (本地离线)   │
                       └──────────────┘
```

### 1.2 数据流（典型场景）

**场景 1：录入题目 → AI 打标 → 入库**

```
[教师] 在 /questions/new 编辑题干
  → POST /api/v1/questions/ 创建题目
  → 题目入库（is_verified=false）
  → 后台触发打标任务
    → 调 LLM 打标 (async)
    → 更新题目字段
    → 触发 Embedding (async)
    → 写入 sqlite-vec
  → 前端轮询任务状态
  → 教师在 UI 上看到打标结果，校对后 is_verified=true
```

**场景 2：智能组卷**

```
[教师] 在 /papers/generate 设置约束
  → POST /api/v1/papers/generate
  → 组卷引擎 (paper_generator.generate)
    → 按 (题型, 难度) 分桶
    → 必含知识点校验
    → 候选不足时扩展
  → 创建 Paper + PaperQuestion (含快照)
  → 返回 paper_id
  → 教师预览 / 调整 / 导出
```

**场景 3：针对性出题**

```
[教师] 进入某学生学情
  → 看到薄弱知识点 Top 5
  → 点击"针对薄弱点生成练习"
  → POST /api/v1/analytics/students/{id}/targeted-practice
  → generate_targeted_practice
    → 按薄弱度排序选题
    → 排除最近 20 次作业做过的题
    → 难度渐进
  → 返回题目列表
  → 教师一键生成针对性作业
```

---

## 2. 技术选型与理由

| 层 | 选型 | 理由 |
|---|---|---|
| 后端框架 | FastAPI | 异步性能、OpenAPI 自动生成、LLM 生态完善 |
| ORM | SQLModel | FastAPI 作者同款，模型即 schema |
| 数据库 | SQLite + `question_embeddings` | MVP 零部署；向量索引作为可选能力后置 |
| 迁移 | Alembic | schema 演化标准方案 |
| 认证 | JWT (python-jose + passlib) | 无状态、可分布式 |
| 任务 | FastAPI BackgroundTasks | MVP 简化方案，后期切 Celery |
| LLM | MiniMax API（主）+ Ollama（兜底）| 国内合规 + 完全离线兜底 |
| 前端 | Next.js 15 App Router | 当前最热、SSR/CSR 灵活 |
| UI | Tailwind + shadcn/ui | 个人项目最快搭出体面 UI |
| 编辑器 | Textarea + KaTeX（当前） | 先保证结构化录入和公式预览，富文本编辑待后续决策 |

---

## 3. 关键架构决策（ADR）

### ADR-001：MVP 用 SQLite，后期切 PostgreSQL

**状态**：✅ 采纳

**背景**：MVP 阶段需要快速验证业务，跑通"录入→检索→导出"闭环。

**决策**：
- MVP 用 SQLite（单文件，零部署）
- 后期切 PostgreSQL（通过 Alembic 迁移，SQLModel 设计就是为此）

**后果**：
- ✅ 个人开发者零部署成本
- ⚠️ 单写者并发瓶颈：50 用户低频场景能用，500 活跃用户会卡
- ⚠️ 必须用 SQLModel 而非原生 SQLAlchemy，便于平滑切换

**切 PG 触发条件**：活跃用户 > 200 或题量 > 5 万

---

### ADR-002：题目-试卷用快照模式

**状态**：✅ 采纳

**背景**：教师改原题时，已出过的试卷不应受影响。

**决策**：
- `paper_questions` 存 `stem_snapshot` / `answer_snapshot` / `analysis_snapshot` 字段
- 原题改了不影响历史卷

**后果**：
- ✅ 数据安全，符合教育行业惯例
- ⚠️ 数据冗余：5000 题 × 5 份试卷 = 2.5 万行快照，可接受
- ⚠️ 改题时教师要主动复制产生新题，无法"全局更新"

---

### ADR-003：填空题答案多空独立 + 等价规则

**状态**：✅ 采纳

**背景**：填空题常有多个空，每个空独立答案；同时答案可能有多种等价写法。

**决策**：
- `question_answers` 表每条存一个空的答案
- `blank_index` 区分多空
- `match_rule` (JSON) 存等价规则（正则/多种写法）

**后果**：
- ✅ 多空题精细化判分
- ✅ 支持 $1/2 = 0.5 = 1÷2$ 等价
- ⚠️ 等价规则匹配需要单独测试覆盖

---

### ADR-004：图片存本地 FS + MD5 去重

**状态**：✅ 采纳

**背景**：MVP 阶段不上对象存储；图可能有大量重复（同张等腰三角形用在 20 道题）。

**决策**：
- 本地文件系统存储（`./data/images/`）
- `media_resource` 表管理所有二进制
- MD5 去重，N:M 关联到题目
- 后期切 MinIO

**后果**：
- ✅ 部署简单（与项目同机）
- ✅ 重复图只存一份
- ⚠️ 单机故障 = 媒体丢失，必须备份

---

### ADR-005：LLM 异步化 + BackgroundTasks

**状态**：✅ 采纳

**背景**：切题/打标/Embedding 调用 LLM 耗时 30-60 秒，同步会卡死前端。

**决策**：
- MVP 用 FastAPI BackgroundTasks（轻量）
- 任务状态写 `background_tasks` 表
- 前端轮询 `/api/v1/llm/tasks/{id}` 查进度
- 后期切 Celery 时改 `task_service.py` 即可

**后果**：
- ✅ 用户体验好（不卡）
- ✅ 任务可追踪、可重试
- ⚠️ MVP 进程重启会丢失 in-flight 任务
- ⚠️ 任务堆积时无优先级队列

---

### ADR-006：基础迁移保存 Embedding，向量索引可选接入

**状态**：R0 已修订

**背景**：去重和相似题推荐需要向量检索，但 sqlite-vec 属于可选扩展，不能阻断基础数据库迁移和服务启动。

**决策**：
- 基础迁移使用 `question_embeddings` 保存向量、维度和模型；
- Embedding 写入不依赖 sqlite-vec；
- R5 再按运行数据库启用 sqlite-vec 或 pgvector 索引；
- 相似度查询通过独立 repository 隔离数据库实现。

**后果**：
- 基础系统可在标准 SQLite 上完成空库迁移；
- Embedding 生成和持久化当前可用；
- 在 R5 接入向量索引前，不提供高性能相似度检索。

---

### ADR-007：教师代维护学生信息（学生不登录）

**状态**：✅ 采纳（与原规划文档的关键差异）

**背景**：培训机构场景，简化学生端复杂度。

**决策**：
- 学生表存在但**不实现登录**
- 教师录入学生信息 → 录入作答结果 → 系统分析
- 学情分析只对教师可见

**后果**：
- ✅ 不用做学生端 App / 小程序
- ✅ 不用做答题监考
- ✅ 教师是系统唯一使用者
- ⚠️ 学生无法自助查错题（教师打印给ta）

---

### ADR-008：SQLite 安全在线备份与媒体一致性归档

**状态**：✅ 采纳（R6 实施）

**背景**：直接热拷贝正在写入的 SQLite 文件会导致数据库损坏或快照撕裂；媒体图片分散存储，需要与数据库快照保持一致。

**决策**：
- 采用 SQLite 原生 `sqlite3.Connection.backup()` 在线热备份 API，并发读写时无损导出一致性快照；
- 备份包统一打包为 ZIP 归档，包含 `database.db`、`media/` 完整目录及 `manifest.json`；
- 备份包强制记录 SHA256 校验和、文件大小与文件数；
- 恢复流程执行 SHA256 比对、`PRAGMA integrity_check`、并生成恢复前快照 `pre_restore_backup` 兜底；
- 提供 CLI 命令行工具与系统管理 API，支持保留策略与自动过期清理。

**后果**：
- ✅ 零停机备份与原子恢复，规避快照损坏风险；
- ✅ 媒体与数据库在单一归档包中严格版本对应；
- ⚠️ 随着题量和媒体增加，备份包体积增大，需通过可配置保留策略控制磁盘占用。

---

### ADR-009：分层健康探针与全链路请求追踪可观测性

**状态**：✅ 采纳（R6 实施）

**背景**：容器编排与生产运维需要区分进程存活（Liveness）与依赖就绪（Readiness）；故障排查需要精确定位请求耗时并遵守数据隐私规范。

**决策**：
- 提供 `/health/live`（轻量进程探测）与 `/health/ready`（探测数据库 `SELECT 1` 及数据/媒体/日志/备份目录可写状态，异常返回 503）；保持 `/health` 综合向后兼容；
- 挂载 `RequestLoggingMiddleware`，统一透传或生成 `X-Request-ID`，并在响应头回填 `X-Response-Time-Ms` 耗时；
- 严格脱敏 Authorization、Token、Cookie、密码及学生身份证/联系电话，杜绝敏感信息进入日志。

**后果**：
- ✅ 容器或反向代理可进行精准健康探测与自动重启/摘流；
- ✅ 请求具备全局 Trace ID，运维排查高效；
- ✅ 满足教育培训场景数据合规要求。

---

## 4. 已知问题与风险

### P0（必须修）

| 问题 | 当前状态 |
|---|---|
| 同步/异步 Session 混用 | ✅ R0 已统一为同步 SQLModel Session |
| Alembic 空库迁移 | ✅ R0 已通过本地空目录、空库验证 |
| sqlite-vec 阻断迁移 | ✅ R0 已解耦为可移植 Embedding 存储 |
| Docker 一键启动 | ✅ 配置已校准并在生产部署手册中说明 |

### P1（影响体验）

| 问题 | 修复 |
|---|---|
| 针对性出题 random.sample 未按薄弱度加权 | ✅ R2 已改为多级加权排序选题算法 |
| JWT 无 refresh token | ✅ R1 已实现 HttpOnly Cookie 轮换与 Bearer 会话双轨保护 |
| Excel 导入错误反馈不友好 | ✅ R2 已实现定位行列号与原因的结构化错误报告 |
| 前端缺题目编辑页 / 组卷页 / 学情页 | ✅ R1-R5 已补齐 21 个前端页面并全量生产构建成功 |

### P2（不影响功能）

| 问题 | 修复 |
|---|---|
| 审计日志无写入点 | ✅ R1 已在全部核心业务写操作与异常点统一注入 AuditLog |
| 无备份自动化 | ✅ R6 已实现安全在线热备份、清单自检、保留策略与恢复演练 |
| 核心业务测试不足 | ✅ 全量 77 项后端自动化测试 + 端到端闭环测试 100% 通过 |
---

## 5. 后续里程碑

| 阶段 | 周次 | 目标 |
|---|---|---|
| **MVP** | D1-D16 | 业务跑通，录 200 题实测 |
| 第二批 | D17-D30 | 文档导入 + PDF 导出 + 相似题 + 看板 |
| 第三批 | D31+ | AI 生成新题 + 几何 + 自适应出题 |

---

## 6. 部署架构

```
生产环境（1 台 Linux 云服务器）：
- Docker Compose 起 2 个容器
  - backend（FastAPI）
  - frontend（Next.js standalone）
- Caddy 反向代理 + HTTPS
- 数据卷持久化：
  - ./backend/data/math_bank.db（SQLite）
  - ./backend/data/images/（媒体）
  - ./backend/data/logs/（日志）
- 每日 cron 自动备份
```

部署、备份与恢复文档将在修复计划 R6 完成后补充；当前执行要求见 [REMEDIATION_PLAN.md](REMEDIATION_PLAN.md)。

---

## 7. 文档索引

| 文档 | 路径 | 用途 |
|---|---|---|
| 项目 Handoff | [HANDOFF.md](HANDOFF.md) | 当前状态、本地启动、已完成修改和下一阶段 |
| 需求文档 | [PRD.md](PRD.md) | 业务需求 + 结构化决策 |
| 架构文档 | [ARCHITECTURE.md](ARCHITECTURE.md) | 本文档 |
| 原功能路线图 | [ROADMAP.md](ROADMAP.md) | 原 MVP/二批/三批规划；勾选不代表验收通过 |
| 接管调研报告 | [AUDIT_REPORT.md](AUDIT_REPORT.md) | 实现现状、风险和功能缺口 |
| 优化修复计划 | [REMEDIATION_PLAN.md](REMEDIATION_PLAN.md) | 当前唯一修复执行顺序和验收门槛 |
| 根目录 README | [README.md](../README.md) | 项目状态、结构和开发入口 |
| 后端 README | [README.md](../backend/README.md) | 后端开发、迁移和验证约定 |
| 前端 README | [README.md](../frontend/README.md) | 前端页面、环境和开发约定 |