# InterviewForge architecture

## Contract

Resume statements are source text; claims are falsifiable capability propositions.
Repository observations retain paths, lines, hashes and exact excerpts. Imported
interview experiences and reference answers retain their document origin.

The answerer produces natural candidate speech and a separate audit trail. Missing
implementation context can be completed through technical reasoning and specific
experiment plans. Audit records distinguish source observations, resume assertions,
external references and inferred details. Simulation assesses answerability; human
retest evidence establishes mastery.

## Pipeline

1. Import images and documents into a persistent material library. Readers return
   source blocks; offline or structured model extraction creates questions, answers,
   explicit follow-ups and topics. Validate quotations against source locations.
2. Extract source-bound claims from resume/JD and compute explainable risk.
3. Read a bounded repository snapshot without executing target code. Record excerpts,
   symbols, hashes, coverage limitations and claim relevance.
4. On each turn, retrieve live interview material matching the claim/JD. Interviewer
   receives claims, spoken history and question seeds, including existing follow-ups.
   It receives no repository excerpts/paths, reference answers or answer audit.
5. Retrieve reference answers for the chosen question. Answerer combines claim context,
   bounded source evidence and reference material. Direct speech develops a coherent
   design and validation story; reasoning basis, inference and experiment plans are
   separate typed fields. Source citations must refer to supplied records.
6. Commit the completed turn and selected material snapshots together. Track claim
   depth, coverage and novelty; route further questions from prior answer signals.
7. Merge anchored knowledge into a graph and derive focused exercises. Default learning
   includes P0/P1 concepts at distance <= 1. Review distinguishes material and mastery gaps.
8. Human retest saves a question before revealing references. Save the human answer
   before model feedback; retry feedback independently. Readiness requires two distinct
   recent assessed answers passing explicit human review.

## Components

Exactly two autonomous classes: Interviewer and RepositoryAnswerer. Document reading,
material extraction/retrieval, graph merging, grading and report rendering are services.
Pydantic models define the executable contracts; argparse provides the CLI.

The material package is standalone and does not import session schemas. `MaterialState`
contains documents and items, while session `materials` contains selected immutable
item snapshots. Kind checks keep interview question seeds and reference answers in
their appropriate input paths. External references do not become repository evidence.

`LLMClient` supports text and structured generation; the compatible adapter also
supports image transcription. Offline mode uses deterministic Redis/RAG/service
curricula and lexical material retrieval. OCR uses local Tesseract or configured vision,
with bounded file/page/text processing.

## State and failure behavior

Session `interview_state.json` and library `materials.json` are separate authoritative
JSON stores, each protected by a process lock and atomic replacement. Other JSON and
Markdown files are regenerable reports.

Reading/extraction completes before an import is committed. Content hash plus kind
deduplicates imports. Writers reload the latest snapshot while holding the library lock
to avoid lost updates. Multi-file import commits one document at a time.

A completed turn stores material snapshots with its references. Each new turn consults
the attached live library, so imports become available immediately and removed items
stop appearing in future retrieval. Historical snapshots continue to render citations.
`attach-library` changes only the source for subsequent turns.

Provider errors abort an uncommitted turn or document; earlier commits survive.
Human submissions survive grading failure. Reset archives prior session history and
does not delete the project repository.

## Outputs and limits

`transcript.md` and `best_answer_cards.md` contain natural spoken answers.
`answer_audit.md/.json` records source reasoning, inferred details, experiment plans and
unverified assertions. `material_usage.json` links actual citations to question/turn IDs;
session `materials.json` exports the corresponding context snapshots.

Text scanning and Python AST are not full program analysis. A source excerpt establishes
source text, and experiment parameters are not measurements. Imported results belong to
their source author. Schema and lexical checks constrain errors but cannot establish
arbitrary natural-language correctness or replace real model quality evaluation.
