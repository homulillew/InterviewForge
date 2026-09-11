# Data contracts

Executable definitions: [models.py](../interview_forge/schemas/models.py).
Regenerate distributable contracts using `interview-forge schemas --output schemas`.
Pydantic v2 emits JSON Schema through `model_json_schema()` ([official documentation](https://docs.pydantic.dev/latest/concepts/json_schema/)).

| Contract | Meaning |
|---|---|
| ResumeStatement | Exact source text, project and line |
| CapabilityClaim | Testable capability, dimension, risk, evidence links, separate answerability/mastery |
| RepoEvidence | Exact excerpt, relative path, symbol, line range, SHA256, type and limitations |
| EvidenceMatch | Question-aware retrieval score and reasons; relevance is not proof |
| RepositoryMap | File/symbol/category snapshot with skipped files and limitations |
| InterviewQuestion / InterviewTurn | Claim, depth/level, previous-turn provenance and grounded answer |
| InterviewSession | Versioned authoritative state and all reference validation |
| Answer | Direct expression, evidence IDs, general knowledge, unsupported claims and next questions |
| KnowledgeNode / KnowledgeEdge | Shared concepts, typed relations and claim/question/project provenance |
| StudyCard / StudyTask / Exercise | Bounded explanation and gap-bound evidence-producing practice |
| MasteryState | Human evidence and assessment origin, independent from material answerability |
| RetestAttempt / Assessment | Pending question, human submission, delayed reference and advisory/reviewed score |
| PostInterviewReview | Coverage, gap categories, next round and learning updates |

The internal structure is a graph; tree rendering uses visited-node markers to handle
shared prerequisites and cycles. Source-claim and triggered-question relations are stored
on nodes; node-to-node relationships are stored in edges. Session schema version is 1.0;
unsupported versions fail validation instead of silently migrating.

`Answer.evidence_selection` is optional for older snapshots and records the bounded candidate context. Citations and retrieval candidates must belong to the question’s claim. A submitted retest may have null reference/assessment while feedback is pending; the human answer is already durable. Readiness validation checks the latest two assessed attempts, not merely any historical passing pair.
