# CLI reference

Install from the repository: `python -m pip install -e '.[dev,documents]'`.
Python 3.11+, Linux/macOS. All commands also work as `python -m interview_forge`.
Resume/JD inputs are UTF-8 text/Markdown; the material library also reads PDF, DOCX and images.

## Material library

```bash
interview-forge library add examples/materials/interview.md \
  --kind interview --tag Redis --company Example --role Backend
interview-forge library add examples/materials/reference_answer.md --kind answer
interview-forge library add examples/materials/redis-answer.docx --kind answer
interview-forge library add examples/materials/redis-interview.png \
  --kind interview --ocr local --ocr-language chi_sim+eng
interview-forge library add /path/to/material-folder --kind interview
interview-forge library list
interview-forge library search 'Redis 幂等' --kind interview --limit 5
interview-forge library search '压测 对照实验' --kind answer --json
interview-forge library show doc_ID
interview-forge library show item_ID
interview-forge library remove doc_ID
```

Replace `doc_ID` and `item_ID` with values from list/search output. All library subcommands
accept `--library DIRECTORY` and `--json`; the default is `.interviewforge/library` under
the current working directory. `show` always prints the full JSON record. Repeated
`--tag` values add multiple tags. Search supports `--limit 1` through `50`.

`add` accepts one or more files or folders and requires `--kind interview|answer`.
Folders are traversed recursively, skipping hidden directories, symlinks and the library
directory. Imports are deduplicated by file content and kind. Each file commits atomically;
in a batch, successfully imported earlier files remain if a later file fails.

Offline extraction recognizes Q/A labels, Chinese question/answer labels, numbered
questions, Markdown headings and explicit follow-ups. Reference prose can use section
titles. Add `--provider compatible --base-url URL --model MODEL` for semantic extraction.
The model extracts source-bound items in batches of up to 32,000 source characters.
It does not author answers absent from the imported document.

Supported formats: TXT, TEXT, MD, Markdown, PDF, DOCX, PNG, JPG, JPEG and WebP.
DOCX paragraphs and tables use standard-library parsing. PDF and images require the
`documents` extra. Old DOC files need conversion to DOCX.

| OCR option | Behavior |
|---|---|
| `--ocr auto` | Default: local Tesseract first, then a configured vision client on failure |
| `--ocr local` | Local Tesseract only |
| `--ocr vision` | Compatible model with image support |
| `--ocr off` | Read text layers only; no image/scanned-page OCR |
| `--ocr-language chi_sim+eng` | Default local OCR languages; e.g. `eng` for English |

Local OCR requires Tesseract and language data; inspect them with `tesseract --list-langs`.
A compatible text-only model cannot perform vision OCR. PDF text pages keep their text
layer; empty pages are recognized individually. Partial-page failures and language
fallbacks are reported and retained in document warnings.

The reader limits one file to 25 MiB, a PDF to 100 pages and extracted text to 2,000,000
characters. A folder batch is limited to 200 files. The library stores parsed blocks,
hashes, item IDs and source locations in its own `materials.json`.

## Sessions

```bash
interview-forge start --resume resume.md --repo /path/to/project --jd jd.md \
  --session sessions/my-project --library /path/to/my-library \
  --max-turns 12 --max-depth 5 --run
interview-forge attach-library --session sessions/my-project --library /path/to/my-library
interview-forge run --session sessions/my-project --turns 2
interview-forge pause --session sessions/my-project
interview-forge resume --session sessions/my-project --turns 3
interview-forge status --session sessions/my-project
interview-forge score --session sessions/my-project
interview-forge report --session sessions/my-project
interview-forge tree --session sessions/my-project
interview-forge reset --session sessions/my-project
interview-forge schemas --output schemas
```

`start` without `--run` prepares state only. Its default `--library` is the same directory
used by library commands. The absolute library path is saved in session configuration.
`attach-library` links or switches a library for an existing session. Each subsequent
turn retrieves current matching interview questions and reference answers, so new imports
need no session restart. Completed sessions still require reset or a new session.

`run --turns N` adds up to N turns without increasing the total budget. `resume` clears
pause. `reset` archives previous state under `archives/` and keeps input snapshots;
create a new session to rescan a changed repository.

Candidate speech is in `transcript.md` and `best_answer_cards.md`. Source excerpts,
reasoning, inferred details and experiment plans are in `answer_audit.md/.json`.
Session `materials.json` contains selected material snapshots; `material_usage.json`
records actual question/answer citations by turn. These snapshots preserve history when
a library document is removed. The library and session files named `materials.json`
have different roles and structures; do not copy one over the other.

## Human retests

```bash
interview-forge retest --session sessions/my-project
interview-forge answer --session sessions/my-project --file my-answer.md
interview-forge answer --session sessions/my-project --text '我的回答……'
interview-forge grade-retest --session sessions/my-project --attempt r1
interview-forge retest --session sessions/my-project --node KNOWLEDGE_NODE_ID
interview-forge review-retest --session sessions/my-project --attempt r1 \
  --score 0.85 --rationale '人工核对了机制、反例和验证方法'
```

Use either `--file` or `--text` for one submission. `retest` repeats a pending unanswered
question after restart without revealing the reference or rubric. `answer` commits the
human answer before model requests. If reference generation or grading fails, `status`
shows feedback pending; `grade-retest` retries the saved submission. Completed feedback
is returned unchanged when retried with an explicit `--attempt`.

`retest_feedback.md` contains submitted answers and subsequent feedback/reference.
Its source audit is exported separately in `answer_audit.md/.json`. Start the next
retest after current feedback completes.

A review score is 0–1; repeated `--missed` flags record missed points. Readiness needs
the latest two assessed answers to be distinct and explicitly reviewed as passing,
with no missed points. New unreviewed assessments, failed retests or downward corrections
revoke readiness. Generated answers and model scores alone do not establish mastery.

## Compatible model provider

```bash
# Set INTERVIEWFORGE_API_KEY in the environment if the endpoint requires authentication.
interview-forge start --resume resume.md --repo /path/to/project \
  --session sessions/live --provider compatible \
  --base-url http://localhost:8000/v1 --model your-model --run

interview-forge library add /path/to/scanned.pdf --kind interview \
  --ocr vision --provider compatible \
  --base-url http://localhost:8000/v1 --model your-vision-model
```

The URL is an API prefix; `/chat/completions` is appended. Compatible mode sends the
source data needed by the operation to that endpoint: resume/JD, selected repository or
reference excerpts, imported document blocks, and images for vision OCR. Credentials
are not saved in state. Session provider/model/base URL persist; library import provider
settings are supplied per command.

The adapter uses standard HTTP and local Pydantic validation, with no vendor SDK.
HTTP 429/5xx get at most three attempts. Invalid structured JSON gets one repair attempt.
Timeout is 45 seconds per request. Invalid citations or quality violations stop the turn;
completed turns remain saved. There is no silent switch to offline mode.

An ordinary compatible turn requests question, answer and knowledge generation; setup
also extracts claims. Answer repair, document batches, scanned pages and provider retries
can increase request count. Offline mode makes no model network requests.
