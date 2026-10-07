# D5a1 Bulk Import Foundation Report

## 1. 实现结论

D5a1 已实现“网易 CSV → ImportSession → RawImportRow → 行级校验/重复标记 →
统计 → 刷新恢复”的独立原始数据导入链路。

本轮只保存 Raw Intake，不创建或更新 Company、Contact、Import Evidence、
Opportunity、Research、ProspectBatch、Outreach 或 Draft，不调用 Provider、LLM，
也不会发送邮件。

超过 20 MB、超过 20,000 数据行、空文件、非法表头、不可解析 CSV 或不支持的编码，
统一在创建 ImportSession 前返回结构化 422。选择“不创建 failed Session”的原因是：
这些属于请求级预检拒绝，没有任何有效 Raw Intake 需要恢复；避免数据库累积大量零行失败记录。

## 2. Git 分支、Commit、PR

- 基线：`main@05a9b2a`，实现前 `main == origin/main`。
- 分支：`feat/netease-bulk-import-foundation`。
- Commit：本报告随 feature `HEAD` 以
  `feat(import): add traceable bulk CSV intake` 提交；不可自引用的最终 SHA 以 PR head 为准。
- PR：目标 `main`，标题
  `feat(import): add traceable NetEase bulk CSV intake`；PR URL 在推送后创建并由最终交付回复提供。
- PR #4 和 `feat/real-prospect-calibration-mvp` 未修改、未合并、未关闭、未 cherry-pick。

## 3. 修改文件分类

### Backend Domain / Persistence

- `app/domain/bulk_import/`：ImportSession、RawImportRow、状态和不变量。
- `app/database/models/bulk_import.py`：两个 SQLAlchemy 模型。
- `app/database/mappers/bulk_import.py`：显式 Domain/ORM Mapper。
- `app/database/repositories/bulk_import.py`：Session 查询、幂等查询、批量写入和 Raw 行分页。
- `app/database/uow.py`、`app/domain/repositories.py`：Bulk Import Repository/UoW 端口接入。
- `app/database/migrations/versions/d5a1c2d3e4f5_add_bulk_import_foundation.py`：独立后继 Migration。

### Backend Application / API

- `app/services/bulk_import/csv_intake.py`：标准库 csv、流式预检、编码检测、行校验和批次生成。
- `app/workflows/bulk_import/`：同步 HTTP 生命周期内的 Session 创建、每 500 行提交、终态统计。
- `app/schemas/bulk_import.py`：API typed schemas。
- `app/api/routes/bulk_import.py`：独立 Import Session API。
- `app/api/deps.py`、`app/api/router.py`：依赖注入和路由注册。
- `specs/workflow.yaml`：声明 D5a1 边界、状态和限制。

### Frontend / E2E

- `src/features/bulk-import/`：独立“批量导入”面板。
- `src/lib/api.ts`：Import Session 和 Raw Row typed client。
- `src/app/page.tsx`：通过 `import_session_id` 恢复。
- `src/lib/i18n.tsx`：中英文导入文案。
- `e2e/tests/bulk-import.spec.ts`：上传和刷新恢复 Playwright 用例。

### Tests / CI

- Domain、CSV parser、PostgreSQL API、10,000 行性能和 Migration 测试。
- PR workflow 增加 D5a1 测试、修改文件 strict mypy 和 Frontend lint。

## 4. 数据库模型和约束

### ImportSession

字段包括：id、source、original_filename、file_type、file_size_bytes、file_sha256、
mapping_json、encoding、status、total/accepted/invalid/duplicate_rows、started_at、
completed_at、error_summary、created_at、updated_at。

约束：

- `UNIQUE(source, file_sha256)`：同源同文件只保留一个 Session。
- 状态 CHECK：receiving、processing、completed、partial_failed、failed。
- 行数均非负，且 accepted + invalid + duplicate 必须等于 total。
- `(status, created_at)` 索引。

重复上传返回既有 Session 和 HTTP 200；首次创建返回 HTTP 201。选择返回现有 Session，
而不是 409，是为了让浏览器刷新、重试和网络不确定场景天然幂等。

### RawImportRow

字段包括：id、import_session_id、row_number、raw_payload JSONB、row_hash、status、
error_codes JSONB、created_at。

约束：

