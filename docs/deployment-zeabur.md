# Zeabur 部署（v0.3.0-alpha.2 RC）

拓扑（与 `docker-compose.prod.yml` 一致）：

```
浏览器 → Frontend（公网域名，Next.js standalone）
           └─ 运行期 Route Handler 代理（仅白名单 /api/v1/* 路径）
                → Backend（仅私有网络，不绑定公网域名）
                → Worker（独立私有服务，无公网端口）
                     → PostgreSQL / Redis（私有网络）
```

安全要点：

- **Backend 不配置公网域名。** Research API 尚未做连接级 IP pinning
  （ADR-0026），匿名公网暴露是已知阻塞；私有网络 + 前端白名单代理是当前
  唯一批准的暴露方式。
- 浏览器只请求同源 `/api/...`；`BACKEND_INTERNAL_URL` 是**服务端**变量，
  绝不能带 `NEXT_PUBLIC_` 前缀。
- 白名单路径见 `apps/frontend/src/app/api/v1/[...path]/route.ts`，无任意 URL
  代理。

## Zeabur 控制台步骤

1. 创建项目，添加 **PostgreSQL** 与 **Redis** 服务（记下私网连接串）。
2. 添加 **Backend** 服务：Git 部署本仓库，Root Directory `apps/backend`，
   Dockerfile target `prod`。**不要**为它绑定公网域名。
   环境变量（Service → Variables）：
   - `APP_ENV=production`
   - `DATABASE_URL=`（Zeabur Postgres 私网串）
   - `REDIS_URL=`（Zeabur Redis 私网串）
   - `RESEARCH_EXTRACTOR_PROVIDER=deepseek`
   - `RESEARCH_MODEL=deepseek-v4-pro`
   - `DEEPSEEK_API_KEY=`（Secret）
   - `DEEPSEEK_BASE_URL=https://api.deepseek.com`
   - `EMAIL_GENERATOR_PROVIDER=fake`
   - `BACKEND_CORS_ORIGINS=["https://<你的前端域名>"]`
3. 添加 **Worker** 服务：同样使用 Root Directory `apps/backend` 与
   Dockerfile target `prod`，启动命令为
   `uv run --no-dev python -m app.worker`。复制 Backend 的数据库、Redis、
   Research 与 Email Provider 变量；**不要绑定公网域名或端口**。D3a 使用
   PostgreSQL Job/Lease，不把 Redis 当任务队列。
4. 添加 **Frontend** 服务：Root Directory `apps/frontend`，Dockerfile
   target `prod`，绑定公网域名。
   构建变量：`NEXT_PUBLIC_ENABLE_RESEARCH=true`。
   运行变量：`BACKEND_INTERNAL_URL=http://<backend 服务名>.zeabur.internal:8000`。
5. Backend 首次启动后在其终端执行一次迁移：
   `uv run --no-dev alembic upgrade head`。
6. 线上 smoke：打开前端域名 → Provider 徽章显示 deepseek →
   对一家公司跑通 研究 → 确认 → 分析 → 草稿 → 刷新恢复。
   另验证创建批次后 API 返回 202，Worker 服务领取 Job，停止并重启 Worker
   后过期 lease 能恢复，且 Backend 的查询接口在 Worker 停止时仍可读取。
   浏览器直接访问 `https://<前端域名>/api/v1/health/runtime` 应返回 JSON
   且**不含**任何密钥；backend 无公网地址可访问。

本地演练：`docker compose -f docker-compose.prod.yml --env-file .env.production up --build`。

Smoke 通过后才创建 tag `v0.3.0-alpha.2`。
