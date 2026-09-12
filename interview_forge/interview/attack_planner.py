"""Deterministic, explainable attack opportunity selection."""

from collections import Counter
from interview_forge.schemas.models import AttackPlan, ChallengeOperator as O, Dimension as D
from interview_forge.corpus.patterns import SPEC

SURFACE_OPERATORS = {
    D.problem: [O.WHY_NECESSARY],
    D.mechanism: [O.MECHANISM_PRESSURE, O.FUNDAMENTAL_DRILL],
    D.decision: [O.WHY_NOT_SIMPLER, O.WHY_NOT_ALTERNATIVE],
    D.engineering: [O.IMPLEMENTATION_PRESSURE],
    D.tradeoff: [O.BOUNDARY_PRESSURE, O.COUNTEREXAMPLE, O.CONSISTENCY_PRESSURE],
    D.failure: [O.FAILURE_PRESSURE],
    D.evaluation: [O.METRIC_PRESSURE, O.BASELINE_PRESSURE],
    D.scaling: [O.SCALE_PRESSURE],
    D.ownership: [O.OWNERSHIP_PRESSURE],
    D.debugging: [O.DEBUG_PRESSURE],
    D.fundamentals: [O.FUNDAMENTAL_DRILL],
}


def choose_attack(session, corpus=None):
    counts = Counter(t.question.claim_id for t in session.transcript)
    last = session.transcript[-1] if session.transcript else None
    preferred = last.critique.followup_operators if last else []
    claims = {c.id: c for c in session.claims}
    ranked = []
    for surface in session.attack_surfaces:
        if (
            surface.coverage in {"covered", "exhausted"}
            or counts[surface.claim_id] >= session.config.max_depth
        ):
            continue
        claim = claims[surface.claim_id]
        already_used = {
            t.question.plan.operator
            for t in session.transcript
            if claims[t.question.claim_id].project == claim.project
            and claims[t.question.claim_id].topic == claim.topic
        }
        ops = [operator for operator in SURFACE_OPERATORS[surface.dimension] if operator not in already_used]
        if not ops:
            continue
        trigger = bool(last and last.question.claim_id == claim.id and set(preferred) & set(ops))
        support = 0
        if corpus:
            support = sum(
                1
                for p in corpus.patterns
                if p.attack_dimension == surface.dimension
                and set(claim.technologies) & set(p.applicable_topics)
            )
        style = sum(session.effective_style.operator_distribution.get(o.value, 0) for o in ops)
        same = bool(last and last.question.claim_id == claim.id)
        switch = bool(last and (last.critique.answer_quality >= 0.85 or last.critique.novelty < 0.1))
        depth_limit = min(session.config.max_depth, max(2, round(session.effective_style.median_chain_depth)))
        if session.config.style == "corpus" and same and counts[claim.id] >= depth_limit and not trigger:
            switch = True
        factors = {
            "claim_risk": claim.risk_score / 100,
            "surface_relevance": surface.relevance,
            "unanswered_importance": 1 if surface.coverage == "untouched" else 0.7,
            "corpus_support": 1 + min(0.3, support * 0.05),
            "style_preference": 1 + style,
            "answer_trigger_strength": 2.5 if trigger else 1,
            "novelty": 0.55 if same and switch else 1,
            "repetition_penalty": surface.question_count * 0.25,
        }
        utility = 1
        for name, value in factors.items():
            if name != "repetition_penalty":
                utility *= value
        utility -= factors["repetition_penalty"]
        ordered = [o for o in preferred if o in ops] + [o for o in ops if o not in preferred]
        ranked.append(
            (
                utility,
                -surface.question_count,
                surface.id,
                AttackPlan(
                    claim_id=claim.id,
                    attack_surface_id=surface.id,
                    goal=f"Test {claim.proposition} through {surface.dimension.value}",
                    unresolved_facets=last.critique.missing_facets if same else [],
                    preferred_operators=ordered,
                    rationale=(
                        "Previous spoken answer exposed an unresolved facet. "
                        if trigger
                        else "Highest useful unresolved resume attack surface. "
                    )
                    + f"utility={utility:.3f}; coverage={surface.coverage}",
                    utility=utility,
                    utility_factors=factors,
                ),
            )
        )
    return max(ranked, key=lambda row: row[:3])[-1] if ranked else None


def update_coverage(surfaces, question, critique, turn_id):
    result = [s.model_copy(deep=True) for s in surfaces]
    surface = next(s for s in result if s.id == question.provenance.attack_surface_id)
    surface.question_count += 1
    surface.last_turn_id = turn_id
    surface.corpus_support = question.provenance.corpus_support
    surface.coverage = (
        "covered"
        if critique.answer_quality >= 0.8 and not critique.missing_facets
        else ("exhausted" if surface.question_count >= 2 or critique.novelty < 0.08 else "partial")
    )
    return result


def intent_for(question):
    return SPEC[question.provenance.challenge_operator][0]
