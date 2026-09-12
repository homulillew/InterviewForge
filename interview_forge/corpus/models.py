"""Private corpus records; runtime sessions retain IDs and small derived traces only."""

from pydantic import Field, model_validator
from typing import Literal
from interview_forge.schemas.models import (
    Model,
    Score,
    Text,
    ClaimType,
    Dimension,
    ProbeIntent,
    ChallengeOperator,
)


class CorpusQuestion(Model):
    id: Text
    case_id: Text
    text: Text
    topic: list[str] = Field(default_factory=list)
    probe_intent: ProbeIntent
    challenge_operator: ChallengeOperator | None = None
    order: int | None = None
    previous_question_id: str | None = None
    answer_context: str | None = None
    answer_feature: list[str] = Field(default_factory=list)
    confidence: Score = 0.6


class QuestionChain(Model):
    id: Text
    case_id: Text
    question_ids: list[str]
    topic: list[str] = Field(default_factory=list)
    depth: int = Field(ge=0)
    quality: Score


class InterviewCase(Model):
    id: Text
    source_file: Text
    source_type: Literal["trace", "ordered_list", "unordered_summary"]
    source_hash: Text
    source_locations: list[str] = Field(default_factory=list)
    reader_warnings: list[str] = Field(default_factory=list)
    normalized_hash: Text
    company: str | None = None
    role: str | None = None
    round: str | None = None
    seniority: str | None = None
    company_confidence: Score = 0
    role_confidence: Score = 0
    round_confidence: Score = 0
    resume_context: list[str] = Field(default_factory=list)
    project_context: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    questions: list[CorpusQuestion] = Field(default_factory=list)
    chains: list[QuestionChain] = Field(default_factory=list)
    case_quality: Score = 0
    duplicate_group: str | None = None
    record_index: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def references(self):
        ids = {q.id for q in self.questions}
        if len(ids) != len(self.questions):
            raise ValueError("duplicate corpus question")
        seen = set()
        for q in self.questions:
            if q.case_id != self.id or (q.previous_question_id and q.previous_question_id not in seen):
                raise ValueError("invalid question chronology")
            seen.add(q.id)
        for chain in self.chains:
            if (
                chain.case_id != self.id
                or not set(chain.question_ids) <= ids
                or chain.depth != len(chain.question_ids)
            ):
                raise ValueError("invalid corpus chain")
        if self.source_type == "unordered_summary" and self.chains:
            raise ValueError("unordered summaries cannot supply chains")
        return self


class QuestionTransition(Model):
    id: Text
    from_question_id: str | None = None
    from_intent: ProbeIntent
    candidate_answer_features: list[str] = Field(default_factory=list)
    trigger_summary: Text
    to_intent: ProbeIntent
    challenge_operator: ChallengeOperator
    example_question_id: Text
    confidence: Score
    source_case_id: Text
    observed_answer: bool = False


class ProbePattern(Model):
    id: Text
    source_case_ids: list[str]
    source_question_ids: list[str]
    applicable_topics: list[str]
    applicable_technology_families: list[str]
    trigger_claim_types: list[ClaimType]
    trigger_answer_features: list[str]
    attack_dimension: Dimension
    challenge_operator: ChallengeOperator
    abstract_pattern: Text
    next_intents: list[ProbeIntent]
    support_count: int = Field(ge=1)
    quality: Score


class InterviewerStyleProfile(Model):
    id: Text
    company: str | None = None
    role_family: str | None = None
    round: str | None = None
    seniority: str | None = None
    sample_size: int = Field(ge=0)
    median_chain_depth: float = Field(ge=0)
    p75_chain_depth: float = Field(ge=0)
    probe_distribution: dict[str, Score]
    operator_distribution: dict[str, Score]
    transition_distribution: dict[str, Score]
    question_length_median: float = Field(ge=0)
    style_features: list[str]
    confidence: Score
    parent_profile_ids: list[str] = Field(default_factory=list)


class CompiledCorpus(Model):
    cases: list[InterviewCase]
    transitions: list[QuestionTransition]
    patterns: list[ProbePattern]
    style_profiles: list[InterviewerStyleProfile]

    @model_validator(mode="after")
    def references(self):
        cases = {c.id for c in self.cases}
        qs = {q.id: q for c in self.cases for q in c.questions}
        if len(cases) != len(self.cases) or len(qs) != sum(len(c.questions) for c in self.cases):
            raise ValueError("duplicate corpus identifiers")
        for records in (self.transitions, self.patterns, self.style_profiles):
            if len({r.id for r in records}) != len(records):
                raise ValueError("duplicate compiled record identifiers")
        style_ids = {p.id for p in self.style_profiles}
        for profile in self.style_profiles:
            if not set(profile.parent_profile_ids) <= style_ids or profile.id in profile.parent_profile_ids:
                raise ValueError("invalid style parent provenance")
            for distribution in (
                profile.probe_distribution,
                profile.operator_distribution,
                profile.transition_distribution,
            ):
                if distribution and abs(sum(distribution.values()) - 1) > 1e-6:
                    raise ValueError("invalid style distribution")
        for t in self.transitions:
            if (
                t.source_case_id not in cases
                or t.example_question_id not in qs
                or t.from_question_id not in qs
            ):
                raise ValueError("dangling transition")
            previous, following = qs[t.from_question_id], qs[t.example_question_id]
            if previous.case_id != t.source_case_id or following.previous_question_id != previous.id:
                raise ValueError("transition chronology mismatch")
            if t.candidate_answer_features and (not t.observed_answer or not previous.answer_context):
                raise ValueError("unobserved answer-conditioned transition")
        for p in self.patterns:
            if not set(p.source_case_ids) <= cases or not set(p.source_question_ids) <= qs.keys():
                raise ValueError("dangling pattern")
            if not p.source_question_ids or {qs[qid].case_id for qid in p.source_question_ids} != set(
                p.source_case_ids
            ):
                raise ValueError("pattern source questions disagree with cases")
        return self
