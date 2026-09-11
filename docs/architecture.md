# InterviewForge architecture

## Contract

Resume statements are source text; claims are falsifiable capability propositions.
Repository observations are excerpts, never proof of ownership or production results.
Simulation evaluates answerability. Only human retest evidence updates mastery.

## Pipeline

1. Extract source-bound capability claims, validate quality, compute explainable risk.
2. Read a bounded repository snapshot (no code execution), classify files and symbols,
   link relevant excerpts to claims. Rank the bounded answer context against the current question,
   recording lexical relevance and artifact-type reasons separately from factual confidence. Record omissions, hashes and coverage limitations.
3. Interviewer receives a deliberately narrowed view: claims, JD, spoken answers and
   observed gaps. It never receives repository paths, excerpts or evidence objects.
4. Answerer selects only existing evidence IDs. Project grounding is rendered from
   immutable source excerpts. Technical explanation, proposed improvements and
   unverified resume assertions are separate fields.
5. Controller persists each completed turn, tracks per-claim depth, coverage and novelty;
   adapts next questions to answer signals. Max turns and per-claim limits bound cost.
6. Extract source-bound knowledge nodes, merge shared concepts into a graph; derive
   concise cards and gap-bound exercises. Default plan includes P0/P1, distance <= 1.
7. Review reports material gaps and next-round actions, without grading a simulated user.
8. Retest stores an unanswered question first. Human submission precedes reference
   generation. Commit the human submission first; feedback can be retried separately.
   The latest two assessed answers must pass explicit human review before interview_ready.

## Components

Two agent classes only: Interviewer and RepositoryAnswerer. Extraction, graph merging,
scoring, storage and report rendering are services, not additional autonomous agents.
Pydantic is the executable contract; `schemas` exports JSON Schema. argparse provides
CLI. JSON is authoritative; Markdown and per-domain JSON files are regenerable views.

`LLMClient` supports generate and structured_generate. The optional compatible HTTP
adapter consumes independently maintained prompts and validates all structured output.
No provider is contacted in offline mode. Offline mode is a transparent deterministic
baseline with Redis/RAG/service curricula, not a general semantic interview model.

## State and failure behavior

A process lock protects a session transaction. `interview_state.json` is atomically
replaced and validated; denormalized outputs can be regenerated after interruption.
Each completed turn commits separately. Provider errors stop without silently switching
to demo output; resume retries the uncommitted turn. Session config pins mode and model.
Reset archives the prior state; never deletes the project repository.

## Limits

Text scanning and Python AST symbols are not full interprocedural analysis. Missing
matches mean not verified in this snapshot, not absent in every deployment. Source
excerpts prove source text, not runtime behavior. LLM semantic judgments need review;
lexical filters and JSON validation cannot prove arbitrary generated text truthful.
