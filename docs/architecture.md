# Corpus-grounded adversarial interviewer architecture

Package 0.3.1, session schema 2.0, corpus SQLite schema 1. Baseline and design decisions are in
[corpus-harness-design.md](corpus-harness-design.md); executable models are in `schemas/models.py`
and `corpus/models.py`.

## Inputs and the two-agent boundary

ResumeStatement is original text. AtomicClaim is an actual assertion with claim_type,
technologies and concepts; it has no Dimension. AttackSurface owns Dimension, relevance,
priority and persisted coverage. Risk ranks assertions; utility ranks useful surfaces.

Only Interviewer and RepositoryAnswerer are agents. Corpus normalization, deduplication,
chains, pattern compilation, retrieval, AttackPlanner, QuestionPlanner, AnswerCritic,
knowledge extraction/compression, learning and grading are services, even when a service
uses the configured model for a bounded structured operation.

| Recipient | Allowed input | Excluded input |
|---|---|---|
| Interviewer renderer | Allowlisted resume assertion, surface, plan, abstract operators, statistics, spoken history | Source paths/excerpts/IDs, repository map, blue audit, raw corpus questions |
| AnswerCritic | Resume assertion, question, expected facets, current/prior speech | Repository evidence, source coverage, blue signals and audit |
| RepositoryAnswerer model | Question ID/text, atomic resume assertion, bounded static excerpts | Corpus, style, operators, plans, transitions, reference-answer documents |

The engine supplies only operator abstractions to the renderer. Raw corpus wording stays in
the local controller for the copy guard. The controller owns IDs/provenance; renderer output
is only RenderedQuestion. Guards reject trivia, missing resume anchor, unrelated recognized
technology, invented numeric/selected architectural premises, multiple main questions,
exact/near repeats and normalized 24-character copying. These checks do not prove arbitrary
natural-language factuality; model quality review remains necessary.

## Corpus and retrieval

`corpus/normalize.py` reads heterogeneous post shapes using shared document readers. Explicit
metadata is preserved; missing company/round stays unknown. Ordered lists teach sequence at
lower confidence; answer-conditioned transitions require actual candidate answer context;
unordered summaries contribute no invented chains. Repeated posts share duplicate groups.

`storage.py` owns FTS5, normalized tables and full compiled revision payloads. Transactions use
BEGIN IMMEDIATE and compare-and-swap current revision. UUID identifies the database; SHA-256
verifies immutable revision content. Ingest replaces normalized records from changed files,
archives prior compiled revisions, and commits a whole batch. Rebuild recompiles normalized
records. Raw input files are not copied to session or distributions.

Three APIs remain separate: content retrieval gates direct/transferable/style_only/reject and
weights resume relevance above company; transition retrieval uses previous intent and spoken
answer features; style retrieval blends sample-confidence-weighted hierarchical profiles.
Duplicates count once in statistical profiles. No company-specific personality is hardcoded.

AttackPlan selects assertion/surface and useful operator candidates. QuestionPlan records the
target, alternative, assumptions, expected points, matches, patterns, transitions, style and
adaptation reason. Rendering follows that plan. After answering, the red critic determines
coverage and unresolved facets. Next surface utility considers risk, relevance, coverage,
corpus support, style preference, answer trigger, repetition, novelty and depth limits.

## Evidence, speech and learning

Static scanning reads bounded text and AST without executing a target repository. Every
lexical evidence association creates EvidenceRelation(relation=related). direct_support,
partial_support, limitation and contradicts are explicit vocabulary for future reviewed
relations; the scanner never assigns them. Implementation/config/validation/metric/ownership
facets remain distinct from relevance. No performance result is proven by test source.

Answer serializes `spoken_answer` separately from reasoning_basis, inferred_details,
experiment_plan, source selection and unsupported_claims. Python read access to
`direct_interview_answer` remains a compatibility property. The red critic reads speech only.
MaterialGap and AnswerGap do not establish a human MasteryGap.

Knowledge extraction adds at most four nodes per model turn, two opportunities in the offline
baseline. Canonical aliases and title matching merge concepts and retain provenance. Study
cards contain answered FollowupQA. Greedy weighted set cover combines related nodes into
exercises; human gaps retain their own review/recovery evidence.

## Persistence and migration

`interview_state.json` is authoritative, process-locked and atomically replaced. A turn is
committed only after renderer, answerer, critic and knowledge stages succeed. Exported reports
are disposable views. Sessions store a corpus pin and small used match/transition references,
not complete corpus records. Provider/model configuration persists with the session. Every
turn verifies database identity, revision integrity and effective style against the pinned
revision. New ingest affects only new sessions. Reset archives state and retains the pin.

`migrate-session` validates the separate legacy model, maps old dimension-bearing claims to
re-extracted assertions/surfaces, preserves spoken history and human work, archives original
bytes and saves schema 2.0. Unknown historical corpus provenance is labeled migration.
Historical material snapshots remain archival, never new runtime context.

Human retest persists submission before generating reference/assessment. Failed feedback is
resumable and cannot overwrite the saved answer. Two distinct latest assessed answers must
pass actual human review for readiness. New assessment or downgrade invalidates old readiness.
