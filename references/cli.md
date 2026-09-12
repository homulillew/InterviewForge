# CLI reference — schema 2.0

Python 3.11+, POSIX locking. Install `python -m pip install -e '.[dev,documents]'`.
Every command also works as `python -m interview_forge`.

## Corpus

```bash
interview-forge corpus ingest ./my-posts --db ~/.interviewforge/corpus.sqlite3
interview-forge corpus ingest image.png notes.docx --corpus ~/.interviewforge/corpus.sqlite3 --ocr local
interview-forge corpus stats --corpus ~/.interviewforge/corpus.sqlite3
interview-forge corpus inspect --company bytedance --role backend
interview-forge corpus inspect --id PATTERN_OR_CASE_ID --revision REVISION_HASH
interview-forge corpus rebuild
```

`--db` aliases `--corpus` for corpus management. Default database is
`~/.interviewforge/corpus.sqlite3`. Ingest accepts one or more files/directories, MD/TXT,
JSON/JSONL, PDF/DOCX and images. JSON may contain a list, `cases`, `questions`, Q/A dictionaries,
or interviewer/candidate messages. Missing metadata is not inferred from filenames.

Ingest takes `--provider offline|compatible --base-url URL --model NAME` for semantic
normalization; vision additionally requires an image-capable endpoint. OCR options are
`--ocr auto|local|vision|off --ocr-language chi_sim+eng`. Local Chinese OCR requires Tesseract
and installed language packs. Corpus batch failures do not update current revision.
`rebuild` uses normalized records; re-ingest to reread changed source files.

## Sessions and provenance

```bash
interview-forge start --resume resume.md --repo /path/to/project --jd jd.md \
  --corpus ~/.interviewforge/corpus.sqlite3 --company bytedance --role ai-engineer \
  --round tech-2 --seniority senior --style corpus --session sessions/my-project --run
interview-forge run --session sessions/my-project --turns 2
interview-forge explain-question --session sessions/my-project --question q1
interview-forge pause --session sessions/my-project
interview-forge resume --session sessions/my-project --turns 3
interview-forge status --session sessions/my-project
interview-forge score --session sessions/my-project
interview-forge tree --session sessions/my-project
interview-forge report --session sessions/my-project
interview-forge reset --session sessions/my-project
interview-forge migrate-session --session sessions/legacy
```

Resume/JD are UTF-8 text/Markdown. `start` defaults to neutral style and no corpus.
`--style corpus` requires a compiled database. Neutral mode can still retrieve content
patterns when `--corpus` is supplied. `--max-turns` defaults to 12 (1–100), `--max-depth`
to 5 (1–10). `--deep-dive` includes deeper learning concepts. Start without `--run` only
prepares the snapshot. Completed sessions need reset or a new directory; a changed
repository or latest corpus revision requires a new session. Reset preserves the corpus pin.

`explain-question` shows the atomic anchor, surface, operator, attack utility, adaptation,
used matches with direct/transferable applicability, transition references and style backoff.

## Preparation documents

```bash
interview-forge library add reference.docx --kind answer
interview-forge library add interview.png --kind interview --ocr local
interview-forge library search 'Redis 幂等' --kind answer --json
interview-forge library list
interview-forge library show ITEM_OR_DOCUMENT_ID
interview-forge library remove DOCUMENT_ID
interview-forge attach-library --session sessions/my-project --library /path/to/library
```

The previous material-library API remains available for preparation and reference lookup.
Its default is `.interviewforge/library` relative to the working directory. Directory imports
commit per document; corpus ingest commits per batch. Library content never enters the new
defender runtime. `attach-library` stores the preparation location and does not change a pin.

## Human retest

```bash
interview-forge retest --session sessions/my-project
interview-forge answer --session sessions/my-project --file my-answer.md
interview-forge grade-retest --session sessions/my-project --attempt r1
interview-forge retest --session sessions/my-project --node KNOWLEDGE_NODE_ID
interview-forge review-retest --session sessions/my-project --attempt r1 \
  --score 0.85 --rationale '人工核对机制、反例和验证方法' --missed '遗漏点'
```

Use `answer --text '...'` instead of `--file` if desired. Submission is saved before feedback.
`grade-retest` retries pending feedback and returns completed feedback unchanged. Readiness
needs the latest two distinct assessed answers to pass human review, score >= 0.8, no missed
points. Only record an actual human review; simulated/model answers do not establish mastery.

## Provider, eval and export

```bash
interview-forge start --resume resume.md --repo ./repo --session sessions/live \
  --provider compatible --base-url http://localhost:8000/v1 --model your-model --run
interview-forge eval corpus --corpus ~/.interviewforge/corpus.sqlite3 \
  --cases evals/corpus/cases.json --output .interviewforge/eval/metrics.json
interview-forge schemas --output schemas
```

Cases may be JSON or JSONL, 1–100 records with `resume`, optional target/style/max_turns and
`expected_operators`. Eval runs the offline pipeline; output defaults to
`.interviewforge/evaluations/metrics.json` and companion Markdown. Manual semantic metrics
are explicitly pending labels. Output accepts a JSON filename or directory.

Compatible mode uses the configured Chat Completions prefix, standard HTTP, structured
schema validation and bounded retries. Set `INTERVIEWFORGE_API_KEY` when needed; secrets are
not serialized. A normal turn calls renderer, answerer, critic and knowledge extraction;
invalid JSON/guard repairs can add calls. There is no silent switch to offline on failure.
