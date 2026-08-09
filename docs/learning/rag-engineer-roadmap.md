# US Importer Hunter — RAG Engineer Learning Roadmap

日期：2026-08-08
适用项目：US Importer Hunter Evidence-Grounded RAG 0→1
学习目标：Leo 能解释、实现、评估和审计项目中的 RAG，而不是只会调用向量数据库 SDK

---

## 0. 使用方式

本路线按项目真实交付顺序组织。学习阶段 `L1–L12` 与开发报告中的 `R1–R9` 有关联，
但不是一一同名：学习先建立原理，再进入对应实现。

| 学习阶段 | 主要对应开发阶段 |
| --- | --- |
| L1 RAG Fundamentals | R0/R1 |
| L2 Ingestion | R1 |
| L3 Chunking | R1/R2 |
| L4 Embeddings | R2 |
| L5 pgvector | R2/R3 |
| L6 Retrieval | R3 |
| L7 Hybrid Search | R5 |
| L8 Reranking | R6 |
| L9 Grounded Generation | R4 |
| L10 Evaluation | R1–R7 横切 |
| L11 Observability | R3–R8 横切 |
| L12 Agentic RAG | R9，非 MVP |

学习纪律：

1. 每阶段先写自己的答案，再让 Codex review；禁止先复制标准答案。
2. 每个实验必须保存输入、配置、输出和结论，不能只截图“跑通了”。
3. 默认实验使用 fixture、Fake Provider 或本地预计算数据，不调用真实付费 API。
4. 不读取、粘贴、记录真实 API Key。
5. 任何实验不得修改 deterministic CSV 清洗、Entity Resolution、Routing、Suppression。
6. 每个阶段至少能用 US Importer Hunter 的真实类和边界解释一次，而不是只讲通用术语。
7. 进入下一阶段前完成验收；不会解释的代码不算学会。

建议为每阶段建立学习记录：

```text
docs/learning/notes/Lxx-<topic>-notes.md
```

记录至少包含：我的解释、实验、失败、指标、仍不理解的问题。本文档只定义路线，本轮不创建
这些阶段笔记。

---

## L1 — RAG Fundamentals

### 必须理解的原理

- RAG 是“检索 + 上下文约束 + 生成 + 验证”的系统，不等于 embedding/vector search。
- Parametric knowledge、curated knowledge、company evidence、deterministic facts 的区别。
- Retrieval quality 和 generation quality 是两个不同问题；好答案不能证明检索正确。
- Grounding、citation、provenance、faithfulness、answerability 的区别。
- US Importer Hunter 中 Company 保存事实、Opportunity 保存判断；RAG Claim 在人工审核前
  既不是 Company fact，也不是 Opportunity judgment。
- deterministic pipeline 与 probabilistic research pipeline 必须分开。

### 必须自己回答的问题

1. 为什么不能用 LLM 代替 Entity Resolution 或 Prospect Routing？
2. 为什么“模型给出了 URL”不能证明引用真实？
3. 为什么 `apps/backend/knowledge/` 的行业知识不能证明某家公司正在进口？
4. 当前 `ClaimValidator` 已经解决了哪些 hallucination 问题，又没解决哪些？
5. 为什么 A Tier 每批 5 家的限制对 RAG 容量规划很重要？

### 必须自己执行的小实验

用三段手写文本模拟：Company A 官网、Company B 官网、行业通用知识。人工构造一个问题，
分别执行：

1. 不检索直接回答。
2. 把三段全部放进上下文回答。
3. 只放 Company A evidence 回答。

逐条标注答案中的 atomic claims：supported、unsupported、wrong-company、general knowledge。
写出为什么“上下文更多”可能反而更危险。

### Codex 可以实现什么

- 生成离线 fixture 和实验 runner。
- 检查项目中的 Domain/Workflow/Repository 边界。
- 为 Leo 的解释指出概念混淆。
- 生成 deterministic citation checker，但不替 Leo 判断业务语义。

### Leo 必须亲自理解什么

- 事实、判断、建议在产品中的不同法律和业务风险。
- 哪类错误会导致销售人员向错误公司发送错误信息。
- 为什么 Evidence Review 是产品能力，不是“模型不够好”的临时补丁。

