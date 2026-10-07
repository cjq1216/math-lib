# 备份、保留与灾难恢复手册 (BACKUP_RESTORE.md)

> 系统：初中数学题库与学情分析系统  
> 版本：v1.2 (R0-R6 里程碑收口版)  
> 责任角色：系统管理员 / 运维工程师

---

## 1. 核心安全机制与设计原则

### 1.1 为什么禁止直接复制 SQLite 数据库文件？
传统直接拷贝文件（如 `cp math_bank.db backup.db` 或批处理 `copy`）在系统有并发读写或 WAL（Write-Ahead Logging）未合并时，极易造成**快照撕裂（Torn Page）**与数据库不可逆损坏。

本系统采用 SQLite 原生提供的 **`sqlite3.Connection.backup()` 在线热备份 API**：
- **一致性快照**：由 SQLite 引擎内核在事务安全边界内逐页复制；
- **零停机时间**：备份期间不阻断教师组卷、录入题目和批改作业；
- **自检防线**：备份完成后立即自动执行 `PRAGMA integrity_check` 完整性检验。

### 1.2 媒体与数据强一致性打包
数学试卷包含大量几何图形、函数图像与选项图片。单单备份数据库无法保证图题一致。本系统将**数据库热快照**与**本地媒体目录**统一打包为一个独立的 ZIP 归档包。

---

## 2. 备份归档包规格

备份文件默认保存在 `backend/data/backups/` 目录下，文件命名规范为：
```text
math_bank_backup_{YYYYMMDD_HHMMSS}_{short_uuid}.zip
```

### 2.1 归档结构
```text
math_bank_backup_20261007_014045_1e8e364849b9.zip
├── manifest.json        # 备份元数据、SHA256 校验和、媒体统计
├── database.db          # SQLite 完整一致性数据库
└── media/               # 本地媒体文件完整副本
    ├── question_images/
    ├── option_images/
    └── formula_images/
```

### 2.2 清单文件 `manifest.json` 示例
```json
{
  "backup_id": "1e8e364849b9",
  "created_at": "2026-10-07T09:40:45.915000",
  "app_name": "math-bank-backend",
  "app_version": "0.1.0",
  "database_filename": "database.db",
  "database_sha256": "4a1f879b2c34d...789e0",
  "database_size_bytes": 413696,
  "media_file_count": 60,
  "media_total_bytes": 27289,
  "description": "每日定时自动备份",
  "retention_days": 30
}
```

---

## 3. 定时自动备份配置

### 3.1 Linux 环境 (Crontab)

使用系统 cron 每天凌晨 02:00 自动执行热备份并清理过期文件：

```bash
# 打开定时任务编辑
crontab -e

# 添加如下任务（以 /opt/math-bank 为安装目录为例）：
0 2 * * * cd /opt/math-bank/backend && .venv/bin/python -m app.cli.backup create --description "每日定时自动备份" >> /var/log/math_bank_backup.log 2>&1
```

### 3.2 Windows 环境 (任务计划程序)

编写批处理脚本 `C:\math-bank\backend\scripts\cron_backup.bat`：
```bat
@echo off
cd /d E:\work\math-lib\backend
.venv\Scripts\python.exe -m app.cli.backup create --description "每日计划任务自动备份"
```
在 Windows 任务计划程序中配置每日 02:00 触发执行该批处理。

---

## 4. 运维 CLI 工具操作指南

在 `backend` 目录下通过命令行直接调度运维功能：

### 4.1 手动创建备份
```bash
python -m app.cli.backup create --description "考前题库封盘备份"
```
输出示例：
```text
正在创建系统数据与媒体完整备份...
备份成功！
文件名: math_bank_backup_20261007_094045_1e8e364849b9.zip
ID: 1e8e364849b9
大小: 35840 字节
数据库 SHA256: 4a1f879b...
媒体文件数: 60
```

### 4.2 查询历史备份
```bash
python -m app.cli.backup list
```
输出示例：
```text
共发现 3 个备份：
文件名                                        | 大小(KB)   | 时间                 | 状态
------------------------------------------------------------------------------------------
math_bank_backup_20261007_094045_1e8e.zip     | 35.0       | 2026-10-07T09:40:45  | valid
math_bank_backup_20261006_020000_8ab1.zip     | 34.8       | 2026-10-06T02:00:00  | valid
math_bank_backup_20261005_020000_92c3.zip     | 34.5       | 2026-10-05T02:00:00  | valid
```

### 4.3 强制保留策略清理
系统在每次生成备份时会自动执行清理；亦可手动触发：
```bash
python -m app.cli.backup cleanup
```
*保留策略规则*：
- 保留最长天数：由 `.env` 的 `BACKUP_RETENTION_DAYS` 配置（默认 30 天）；
- 最大备份数量：由 `.env` 的 `BACKUP_MAX_COUNT` 配置（默认 20 个）；
- 核心保底：**无论任何情况下，始终保留最新的 1 个完整备份**。

### 4.4 从备份执行数据恢复
```bash
python -m app.cli.backup restore math_bank_backup_20261007_094045_1e8e.zip --confirm
```

---

## 5. 管理端系统 API 接口说明

所有系统备份 API 均强制 `require_admin` 角色鉴权，写操作全量写入 `AuditLog`。

| 方法 | 接口路径 | 说明 | 权限 |
|---|---|---|---|
| `POST` | `/api/v1/system/backup` | 创建新备份归档包 | 管理员 |
| `GET` | `/api/v1/system/backups` | 获取历史备份清单列表 | 管理员 |
| `GET` | `/api/v1/system/backups/{filename}/download` | 下载指定的备份 ZIP 包 | 管理员 |
| `POST` | `/api/v1/system/restore` | 执行覆盖恢复（需 `confirm=true`） | 管理员 |
| `DELETE` | `/api/v1/system/backups/{filename}` | 安全删除指定备份归档 | 管理员 |

---

## 6. 灾难恢复标准作业程序 (SOP)

### 场景：人为误删题目 / 硬件故障需要还原数据

1. **第 1 步：确认待恢复的目标备份**
   ```bash
   python -m app.cli.backup list
   ```
   定位到发生故障前的最后一个有效备份文件名。

2. **第 2 步：执行原子覆盖还原**
   ```bash
   python -m app.cli.backup restore math_bank_backup_xxxx.zip --confirm
   ```

3. **第 3 步：内部恢复防线保障**
   - **自检**：解压后首先对 `database.db` 计算 SHA256 并与 `manifest.json` 对比；执行 `PRAGMA integrity_check`；
   - **预备份**：在覆盖前，系统会自动将当前的损坏/待替换数据库另存为：
     `data/math_bank_prerestore_{YYYYMMDD_HHMMSS}.db`
     确保在发生恢复二次事故时随时回滚；
   - **覆盖**：原子覆盖数据库文件并解压恢复全部关联媒体图片。

4. **第 4 步：服务状态确认**
   ```bash
   curl http://127.0.0.1:8000/health/ready
   ```
   验证响应返回 `{"status": "ready"}` 且数据库与存储检查全绿。
