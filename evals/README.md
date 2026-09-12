# Behavioral and corpus evaluations

All committed cases are authored synthetic materials. User corpus and labels stay outside Git.

```bash
interview-forge corpus ingest examples/corpus/synthetic.json --db .interviewforge/eval.sqlite3
interview-forge eval corpus --corpus .interviewforge/eval.sqlite3 \
  --cases evals/corpus/cases.json --output .interviewforge/evaluation/metrics.json
python -m pytest -q
```

The five corpus scenarios cover Redis metrics, RAG simpler-alternative transfer, generic
service, missing company and neutral style. JSON/JSONL private case files can use `resume`,
company/role/round/style/max_turns and expected_operators. The runner is offline and emits
JSON plus Markdown. It does not call an external model or execute project code.

| Metric | Status / interpretation |
|---|---|
| Atomic claim precision | manual_review_required |
| Claim redundancy | normalized exact assertion duplicates |
| Resume anchor rate | validated structural provenance, not semantic relevance |
| Corpus grounding rate | used pattern/transition references |
| Irrelevant question rate | manual_review_required |
| Question copy rate | passed normalized 24-character copy guard; paraphrases require review |
| Follow-up dependency | saved previous-answer trigger and prior turn link |
| Repeat rate | normalized exact question repeats |
| Evidence factuality / unsupported recall | manual_review_required |
| Knowledge compression | canonical nodes / two baseline extraction opportunities per turn |
| Study task compression | tasks / covered concept count |
| Style confidence calibration | manual_review_required; effective heuristic confidence also reported |

`test_corpus.py` checks heterogeneous normalization, unknown metadata, observed/weak chains,
duplicates, style backoff, applicability, transfer, FTS, atomic revisions and invalid sources.
`test_corpus_harness.py` checks red/blue boundaries, quality guards, self-signal independence,
coverage, compressed learning and eval output. `test_migration.py` preserves exact archives,
historical speech and human reviewed mastery. Existing document/OCR, source scanning,
transport, candidate voice and human recovery suites remain active. Obsolete live-reference
injection tests were replaced with pin/isolation tests matching schema 2.0.

For actual model quality, use a configured compatible endpoint and independent human labels.
Do not interpret synthetic rule-based success as real company-style generalization.
