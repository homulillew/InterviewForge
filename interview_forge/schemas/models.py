"""Versioned contracts. Cross-object provenance is validated at the session boundary."""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, AliasChoices
from interview_forge.materials.models import MaterialItem

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
    debugging = "Debugging"
    fundamentals = "Fundamentals"


class ClaimType(str, Enum):
    implementation = "implementation"
    architecture = "architecture"
    technology_choice = "technology_choice"
    outcome = "outcome"
    metric = "metric"
    ownership = "ownership"
    scale = "scale"
    reliability = "reliability"
    optimization = "optimization"


class ChallengeOperator(str, Enum):
    WHY_NECESSARY = "WHY_NECESSARY"
    WHY_NOT_SIMPLER = "WHY_NOT_SIMPLER"
    WHY_NOT_ALTERNATIVE = "WHY_NOT_ALTERNATIVE"
    MECHANISM_PRESSURE = "MECHANISM_PRESSURE"
    IMPLEMENTATION_PRESSURE = "IMPLEMENTATION_PRESSURE"
    OWNERSHIP_PRESSURE = "OWNERSHIP_PRESSURE"
    METRIC_PRESSURE = "METRIC_PRESSURE"
    BASELINE_PRESSURE = "BASELINE_PRESSURE"
    FAILURE_PRESSURE = "FAILURE_PRESSURE"
    BOUNDARY_PRESSURE = "BOUNDARY_PRESSURE"
    SCALE_PRESSURE = "SCALE_PRESSURE"
    DEBUG_PRESSURE = "DEBUG_PRESSURE"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    CONSISTENCY_PRESSURE = "CONSISTENCY_PRESSURE"
    FUNDAMENTAL_DRILL = "FUNDAMENTAL_DRILL"


class ProbeIntent(str, Enum):
    problem = "problem"
    mechanism = "mechanism"
    decision = "decision"
    implementation = "implementation"
    ownership = "ownership"
    evaluation = "evaluation"
    failure = "failure"
    boundary = "boundary"
    scaling = "scaling"
    debugging = "debugging"
    fundamentals = "fundamentals"


class Applicability(str, Enum):
    direct = "direct"
    transferable = "transferable"
    style_only = "style_only"
    reject = "reject"


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


class AtomicClaim(Model):
    id: Text
    statement_id: Text
    proposition: Text
    claim_type: ClaimType
    technologies: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    topic: Text
    project: Text
    source_quote: Text
    risk_score: float = Field(default=0, ge=0, le=100)
    risk_factors: dict[str, Score] = Field(default_factory=dict)
    risk_reasons: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    answerability: Literal["unknown", "low", "medium", "high"] = "unknown"
    mastery: MasteryState = Field(default_factory=MasteryState)


# Import compatibility only: the old dimension-bearing model lives in legacy_v1.
CapabilityClaim = AtomicClaim


class AttackSurface(Model):
    id: Text
    claim_id: Text
    dimension: Dimension
    relevance: Score
    priority: Literal["P0", "P1", "P2", "P3"]
    rationale: Text
    coverage: Literal["untouched", "partial", "covered", "exhausted"] = "untouched"
    question_count: int = Field(default=0, ge=0)
    last_turn_id: str | None = None
    corpus_support: Score = 0


class AttackPlan(Model):
    claim_id: Text
    attack_surface_id: Text
    goal: Text
    unresolved_facets: list[str] = Field(default_factory=list)
    preferred_operators: list[ChallengeOperator] = Field(min_length=1)
    rationale: Text
    utility: float = 0
    utility_factors: dict[str, float] = Field(default_factory=dict)


class QuestionPlan(Model):
    claim_id: Text
    attack_surface_id: Text
    operator: ChallengeOperator
    target_concept: Text
    alternative: str | None = None
    assumptions_to_test: list[str] = Field(default_factory=list)
    expected_points: list[str] = Field(default_factory=list)
    followup_candidates: list[str] = Field(default_factory=list)
    corpus_match_ids: list[str] = Field(default_factory=list)
    pattern_ids: list[str] = Field(default_factory=list)
    transition_ids: list[str] = Field(default_factory=list)
    style_profile_id: str | None = None
    style_backoff_path: list[str] = Field(default_factory=list)
    adaptation_reason: Text
    previous_answer_trigger: str = ""


