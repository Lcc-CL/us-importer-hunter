# ADR-0028 — Evidence-Grounded Research Document ownership

状态：**已批准**
日期：2026-08-09
相关：ADR-0016、ADR-0017、ADR-0025、ADR-0026

## 背景

现有 Website Research 保存一次运行、抓取页面元数据、Claims 与人工 Promotions，
但不保存可复用的 cleaned source content。RAG 后续需要稳定的 Document/Chunk citation，
不能用 `ResearchPage.position` 代替跨运行内容 identity，也不能建立第二套 Research 业务模型。

## 决策

Research bounded context 继续只有一套业务链，各对象职责如下：

- `ResearchRun`：一次研究执行的 aggregate root，拥有 pages、claims、rejections、promotions。
- `ResearchPage`：某次 run 的 fetch record；记录 requested/final URL、抓取元数据和可选
  `document_id`。同一 Document 可被多次 run/page 复用。
- `ResearchDocument`：某家公司某个 canonical URL 的一次 immutable cleaned-content
  version。它是 durable corpus identity，不拥有 Claim，也不代表 Company fact。
- `ResearchDocumentChunk`：R2 才定义的 Document 子资源和 retrieval unit；R1 不实现。
- `ResearchClaim`：当前 ResearchRun 的结构化主张；R1 保持 page citation 语义，R2/R3
  再 additive 增加 document/chunk citation。

`ResearchDocument.company_id` 必填。没有 canonical Company 的 standalone prospect research
继续产生原有 ResearchRun/Claim，但 R1 不写 company-scoped corpus。

成功抓取、清洗后的页面在 ResearchRun 最终持久化事务中创建或复用 Document，
ResearchPage 可链接该 Document。失败 fetch 不创建空 Document。unsafe/thin content 可以作为
`quarantined` Document 留痕，但不能进入未来 ready retrieval corpus。

Repository 继续接受和返回 Domain objects；ORM model 不跨边界。Provider、Extractor 和
Website tool 都不能访问 Repository。

## 后果

- 现有 ResearchRun → Claim → Human Promotion 链不变。
- R2 可以在 Document 下增加 Chunk，而不改变 Company、Opportunity 或 Routing。
- standalone research 暂无 durable company corpus，这是有意的 company-isolation 门禁。
- ResearchRun 与 ResearchDocument 在同一事务落库；失败不会留下半链接 page。
