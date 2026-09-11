"""Versioned contracts. Cross-object provenance is validated at the session boundary."""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=16000)]
Score = Annotated[float, Field(ge=0, le=1)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Dimension(str, Enum):
    problem = "Problem Understanding"
    mechanism = "Mechanism Understanding"
    decision = "Technology Decision"
    engineering = "Implementation / Engineering"
    tradeoff = "Trade-off Awareness"
    failure = "Failure Handling"
    evaluation = "Evaluation / Measurement"
    scaling = "Scaling"
    ownership = "Ownership"


class ResumeStatement(Model):
    id: Text
    text: Text
    project: Text
    line: int = Field(ge=1)


class MasteryState(Model):
    status: Literal["unknown", "learning", "needs_practice", "interview_ready"] = "unknown"
    evidence: list[str] = Field(default_factory=list)
    assessed_by: Literal["none", "heuristic", "model", "human_reviewer"] = "none"

    @model_validator(mode="after")
    def supported(self):
        if self.status == "interview_ready" and (not self.evidence or self.assessed_by != "human_reviewer"):
            raise ValueError("interview_ready requires reviewed human retest evidence")
        return self


class CapabilityClaim(Model):
    id: Text
    statement_id: Text
    proposition: Text
    dimension: Dimension
    topic: Text
    project: Text
    source_quote: Text
    risk_score: float = Field(default=0, ge=0, le=100)
    risk_factors: dict[str, Score] = Field(default_factory=dict)
    risk_reasons: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    answerability: Literal["unknown", "low", "medium", "high"] = "unknown"
    mastery: MasteryState = Field(default_factory=MasteryState)


class RepoEvidence(Model):
    id: Text
    file_path: Text
    symbol: str | None = None
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    evidence_type: Literal["implementation", "test", "documentation", "config", "dependency", "evaluation"]
    summary: Text
    excerpt: Text
    sha256: Text
    confidence: Score
    supports_claim: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_range(self):
        if self.line_end < self.line_start:
            raise ValueError("reversed source range")
        from pathlib import PurePosixPath
        if PurePosixPath(self.file_path).is_absolute() or ".." in PurePosixPath(self.file_path).parts:
            raise ValueError("evidence paths must be repository relative")
        return self


class RepositoryMap(Model):
    root: Text
    revision: str | None = None
    files: list[str] = Field(default_factory=list)
    languages: dict[str, int] = Field(default_factory=dict)
    sections: dict[str, list[str]] = Field(default_factory=dict)
    symbols: dict[str, list[str]] = Field(default_factory=dict)
    skipped: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class InterviewQuestion(Model):
    id: Text
    claim_id: Text
    text: Text
    dimension: Dimension
    level: int = Field(ge=0, le=9)
    depth: int = Field(ge=0, le=9)
    subtopic: Text
    rationale: Text
    based_on_turn: str | None = None
    expected_points: list[str] = Field(default_factory=list)


class EvidenceMatch(Model):
    evidence_id: Text
    relevance_score: float = Field(ge=0)
    reasons: list[Text] = Field(min_length=1)


class Answer(Model):
    question_id: Text
    direct_interview_answer: Text
    evidence_selection: list[EvidenceMatch] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    technical_explanation: Text
    technology_decision: Text
    failure_modes: list[str]
    unsupported_claims: list[str]
    likely_followups: list[str]
    related_knowledge: list[str]
    improvement_directions: list[str]
    answerability: Literal["low", "medium", "high"]
    signals: list[Literal["vague", "api_only", "no_implementation", "no_decision", "no_measurement", "failure_gap", "solid"]]
    provenance: Literal["offline", "model"]


class InterviewTurn(Model):
    id: Text
    question: InterviewQuestion
    answer: Answer
    kind: Literal["simulation"] = "simulation"
    weaknesses_observed: list[str]
    new_knowledge_ids: list[str] = Field(default_factory=list)


class KnowledgeNode(Model):
    id: Text
    title: Text
    category: Text
    priority: Literal["P0", "P1", "P2", "P3"]
    interview_distance: int = Field(ge=0, le=3)
    source_claims: list[str] = Field(min_length=1)
    triggered_questions: list[str] = Field(min_length=1)
    project_anchors: list[str] = Field(min_length=1)
    interview_one_liner: Text
    core_explanation: Text
    key_mechanism: Text
    decision_logic: Text
    failure_modes: list[str]
    alternatives: list[str]
    common_traps: list[str]
    likely_followups: list[str]
    practice_questions: list[str]
    retest_questions: list[str]
    mastery: MasteryState = Field(default_factory=MasteryState)
    evidence: list[str] = Field(default_factory=list)


class KnowledgeEdge(Model):
    source: Text
    target: Text
    relation_type: Literal["requires", "explains", "used_by", "alternative_to", "causes", "mitigates", "measured_by", "scales_to", "failure_of", "derived_from_project", "triggered_by_question"]
    provenance: Text
    distance: int = Field(ge=0, le=3)
    confidence: Score


class KnowledgeGraph(Model):
    nodes: list[KnowledgeNode] = Field(default_factory=list)
    edges: list[KnowledgeEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_edges(self):
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("duplicate knowledge node")
        for e in self.edges:
            if e.source not in ids or e.target not in ids or e.source == e.target:
                raise ValueError("invalid graph edge")
        return self


class StudyCard(Model):
    node_id: Text
    one_liner: Text
    explanation: Text
    followups: list[str]
    time_minutes: int = Field(default=5, ge=1, le=15)


class Exercise(Model):
    kind: Literal["theory", "mechanism", "design_decision", "alternative_comparison", "failure_mode", "debugging", "implementation", "system_design", "performance_evaluation", "project_improvement", "from_scratch", "debug_broken", "extend", "optimize", "mini_evaluation", "ablation"]
    prompt: Text
    evidence_produced: Text


class StudyTask(Model):
    id: Text
    node_id: Text
    weakness: Text
    evidence_from_interview: list[str] = Field(min_length=1)
    root_knowledge_gap: Text
    gap_kind: Literal["material_gap", "mastery_gap"]
    learning_objectives: list[str]
    exercises: list[Exercise]
    project_task: Text
    retest_questions: list[str]
    mastery_criteria: list[str]
    status: Literal["pending", "completed"] = "pending"


class Assessment(Model):
    score: Score
    missed_points: list[str]
    rationale: Text
    assessor: Literal["heuristic", "model", "human_reviewer"]


class RetestAttempt(Model):
    id: Text
    node_id: Text
    question: InterviewQuestion
    human_answer: Text | None = None
    reference: Answer | None = None
    assessment: Assessment | None = None

    @model_validator(mode="after")
    def conceal(self):
        if self.human_answer is None and (self.reference is not None or self.assessment is not None):
            raise ValueError("reference/assessment forbidden before candidate submission")
        return self


def reviewed_ready(attempts: list[RetestAttempt]) -> bool:
    recent = [r for r in attempts if r.assessment is not None][-2:]
    return len(recent) == 2 and len({r.question.text for r in recent}) == 2 and all(
        r.assessment.assessor == "human_reviewer" and r.assessment.score >= 0.8
        and not r.assessment.missed_points for r in recent)


class PostInterviewReview(Model):
    claim_coverage: dict[str, int]
    strongly_defended_claims: list[str]
    weakly_defended_claims: list[str]
    unsupported_claims: list[str]
    knowledge_gaps: list[str]
    engineering_gaps: list[str]
    decision_making_gaps: list[str]
    failure_mode_gaps: list[str]
    evaluation_gaps: list[str]
    recommended_next_round: list[str]
    study_tasks: list[str]
    knowledge_graph_update: list[str]
    interpretation: str = "Simulation describes material answerability, not candidate mastery."


class SessionConfig(Model):
    provider: Literal["offline", "compatible"] = "offline"
    model: str | None = None
    base_url: str | None = None
    max_turns: int = Field(default=12, ge=1, le=100)
    max_depth: int = Field(default=5, ge=1, le=10)
    deep_dive: bool = False


class InterviewSession(Model):
    schema_version: Literal["1.0"] = "1.0"
    id: Text
    status: Literal["ready", "running", "paused", "completed"] = "ready"
    resume: Text
    jd: str = ""
    config: SessionConfig
    statements: list[ResumeStatement]
    claims: list[CapabilityClaim]
    repository_map: RepositoryMap
    evidences: list[RepoEvidence]
    transcript: list[InterviewTurn] = Field(default_factory=list)
    knowledge_graph: KnowledgeGraph = Field(default_factory=KnowledgeGraph)
    study_cards: list[StudyCard] = Field(default_factory=list)
    study_plan: list[StudyTask] = Field(default_factory=list)
    retests: list[RetestAttempt] = Field(default_factory=list)
    review: PostInterviewReview | None = None
    stop_reason: str | None = None

    @model_validator(mode="after")
    def references(self):
        def unique(items):
            ids = {x.id for x in items}
            if len(ids) != len(items):
                raise ValueError("duplicate IDs")
            return ids
        sids, cids, eids = unique(self.statements), unique(self.claims), unique(self.evidences)
        tids = unique(self.transcript)
        nids = unique(self.knowledge_graph.nodes)
        unique(self.study_plan)
        unique(self.retests)
        questions = [t.question for t in self.transcript] + [r.question for r in self.retests]
        qids = unique(questions)
        by_statement = {s.id: s for s in self.statements}
        for c in self.claims:
            if c.statement_id not in sids or c.source_quote not in by_statement[c.statement_id].text:
                raise ValueError("claim must quote its resume statement")
            if not set(c.evidence_ids) <= eids:
                raise ValueError("dangling claim evidence")
            for eid in c.evidence_ids:
                if c.id not in next(e.supports_claim for e in self.evidences if e.id == eid):
                    raise ValueError("claim links must be bidirectional")
        for e in self.evidences:
            if not set(e.supports_claim) <= cids:
                raise ValueError("dangling evidence claim")
            for cid in e.supports_claim:
                if e.id not in next(c.evidence_ids for c in self.claims if c.id == cid):
                    raise ValueError("evidence links must be bidirectional")
        for q in questions:
            if q.claim_id not in cids or (q.based_on_turn and q.based_on_turn not in tids):
                raise ValueError("dangling question provenance")
        def validate_answer(answer, question):
            allowed = {e.id for e in self.evidences if question.claim_id in e.supports_claim}
            if not set(answer.evidence_ids) <= allowed:
                raise ValueError("answer evidence does not support its claim context")
            if not {m.evidence_id for m in answer.evidence_selection} <= allowed:
                raise ValueError("invalid retrieval provenance")
        for t in self.transcript:
            validate_answer(t.answer, t.question)
            if t.answer.question_id != t.question.id or not set(t.answer.evidence_ids) <= eids:
                raise ValueError("invalid answer references")
            if not set(t.new_knowledge_ids) <= nids:
                raise ValueError("invalid turn knowledge references")
        for n in self.knowledge_graph.nodes:
            if not set(n.source_claims) <= cids or not set(n.triggered_questions) <= qids or not set(n.evidence) <= eids:
                raise ValueError("dangling knowledge provenance")
        for task in self.study_plan:
            if task.node_id not in nids or not set(task.evidence_from_interview) <= tids | {r.id for r in self.retests}:
                raise ValueError("study task without observed gap provenance")
        for card in self.study_cards:
            if card.node_id not in nids:
                raise ValueError("dangling study card")
        for edge in self.knowledge_graph.edges:
            if edge.provenance not in qids:
                raise ValueError("graph edge lacks question provenance")
        human_attempts = {r.id: r for r in self.retests if r.human_answer is not None}
        for r in self.retests:
            if r.node_id not in nids:
                raise ValueError("dangling retest node")
            if r.reference:
                validate_answer(r.reference, r.question)
            if r.reference and (r.reference.question_id != r.question.id or not set(r.reference.evidence_ids) <= eids):
                raise ValueError("invalid retest reference")
        for item in [*self.claims, *self.knowledge_graph.nodes]:
            if not set(item.mastery.evidence) <= human_attempts.keys():
                raise ValueError("mastery requires actual submitted human attempts")
            for rid in item.mastery.evidence:
                attempt = human_attempts[rid]
                if isinstance(item, KnowledgeNode) and attempt.node_id != item.id:
                    raise ValueError("mastery evidence belongs to another knowledge node")
                if isinstance(item, CapabilityClaim):
                    node = next(n for n in self.knowledge_graph.nodes if n.id == attempt.node_id)
                    if item.id not in node.source_claims:
                        raise ValueError("mastery evidence belongs to another claim")
            if item.mastery.status == "interview_ready":
                if isinstance(item, KnowledgeNode):
                    relevant = [r for r in self.retests if r.node_id == item.id and r.assessment]
                    if not reviewed_ready(relevant):
                        raise ValueError("readiness requires the latest two assessed answers to pass human review")
                    if not {r.id for r in relevant[-2:]} <= set(item.mastery.evidence):
                        raise ValueError("readiness omits its latest review evidence")
                else:
                    relevant_nodes = [n for n in self.knowledge_graph.nodes if item.id in n.source_claims]
                    if not relevant_nodes or any(n.mastery.status != "interview_ready" for n in relevant_nodes):
                        raise ValueError("claim readiness requires all associated knowledge nodes to be ready")
        return self