### 面试问题

1. RAG 与 fine-tuning 分别解决什么问题？
2. 一个 RAG 答案有正确 citation，为什么仍可能不 faithful？
3. 如何设计一个系统，使模型不能引用 Company B 的 chunk 回答 Company A？
4. Retrieval、Context Building、Generation、Validation 各自的责任是什么？
5. 什么情况下不应该使用 RAG？

### 验收标准

- 能在 5 分钟内画出本项目 deterministic path 与 RAG path，且没有交叉越权。
- 能用当前 `ResearchRun → ResearchClaim → ResearchPromotion → Company` 解释 grounding。
- 能独立指出至少 5 种“答案看起来正确但证据链错误”的情况。
- 完成实验记录，所有 atomic claims 有分类。

---

## L2 — Document Ingestion

### 必须理解的原理

- Source discovery、fetch、clean、normalize、dedup、version、provenance 是不同阶段。
- URL identity 不等于 content identity；同一 URL 会变化，不同 URL 可能内容相同。
- immutable document version 能让历史 Claim citation 可复现。
- content hash、canonical URL、ETag/Last-Modified 各自能证明什么、不能证明什么。
- failed fetch 是一次 attempt，不应伪造为空 Document。
- 抓取第三方内容必须考虑 SSRF、private IP、redirect、robots、size/decompression budget。

### 必须自己回答的问题

1. 为什么不能每次 Research 都覆盖旧页面 content？
2. 同一个 URL 内容变化后，旧 Claim 应指向哪个版本？
3. 两个 URL 的 cleaned content hash 相同，应怎样 dedup 又保留 provenance？
4. 为什么项目只保存 cleaned text，而不默认保存 raw HTML？
5. `ResearchPage` 与 `ResearchDocument` 的职责如何区分？

### 必须自己执行的小实验

准备四个本地 HTML fixtures：

- 同 URL 同内容。
- 同 URL 修改一段内容。
- 不同 URL 同内容。
- 含 script、隐藏文本和 prompt injection 的页面。

运行现有 cleaner，计算 raw hash 与 cleaned hash，手工设计每次 ingestion 应产生的
Document/version/dedup 结果。验证 injection 文本是否会进入 cleaned content，并记录理由。

### Codex 可以实现什么

- R1 的 Document aggregate、mapper、repository、fixtures 和 migration。
- 复用 SafeFetcher/URL Guard，添加 idempotency tests。
- 生成 refresh/change matrix 和 database constraints。

### Leo 必须亲自理解什么

- 为什么 immutable version 比简单 `updated_at` 更适合审计。
- 哪些来源值得 first-party/authoritative/unverified trust level。
- 哪些内容不应长期保存，以及保留策略如何影响产品风险。

### 面试问题

1. 如何设计幂等网页 ingestion pipeline？
2. URL canonicalization 有哪些陷阱？
3. content hash 去重会丢失哪些 provenance？
4. 如何处理成功抓取但内容为空、过薄或被 JavaScript 渲染的页面？
5. 如何防止 SSRF 与 redirect 绕过？

### 验收标准

- 能设计同内容、变更内容、失败抓取、重复 URL 的状态转换表。
- 能解释现有 `SafeFetcher` 的所有关键预算和边界。
- 能说明为什么 R1 不需要 pgvector。
- 实验包含 hash、cleaned output、预期 Document 行和安全结论。

---

## L3 — Chunking

### 必须理解的原理

- chunk 是 retrieval unit，不是任意字符切片。
- chunk 太大降低 precision、增加 token；太小丢失语义和 citation 可读性。
- overlap 能补边界，但会制造重复召回、成本和 context domination。
- fixed token、recursive、semantic、structure-aware 的适用面和可复现性。
- heading path、page number、offset、chunker version 是 citation/debug 的一部分。
- 不同来源必须采用不同结构规则；贸易证据不能按网页段落逻辑处理。

### 必须自己回答的问题

1. 为什么 `chunk_size=1000` 不是设计？
2. About 页面与 Product catalog 的结构边界有什么不同？
3. 如何避免一个 footer 在几十个页面中重复成为高频 chunk？
4. PDF 跨页句子和表格应该如何处理？
5. 为什么 semantic chunking 不适合本项目第一版？

