# L03 — Chunking Notes

## 我的理解

> Leo TODO：用自己的语言填写，不粘贴标准答案。

## 需要回答的问题

- ResearchDocument 是什么？
- ResearchDocumentChunk 是什么？
- 为什么 chunk 是 retrieval unit？
- 为什么 chunk 越大不一定越好？
- 为什么 chunk 越小也不一定越好？
- overlap 解决什么问题？
- overlap 为什么会制造 retrieval noise？
- stable chunk identity 为什么影响 citation？
- structure-aware chunking 和 fixed-size chunking 的区别是什么？
- 什么情况下 semantic chunking 值得引入？
- R2a 为什么暂时不能用 Recall@K？
- 你会怎样用真实业务问题选择 chunk size？

> Leo TODO：以上问题不要由 Codex 代答。完成 `L03-chunking-human-review.md` 后，用本轮真实错误案例回答。

## Chunking 实验

- 对 Homepage、About、Product、Blog/News 与 text PDF fixtures 运行离线可视化 CLI。
- 对 oversized section 比较 target、hard max 与 overlap 参数。
- 对 very-short-sections 验证相邻短 section merge。
- 对 repeated-footer-nav 验证 deterministic boilerplate/duplicate filtering。
- 重复运行同一 Document/version，比较 chunk sequence、offsets 与 UUID5 IDs。

## 错误案例

> Leo TODO：记录 boundary、过大/过小 chunk、重复内容、错误 heading 与 overlap domination。

## 指标

- 记录每个 fixture 的 chunk count、token count 与 hard-max violations。
- 记录 duplicate ratio、boilerplate ratio、overlap ratio。
- 当前阶段记录 `question_evidence_coverage`、`boundary_break_count`、`chunks_required_per_answer`，但在人工标注前保持 `PENDING_HUMAN_LABEL`。
- 当前阶段不使用 Recall@K、MRR、nDCG；它们需要 R3 Retriever 与固定 query-to-evidence labels。
- 完成人工 relevance 与 boundary label 后，再判断 chunk quality calibration 是否通过。

## 仍不理解的问题

> Leo TODO：记录实验后仍无法解释的问题。

## 面试题

- 如何选择 chunk size 与 overlap？
- 什么时候 structure-aware chunking 优于 semantic chunking？
- 如何评估 chunking，而不是只看几个示例？
- 如何处理表格、列表、PDF page boundary 与超长句子？
- 重切 chunk 后如何保持历史 citation？

## Leo TODO

- [ ] 完成“我的理解”。
- [ ] 回答全部“需要回答的问题”。
- [ ] 运行 `visualize_research_chunks.py` 检查至少 5 类 fixture。
- [ ] 完成 `L03-chunking-human-review.md` 的 10 个业务问题。
- [ ] 对照 `L03-chunk-boundary-review.md` 解释至少 3 个切分位置。
- [ ] 填写 `L03-chunking-relevance-template.jsonl` 的人工 relevant IDs。
- [ ] 记录至少 3 个错误案例和参数调整理由。
- [ ] 口述回答全部面试题。
