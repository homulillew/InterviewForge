# Behavioral evals

Run `pytest tests/test_evals_cli.py -q`. Fixtures under `examples/` are authored here.

| Case | Trigger | Expected behavior |
|---|---|---|
| Redis | Redis Lua prevents overselling, +40% claim | Atomicity, conditional SQL alternative, concurrent correctness; no file trivia; metric unverified |
| RAG | Reranker improves retrieval | First-stage limits, quality evaluation, top_k/latency trade-offs; injected ranker not assumed cross-encoder |
| Service | Resume claims circuit breaker, source only health endpoint | Circuit breaker claim unsupported; no “we implemented” fabrication |

`tests/test_agents.py` probes dynamic branches and blind interviewer input;
`tests/test_llm.py` sends requests to a local mock HTTP server and checks malformed output,
failed-turn recovery and fabricated project claims. These are contract evals, not a live
model-quality benchmark.

For a configured semantic model, run the same examples with `--provider compatible` and
review: claim faithfulness, evidence relevance, one main question, prior-answer dependency,
mechanism correctness, honest unsupported assertions, bounded knowledge expansion and
retention of source links. Source-quote checks and lexical guards alone cannot prove
semantic quality or immunity to all prompt injection. No live endpoint is required by CI.
