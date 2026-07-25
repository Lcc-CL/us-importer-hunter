# Zeabur 部署（v0.3.0-alpha.2 RC）

拓扑（与 `docker-compose.prod.yml` 一致）：

```
浏览器 → Frontend（公网域名，Next.js standalone）
           └─ 服务端 rewrites 代理（仅白名单 /api/v1/* 路径）
                → Backend（仅私有网络，不绑定公网域名）
                     → PostgreSQL / Redis（私有网络）
```

安全要点：

- **Backend 不配置公网域名。** Research API 尚未做连接级 IP pinning
  （ADR-0026），匿名公网暴露是已知阻塞；私有网络 + 前端白名单代理是当前
  唯一批准的暴露方式。
- 浏览器只请求同源 `/api/...`；`BACKEND_INTERNAL_URL` 是**服务端**变量，
  绝不能带 `NEXT_PUBLIC_` 前缀。
- 白名单路径见 `apps/frontend/next.config.ts`：`health/runtime`、
  `research/*`、`mvp/*`、`companies/*`，无任意 URL 代理。

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
3. 添加 **Frontend** 服务：Root Directory `apps/frontend`，Dockerfile
   target `prod`，绑定公网域名。
   构建变量：`NEXT_PUBLIC_API_BASE_URL=`（留空 → 同源）、
   `NEXT_PUBLIC_ENABLE_RESEARCH=true`。
   运行变量：`BACKEND_INTERNAL_URL=http://<backend 服务名>.zeabur.internal:8000`。
4. Backend 首次启动后在其终端执行一次迁移：
   `uv run --no-dev alembic upgrade head`。
5. 线上 smoke：打开前端域名 → Provider 徽章显示 deepseek →
   对一家公司跑通 研究 → 确认 → 分析 → 草稿 → 刷新恢复。
   浏览器直接访问 `https://<前端域名>/api/v1/health/runtime` 应返回 JSON
   且**不含**任何密钥；backend 无公网地址可访问。

本地演练：`docker compose -f docker-compose.prod.yml --env-file .env.production up --build`。

Smoke 通过后才创建 tag `v0.3.0-alpha.2`。
