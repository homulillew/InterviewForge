# Corpus interview harness implementation design

Baseline: commit 3892de9, schema 1.0, 156 passing tests and clean ruff. This builds on
the existing material readers and static repository scanner. It changes the semantics
of claims and question generation, so new sessions use schema 2.0 (package 0.3.1).

## Decisions

1. AtomicClaim represents a quoted assertion, never a required competency. Dimension
   belongs to an independently generated AttackSurface. Risk ranks assertions; surface
   utility incorporates unanswered facets, prior spoken-answer critique and style.
2. CorpusCompiler is a service using the existing text/vision transport. It accepts
   local text, JSON/JSONL and the existing document formats, normalizes explicit metadata,
   learns ordered chains and abstract operators, then commits a version to SQLite/FTS5.
   Trace, ordered list and unordered summary have different priors. Only observed
   answer context can supply answer-conditioned transitions. Duplicate groups count once.
3. SQLite retains immutable compiled revisions. Sessions pin a revision and effective
   profile; ingest/rebuild does not change an ongoing session. Raw user files are never
   copied to Git, distributions or session state. Local inspection resolves source IDs.
4. Content, transitions and style have separate retrieval APIs. Applicability explicitly
   distinguishes direct, transferable, style-only and reject. Resume relevance dominates
   company match. Transferable operators carry no foreign technology into rendering.
5. AttackPlan -> QuestionPlan -> renderer -> deterministic guards. Only the renderer
   uses the Interviewer model. Its allowlisted context has no repository paths, excerpts,
   identifiers or blue audit. Corpus contributes abstractions, never a pile of raw posts.
6. RepositoryAnswerer receives a stripped question, atomic resume claim and bounded
   static evidence. It receives no corpus, company style or planning metadata. Existing
   reference documents remain available as preparation materials, outside the defender.
7. AnswerCritic is a blind service evaluating spoken content, not source availability.
   MaterialGap, AnswerGap and human-only MasteryGap are distinct. Blue self-signals remain a legacy diagnostic field and never route new questions.
8. Canonical concepts replace facet-named knowledge nodes. Small per-turn extraction is
   merged, and greedy multi-node exercises maximize relevant coverage per study minute.
   Human submissions, reviews, readiness revocation and atomic commits remain intact.

## Migration and execution order

An explicit `migrate-session --session ...` validates schema 1.0, archives the original bytes,
maps old claim/facet identifiers to assertions and surfaces, and preserves spoken history,
source quotations and human submissions. No silent migration during normal load.

Implementation order: contracts/claims/migration; compiler/storage; retrieval/style;
planner/renderer/critic; engine/retest; compressed learning; CLI/reports/evals; tests/docs.
Offline remains an authored baseline when no corpus is pinned; corpus style requires
an actual compiled database. No live model quality or company generalization is claimed
by synthetic contract tests.
