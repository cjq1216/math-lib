# 部署与运维手册 (DEPLOYMENT.md)

> 系统：初中数学题库与学情分析系统  
> 版本：v1.2 (R0-R6 里程碑收口版)  
> 适用环境：Windows 10/11 本地开发、Linux (Ubuntu/Debian) 生产服务器、Docker 容器化部署

---

## 1. 架构与运行拓扑

```
                            [客户端浏览器 (教师/管理员)]
                                         │
                                         ▼ HTTPS / HTTP (端口 80/443 或 3000)
                     ┌───────────────────────────────────────┐
                     │     反向代理 (Caddy / Nginx / Next.js)  │
                     └───────────────────┬───────────────────┘
                                         │ 同源转发 /api/v1/ & /static/
                                         ▼
                     ┌───────────────────────────────────────┐
                     │          FastAPI 后端服务 (端口 8000)   │
                     │  - 同步 SQLModel Session (线程池调度)    │
                     │  - Request ID 链路追踪与脱敏日志         │
                     │  - MiniMax 线上 LLM 客户端              │
                     └──────────┬─────────────────┬──────────┘
                                │                 │
                                ▼                 ▼
                     ┌──────────────────┐ ┌──────────────────┐
                     │ SQLite 数据库     │ │ 本地媒体文件存储  │
                     │ data/math_bank.db│ │ data/images/     │
                     └──────────────────┘ └──────────────────┘
```

---

## 2. 软硬件环境要求

| 组件 | 最低配置 | 推荐配置 | 说明 |
|---|---|---|---|
| **操作系统** | Windows 10 / Ubuntu 22.04 LTS | Ubuntu 22.04 LTS / Windows 11 | 支持跨平台 |
| **CPU / 内存** | 2 核 CPU / 4GB RAM | 4 核 CPU / 8GB RAM | 零本地模型权重负担，轻量高效 |
| **磁盘空间** | 10 GB SSD 可用空间 | 50 GB SSD 可用空间 | 满足万道题目与媒体归档 |
| **Python** | Python >= 3.11 | Python 3.11 - 3.14 | 后端开发与运行环境 |
| **Node.js** | Node.js >= 18.18 | Node.js >= 20 LTS | 前端构建与 SSR 渲染 |

---

## 3. 本地开发与单机快速部署

### 3.1 后端服务部署

1. **进入后端目录并创建虚拟环境**：
   ```bash
   cd backend
   python -m venv .venv
   ```

2. **激活虚拟环境**：
   - Windows: `.venv\Scripts\activate`
   - Linux / macOS: `source .venv/bin/activate`

3. **安装依赖**：
   ```bash
   pip install -e ".[dev]"
   ```

4. **初始化环境配置**：
   ```bash
   # Windows
   copy .env.example .env
   # Linux / macOS
   cp .env.example .env
   ```
   *根据实际需要编辑 `.env` 中的 `MINIMAX_API_KEY`。*

5. **执行数据库平滑迁移**：
   ```bash
   alembic upgrade head
   ```

6. **启动后端服务**：
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   *服务健康检查*：`curl http://127.0.0.1:8000/health/ready`

---

### 3.2 前端服务部署

1. **进入前端目录并安装依赖**：
   ```bash
   cd frontend
   npm install
   ```

2. **配置反向代理目标**：
   ```bash
   # Windows
   copy .env.example .env.local
   # Linux / macOS
   cp .env.example .env.local
   ```
   确保 `.env.local` 包含：
   ```dotenv
   API_PROXY_TARGET=http://localhost:8000
   NEXT_PUBLIC_API_BASE=
   ```

3. **生产构建与启动**：
   ```bash
   npm run build
   npm run start
   ```
   *开发模式*：`npm run dev`（访问 `http://localhost:3000`）

---

## 4. 生产环境部署 (Linux + Systemd / PM2)

### 4.1 后端 Systemd 服务托管

创建 `/etc/systemd/system/math-bank-backend.service`：

```ini
[Unit]
Description=Math Bank Backend Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/math-bank/backend
ExecStart=/opt/math-bank/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5
EnvironmentFile=/opt/math-bank/backend/.env

[Install]
WantedBy=multi-user.target
```

启动并启用开机自启：
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now math-bank-backend
sudo systemctl status math-bank-backend
```

### 4.2 前端 PM2 托管

```bash
cd /opt/math-bank/frontend
npm run build
pm2 start npm --name "math-bank-frontend" -- start
pm2 save
pm2 startup
```

### 4.3 Caddy 反向代理与 HTTPS 配置

在 `/etc/caddy/Caddyfile` 中配置：

```caddy
exam.your-institution.com {
    encode gzip zstd

    # 前端主入口
    reverse_proxy 127.0.0.1:3000

    # 后端接口及静态文件代理
    handle_path /api/v1/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle_path /static/* {
        reverse_proxy 127.0.0.1:8000
    }

    log {
        output file /var/log/caddy/math_bank_access.log
    }
}
```

---

## 5. Docker 容器化部署

项目根目录提供完整的容器编排能力：

1. **检查根目录配置**：
   - `docker-compose.yml`
   - `backend/Dockerfile`
   - `frontend/Dockerfile`

2. **启动命令**：
   ```bash
   docker compose up -d --build
   ```

3. **数据持久化卷**：
   - `backend/data/` 挂载于宿主机，保证 `math_bank.db`、`images/`、`logs/` 与 `backups/` 物理留存。

4. **健康探针配置**：
   容器内置 Python 健康检查：
   ```bash
   curl -f http://127.0.0.1:8000/health/ready || exit 1
   ```

---

## 6. 生产安全基线自检清单

- [ ] **密钥安全**：已将 `JWT_SECRET_KEY` 替换为至少 32 位的随机安全字符串；
- [ ] **运行环境**：生产环境已设置 `APP_ENV=production` 且 `APP_DEBUG=false`（自动关闭 `/docs` 与 `/redoc`）；
- [ ] **Cookie 安全**：HTTPS 域名部署时，将 `AUTH_COOKIE_SECURE=true`、`AUTH_COOKIE_SAMESITE=lax`；
- [ ] **首管理员保护**：首次启动后立即完成管理员注册，系统将永久锁定公开注册接口；
- [ ] **健康探针**：监控系统已配置对 `/health/ready`（每分钟轮询）和 `/health/live`（每 10 秒存活探测）；
- [ ] **灾备计划**：配置每日定时热备份任务（参考 `BACKUP_RESTORE.md`）。