class QuestionProvenance(Model):
    resume_statement_id: Text
    atomic_claim_id: Text
    attack_surface_id: Text
    corpus_match_ids: list[str] = Field(default_factory=list)
    probe_pattern_ids: list[str] = Field(default_factory=list)
    transition_ids: list[str] = Field(default_factory=list)
    challenge_operator: ChallengeOperator
    style_profile_id: str | None = None
    style_backoff_path: list[str] = Field(default_factory=list)
    adaptation_reason: Text
    resume_relevance: Score = 1
    corpus_support: Score = 0
    style_confidence: Score = 0
    origin: Literal["authored_baseline", "corpus", "migration", "human_retest"] = "authored_baseline"


class AnswerCritique(Model):
    covered_facets: list[str] = Field(default_factory=list)
    missing_facets: list[str] = Field(default_factory=list)
    vague_assertions: list[str] = Field(default_factory=list)
    new_assertions: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    answer_features: list[str] = Field(default_factory=list)
    followup_operators: list[ChallengeOperator] = Field(default_factory=list)
    suggested_next_surfaces: list[str] = Field(default_factory=list)
    answer_quality: Score = 0
    novelty: Score = 1


class MaterialGap(Model):
    kind: Literal["material_gap"] = "material_gap"
    description: Text


class AnswerGap(Model):
    kind: Literal["answer_gap"] = "answer_gap"
    description: Text


class MasteryGap(Model):
    kind: Literal["mastery_gap"] = "mastery_gap"
    attempt_id: Text
    description: Text


class EvidenceRelation(Model):
    evidence_id: Text
    claim_id: Text
    relation: Literal["related", "direct_support", "partial_support", "limitation", "contradicts"] = "related"
    facets: list[Literal["implementation", "config", "validation", "metric", "ownership", "architecture"]]
    confidence: Score
    rationale: Text


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
    related_claim_ids: list[str] = Field(default_factory=list)
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
    material_ids: list[str] = Field(default_factory=list)
    material_question: str | None = None
    plan: QuestionPlan
    provenance: QuestionProvenance


class EvidenceMatch(Model):
    evidence_id: Text
    relevance_score: float = Field(ge=0)
    reasons: list[Text] = Field(min_length=1)


class Answer(Model):
    question_id: Text
    spoken_answer: Text = Field(validation_alias=AliasChoices("spoken_answer", "direct_interview_answer"))
    evidence_selection: list[EvidenceMatch] = Field(default_factory=list)
    reference_material_ids: list[str] = Field(default_factory=list)
    reasoning_basis: list[str] = Field(default_factory=list)
    inferred_details: list[str] = Field(default_factory=list)
    experiment_plan: list[str] = Field(default_factory=list)
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
    material_gaps: list[MaterialGap] = Field(default_factory=list)

    @property
    def direct_interview_answer(self) -> str:
        return self.spoken_answer


class InterviewTurn(Model):
    id: Text
    question: InterviewQuestion
    answer: Answer
    kind: Literal["simulation"] = "simulation"
    weaknesses_observed: list[str]
    new_knowledge_ids: list[str] = Field(default_factory=list)
    critique: AnswerCritique = Field(default_factory=AnswerCritique)
    answer_gaps: list[AnswerGap] = Field(default_factory=list)
    attack_plan: AttackPlan | None = None


class FollowupQA(Model):
    question: Text
    answer: Text
    priority: Literal["P0", "P1", "P2", "P3"] = "P1"
    interview_distance: int = Field(default=1, ge=0, le=3)


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
    followup_qa: list[FollowupQA] = Field(default_factory=list)


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
    title: str = ""
    priority: Literal["P0", "P1", "P2", "P3"] = "P1"
    interview_distance: int = Field(default=1, ge=0, le=3)
    must_know: list[str] = Field(default_factory=list)
    boundary: list[str] = Field(default_factory=list)
    common_traps: list[str] = Field(default_factory=list)
    followup_qa: list[FollowupQA] = Field(default_factory=list)
    project_anchors: list[str] = Field(default_factory=list)
    retest_questions: list[str] = Field(default_factory=list)


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
    gap_kind: Literal["material_gap", "answer_gap", "mastery_gap"]
    learning_objectives: list[str]
    exercises: list[Exercise]
    project_task: Text
    retest_questions: list[str]
    mastery_criteria: list[str]
    status: Literal["pending", "completed"] = "pending"
    covers_node_ids: list[str] = Field(default_factory=list)
    estimated_minutes: int = Field(default=15, ge=1, le=120)
    interview_value: float = Field(default=1, ge=0)


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
    library_path: str | None = None
    corpus_path: str | None = None
    company: str | None = None
    role: str | None = None
    round: str | None = None
    seniority: str | None = None
    style: Literal["neutral", "corpus"] = "neutral"


