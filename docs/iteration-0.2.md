# v0.2 — Evidence relevance and recoverable retests

## What changed

1. **Question-aware evidence retrieval.** Previously linked excerpts were ordered by
   file name and type. A relevant late file could miss the context budget. Retrieval now
   uses question/claim terms, small Chinese-to-code concept mappings, term rarity and
   question-specific artifact preferences. It keeps a bounded context and at most two
   chunks per file. `EvidenceMatch` records the selection score and reasons. A relevance
   match remains a search hypothesis, not proof of behavior.
2. **Readable answers with inspectable grounding.** Direct interview answers contain the
   explanation and scope boundary. Exact excerpts and paths are shown separately in
   answer cards, followed by retrieval rationale. Test and evaluation source files no
   longer suppress the missing-measurement signal: source text does not prove execution
   or measured improvement. Markdown excerpts use fences that cannot be closed by a
   shorter backtick sequence in the source.
3. **Durable candidate submission.** CLI `answer` saves the human text before making any
   provider request. If feedback fails, `grade-retest` resumes from that saved submission.
   Repeating completed feedback with an explicit attempt ID is idempotent; a different
   answer cannot overwrite a pending submission. `status` identifies pending feedback,
   and `retest_feedback.md` shows submissions and completed reference material separately.
4. **Correctable readiness.** Readiness now requires the latest two assessed answers to
   be distinct and explicitly reviewed as passing. Older successful answers cannot mask
   a new unreviewed model assessment or a failed retest. Correcting an old passing review
   downward recomputes derived mastery and study tasks instead of failing validation
   against the stale ready state.

## New command

```bash
interview-forge grade-retest --session sessions/my-project --attempt r1
```

Use this after an interrupted or failed `answer` command. The answer already stored in
`interview_state.json` is reused. It is not necessary to retype it or reveal credentials
in a command argument.

## Compatibility and limits

The package version is 0.2.0. Session schema version remains 1.0; the added retrieval
metadata has a default, and snapshots without it load successfully. Old impossible
readiness states now fail validation rather than accepting contradictory review evidence.
The authoritative snapshot remains JSON; Markdown reports are regenerated views.

Lexical retrieval does not establish entailment, and static sources still cannot prove
production performance or personal ownership. The optional model provider was exercised
through mock/fixture tests, not an externally configured live model. This iteration does
not add a UI or execute target repository code.

## Validation

`pytest -q`: **50 passed** (11 additional regressions over the previous 39).
`ruff check .`: passed. Redis, RAG and generic service golden scenarios remain covered.
Additional tests cover ranking under a context budget, irrelevant links, static tests vs
measurements, separate answer/source rendering, legacy loading, provider outage recovery,
submission integrity, re-review downgrades, advisory model scores and feedback concealment.