### 必须自己执行的小实验

从 fixture 选择 Homepage、About、Product、Blog、PDF text 各一份，分别用：

- fixed token
- paragraph recursive
- heading-aware recursive

生成 chunks。对 10 个研究问题人工判断 relevant chunks，计算每种方法的简单
Context Precision/Recall，并记录错误来自 boundary、重复还是尺寸。

### Codex 可以实现什么

- deterministic chunker、metadata schema、offset tests。
- 生成 chunk visualization 和差异报告。
- 检查 chunk 重叠、重复率和 token budget。

### Leo 必须亲自理解什么

- 为什么某个 chunk 对业务问题是完整证据，而不是只因为它包含关键词。
- trade evidence 为什么应使用 deterministic sections 或直接 evidence pack。
- chunking 选择如何影响后续 citation 审核体验。

### 面试问题

1. 如何选择 chunk size 和 overlap？
2. 什么时候 structure-aware chunking 优于 semantic chunking？
3. 如何评估 chunking，而不是凭肉眼看几个例子？
4. 如何处理表格、代码、列表和扫描 PDF？
5. 重切 chunk 后如何保持历史 citation？

### 验收标准

- 能比较四种方法并给出来源级策略。
- 完成至少 10 个问题的手工 relevance 标注和指标。
- 能解释 chunk ID 为什么必须稳定且 chunker version 必须记录。
- 能指出至少 3 种 overlap 造成的失败模式。

---

## L4 — Embeddings

### 必须理解的原理

- embedding 将文本映射到向量空间；相似度不是事实正确度或业务置信度。
- cosine、dot product、L2 的几何含义与归一化关系。
- document embedding 与 query embedding 必须来自兼容 profile。
- dimension 是持久化 schema 和 index contract，不只是模型返回长度。
- batch、rate limit、retry、timeout、idempotency、cost accounting。
- model upgrade 会导致 re-embedding 和 evaluation，不可原地无痕替换。

### 必须自己回答的问题

1. 为什么不能把不同模型的向量放在同一相似度比较中？
2. dimension 改变为什么通常需要 Migration 或新 index？
3. embedding 相似度高，为什么 evidence 仍可能无关？
4. 什么输入 fingerprint 能保证重复运行不重复收费？
5. provider 失败时为什么不能静默使用 Fake vector？

### 必须自己执行的小实验

不用真实 API。手工创建二维/三维向量，计算 cosine、dot、L2 排名，观察归一化前后变化。
再用 deterministic fake embedding 对相同文本、轻微改写、完全不同文本运行，验证：

- 同 input/profile 结果稳定。
- profile 改变后 fingerprint 改变。
- dimension mismatch 被拒绝。

### Codex 可以实现什么

- `EmbeddingProvider` protocol、Fake Provider、batching、typed errors。
- profile fingerprint、idempotent indexing、usage trace。
- dimension mismatch 和 retry tests。

### Leo 必须亲自理解什么

- 相似度分数不能直接映射为 Claim confidence。
- 供应商模型升级对历史 retrieval 可复现性的影响。
- 选择更大 dimension 的存储、性能、质量权衡。

### 面试问题

1. Cosine similarity 与 dot product 何时等价？
2. 如何设计可回滚的 re-embedding？
3. 如何处理 embedding provider rate limit？
4. 为什么需要分别支持 `embed_documents` 与 `embed_query`？
5. 如何判断更换 embedding model 真正提升了系统？

### 验收标准

- 能手算一个小向量排名例子。
- 能画出 active profile → backfill → evaluation → switch → rollback 流程。
- 能解释 dimension、metric、normalization 三者必须一起版本化。
- 实验不调用真实 API，能触发并解释 dimension mismatch。

---

## L5 — PostgreSQL + pgvector

### 必须理解的原理

