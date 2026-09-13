# 项目接管调研报告

> 项目：初中数学题库与学情分析系统  
> 审查日期：2026-09-12  
> 审查范围：`docs/`、`backend/`、`frontend/`、Docker 与启动配置  
> 结论状态：接管基线，后续修复以本文和 `REMEDIATION_PLAN.md` 为准

---

## 1. 执行结论

当前项目已经具备较完整的产品构想、数据模型、API 路由和前端页面骨架，但尚不能认定为可运行、可验收的 MVP。

项目当前更准确的定位是：

- 前端页面原型可构建；
- 后端主要领域模型和路由已铺开；
- 智能组卷、学情分析、LLM 任务已存在初步算法或框架；
- 数据库会话、迁移、权限、成绩明细和部署链路存在阻断级问题；
- Roadmap 中部分“已完成”只代表已有模型、函数或页面，不代表端到端验收通过。

在修复基础链路前，不应继续推进第二批功能。推荐先完成：

1. 恢复后端和数据库可运行基线；
2. 完成认证授权和对象级数据隔离；
3. 重构每题成绩数据结构，打通学情分析闭环；
4. 修正智能组卷约束并完成 MVP 导出；
5. 再进入文档导入、媒体、LLM 和向量检索增强。

---

## 2. 审查方法与验证范围

### 2.1 已检查内容

- 产品需求：`docs/PRD.md`
- 架构设计：`docs/ARCHITECTURE.md`
- 功能路线图：`docs/ROADMAP.md`
- 后端：FastAPI 路由、SQLModel 模型、服务、Alembic 迁移
- 前端：Next.js 页面、API 客户端、共享类型和核心组件
- 部署：Dockerfile、Compose、环境模板和启动脚本

### 2.2 已执行验证

| 验证项 | 结果 |
|---|---|
| `frontend: npm run type-check` | 通过 |
| `frontend: npm run build` | 通过，14 个页面完成生产构建 |
| `frontend: npm run lint` | 失败；没有 ESLint 配置，`next lint` 进入交互式初始化 |
| 前端依赖解析 | 通过；发现 React Query、Zustand 未使用 |
| 后端测试目录 | 未发现 |
| ESLint、部署、已知问题、备份文档 | 未发现 |

### 2.3 未完成的运行验证

当前工作环境没有可用 Python 运行时，Docker 命令也不可用，因此未实际启动后端或 Compose。本文中由静态代码可以确定的事实直接陈述；依赖运行环境才能最终确认的后果标记为“推断”。

---

## 3. P0 阻断问题

## 3.1 数据库会话模型整体不一致

`backend/app/core/database.py` 创建的是 SQLAlchemy `AsyncSession`，但路由和服务均按同步 SQLModel `Session` 使用：

- `session.exec(...)`
- `session.get(...)`
- `session.commit()`
- `session.refresh(...)`

涉及认证、题目、班级、学生、作业、组卷、学情和后台任务等几乎全部数据库路径。

典型位置：

- `backend/app/api/v1/auth.py:24-43`
- `backend/app/api/v1/questions.py:34-76`
- `backend/app/services/paper_generator.py:54-104`
- `backend/app/services/analytics_service.py:31-96`
- `backend/app/services/task_service.py:38-103`

仅 Embedding 写入路径局部使用了 `await session.execute/commit`。

**推断后果：**数据库接口会出现 `AsyncSession` 不支持 `exec` 或协程未等待的问题，核心接口不能可靠运行。

**建议：**MVP 阶段统一使用同步 SQLModel Session。SQLite 和目标 QPS 不需要异步数据库复杂度；LLM 网络调用继续保留异步。

## 3.2 Alembic 迁移不能形成可靠基线

`backend/alembic/env.py` 导入了不存在的模块：

- `sub_question`
- `question_answer`
- `question_knowledge`
- `class_student`
- `paper_question`
- `homework_result`

这些模型实际定义在 `question.py`、`class_.py`、`paper.py` 和 `homework.py` 中。

同时，`0002_vec_questions.py` 无条件创建 `vec0` 虚表，但项目没有 sqlite-vec 安装和扩展加载逻辑。

**推断后果：**迁移可能先因模型导入失败退出；即使修复导入，也可能因 `no such module: vec0` 失败。

## 3.3 本地启动和 Docker 链路不一致

发现以下独立问题：

1. 后端镜像在复制 `app/` 前执行项目安装；Hatch 配置要求打包 `app`。
2. 后端镜像未复制 `alembic.ini` 和 `alembic/`。
3. production 模式不自动迁移，容器启动命令也没有迁移步骤。
4. `StaticFiles` 在数据目录创建前挂载，本地首次启动可能失败。
5. Compose 使用 `.env-data`，README 和启动脚本生成的是 `backend/.env`。
6. `backend/.env.example` 是带 Markdown 围栏的说明文档，不是干净的 dotenv 模板。
7. Compose 健康检查使用 `curl`，后端镜像没有安装 curl。
8. 前端 Dockerfile 复制不存在的 `frontend/public/`。

