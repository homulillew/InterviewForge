---
name: interview-forge
description: Compile private interview experiences into a local corpus, run resume-grounded adversarial technical interviews with repository-aware candidate answers, and build focused study cards and human retests.
---

# InterviewForge

Let the resume decide WHAT to test, corpus patterns decide HOW to challenge it, and the
previous spoken answer decide WHERE to probe next. Read [CLI](references/cli.md) for commands
and [architecture](docs/architecture.md) when changing the workflow.

## Inputs and corpus

Use UTF-8 resume/JD and a static project repository. Compile local interview images,
PDF/DOCX, text or JSON/JSONL with `corpus ingest`. Keep user corpus outside tracked examples
and release artifacts. Shared readers preserve available source text; do not invent missing
answers, company, round or chronology. Trace, ordered-list and summary priors differ.
Deduplicate independent samples before learning statistical style.

Reference-answer documents remain in the preparation `library`; they are available for
lookup, not RepositoryAnswerer runtime context. New sessions pin corpus revision, database
identity, effective profile and provider/model. New ingest must not alter an ongoing session.
See [corpus rules](rules/corpus-applicability.md) and [style rules](rules/style-confidence.md).

## Interview boundaries

- Extract AtomicClaim assertions quoted from the resume. Dimension belongs only to
  AttackSurface. Rank claim risk first, then useful unanswered attack opportunities.
- Keep exactly two agents: Interviewer and RepositoryAnswerer. Compiler, planner, critic,
  knowledge and grading are services.
- Interviewer and red AnswerCritic cannot see repository paths, excerpts, evidence IDs,
  blue audit or self-reported routing signals. Critic evaluates spoken content only.
- RepositoryAnswerer receives only the current question, resume assertion, relevant static
  evidence and general knowledge. It cannot see corpus, company style, plans or operators.
- Select AttackPlan, retrieve content/transitions/style independently, gate applicability,
  build QuestionPlan, render one primary question and validate it before answering. Transfer
  abstract challenge structure without importing unrelated source technologies. Every
  question retains validated provenance; use `explain-question` for inspection.
- Answer as a candidate, directly and concretely. Complete missing engineering details and
  experimental inputs with coherent reasoning. Keep audit phrases out of speech; preserve
  assumptions, source limits and unverified measurements in separate audit fields.

Read [claim quality](rules/claim-quality.md), [question quality](rules/question-quality.md),
[depth](rules/interview-depth.md), and [evidence boundaries](rules/evidence-boundary.md).

## Persistence, learning and human work

Load authoritative `interview_state.json`; use locks and atomic saves. Schema 1.0 requires
explicit `migrate-session`, which archives original bytes and preserves human work. Reset
archives history and keeps the input/corpus snapshot; new source versions need a new session.

Compress canonical knowledge concepts, preserve provenance, and provide answered FollowupQA.
Prefer multi-node exercises with high interview benefit per study minute. MaterialGap,
AnswerGap and human-only MasteryGap remain distinct. Follow [learning rules](rules/learning-efficiency.md).

Retest saves one question, waits for the user's independent answer, and persists that answer
before generating feedback. Resume failed feedback with `grade-retest`. Never record an
imaginary human review to promote readiness. Respect turn/depth budgets, surface exhaustion,
strong answers, novelty and higher-value unexplored assertions.

Return report/answer-card paths and the next useful exercise. Describe offline heuristics and
manual-review metrics accurately; synthetic tests do not establish real company style or
live model quality. See [current limits](docs/iteration-0.3.1.md) and [schemas](references/schemas.md).