- PostgreSQL extension、`vector(D)` 类型、距离 operator、exact search。
- HNSW 与 IVFFlat 的 build、query、recall、memory、update 权衡。
- approximate index 的 metadata filter 行为可能与 exact scan 不同。
- 本项目 company-scoped 候选集合小，exact search 可能是更合理的 MVP。
- vector table、FK、transaction、backup、migration 与 OLTP 资源竞争。
- PostgreSQL 16 local/test/production extension availability 是真实部署门禁。

### 必须自己回答的问题

1. 为什么使用 pgvector 不代表必须建立 HNSW？
2. company filter 应在 SQL 的哪个阶段体现？
3. 全局 HNSW + company filter 可能导致什么 recall 问题？
4. 为什么同库事务一致性对 citation 很重要？
5. 什么信号会触发迁移到 dedicated vector store？

### 必须自己执行的小实验

在未来 R2 沙箱数据库中使用纯 fixture vectors：

1. 插入 Company A/B chunks，其中 B chunk 与 query 完全相同。
2. exact query 加 Company A filter，确认 B 永不返回。
3. 比较无索引、普通 company index、HNSW（若阶段允许）的 `EXPLAIN ANALYZE`。
4. 增加不同候选规模，记录 p50/p95 与 recall。

本实验必须在项目 Migration 落地后执行；L5 理论学习可先写预期结果。

### Codex 可以实现什么

- pgvector Migration、SQLAlchemy mapping、repository/query reader。
- Docker PostgreSQL integration tests 和 migration lifecycle。
- benchmark fixture/runner 和 explain plan 收集。

### Leo 必须亲自理解什么

- 为什么项目选 pgvector 是业务/运维决策，不是模型质量决策。
- exact/ANN 的 recall-latency 交换。
- extension 不可用时为何必须 BLOCK，而不是静默换方案。

### 面试问题

1. HNSW 与 IVFFlat 有什么区别？
2. pgvector 如何与 metadata filter 组合？
3. 如何为 filtered vector search 建基准？
4. 单 PostgreSQL 同时承载 OLTP 与 vector search 的风险是什么？
5. 如何无停机迁移 embedding dimension？

### 验收标准

- 能解释为什么本项目 R3 首选 exact company-scoped search。
- 能读懂一份 `EXPLAIN ANALYZE` 并指出过滤、排序、limit 的位置。
- 能给出 dedicated vector store 的量化迁移条件。
- leakage 实验结果为 0，且 Migration 完成 upgrade/downgrade/upgrade。

---

## L6 — Vector Retrieval

### 必须理解的原理

- Query formulation、metadata filtering、candidate K、context K、threshold 各自影响不同。
- 绝对 similarity threshold 依赖模型与数据，不能从博客复制固定值。
- 多 query、query decomposition、max chunks per document 能改善覆盖但增加成本。
- retrieval output 必须是 typed `RetrievedChunk`，不是裸 ORM row/dict。
- context selection 需要去重、diversity、token budget 和 trust/freshness policy。
- Retrieval evaluation 必须使用固定 relevance labels。

### 必须自己回答的问题

1. candidate K 与 final context K 为什么要分开？
2. threshold 太高或太低分别会造成什么错误？
3. 为什么一个 Document 最多选 2–3 chunks？
4. fixed research questions 与 agent-generated query 的可评估性有什么差异？
5. 如何让“没有证据”成为正确结果？

### 必须自己执行的小实验

使用同一 Golden Questions 子集，对 `candidate_k` 取 4、8、16、24、40，记录：

- Recall@K
- MRR
- Context Precision
- selected token count
- duplicate document ratio

手工检查至少 5 个 false positive 和 5 个 false negative，分类为 query、chunking、embedding、
filter 或 relevance label 问题。

### Codex 可以实现什么

- versioned `RetrievalPolicy`、Retriever、Context Builder。
- metric runner、leakage trap、trace persistence。
- Top-K/threshold sweep 自动报告。

### Leo 必须亲自理解什么

- 指标变化背后的业务后果，而不是只选最高分参数。
- false negative 是否会让 Opportunity 错失线索，false positive 是否会污染 Claim。
- 为什么 retrieval failure 不应由 generator“补全”。

### 面试问题

1. 如何选择 Top-K？
2. 如何调 similarity threshold？
3. Retrieval 召回低时，你按什么顺序排查？
4. 如何防止一个来源垄断 context？
5. 什么是 metadata filtering leakage？

