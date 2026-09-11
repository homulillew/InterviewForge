# CLI reference

Install from the repository: `python -m pip install -e '.[dev]'`. Python 3.11+, Linux/macOS.
All commands also work as `python -m interview_forge`. Inputs are UTF-8 text/Markdown.

```bash
interview-forge start --resume resume.md --repo /path/to/project --jd jd.md \
  --session sessions/my-project --max-turns 12 --max-depth 5 --run
interview-forge run --session sessions/my-project --turns 2
interview-forge pause --session sessions/my-project
interview-forge resume --session sessions/my-project --turns 3
interview-forge status --session sessions/my-project
interview-forge score --session sessions/my-project
interview-forge report --session sessions/my-project
interview-forge tree --session sessions/my-project
interview-forge retest --session sessions/my-project
interview-forge answer --session sessions/my-project --file my-answer.md
interview-forge grade-retest --session sessions/my-project --attempt r1
interview-forge retest --session sessions/my-project --node KNOWLEDGE_NODE_ID
interview-forge review-retest --session sessions/my-project --attempt r1 \
  --score 0.85 --rationale '人工核对了机制、反例和验证方法'
interview-forge reset --session sessions/my-project
interview-forge schemas --output schemas
```

`start` without `--run` prepares state only. The offline provider makes no network calls.
`run --turns N` runs up to N additional turns without increasing the session's total budget.
`resume` clears pause. `reset` keeps input snapshots and archives previous state under
`archives/`; create a new session to rescan a changed repository.

`retest` repeats the pending unanswered question after restart; it does not reveal an
answer or expected rubric points. `answer` produces feedback/reference only after a human
submission. The human answer is committed to the authoritative snapshot **before** any
model request. If reference generation or grading fails, `status` shows feedback pending;
use `grade-retest` to retry the saved submission. It cannot overwrite the human answer.
Completed feedback is returned unchanged when retried with an explicit `--attempt`.
`retest_feedback.md` contains submitted answers, feedback and separately quoted grounding;
it contains no rubric/reference for unanswered retests. Start the next retest after the
current feedback is complete.

A review score is 0–1; use repeated `--missed` for specific missing points.
Readiness needs the latest two assessed answers to be distinct and explicitly reviewed
as passing with no missed points. A new unreviewed model assessment, a failed retest or
a downward correction of a review revokes readiness. Generated
or keyword-based scores alone never meet that criterion.

## Compatible model provider

```bash
# Set credentials in the environment if your endpoint requires them.
export INTERVIEWFORGE_API_KEY='your-key'
interview-forge start --resume resume.md --repo /path/to/project \
  --session sessions/live --provider compatible \
  --base-url http://localhost:8000/v1 --model your-model --run
```

The URL is an API prefix; `/chat/completions` is appended. Compatible mode sends resume/JD
and selected source excerpts to that endpoint. Credentials are not saved in session state.
Config (provider, model, base URL) persists, so later commands use the same backend.
The adapter uses standard HTTP, JSON-in-prompt schemas and local Pydantic validation; it
does not require a vendor SDK or proprietary structured-output extension.

HTTP 429/5xx get at most three attempts. Invalid structured JSON gets one repair attempt.
Timeout is 45 seconds per request. Invalid citations or quality violations stop the turn;
there is no silent fallback to offline. Completed turns remain resumable. A full compatible
turn makes three model calls: question, answer, knowledge; setup adds one claim-extraction
call. Model providers, timeouts and malformed outputs can increase request count.
