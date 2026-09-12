# Data contracts

Executable definitions: [session models](../interview_forge/schemas/models.py) and
[material models](../interview_forge/materials/models.py).
Regenerate distributable contracts using `interview-forge schemas --output schemas`.
Pydantic v2 emits JSON Schema through `model_json_schema()` ([official documentation](https://docs.pydantic.dev/latest/concepts/json_schema/)).

| Contract | Meaning |
|---|---|
| ResumeStatement | Exact source text, project and line |
| CapabilityClaim | Testable capability, dimension, risk, evidence links, separate answerability/mastery |
| RepoEvidence | Exact excerpt, relative path, symbol, line range, SHA256, type and limitations |
| EvidenceMatch | Question-aware retrieval score and reasons; relevance is not proof |
| RepositoryMap | File/symbol/category snapshot with skipped files and limitations |
| InterviewQuestion / InterviewTurn | Claim, depth/level, previous-turn provenance, material IDs and candidate answer |
| InterviewSession | Versioned authoritative state and all reference validation |
| Answer | Candidate speech, repository/reference IDs, reasoning basis, inferred details, experiment plan and separate audit fields |
| SourceBlock / DocumentRead | Text, PDF page, DOCX paragraph/table or image location with extraction method and warnings |
| MaterialDocument / MaterialItem / MaterialState | Imported documents, extracted interview questions/reference answers, exact source quotes and persistent library |
| KnowledgeNode / KnowledgeEdge | Shared concepts, typed relations and claim/question/project provenance |
| StudyCard / StudyTask / Exercise | Bounded explanation and gap-bound evidence-producing practice |
| MasteryState | Human evidence and assessment origin, independent from material answerability |
| RetestAttempt / Assessment | Pending question, human submission, delayed reference and advisory/reviewed score |
| PostInterviewReview | Coverage, gap categories, next round and learning updates |

The internal structure is a graph; tree rendering uses visited-node markers to handle
shared prerequisites and cycles. Source-claim and triggered-question relations are stored
on nodes; node-to-node relationships are stored in edges. Session schema version is 1.0;
unsupported versions fail validation instead of silently migrating.

Material library schema version is 1. Library documents retain parsed source blocks;
the session retains selected MaterialItem snapshots. Library edits do not rewrite
material snapshots already retained by a session.

`Answer.evidence_selection` is optional for older snapshots and records the bounded candidate context. Citations and retrieval candidates must belong to the question’s claim. A submitted retest may have null reference/assessment while feedback is pending; the human answer is already durable. Readiness validation checks the latest two assessed attempts, not merely any historical passing pair.

The v0.3 fields are additive: `SessionConfig.library_path` links a live library;
`InterviewSession.materials` retains citation snapshots; `InterviewQuestion.material_ids`
and `material_question` preserve the selected source wording. `Answer.reference_material_ids`
links reference answers, while `reasoning_basis`, `inferred_details`, and `experiment_plan`
hold the separate reasoning audit. Older sessions default these fields to empty values.
Question references must cite interview materials, answer references must cite answer
materials, and every reference must resolve within the saved session snapshot.