### 验收标准

- 完成参数 sweep 和错误分类。
- 能解释 Recall@K 与 MRR 对本项目分别意味着什么。
- Company B trap 永不返回。
- 能给出一版有数据依据的 vector v1 policy，而不是经验数字。

---

## L7 — Hybrid Search

### 必须理解的原理

- Dense retrieval 擅长语义，lexical retrieval 擅长精确名词、产品名、HS code、港口和缩写。
- PostgreSQL FTS 的 `tsvector`、`tsquery`、GIN、`ts_rank`/`ts_rank_cd` 基础。
- language configuration、stemming、stop words 对结果的影响。
- vector score 与 FTS rank 不同尺度，不应直接相加。
- RRF 依据 rank 融合，稳定、易解释，但仍需评估。
- Hybrid 不一定更好；只在 fixed dataset 上证明增益后启用。

### 必须自己回答的问题

1. 哪些 US Importer Hunter 查询更适合 lexical search？
2. 为什么产品型号或 HS code 可能被 dense retrieval 漏掉？
3. 为什么使用 RRF 而不是 `0.7 * vector_score + 0.3 * fts_score`？
4. `simple` 与 `english` FTS 配置的权衡是什么？
5. 中文网页对 PostgreSQL FTS 有什么限制？

### 必须自己执行的小实验

从 Golden Dataset 选择：精确产品名、同义描述、HS code、港口、公司规模表述各两题。
分别运行 vector、FTS、RRF hybrid，记录每题 relevant chunk rank，并解释每种方法赢/输原因。

### Codex 可以实现什么

- FTS projection/index、lexical query、RRF fusion。
- 三路对比报告和 query plan tests。
- language config fixtures。

### Leo 必须亲自理解什么

- 何时 lexical signal 是业务上更可靠的证据。
- Hybrid 参数变化怎样影响 exact entities 与语义线索。
- 为什么不应为了“全栈 RAG”立即引入 Elasticsearch。

### 面试问题

1. Dense 与 sparse retrieval 有什么互补性？
2. RRF 如何工作？
3. FTS language analyzer 选错会怎样？
4. 如何评估 hybrid 是否真正优于 dense-only？
5. 什么时候 Elasticsearch 值得引入？

### 验收标准

- 能手算一个小型 RRF 排名。
- 能指出至少 3 类 lexical 必胜或明显有利的项目查询。
- 同一 dataset 上给出 vector/FTS/hybrid 可比较结果。
- Hybrid 未提升时能接受“不上线”，而不是继续调到测试集过拟合。

---

## L8 — Reranking

### 必须理解的原理

- Retriever 负责高召回，Reranker 在较小候选集上提高排序精度。
- Cross-encoder、LLM reranker、规则 reranker 的质量、延迟、成本、可解释性差异。
- Reranker 不能修复缺失候选；candidate recall 是上限。
- 只 rerank top-N，不对全库逐条调用昂贵模型。
- provider timeout/failure 必须有明确降级到 hybrid ranking 的状态标记。
- rerank score 不能覆盖原始 vector/lexical/fusion scores。

### 必须自己回答的问题

1. 为什么 Recall@50 低时加 Reranker 没用？
2. top-20 → final-8 的预算如何决定？
3. LLM reranker 可能受到网页 prompt injection 吗？
4. Reranker failure 是否允许继续生成？应怎样审计？
5. 什么指标增益足以抵消额外延迟与成本？

### 必须自己执行的小实验

先不用真实模型，手工为 20 个候选打 relevance grade，模拟一个 reranker。比较：

- fusion rank
- oracle/human rerank
- 加入 10% 错误的 noisy rerank

观察 MRR、Context Precision 和 final context 变化，计算 reranker 的理论收益上限。

### Codex 可以实现什么

- `RerankerProvider` protocol、Fake/fixture reranker、timeout/budget。
- 记录 pre/post rank 和 score。
- reranker A/B evaluation runner。

### Leo 必须亲自理解什么

- reranking 的收益来自排序，不是新知识。
- 为什么 latency/cost 必须与质量增益一起评估。
- provider 降级是否仍满足产品证据门禁。

