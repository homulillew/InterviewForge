# Data contracts

Executable models: [session](../interview_forge/schemas/models.py),
[corpus](../interview_forge/corpus/models.py), [preparation library](../interview_forge/materials/models.py).
Regenerate JSON Schema with `interview-forge schemas --output schemas`.

| Contract | Meaning |
|---|---|
| ResumeStatement / AtomicClaim | Original text and actual assertion; claim_type, technologies, concepts, risk; no Dimension on claim |
| AttackSurface / AttackPlan | Dimension and coverage; utility, unresolved facets and operator candidates |
| QuestionPlan / QuestionProvenance | Planned target/alternative/assumptions and validated resume/corpus/style adaptation trace |
| InterviewCase / CorpusQuestion / QuestionChain | Source metadata, question text, observed answer, explicit chronology and quality |
| QuestionTransition / ProbePattern | Observed intent transition and abstract challenge operator with source IDs |
| InterviewerStyleProfile / EffectiveStyle | Deduplicated descriptive statistics, confidence and hierarchical blend |
| CorpusPin / CorpusMatchRef / TransitionRef | Session pin and small references; no full corpus in session |
| RepoEvidence / EvidenceRelation / EvidenceMatch | Exact static source, assessed relation vocabulary, independent retrieval relevance |
| InterviewQuestion / InterviewTurn | Required plan/provenance; spoken answer, red critique and surface update |
| Answer / AnswerCritique | Serialized spoken_answer and separate audit; independent red analysis of speech |
| MaterialGap / AnswerGap / MasteryGap | Source gap, spoken gap and evaluated human-only gap |
| KnowledgeNode / KnowledgeEdge / FollowupQA | Canonical shared concepts, provenance and answered study follow-ups |
| StudyCard / StudyTask / Exercise | Bounded active learning, covers_node_ids, estimated minutes and benefit |
| MasteryState / RetestAttempt / Assessment | Durable human work, delayed reference and explicit reviewed readiness |
| MaterialDocument / MaterialItem / MaterialState | Standalone preparation library, source quotes and locations |

Session schema is **2.0**, corpus SQLite schema is **1**, preparation-library schema remains **1**.
The old dimension-bearing schema is isolated in `schemas/legacy_v1.py`. CapabilityClaim is only
a Python alias for AtomicClaim, not an exported legacy contract. Answer accepts legacy
`direct_interview_answer` on input and exposes a Python read property; schema 2.0 serialization
uses `spoken_answer`.

Normal loading rejects schema 1.0 with `migrate-session` instructions. Migration validates the
legacy state, archives exact input bytes and preserves human/history records. Historical
questions receive origin=migration with unknown corpus support. No fake pattern/style linkage
is inferred from old material IDs.

Session validation covers bidirectional related evidence, relation pairs, assertion/surface
anchors, plan/provenance consistency, corpus revision references, surface counts, graph edges,
study task sources and human mastery evidence. Continuation also validates the pinned database
fingerprint, revision hash, source IDs and effective style. Retrieval relevance does not prove
an EvidenceRelation stronger than related.
