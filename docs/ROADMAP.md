# 项目 Roadmap

> 原始功能规划，保留用于需求追溯。接管审查发现部分勾选项仅代表已有代码或页面，不代表端到端验收通过。当前状态见 [AUDIT_REPORT.md](AUDIT_REPORT.md)，后续执行以 [REMEDIATION_PLAN.md](REMEDIATION_PLAN.md) 为准。

## MVP（16 个工作日）

### 基础架子（R0 本地验收完成）
- [x] FastAPI 项目骨架 + pyproject.toml
- [x] Next.js 15 项目骨架 + Tailwind
- [ ] Docker Compose 一键启动（可选部署能力；本地无 Docker，不阻塞迭代）
- [x] Alembic 迁移（0001-0003）
- [x] JWT 认证 + 登录/注册
- [x] .env.example + start.bat/start.sh

### 题库核心 ✅
- [x] 核心 SQLModel + `background_tasks` + `question_embeddings`
- [x] 题目 CRUD + 多条件检索
- [x] Textarea + KaTeX 公式编辑与预览（Tiptap 未采用）
- [x] 知识点树形管理
- [x] 图片 MD5 去重 + N:M 关联
- [x] Embedding 异步生成与可移植持久化（向量索引待 R5）

### LLM 服务 ✅
- [x] MiniMax API + Ollama 双 provider
- [x] 切题/打标 Prompt 模板
- [x] **异步任务系统（background_tasks 表 + BackgroundTasks）**
- [x] 任务状态轮询端点

### 智能组卷 ✅
- [x] 分层贪心算法
- [x] 必含知识点校验
- [x] 试卷快照模式
- [x] 题型/难度分布

### 班级与作业 ✅
- [x] 学生信息 CRUD + Excel 批量导入
- [x] 班级 + 班级-学生关联
- [x] 作业下发 + 成绩录入
- [x] Excel 成绩模板自动生成

### 学情分析 ✅
- [x] 知识点掌握度聚合
- [x] 薄弱点识别
- [x] 针对性出题
- [x] 班级排行

### 前端页面 ✅（2026-09-12 补齐）
- [x] 题目编辑页 `/questions/new` `/questions/[id]/edit`（LaTeX 实时预览 + 知识点关联 + 小问 + AI 打标）
- [x] 智能组卷配置页 `/papers/generate`（题型/难度/必含禁含知识点 + 结果预览）
- [x] 学情详情页 `/analytics/students/[id]`（薄弱点 + 针对性出题）
- [x] 班级页 `/classes` `/classes/[id]`（学生管理 + Excel 导入 + 排行）
- [x] 作业页 `/homework` `/homework/new` `/homework/[id]`（下发 + 成绩录入 + Excel）
- [x] 题库列表页（多条件筛选）、试卷列表/详情、知识点树管理、学情入口
- [x] 轻量 UI 组件库 + AppShell 导航 + KaTeX 渲染组件（移除 tiptap 依赖）
- [x] 后端补充端点：`PUT /questions/{id}/knowledge`、`PUT /questions/{id}/sub-questions`

### MVP 增强与健壮性 ✅（已在 R1-R6 全部完成并通过端到端验收）
- [x] **针对性出题加权排序**（按掌握度薄弱分值多级加权降序选题）
- [x] **题目列表分页 + 批量操作**（支持多条件联合检索、分页与批量切题入库）
- [x] **Refresh Token 与会话模型**（HttpOnly Cookie 轮换、重放防御与多设备受控会话）
- [x] **Excel 导入结构化错误反馈**（精确定位行列号、错误码与友好中文原因）
- [x] **业务审计日志与请求中间件**（全链路 Request-ID 追踪、敏感数据脱敏、关键写操作 AuditLog）

---

## 第二批能力落地情况（R4-R6 提前完成项与后续储备）

### 文档导入与智能切题 ✅
- [x] Word (.docx) 文本与表格提取引擎 (`doc_extractor.py`)
- [x] PDF 矢量文字版纯 Python 提取解析
- [x] 双栏试卷切题校对工作台（左原文对照、右侧行内微调与一键批量入库）
- [ ] 扫描版 PDF 专用 OCR / LaTeX-OCR（复杂手写与极端扫描件专线，当前提供精准转换指引）

### 智能组卷与导出 ✅
- [x] 智能组卷四步拆分引擎 (`plan` → `generate` → `validate` → `persist`)
- [x] 必含知识点 100% 达标与硬约束校验
- [x] 试卷题目快照与题目微调/替换
- [x] Markdown 与 Word (.docx) 快照级完整格式导出
- [ ] Typst 集成（后续 PDF 排版引擎演进）

### 向量检索与智能增强 ✅
- [x] 纯线上向量持久化与余弦相似度检索 (`vector_service.py`)
- [x] 相似题推荐与查重推荐（未配置 Key 时平滑降级跳过）
- [ ] 历史卷跨试卷相似度分析（后续扩展）
- [ ] AB 卷变式生成（后续扩展）

### 运维与灾备闭环 ✅
- [x] SQLite 原生安全热备份 (`sqlite3.backup` 在线一致性快照，严禁直接 cp)
- [x] 媒体文件完整打包归档与 Manifest SHA256 校验清单
- [x] 备份保留策略与历史文件自动清理（可配置保留数量与天数）
- [x] CLI 命令行运维工具 (`python -m app.cli.backup`) 与管理端 API
- [x] 灾难恢复演练通过（数据篡改后原子恢复、媒体完整还原并自动生成恢复前快照）
- [x] 分层健康探针（存活 `/health/live`、就绪 `/health/ready` 及请求耗时追踪）
- [ ] 独立监控告警平台对接（Prometheus / Grafana）
---

## 第三批（5 周+）

### AI 能力升级
- [ ] AI 参数化生成新题
- [ ] 主观题 AI 辅助判分
- [ ] 自适应出题（强化版）

### 几何题支持
- [ ] L1 标注层（半天）
- [ ] L2 简易画板（3-5 天，可选）
- [ ] L3 Geogebra 集成（2 周，可选）

### 后期扩展
- [ ] 多学科（物理/化学）
- [ ] 多租户（如果卖其他机构）
- [ ] 学生端（如果客户要）