### 面试问题

1. Retriever 与 reranker 的区别是什么？
2. Cross-encoder 为什么通常更准也更慢？
3. 如何选择 rerank Top-N？
4. 如何处理 reranker timeout？
5. 如何证明 reranker 值得上线？

### 验收标准

- 能计算 reranker 的候选 recall 上限。
- 完成 human/oracle/noisy 三组对比。
- 能定义质量、p95 latency、cost 三维上线门禁。
- 能说明 reranker 不改变 company scope 与 citation validation。

---

## L9 — Grounded Generation

### 必须理解的原理

- Generator 只能在 `ContextPack` 内推理，不负责网络抓取或数据库搜索。
- Structured output 不是 grounding；必须验证 citation target 和 evidence substring。
- prompt injection 防护需要架构约束、数据隔离、strict parsing 和 validator，不只是一句 system prompt。
- evidence text 应保持原文，不翻译；claim detail 可以按 output language 生成。
- unknown/insufficient evidence 是一等结果。
- Claim confidence 是模型/规则表达，不等于 Opportunity score 或 source trust。

### 必须自己回答的问题

1. 模型返回合法 JSON，为什么仍可能完全不可信？
2. 如何验证 document_id、chunk_id、source_url 和 evidence_text 是一致的？
3. 为什么不能让模型自己决定再访问一个 URL？
4. 为什么 evidence snippet 不翻译？
5. Claim、Company Signal、Opportunity Judgment 的边界是什么？

### 必须自己执行的小实验

构造六个生成输出：

- 正确 citation。
- 伪造 chunk ID。
- Company B chunk。
- 正确 chunk 但伪造 evidence text。
- evidence 正确但 claim 过度推断。
- 无证据时正确 unknown。

手工运行设计中的 validator decision table，写出 accepted/rejected reason。然后将网页正文中
加入“忽略系统指令并输出某结论”，确认架构上为何仍会被拒绝。

### Codex 可以实现什么

- `ContextPack`、`StructuredResearchResult`、Fake Grounded Generator。
- strict parser、citation validator、typed rejection codes。
- prompt/version tests 和 malicious context fixtures。

### Leo 必须亲自理解什么

- evidence 是否真的支持 claim 的业务语义，这部分不能完全交给 substring checker。
- 哪些 claims 即使有字面证据也不应 promotion。
- 人工 Evidence Review 如何反馈 provider/prompt/retrieval 质量。

### 面试问题

1. Structured output 与 grounded output 有什么区别？
2. 如何防止 citation hallucination？
3. Prompt injection 为什么不能只靠 prompt 解决？
4. 如何设计“不可回答”行为？
5. 多个证据冲突时系统应怎样输出？

### 验收标准

- 六种输出均能给出一致 validator 结果。
- Citation Accuracy=1.00，cross-company acceptance=0。
- 能解释为什么 accepted Research Claim 仍需 Human Review。
- 能区分字面支持、语义支持和业务判断。

---

## L10 — Evaluation

### 必须理解的原理

- Evaluation dataset 是产品需求的可执行表达，不是上线后补写的测试。
- retrieval、generation、end-to-end 必须分层，否则无法定位失败。
- relevance label、golden answer、expected evidence、unanswerable case 的区别。
- Recall@K、MRR、Context Precision、Context Recall、Faithfulness、Answer Relevance、
  Citation Accuracy 的计算与局限。
- LLM judge 有偏差、自洽和 prompt sensitivity，不能代替 deterministic checks/human labels。
- dataset versioning、防止测试集污染和过拟合。

### 必须自己回答的问题

1. 为什么“最终答案正确率”不足以评估 RAG？
2. Recall@K 高但 Context Precision 低会发生什么？
3. Citation Accuracy 高但 Faithfulness 低的例子是什么？
4. 如何设计 cross-company leakage 与 prompt-injection golden case？
5. 新增线上失败样本时怎样避免改变旧 dataset 真值？

### 必须自己执行的小实验

