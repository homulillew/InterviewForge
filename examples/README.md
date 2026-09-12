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
It is offline baseline output using the authored mixed interview library and reference
answers under [materials](materials/). All six turns use imported question and answer
references. [Answer audit](demo-output/answer_audit.md) and
[material usage](demo-output/material_usage.json) retain their sources. The checked-in
snapshot uses repository-relative example paths and can render without a live library.

For a real Chinese screenshot and Word import, activate an environment with document
extras and Chinese Tesseract language data, then run:

```bash
bash scripts/run_material_demo.sh
```

This produces six turns under `sessions/material-demo/session`. Pass a fresh output
directory as the first argument to repeat it. OCR may contain recognition errors;
the source transcription remains available through `library show` and the audit.

The fixtures deliberately lack proof for at least one strong resume assertion. RAG's
wiring test is not a retrieval benchmark; Redis's Lua script does not establish production
failover behavior; the service has no circuit breaker. Target repositories are scanned,
not executed. The package's own tests check the interview pipeline.