class CorpusPin(Model):
    revision: Text
    database_fingerprint: Text
    profile_ids: list[str] = Field(default_factory=list)


class EffectiveStyle(Model):
    id: str | None = None
    sample_size: int = Field(default=0, ge=0)
    confidence: Score = 0
    profile_weights: dict[str, Score] = Field(default_factory=dict)
    backoff_path: list[str] = Field(default_factory=list)
    operator_distribution: dict[str, Score] = Field(default_factory=dict)
    transition_distribution: dict[str, Score] = Field(default_factory=dict)
    median_chain_depth: float = Field(default=3, ge=0)
    question_length_median: float = Field(default=60, ge=0)


class CorpusMatchRef(Model):
    id: Text
    revision: Text
    pattern_id: Text
    source_case_ids: list[str]
    applicability: Applicability
    relevance: Score
    reason: Text


class TransitionRef(Model):
    id: Text
    revision: Text
    example_question_id: Text
    from_question_id: str | None = None


class InterviewSession(Model):
    schema_version: Literal["2.0"] = "2.0"
    id: Text
    status: Literal["ready", "running", "paused", "completed"] = "ready"
    resume: Text
    jd: str = ""
    config: SessionConfig
    statements: list[ResumeStatement]
    claims: list[AtomicClaim]
    attack_surfaces: list[AttackSurface]
    evidence_relations: list[EvidenceRelation] = Field(default_factory=list)
    corpus_pin: CorpusPin | None = None
    effective_style: EffectiveStyle = Field(default_factory=EffectiveStyle)
    corpus_matches: list[CorpusMatchRef] = Field(default_factory=list)
    corpus_transitions: list[TransitionRef] = Field(default_factory=list)
    migration_notes: list[str] = Field(default_factory=list)
    repository_map: RepositoryMap
    evidences: list[RepoEvidence]
    materials: list[MaterialItem] = Field(default_factory=list)
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
        aids = unique(self.attack_surfaces)
        surfaces = {a.id: a for a in self.attack_surfaces}
        matches = {m.id: m for m in self.corpus_matches}
        if len(matches) != len(self.corpus_matches):
            raise ValueError("duplicate corpus matches")
        transitions = {t.id: t for t in self.corpus_transitions}
        if len(transitions) != len(self.corpus_transitions):
            raise ValueError("duplicate corpus transitions")
        for match in [*self.corpus_matches, *self.corpus_transitions]:
            if self.corpus_pin is None or match.revision != self.corpus_pin.revision:
                raise ValueError("corpus reference does not belong to pinned revision")
        if self.effective_style.id and (self.corpus_pin is None or
                not set(self.effective_style.profile_weights) <= set(self.corpus_pin.profile_ids)):
            raise ValueError("style profile does not belong to pin")
        for surface in self.attack_surfaces:
            if surface.claim_id not in cids or (surface.last_turn_id and surface.last_turn_id not in tids):
                raise ValueError("dangling attack surface")
        mids = unique(self.materials)
        materials_by_id = {m.id: m for m in self.materials}
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
                if c.id not in next(e.related_claim_ids for e in self.evidences if e.id == eid):
                    raise ValueError("claim links must be bidirectional")
        for e in self.evidences:
            if not set(e.related_claim_ids) <= cids:
                raise ValueError("dangling evidence claim")
            for cid in e.related_claim_ids:
                if e.id not in next(c.evidence_ids for c in self.claims if c.id == cid):
                    raise ValueError("evidence links must be bidirectional")
        for q in questions:
            p, plan = q.provenance, q.plan
            claim = next((c for c in self.claims if c.id == q.claim_id), None)
            if claim is None or p.atomic_claim_id != claim.id or p.resume_statement_id != claim.statement_id:
                raise ValueError("question lacks a valid atomic resume anchor")
            if p.attack_surface_id not in aids or surfaces[p.attack_surface_id].claim_id != claim.id:
                raise ValueError("question lacks a valid attack surface")
            if q.dimension != surfaces[p.attack_surface_id].dimension:
                raise ValueError("question dimension differs from its attack surface")
            if (plan.claim_id, plan.attack_surface_id, plan.operator) != (claim.id, p.attack_surface_id, p.challenge_operator):
                raise ValueError("question plan and provenance disagree")
            for field, other in (("corpus_match_ids", "corpus_match_ids"), ("pattern_ids", "probe_pattern_ids"),
                                 ("transition_ids", "transition_ids"), ("style_backoff_path", "style_backoff_path")):
                if getattr(plan, field) != getattr(p, other):
                    raise ValueError("question plan provenance lists disagree")
            if not set(p.corpus_match_ids) <= matches.keys() or not set(p.transition_ids) <= transitions.keys():
                raise ValueError("question cites unknown corpus reference")
            if set(p.probe_pattern_ids) != {matches[mid].pattern_id for mid in p.corpus_match_ids}:
                raise ValueError("question pattern does not match corpus reference")
            if any(matches[mid].applicability not in {Applicability.direct, Applicability.transferable} for mid in p.corpus_match_ids):
                raise ValueError("inapplicable corpus reference in question")
            if p.style_profile_id != plan.style_profile_id or (p.style_profile_id and p.style_profile_id != self.effective_style.id):
                raise ValueError("question uses an unpinned style")
            if not set(q.material_ids) <= mids:
                raise ValueError("question refers to missing material snapshot")
            if any(materials_by_id[mid].kind != "interview" for mid in q.material_ids):
                raise ValueError("interviewer can only cite interview material")
            if q.material_question is not None and not any(q.material_question in
                    [materials_by_id[mid].question, *materials_by_id[mid].followups] for mid in q.material_ids):
                raise ValueError("question's source wording is not in cited material")
            if q.claim_id not in cids or (q.based_on_turn and q.based_on_turn not in tids):
                raise ValueError("dangling question provenance")
        def validate_answer(answer, question):
            if question.provenance.origin != "migration" and answer.reference_material_ids:
                raise ValueError("Runtime answerer cannot cite preparation or corpus material")
            if not set(answer.reference_material_ids) <= mids:
                raise ValueError("answer refers to missing material snapshot")
            if any(materials_by_id[mid].kind != "answer" for mid in answer.reference_material_ids):
                raise ValueError("answer references must be answer documents")
            allowed = {e.id for e in self.evidences if question.claim_id in e.related_claim_ids}
            if not set(answer.evidence_ids) <= allowed:
                raise ValueError("answer evidence does not support its claim context")
            if not {m.evidence_id for m in answer.evidence_selection} <= allowed:
                raise ValueError("invalid retrieval provenance")
        for surface in self.attack_surfaces:
            turns = [t for t in self.transcript if t.question.provenance.attack_surface_id == surface.id]
            if surface.question_count != len(turns) or surface.last_turn_id != (turns[-1].id if turns else None):
                raise ValueError("attack surface coverage history is inconsistent")
        for t in self.transcript:
            if t.attack_plan and (t.attack_plan.claim_id, t.attack_plan.attack_surface_id) != (t.question.claim_id, t.question.plan.attack_surface_id):
                raise ValueError("attack plan does not match question plan")
            validate_answer(t.answer, t.question)
            if t.answer.question_id != t.question.id or not set(t.answer.evidence_ids) <= eids:
                raise ValueError("invalid answer references")
            if not set(t.new_knowledge_ids) <= nids:
                raise ValueError("invalid turn knowledge references")
        for n in self.knowledge_graph.nodes:
            if not set(n.source_claims) <= cids or not set(n.triggered_questions) <= qids or not set(n.evidence) <= eids:
                raise ValueError("dangling knowledge provenance")
        for task in self.study_plan:
            if task.node_id not in nids or not set(task.covers_node_ids) <= nids or not set(task.evidence_from_interview) <= tids | {r.id for r in self.retests}:
                raise ValueError("study task without observed gap provenance")
            if task.gap_kind == "mastery_gap" and not set(task.evidence_from_interview) <= {
                    r.id for r in self.retests if r.human_answer and r.assessment}:
                raise ValueError("mastery gap requires assessed human submissions")
        relation_keys = set()
        for relation in self.evidence_relations:
            key = (relation.evidence_id, relation.claim_id)
            if key in relation_keys or key[0] not in eids or key[1] not in cids:
                raise ValueError("invalid evidence relation")
            relation_keys.add(key)
        expected_relations = {(e.id, cid) for e in self.evidences for cid in e.related_claim_ids}
        if relation_keys != expected_relations:
            raise ValueError("evidence relations must cover related claim links")
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
