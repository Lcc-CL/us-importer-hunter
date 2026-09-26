# 生产部署（平台无关）

部署只依赖 Docker 镜像和环境变量，不绑定任何托管平台。可以部署到任意一台
装有 Docker 的 Linux 服务器，也可以部署到任何能跑 Dockerfile 的容器平台，
平台之间随时切换，只需要把同一组环境变量搬过去。

拓扑（与 `docker-compose.prod.yml` 一致）：

```
浏览器 → Frontend（唯一公网入口，Next.js standalone，访问口令保护）
           └─ 运行期 Route Handler 代理（仅白名单 /api/v1/* 路径）
                → Backend（仅私有网络，不暴露端口）
                → Worker（独立进程，无端口）
                     → PostgreSQL / Redis（私有网络，或托管服务）
```

安全要点：

- **Backend 不对公网暴露。** Research API 尚未做连接级 IP pinning
  （ADR-0026），匿名公网暴露是已知阻塞；私有网络 + 前端白名单代理是当前
  唯一批准的暴露方式。
- 浏览器只请求同源 `/api/...`；`BACKEND_INTERNAL_URL` 是**服务端**变量，
  绝不能带 `NEXT_PUBLIC_` 前缀。
- 白名单路径见 `apps/frontend/src/app/api/v1/[...path]/route.ts`，无任意 URL
  代理。`research` 不在白名单内：Research API 不经前端代理对外暴露。
- 整个前端（含 `/api/v1` 代理）由访问口令保护（`apps/frontend/src/proxy.ts`，
  HTTP Basic，用户名任意，密码为 `FRONTEND_ACCESS_PASSWORD`）。生产环境未设置
  该变量时所有请求返回 503（fail closed）。
- 真实密钥只放在服务器上的 `.env.production`（已被 git 忽略）或平台的
  Secret 变量里，绝不提交。

## 方式一：任意 Linux 服务器（Docker Compose，推荐）

前置条件：Docker Engine 24+ 与 Compose v2 插件；服务器能 `git clone` 本仓库
（私有仓库请给服务器配只读 Deploy Key）。

首次部署：

```bash
git clone git@github.com:Lcc-CL/us-importer-hunter.git
cd us-importer-hunter
cp .env.production.example .env.production
# 编辑 .env.production：至少填写 POSTGRES_PASSWORD、FRONTEND_ACCESS_PASSWORD、
# FRONTEND_ORIGIN，以及所用 Provider 的 API Key
./scripts/deploy.sh
```

`scripts/deploy.sh` 依次执行：拉取目标版本 → 构建镜像 → 运行 Alembic 迁移 →
启动全部服务 → 等待 backend / worker / frontend 健康检查通过，任何一步失败
都会以非零退出码结束。

日常更新与回滚：

```bash
./scripts/deploy.sh                      # 部署 origin/main 最新提交
DEPLOY_REF=<tag 或 commit> ./scripts/deploy.sh   # 部署指定版本（回滚）
SKIP_PULL=1 ./scripts/deploy.sh          # 按当前工作区部署，不拉代码
make prod-ps / make prod-logs / make prod-down
```

注意回滚只回退代码；如果新版本已经跑过数据库迁移，需要先确认旧版本兼容新
schema，必要时手动 `alembic downgrade`。

### HTTPS 与反向代理

前端容器默认监听 `0.0.0.0:3000`。建议在同机放一个反向代理终止 TLS，并在
`.env.production` 中设置 `FRONTEND_BIND=127.0.0.1`，让 3000 端口只对本机开放。
Caddy 示例（自动申请证书）：

```
hunter.example.com {
    reverse_proxy 127.0.0.1:3000
}
```

Nginx 示例：

```nginx
server {
    listen 443 ssl;
    server_name hunter.example.com;
    # ssl_certificate / ssl_certificate_key …
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

`FRONTEND_ORIGIN` 填最终的公网地址（如 `https://hunter.example.com`）。

### 使用托管数据库

在 `.env.production` 中设置 `DATABASE_URL` / `REDIS_URL` 后，backend 与 worker
会优先使用它们（`postgres://`、`postgresql://` 会自动转换为 asyncpg 方案）；
compose 自带的 postgres/redis 容器仍会启动但不再被使用。

## 方式二：GitHub Actions 自动部署

`.github/workflows/deploy.yml` 在每次推送 `main`（或手动触发）时通过 SSH 登录
服务器，执行 `DEPLOY_REF=<本次提交> ./scripts/deploy.sh`。未配置时整个 job
自动跳过，不会报错。先按方式一完成首次部署，再在仓库
Settings → Secrets and variables → Actions 中添加：

| 类型 | 名称 | 内容 |
|---|---|---|
| Variable | `DEPLOY_HOST` | 服务器地址（设置后即启用自动部署） |
| Variable | `DEPLOY_USER` | SSH 用户（需能执行 docker） |
| Variable | `DEPLOY_PATH` | 服务器上仓库目录的绝对路径 |
| Variable | `DEPLOY_PORT` | SSH 端口，可选，默认 22 |
| Secret | `DEPLOY_SSH_KEY` | 该用户的 SSH 私钥（建议专用密钥） |
| Secret | `DEPLOY_KNOWN_HOSTS` | `ssh-keyscan -p <端口> <服务器>` 的输出，用于校验主机指纹 |

要暂停自动部署，删除 `DEPLOY_HOST` 变量即可。

## 方式三：任意容器平台

任何支持 Dockerfile 的平台都可以，按下表建 3 个服务（外加平台提供的
PostgreSQL 16 与 Redis 7）：

| 服务 | 构建 | 启动命令 | 公网 |
|---|---|---|---|
| backend | `apps/backend`，target `prod` | 镜像默认 | **否** |
| worker | `apps/backend`，target `prod` | `uv run --no-dev python -m app.worker` | 否 |
| frontend | `apps/frontend`，target `prod` | 镜像默认 | 是，端口 3000 |

- backend 与 worker 使用同一组变量：`APP_ENV=production`、`DATABASE_URL`、
  `REDIS_URL`、Research 与 Email Provider 变量（见 `.env.production.example`），
  以及 `BACKEND_CORS_ORIGINS=["https://<前端域名>"]`。
- frontend 构建变量 `NEXT_PUBLIC_ENABLE_RESEARCH=false`；运行变量
  `BACKEND_INTERNAL_URL=http://<backend 私网地址>:8000` 和
  `FRONTEND_ACCESS_PASSWORD`（Secret）。
- 首次启动及每次升级后，在 backend 中执行一次迁移：
  `uv run --no-dev alembic upgrade head`。

## 上线 smoke

1. 打开前端地址 → 浏览器弹出口令框，输入 `FRONTEND_ACCESS_PASSWORD` →
   Provider 徽章显示正确的 Provider → 对一家公司跑通 分析 → 草稿 → 刷新恢复。
2. 创建批次后 API 返回 202，Worker 领取 Job；停止并重启 Worker 后过期 lease
   能恢复，且 Backend 的查询接口在 Worker 停止时仍可读取。
3. 未带口令访问 `https://<前端地址>/api/v1/health/runtime` 应返回 401；
   带口令访问应返回 JSON 且**不含**任何密钥；`/api/v1/research/...` 应返回
   404；backend 没有可从公网访问的地址。