因此 Roadmap 中“Docker Compose 一键启动”和“Alembic 迁移完成”尚无可执行证据。

## 3.4 认证与授权尚未落地

当前只有登录签发 JWT 的代码，没有完整认证授权：

- `/auth/me` 返回 501；
- 业务接口没有 `get_current_user` 依赖；
- 用户管理没有管理员权限检查；
- 注册接口公开，首个用户之后仍可公开创建教师账号；
- 教师可以访问全部班级、学生和学情；
- `created_by`、`recorded_by` 等字段由客户端提交，可被伪造；
- 前端只检查 localStorage 中是否存在 token，不验证 token，也不保护业务路由。

这与 PRD 的角色权限矩阵和教师对象级数据隔离要求不符。

## 3.5 学情分析输入数据闭环断裂

学情聚合依赖每题结果中存在：

```json
{
  "question_id": 1,
  "is_correct": true,
  "kp_ids": [1, 2]
}
```

但实际入口没有形成该结构：

- 前端手工成绩录入只提交总分和用时；
- Excel 导入只生成 `question_index`、`score`、`is_correct`；
- 对错版 Excel 的 `√/×` 不会被解析；
- Excel 明细没有映射到 `paper_question_id` 或 `question_id`；
- Excel 导入将满分固定为 100，百分比直接等于总分。

因此知识点统计、薄弱点和针对性出题缺少可靠输入。

其他学情问题：

- `recent_5_accuracy` 和趋势字段没有计算；
- 正确率恢复后，原薄弱点不会自动解除；
- “难度加权”实际只是累计原始分数；
- 班级排行未指定作业时会按结果记录排行，学生可能重复；
- 班级平均分混合不同满分试卷的原始分数。

## 3.6 MVP 导出仍是占位实现

PRD 将 Markdown 和 Word 导出列为 MVP 和验收项，但 `backend/app/api/v1/papers.py` 仅返回“导出功能开发中”，项目也没有 Word 生成依赖。

前端已经展示导出按钮，使界面状态与真实能力不一致。

---

## 4. P1 核心设计问题

## 4.1 智能组卷不能保证约束

当前组卷算法存在：

- 候选不足时静默少出题；
- 不返回不可满足约束的原因；
- 扩展候选可能重复选中已有题目；
- 必含知识点替换时没有继续约束题型、难度和禁含知识点；
- 必含知识点没有候选时静默继续；
- 每题分值简单等分；
- 没有生成后约束复核；
- 没有卷内雷同和历史卷相似检测；
- 没有手动调整、替换、排序和改单题分值接口。

因此尚不能支持 PRD 中“约束达标率 >95%”的验收目标。

## 4.2 关键表缺少组合唯一约束

建议至少增加：

- `class_students(class_id, student_id)`
- `question_knowledge(question_id, knowledge_point_id)`
- `paper_questions(paper_id, display_order)`
- `homework_results(homework_id, student_id)`
- `student_kp_stats(student_id, knowledge_point_id)`
- `weak_points(student_id, knowledge_point_id)`

当前“先查询、再插入”的防重方式不能防止并发重复。

SQLite 还没有看到启用 `PRAGMA foreign_keys=ON` 的逻辑，级联删除约束可能不生效。

## 4.3 班级成员生命周期错误

移除学生只设置 `left_at`，但班级成员列表不筛选 `left_at`；重新添加时又把历史关联视为已存在。

结果是学生移除后仍可能显示，并且无法重新加入。

## 4.4 媒体资源没有接入题目

虽然存在 `QuestionMedia` 模型，但没有关联 API 和前端编辑能力。

当前引用计数按上传次数增加，而不是按真实题目关联维护：

- 新资源上传即引用数为 1；
- 重复上传继续增加；
- 未建立 `question_media` 关系；
- 未使用的资源也无法正常删除。

还缺少文件类型、大小、图片解码安全校验和图片相似检测。

## 4.5 LLM 服务与架构声明不一致

文档宣称 MiniMax 失败时自动切换 Ollama，但代码只是按配置二选一。

其他缺口：

- 分段切题失败被吞掉，任务可能以成功状态返回部分结果；
- 无重试、退避和限流；
- 任务进度基本不更新；
- `source_id` 没有用于持久化切题结果；
- 无来源文件 API 和校对页面；
- Embedding 不会在题目入库后自动触发；
- 无向量相似题查询接口；
- 进程重启后没有任务恢复机制。

