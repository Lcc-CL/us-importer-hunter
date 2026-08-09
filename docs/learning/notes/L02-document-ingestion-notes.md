# L02 — Document Ingestion Notes

## 我目前的解释

> Leo TODO：用自己的语言填写，不粘贴标准答案。

## 我需要回答的问题

- 为什么不能每次 Research 都覆盖旧页面 content？
- 同一 URL 内容变化后，旧 Claim 应引用哪个版本？
- 两个 URL 的 cleaned content hash 相同，如何去重又保留 provenance？
- 为什么只保存 cleaned text，而不默认保存 raw HTML？
- `ResearchPage` 与 `ResearchDocument` 的职责如何区分？

## 本阶段实验

- 使用 R1 fixture 比较同 URL 同内容与同 URL 变更内容的 ingestion 结果。
- 使用不同 URL 的相同 cleaned content 验证 `duplicate_of_document_id`。
- 比较 Company A/B 相同 content hash 的 Document identity。
- 运行 malicious HTML、空内容与 heading/list cleaner fixtures。
- 在 PostgreSQL 中并发写入同 Company、同 canonical URL、同内容。

## 实验结果

- R1 ingestion/source fixture 共 10 条。
- 同 URL 同内容复用 current Document；同 URL 变更内容生成 immutable 新版本。
- 不同 URL 相同内容保留独立 Document，并可链接同 Company 的 duplicate root。
- 跨 Company 不共享 Document identity。
- PostgreSQL advisory lock 与 partial unique index 共同限制每个 Company URL 只有一个 current Document。
- cleaned text 最大保留 40,000 字符；raw HTML 不持久化。

## 我理解错的地方

> Leo TODO：记录实验前后的认知修正。

## 面试题

- 如何设计幂等网页 ingestion pipeline？
- URL canonicalization 有哪些陷阱？
- content hash 去重会丢失哪些 provenance？
- 如何处理成功抓取但内容为空、过薄或依赖 JavaScript 的页面？
- 如何防止 SSRF 与 redirect 绕过？

## Leo TODO

- [ ] 完成“我目前的解释”。
- [ ] 回答全部“我需要回答的问题”。
- [ ] 记录四类 ingestion fixture 的状态转换。
- [ ] 阅读 advisory lock 与 partial unique index 的实现和测试。
- [ ] 口述回答全部面试题。
