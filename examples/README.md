# Reproducible demos

Run from the project root after installation:

```bash
bash scripts/run_demo.sh
interview-forge tree --session sessions/demo/redis
interview-forge retest --session sessions/demo/redis
interview-forge answer --session sessions/demo/redis --text '这里写你自己的独立回答'
```

The script runs Redis, RAG and generic service fixtures for six turns each. Existing
session directories are intentionally not overwritten; choose a fresh output directory
as the script's first argument for another run.

A checked-in Redis run is available in [demo-output](demo-output/post_interview_review.md),
including [transcript](demo-output/transcript.md), [answer cards](demo-output/best_answer_cards.md),
[knowledge tree](demo-output/knowledge_tree.md) and [practice](demo-output/practice_questions.md).
It is offline baseline output; source paths in the snapshot reflect the generating workspace.
Regenerate in your own workspace rather than relying on these paths for fresh analysis.

The fixtures deliberately lack proof for at least one strong resume assertion. RAG's
wiring test is not a retrieval benchmark; Redis's Lua script does not establish production
failover behavior; the service has no circuit breaker. Target repositories are scanned,
not executed. The package's own tests check the interview pipeline.
