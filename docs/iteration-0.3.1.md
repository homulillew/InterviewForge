# v0.3.1: corpus-grounded adversarial interviewer

This is the semantic v0.3 redesign requested after the earlier material-library release.
The package advances from 0.3.0 to 0.3.1; session schema advances from 1.0 to 2.0.

## Implemented

Atomic assertions and independent attack surfaces; assertion risk and explainable attack
utility; heterogeneous corpus normalization using text/document/OCR readers; observed versus
weak chains; exact and shingle duplicate groups; abstract operators; local versioned SQLite
and FTS5; content/transition/style lanes; applicability gating; sample-aware style backoff;
plan-render-guard pipeline; independent repository-blind red critic; corpus-blind defender;
spoken answer/audit separation; related-only static source mapping; canonical concept aliases;
answered follow-ups; multi-node greedy exercises; durable human retest; explicit migration;
provenance/style reports; corpus management and JSON/Markdown evaluation.

Existing library read/search/delete, bounded repository scanning, model transport/retry,
source quotation validation and human feedback recovery remain available. Live preparation
reference injection was intentionally removed to satisfy the new defender isolation contract.
Raw user corpus is excluded from tracked examples and distribution manifests. Public corpus
and eval files are authored synthetic fixtures.

## Minimum implementations and limits

- Compiler normalization uses structured model extraction or deterministic syntax parsing.
  Operators and patterns are currently compiled through a fixed ontology and keyword rules,
  not a trained semantic abstraction model. The ontology has 15 implemented operators.
- Retrieval combines FTS hits, recognized technology, surface and applicability rules.
  It does not have embeddings or learned reranking. A generic unfamiliar technology can
  require compatible normalization and future ontology expansion.
- Style distributions are empirical sample summaries. n/(n+12) confidence and hierarchical
  blending are heuristics, not a calibrated probability of a real company's behavior.
- Guard checks are lexical. They reject recognized unrelated technologies, selected invented
  premises and literal copying but cannot prove complete semantic correctness or originality.
- The offline answerer has Redis/RAG/service curricula. Compatible mode provides model
  reasoning; no live model endpoint was used as evidence of response quality in this change.
- Source relations stronger than related are represented and validated but not automatically
  inferred. Human review or a future dedicated evidence assessment service must establish them.
- Canonicalization is alias/title-based, not semantic graph clustering. Per-turn bounds and
  greedy exercise coverage reduce growth without proving an optimal learning curriculum.
- Corpus compiles in memory and near deduplication is O(n²) worst case. Batch limits are
  200 files, 25 MiB/file, 500 JSON posts/file, 200 questions/post, 200k characters/post,
  and 32k characters/post for semantic normalization. Oversized inputs fail rather than truncate.
  Rebuild uses normalized records; there is no background file watcher or automatic pin update.
- Evaluation is offline. Several semantic metrics are manual_review_required; structural
  anchor/copy rates are named proxies, not accuracy claims. No human labeling UI is included.
- Schema migration preserves legacy IDs/history and cannot invent a missing corpus trace.
  Legacy concept names stay intact to preserve human references; new nodes use canonical names.

## Recommended v0.4 work

1. Add manually labeled real-user evals stored privately: assertion precision, applicability,
   question relevance, evidence factuality and style confidence calibration.
2. Introduce audited semantic pattern abstraction and embedding retrieval with the same
   red/blue boundaries and resume-first gate; evaluate operator/renderer agreement.
3. Scale incremental dedup/index compilation and revision retention tooling for larger corpora.
4. Add reviewed evidence relation assessment and semantic concept merging with stable ID redirects.
5. Add a preparation UI for source correction, answered-card editing and actual human review.
