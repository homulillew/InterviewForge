# v0.3.1 validation

Validated locally on 2026-09-13 with Python 3.12. Package 0.3.1, session schema 2.0.

- Full pytest suite: **184 passed**, including real Chinese image/scanned-PDF OCR in the
  available Tesseract/document environment. Obsolete live corpus/reference injection tests
  were replaced by revision-pin, isolation and migration tests; baseline was 156 tests.
- `ruff check .`, `git diff --check`, Skill creator `quick_validate.py` and local documentation
  link checks passed. Forty-six JSON Schemas exported; obsolete CapabilityClaim schema removed.
- Corpus fixtures: six authored posts, sixteen questions, eleven transitions, four observed
  answer-conditioned transitions, fifteen compiled patterns and sixteen style profiles.
- Five offline evaluation scenarios: structural resume anchor rate 1.0; corpus-reference
  grounding rate 0.70; exact repeat and guarded literal-copy rates 0; saved follow-up-trigger
  rate 0.20; knowledge compression ratio 0.50; task/covered-node ratio 0.35. These are proxy
  metrics on synthetic cases. Atomic precision, semantic relevance, evidence factuality,
  unsupported recall and style calibration remain manual_review_required.
- Redis, RAG and service CLI simulations run to six turns with JSON/Markdown reports.
  Chinese PNG corpus ingestion plus DOCX preparation import runs a six-turn pinned interview.
  Image demo has four extracted questions and zero preparation-material snapshots in runtime.
- Regression coverage includes cross-assertion repeated-probe prevention, planned-operator
  checks, red interviewer/critic blindness, corpus-free defender input, duplicate sample
  counting, style backoff, transferable patterns, missing metadata, FTS, compare-and-swap,
  revision integrity, failed-batch recovery, canonical cards and multi-node exercises.
- Migration archives exact schema 1.0 bytes and preserves historical speech, node IDs, human
  answers, explicit review records and reviewed node readiness. Failed migration leaves the
  original untouched. Existing submission-before-feedback and readiness downgrade tests pass.
- Wheel and source distribution built. Installed wheel outside the checkout runs corpus
  ingest, two interview turns, durable human submission and feedback, state roundtrip and
  packaged prompt loading. Archive inspection found no SQLite corpus or private-material
  directories; wheel has no examples, source distribution uses explicit synthetic fixtures.

No live model endpoint or actual company corpus was evaluated. The local HTTP server and
fixture client validate transport/contracts, not model technical reasoning quality. Only
Python 3.12 was executed locally. No production performance or unexecuted target benchmark
is claimed. Current minimum implementations and v0.4 work are documented in
[iteration-0.3.1.md](iteration-0.3.1.md).
