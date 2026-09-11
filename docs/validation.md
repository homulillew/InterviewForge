# v0.2 validation

Validated locally on 2026-09-11 with Python 3.12 and an isolated editable install.

- `pytest -q`: **50 passed**. Includes three end-to-end fixtures, schema/provenance
  validation, evidence safety, graph deduplication, bounded learning, session locks,
  pause/resume/reset, retest concealment/readiness, a local HTTP adapter test and a
  typed fixture-client pass through claim/question/answer/knowledge/retest generation.
  v0.2 adds retrieval-budget tests, durable submission/outage recovery, feedback concealment
  and readiness downgrade regressions; see [iteration notes](iteration-0.2.md).
- `ruff check .`: passed.
- Skill creator `quick_validate.py`: passed.
- JSON Schemas exported from the executable Pydantic models.
- Redis, RAG and service demos: six turns each, complete JSON/Markdown artifacts.
- Wheel and source distribution built successfully. Wheel installed to a separate target
  directory and ran a two-turn RAG session and a candidate retest outside the source checkout; packaged prompts
  loaded successfully.
- README/Skill/reference links checked for missing local targets.

No live model endpoint was configured or evaluated. The HTTP server and fixture client
validate interfaces, failure handling and provenance invariants, not a real model's
technical reasoning quality. CI is configured for Python 3.11–3.13; only Python 3.12 was
executed in this local environment.

The repository fixtures are scanned without execution by InterviewForge. No production
performance, Redis failover behavior or retrieval-quality improvement is claimed by
these tests. The checked-in demo is a simulation and leaves all human mastery unknown.