- `UNIQUE(import_session_id, row_number)`。
- `(import_session_id, status)` 索引。
- `(import_session_id, row_hash)` 索引，但 row_hash 不全局唯一。
- Session 删除时 Raw 行 CASCADE；不关联任何既有业务实体。
- 重复行仍完整保存，状态为 duplicate；错误行完整保存，状态为 invalid。

`raw_payload` 保存原字段名到原值的映射、原始值顺序，以及缺失或额外列信息。
用户 Mapping 保存在 Session 中，不覆盖原始字段。

## 5. API 示例

### 创建 Session

```http
POST /api/v1/import-sessions
Content-Type: multipart/form-data

file=@synthetic.csv
source=netease_foreign_trade
mapping={"company_name":"公司名称","contact_email":"邮箱"}
```

响应包含 session_id、status、行数统计、encoding、时间和 `reused_existing`。

### 读取 Session

```http
GET /api/v1/import-sessions/{session_id}
```

### 分页读取 Raw 行

```http
GET /api/v1/import-sessions/{session_id}/rows?page=1&limit=50&status=invalid
```

page 从 1 开始；limit 为 1–200；status 可为 accepted、invalid 或 duplicate。
所有错误使用 `{code, message, request_id}`。

## 6. 前端流程

1. 在现有工作台顶部进入独立“批量导入”。
2. 选择 CSV；source 固定显示为 `netease_foreign_trade`。
3. 可选输入“逻辑字段 → CSV 列名”的 JSON Mapping。
4. 上传期间显示处理中状态。
5. 返回 Session 后展示总行、有效、错误、重复统计。
6. URL 写入 `import_session_id`；刷新后重新 GET Session 和 Raw 行。
7. 支持 Raw 行状态筛选和分页。

页面固定显示：

> 本步骤仅完成原始数据导入和质量检查，尚未进行公司归并、机会评分或邮件发送。

没有新增 A/B/C/D、ProspectBatch、Research、Draft 或 Umail 操作入口。

## 7. 10,000 行性能结果

测试环境：本地 Python 3.12、Docker PostgreSQL 16、FastAPI ASGI test client，
合成 CSV，不包含真实网易或联系人数据。

| 指标 | 结果 |
|---|---:|
| 文件大小 | 437,602 bytes |
| 数据行 | 10,000 |
| 总耗时 | 2.014 秒 |
| tracemalloc 峰值内存 | 7,411,289 bytes（约 7.07 MiB） |
| accepted | 9,990 |
| invalid | 5 |
| duplicate | 5 |
| PostgreSQL Raw 行 | 10,000 |
| 新增 Company/Opportunity/Research/Outreach | 0 / 0 / 0 / 0 |

实现不会调用 `file.read()` 读取全部内容：字节扫描固定 64 KiB，CSV 逐行生成，
每 500 行形成一个数据库写入事务。

## 8. 测试与 Migration 结果

| 门禁 | 结果 |
|---|---|
| D5a1 定向 pytest | 16 passed in 8.17s |
| Domain purity | 1 passed |
| UTF-8-SIG / GB18030 | 通过 |
| 重复上传幂等 | 通过，返回既有 Session |
| 文件内重复行保存并标记 | 通过 |
| 错误行隔离 | 通过 |
| 空文件 / 20 MB / 20,000 行限制 | 通过 |
| API 分页 / status 过滤 | 通过 |
| PostgreSQL 真实 API 集成 | 3 passed |
| 10,000 行性能测试 | 1 passed |
| upgrade → downgrade → upgrade | 通过；2 tests passed |
| D5a1 downgrade 保留旧 Company 数据 | 通过 |
| Alembic head | `d5a1c2d3e4f5`，单 head |
| `alembic check` | No new upgrade operations detected |
| Ruff 全仓 | 通过 |
| 本轮 16 个修改文件 strict mypy | 通过 |
| 全 `mypy app tests --strict` | 已运行；被历史无关错误阻断：entity_resolver 未显式 re-export normalize_company_name |
| Frontend TypeScript | 通过 |
| Frontend lint | 通过；仅 5 条既有 candidate-cards warning，无 error |
| Frontend production build | 通过 |
| Playwright 刷新恢复 | 1 passed in 2.2s |

按照任务要求没有运行 900+ 全量 pytest。全量 mypy 的单个历史错误不在本轮文件中，
且当前 PR workflow 不依赖该历史导出；未越界修改 Import Evidence 代码。

## 9. 安全检查