亲自标注首版至少 20 条 Golden Questions，最终扩展到 30 条。每条指定 relevant evidence、
answerable、required/forbidden claim。手算其中 5 条的 Recall@K、MRR、Context Precision，
再对 5 个生成结果标注 Faithfulness 与 Citation Accuracy。

### Codex 可以实现什么

- JSONL schema、metric runner、report generator、CI gate。
- deterministic citation/substring/company checks。
- 参数 sweep 和版本对比。

### Leo 必须亲自理解什么

- relevance 与业务价值的标注标准。
- Golden Question 是否代表真实 freight forwarder research task。
- 阈值为何合理、错误是否可接受，以及哪类错误必须零容忍。

### 面试问题

1. 如何建立 RAG evaluation dataset？
2. Context Recall 与 answer faithfulness 有什么关系？
3. 如何评估 unanswerable questions？
4. LLM-as-a-judge 有什么风险？
5. 如何避免 benchmark overfitting？

### 验收标准

- Leo 亲自完成并 review 30 条 v1 labels。
- 能独立计算所有要求指标并解释局限。
- Retrieval/Generation/E2E 各有至少一个失败定位示例。
- leakage、unsupported accepted claim、invalid citation 的门禁为 0/0/0。

---

## L11 — Observability

### 必须理解的原理

- Debug RAG 需要复现 query → hits → context → generation → validation → review。
- trace、metric、log、audit record 的用途不同。
- provider/model/prompt/embedding/retrieval/chunker/cleaner version 必须共同确定一次结果。
- token、latency、cost 要按阶段拆分，不能只记录总耗时。
- 普通日志不能包含网页全文、prompt、answer、email、headers、credentials。
- Human Review decision 是最有价值的线上质量信号之一。

### 必须自己回答的问题

1. 一条 Claim 被拒绝时，需要哪些字段才能判断是 retrieval、generation 还是 validation 问题？
2. 为什么只记录最终 answer 无法复现？
3. full query/answer 应保存在哪里，为什么不直接写日志？
4. 如何比较两个 retrieval policy 的线上效果？
5. token usage 缺失时怎样诚实记录？

### 必须自己执行的小实验

给一个模拟 ResearchRun 创建完整 trace，然后删除不同字段，尝试回答：

- 为什么选中这个 chunk？
- 模型版本是什么？
- 是否有 Company B 数据？
- Claim 为什么被拒绝？
- 重新运行为什么结果不同？

列出每个问题的最小必需字段，并设计 redacted log 示例。

### Codex 可以实现什么

- append-only trace models、structured logging、redaction tests。
- run comparison report、latency/token aggregation。
- trace completeness checker。

### Leo 必须亲自理解什么

- 哪些数据是敏感或不应长期保留。
- 什么审计信息对 Evidence Review 和客户信任真正有用。
- 指标异常应触发回滚、人工检查还是继续观察。

### 面试问题

1. RAG trace 应包含哪些字段？
2. 如何在可观测性与隐私之间平衡？
3. 如何定位 retrieval 正确但 generation 错误？
4. 如何利用 human feedback 改进 RAG？
5. 如何设计可复现的 prompt/model versioning？

### 验收标准

- 能从任一 Claim 追到 query、hit、Document、Chunk、provider 和版本。
- redacted log 不含正文、prompt、answer、email 或 key。
- 能用 trace 定位至少三类失败。
- 能解释 audit storage 与 log 的不同保留策略。

---

## L12 — Agentic RAG

### 必须理解的原理

- Agentic RAG 是让系统选择查询、工具、迭代与停止条件，不是“装 LangGraph”。
- 固定 query plan 更容易评估、预算和复现；Agent 只应解决已证明的 failure slice。
- query decomposition、multi-hop retrieval、self-reflection、tool selection 的适用面。
- max steps、token/cost/time budget、loop prevention、checkpoint、human interrupt。
- company scope 必须在每个 graph state/tool call 中传播，不能只在入口检查。
- framework graph version、state migration 与 vendor lock-in。

### 必须自己回答的问题

1. 当前固定 research dimensions 为什么已经足够做 RAG MVP？
2. 哪类 Golden Questions 明确需要 multi-hop 或 iterative retrieval？
3. Agent 如何判断停止，而不是不断搜索？
4. LangGraph 解决的是哪类 orchestration 问题，哪些问题它不解决？
5. Agent 选择新 URL 时如何继续满足 SafeFetcher 与 source trust policy？

