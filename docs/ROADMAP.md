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

### 待补（MVP 第二批）
- [ ] **针对性出题加权排序**（算法优化）
- [ ] **题目列表分页 + 批量操作**
- [ ] **Refresh Token** 实现
- [ ] **Excel 导入结构化错误反馈**
- [ ] **审计日志中间件**

---

## 第二批（3-4 周）

### 文档导入
- [ ] Word (.docx) 解析（python-docx）
- [ ] PDF 解析（PyMuPDF / PaddleOCR）
- [ ] LaTeX-OCR（pix2tex）公式识别
- [ ] 校对界面（左右对照）

### 多格式导出
- [ ] Typst 集成（PDF 导出）
- [ ] Word 导出优化（公式 → OMML）
- [ ] 试卷排版模板

### 智能增强
- [ ] 相似题推荐（向量检索）
- [ ] 卷内雷同检测
- [ ] 历史卷相似度
- [ ] AB 卷生成

### 运维
- [ ] 自动备份脚本（cron）
- [ ] 数据看板（管理员视角）
- [ ] 移动端响应式优化
- [ ] 监控告警（基础）

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