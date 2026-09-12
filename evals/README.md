# Behavioral evals

Run `pytest tests/test_evals_cli.py -q`. Fixtures under `examples/` are authored here.

| Case | Trigger | Expected behavior |
|---|---|---|
| Redis | Redis Lua prevents overselling, +40% claim | Atomicity, conditional SQL alternative, concurrent correctness; no file trivia; metric unverified |
| RAG | Reranker improves retrieval | First-stage limits, quality evaluation, top_k/latency trade-offs; injected ranker not assumed cross-encoder |
| Service | Resume claims circuit breaker, source only health endpoint | Circuit breaker claim unsupported; no “we implemented” fabrication |
| Material import | Chinese PNG, scanned PDF, DOCX, TXT/MD | Extract questions/answers and source locations, deduplicate, preserve quoted text |
| Live library | Import after starting an interview, then remove an earlier document | Next turn uses fresh questions; earlier source snapshots remain readable |
| Reference answers | DOCX contains 200 concurrent requests, 3 replays, 50 ms timeout | Use those parameters coherently, retain reference IDs, replace canned experiment inputs |
| Candidate voice | Resume extends beyond the available repository | Give concrete engineering and experiment reasoning; keep source gaps in separate audit |

`tests/test_agents.py` probes dynamic branches and blind interviewer input;
`tests/test_llm.py` sends requests to a local mock HTTP server and checks malformed output,
failed-turn recovery and fabricated project claims. These are contract evals, not a live
model-quality benchmark.

`tests/test_materials_library.py` covers persistence, provenance, concurrent imports,
Chinese retrieval and structured extraction; `tests/test_document_reader.py` includes
real Chinese image and scanned-PDF OCR when the document extras, Tesseract language data,
and Noto CJK font are installed. `tests/test_material_integration.py` tests live CLI
imports, legacy sessions, source deletion, retest references and report separation.
`tests/test_material_interviewer.py` checks source question classification and isolation;
`tests/test_candidate_answers.py` checks reference use and direct candidate expression.

Run `bash scripts/run_material_demo.sh` in the activated environment for the authored
PNG + DOCX workflow. See `sessions/material-demo/session/best_answer_cards.md` for spoken
answers and `answer_audit.md` / `material_usage.json` for their sources and assumptions.

For a configured semantic model, run the same examples with `--provider compatible` and
review: claim faithfulness, evidence relevance, one main question, prior-answer dependency,
mechanism correctness, useful reference adaptation, separate source audit, bounded knowledge expansion and
retention of source links. Source-quote checks and lexical guards alone cannot prove
semantic quality or immunity to all prompt injection. No live endpoint is required by CI.