## 4.6 API 缺少明确输入输出契约

除认证外，大部分接口直接使用 `payload: dict`，也没有响应模型。

风险包括：

- OpenAPI 无法准确描述请求；
- 缺少统一字段、范围和枚举校验；
- PATCH 使用 `setattr`，存在批量赋值风险；
- 服务端审计字段可由客户端修改；
- 前后端重复维护类型，结构逐渐漂移；
- 提交、回滚边界分散在路由和服务中。

---

## 5. 功能覆盖矩阵

| 模块 | 当前实现 | 审查结论 |
|---|---|---|
| 用户与认证 | 登录、注册、JWT 签发 | 无鉴权依赖和权限控制，不完整 |
| 题库管理 | 基础 CRUD、筛选、知识点、小问 | 无媒体、多空答案写入、完整校对和批量操作 |
| 富文本 | Textarea + KaTeX 预览 | 与 PRD 的 Tiptap 要求不一致 |
| 知识点 | 树、创建、JSON 导入 | 无完整编辑、拖拽、导出和层级约束 |
| 智能组卷 | 分桶和随机贪心原型 | 不保证硬约束，不能验收 |
| 试卷导出 | 前端按钮和占位接口 | 未实现 |
| 班级学生 | 创建、列表、关联、Excel 导入 | CRUD 不完整，成员移除有错误 |
| 作业下发 | 基础创建和列表 | 状态机、名单快照和生命周期不完整 |
| 成绩录入 | 总分录入、Excel 框架 | 每题数据无法支撑学情分析 |
| 学情分析 | 聚合函数和页面 | 核心输入数据断裂，结果不可靠 |
| 针对性出题 | 按薄弱点随机选题 | 不加权、可能不足或重复，不能一键形成作业 |
| 媒体 | 上传和 MD5 查重 | 未与题目形成关联闭环 |
| LLM | 切题、打标、Embedding 框架 | 无真实兜底、任务恢复和校对闭环 |
| 相似题 | sqlite-vec 表和写入片段 | 无可靠安装、自动触发和查询能力 |
| 审计 | 数据表 | 无写入点 |
| 备份 | 文档描述 | 未实现 |
| Docker 部署 | 配置文件 | 存在多处阻断点 |

---

## 6. 需求和设计文档问题

现有 PRD 的目标用户、非目标、核心流程、数据模型和验收轮廓总体合理，但以下内容需要统一：

1. PRD 要求 Tiptap，Roadmap 又记录移除 Tiptap，代码使用 Textarea。
2. 知识点一处要求教材版本切换，锁定决策又要求统一知识点树。
3. 文档导入在模块表中属于第二批，在里程碑中又进入 MVP。
4. PRD 要求 refresh token，Roadmap 标记待补。
5. PRD 要求每日备份，Roadmap 将备份放到第二批。
6. Embedding 内容分别定义为“题干+答案”和“题干+答案+解析”。
7. 加入 `background_tasks` 后实际表数量超过文档所称 19 张。
8. 架构文档把部分未跑通项目标记为“已修复”。
9. PostgreSQL 切换阈值在文档中不一致。
10. 文档索引引用的 `KNOWN-ISSUES.md`、`DEPLOYMENT.md` 不存在。

还需补充以下业务规则：

- 缺考、空白、部分得分和重做的统计规则；
- 多知识点题目的正确率权重；
- 题目、知识点修改后的历史统计策略；
- 转班、退班和历史班级归属；
- Excel 重复导入和幂等规则；
- 组卷约束不可满足时的处理；
- LLM 任务部分成功、重试、取消和恢复；
- 数据恢复演练和备份验收；
- 每个 Roadmap 勾选项对应的可执行验收命令。

---

## 7. 值得保留的设计

以下方向合理，重构时应保留：

- 学生不登录、教师代维护的产品边界；
- 题目与试卷之间使用快照；
- 题目、小问和多空答案分表；
- 知识点使用统一树；
- 媒体资源与题目 N:M；
- 长时 LLM 请求异步化；
- MVP 使用 SQLite；
- 前端统一 API 客户端和 KaTeX 渲染组件；
- 作业结果可以触发可重算的学情聚合。

需要重构的是实现边界和一致性，而不是推翻产品方向。

---

## 8. 接管决策

1. 暂停第二批功能开发。
2. Roadmap 的已勾选项视为“已有代码”，不视为“验收完成”。
3. 修复顺序以 `REMEDIATION_PLAN.md` 为唯一执行计划。
4. 每个迭代必须有可执行验收，不再以文件、模型或页面存在作为完成标准。
5. 完成核心业务闭环前，不接入更多 AI、OCR、几何和看板能力。