- 未读取或输出 `.env` 具体值。
- 未提交真实网易文件、真实邮箱、日志、截图、Playwright trace 或缓存。
- 测试全部使用合成数据。
- 应用代码不记录 raw_payload、联系人邮箱或上传文件内容。
- 处理失败只持久化通用 `bulk_import_processing_failed`，不保存异常中的上传内容。
- API 全程未触发 Research、Provider、Opportunity、Draft 或付费 LLM。

## 10. 技术选型及选择理由

### 标准库 csv + 多遍流式预检

选择：固定大小字节扫描完成文件大小、SHA-256 和编码校验；第二遍验证 CSV/行数；
第三遍逐行生成批次。

理由：在不保留完整文件的情况下，能够在创建 Session 前确定大小、编码、表头和行数，
满足“超限制不创建有效 Session”。

### 每 500 行一个事务

选择：Session 创建、processing 状态、每个 500 行批次、终态各自通过明确 UoW 提交。

理由：避免逐行 commit，同时让处理中 Session 和已完成批次可在 HTTP 中断后被查询。

### 同源同哈希返回既有 Session

理由：上传重试和页面刷新是正常操作，返回现有资源比 409 更适合浏览器工作流；数据库
唯一约束仍负责处理并发竞争。

### 同步 HTTP 执行

理由：本轮无外部 HTTP、Research、LLM；10,000 行实测约 2 秒，暂不需要 Worker，
也不污染 ProspectJob 的深度处理语义。

## 11. 没选替代方案的理由

- 未使用 pandas：会引入非必要依赖并倾向整表内存加载。
- 未接 Worker/ProspectJob：Raw Intake 没有深度业务或外部调用，当前耗时不支持增加队列复杂度。
- 未使用 Celery/Kafka/Redis Queue：超出 MVP 且没有当前负载证据。
- 未扩展 Discovery CSV：Discovery 的 prompt/candidate/Company ingestion 语义与 Raw Intake 不同。
- 未写 Company/Contact/Evidence：D5a1 明确只建立可追溯 Raw 基础设施。
- 未实现 XLSX：属于后续 D5a，不在当前切片。
- 未为每种网易列名写死规则：真实列名未知，使用显式 Mapping，且不覆盖用户提交配置。

## 12. 本轮新增技术债

### 导入仍依赖 HTTP 生命周期

允许原因：当前 10,000 行本地实测约 2 秒，没有外部服务调用；后台化会提前引入恢复、
调度和进度协议。

偿还触发条件：真实文件超过 20,000 行、p95 超过 15 秒，或出现并发上传需求时，
迁移到独立 Background Worker；不得复用 ProspectJob 业务语义。

### 文件需要多遍扫描

允许原因：20 MB 上限内 I/O 成本低，并换取创建 Session 前的确定性拒绝和幂等检查。

偿还触发条件：文件规模显著扩大、对象存储接入，或预检 I/O 成为实际性能热点。

### processing Session 不自动续跑

允许原因：本轮只要求刷新读取恢复，不要求 HTTP 崩溃后的自动续传；已提交的 500 行批次
仍可审计，Session 会保持 processing 或被当前请求标记 failed。

偿还触发条件：出现真实中断案例、需要自动续跑，或迁移后台 Worker 时。

### 不保存原始二进制文件

允许原因：SHA-256、原始字段和值、行号已经满足当前审计和重放基础；避免数据库存 Blob。

偿还触发条件：出现合规要求、需要逐字节复核原文件，或接入对象存储。

## 13. 未完成事项

- XLSX。
- Company entity resolution。
- Contact / CompanyContact。
- Import Evidence Canonical promotion。
- Pre-Score、A/B/C/D、ProspectBatch。
- Umail 导出与回传。
- 自动续跑或后台导入。
- 真实网易列名模板和生产数据验证。
- 历史全量 mypy 中 `normalize_company_name` 显式导出问题；不属于 D5a1，未越界修复。

## 14. D5b 建议（不在本轮实施）

D5b 应只消费已完成或 partial_failed 的 ImportSession/RawImportRow，增加：

1. CompanyExternalIdentity 的 `(source, external_id)` 唯一身份。
2. 确定性的公司高/中/低置信归并规则。
3. Contact person identity 与 CompanyContact 任职关系。
4. ImportEntityDecision 人工复核队列。
5. 所有 Canonical 关系保存 `import_session_id/raw_row_id` 来源。

D5b 不应直接加入 Pre-Score、A/B/C/D 或 Umail；先证明同一网易文件和增量文件不会重复创建
Company/Contact，再进入 D5c。