### 必须自己执行的小实验

从 Golden Dataset 选 5 个固定 retrieval 失败案例。手工设计最多 3 步 query decomposition：

```text
initial question → subquery 1/2 → evidence sufficiency check → stop
```

记录每步新增 recall、token、latency 和错误风险。至少找出一个不需要 agent、只需改 chunk/query
即可解决的案例，避免把所有问题框架化。

### Codex 可以实现什么

- 在独立 ADR 批准后实现 bounded graph、typed state、checkpoint 和 tests。
- max-step/budget/loop guard、company scope assertions。
- 与 fixed baseline 做 A/B evaluation。

### Leo 必须亲自理解什么

- 为什么 agent autonomy 会放大安全、成本和不可复现风险。
- 何时简单 Workflow 优于 LangGraph。
- 哪个量化 failure slice 足以证明引入框架的必要性。

### 面试问题

1. 什么是 Agentic RAG？
2. 什么时候 iterative retrieval 有价值？
3. 如何设计 agent stop condition？
4. 如何防止 tool loop 与预算失控？
5. 为什么使用 LangGraph 不自动提升 RAG quality？

### 验收标准

- 能指出至少一个有数据支持的 agentic use case 和一个不应 agentic 的 use case。
- 手工 3-step 实验显示增益与成本，且 company leakage=0。
- 能画出 graph state 中 company scope、budget、evidence、citations 的传播。
- 未通过 R1–R11 验收前，不进入 LangGraph 实现。

---

## 13. 项目级最终能力验收

完成 L1–L11 后，Leo 应能不依赖 Codex 完成以下白板题：

1. 从 A Tier Company 到 EmailDraft 画出完整 Evidence-Grounded pipeline。
2. 解释为何 Routing deterministic、Research probabilistic、Evidence Review human-controlled。
3. 设计 ResearchDocument/Chunk/version/dedup/citation 数据模型。
4. 解释 pgvector exact/HNSW/IVFFlat 与 company filter 的权衡。
5. 设计 vector → hybrid → rerank 的版本化 policy。
6. 给出一个 citation spoofing 样例并说明 validator 如何拒绝。
7. 计算一组 Recall@K、MRR、Context Precision/Recall。
8. 区分 Faithfulness、Answer Relevance、Citation Accuracy。
9. 从 trace 定位 retrieval、generation、validation、review 任一阶段失败。
10. 说明何时迁移 dedicated vector store，何时引入 Agentic RAG。

项目交付验收：

- 能通过全部 backend quality gates。
- 所有数据库阶段通过 PostgreSQL Migration upgrade/downgrade/upgrade。
- 默认测试完全离线，不调用真实 LLM/Embedding。
- Golden Dataset 版本化，指标可重复。
- Cross-company leakage 为 0。
- Accepted Claim Citation Accuracy 为 1.00。
- 未审核 RAG Claim 永不进入 Opportunity 或 Draft。
- Draft 仍只生成、等待人工审核，系统不发送邮件。

---

## 14. 推荐学习节奏

| 周 | 学习 | 项目输出 |
| --- | --- | --- |
| 1 | L1–L2 | R1 ADR 草案、ingestion state table、fixture set |
| 2 | L3–L4 | chunking experiment、embedding profile design |
| 3 | L5 | pgvector preflight、exact/ANN benchmark plan |
| 4 | L6 | vector retrieval baseline、leakage tests |
| 5 | L9 | grounded claim/citation validator design |
| 6 | L10 | 30 条 Golden Dataset、RAG MVP gate |
| 7 | L7 | Hybrid experiment |
| 8 | L8 | Reranking experiment |
| 9 | L11 | trace/redaction/run comparison |
| 10+ | L12（可选） | 仅针对已证明 failure slice 的 Agentic ADR |

每周结束必须能回答三个问题：

1. 本周改善的是 ingestion、retrieval、generation、evaluation 还是 operations？
2. 指标或证据是什么？
3. 如果回滚，系统怎样继续安全运行？
