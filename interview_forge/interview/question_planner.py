from interview_forge.schemas.models import QuestionPlan, ChallengeOperator as O
from .attack_planner import SURFACE_OPERATORS


def make_question_plan(claim, surface, attack, matches, transitions, style, history):
    allowed = [o for o in SURFACE_OPERATORS[surface.dimension] if o in attack.preferred_operators]
    used = {
        t.question.plan.operator for t in history if t.question.provenance.attack_surface_id == surface.id
    }
    transition_ops = [t.challenge_operator for t in transitions if t.challenge_operator in allowed]
    pattern_ops = [p.challenge_operator for _, p in matches if p.challenge_operator in allowed]
    options = transition_ops + attack.preferred_operators + pattern_ops + allowed
    operator = next((o for o in options if o not in used), options[0])
    selected = [(m, p) for m, p in matches if p.challenge_operator == operator][:3]
    # When there is no unresolved spoken trigger, corpus behavior may choose an operator.
    if not attack.unresolved_facets and not selected and pattern_ops:
        operator = next((o for o in pattern_ops if o not in used), pattern_ops[0])
        selected = [(m, p) for m, p in matches if p.challenge_operator == operator][:3]
    selected_transitions = [t for t in transitions if t.challenge_operator == operator][:2]
    target = " + ".join(claim.technologies[:3]) or claim.topic
    alternative = None
    if operator in {O.WHY_NOT_SIMPLER, O.WHY_NOT_ALTERNATIVE}:
        alternative = (
            "增加候选 top_k"
            if {"RAG", "reranker"} & set(claim.technologies)
            else ("数据库条件 UPDATE" if "Redis" in claim.technologies else "同一数据库事务内同步处理")
        )
    trigger = (
        history[-1].critique.new_assertions[0]
        if history and history[-1].critique.new_assertions
        else (", ".join(history[-1].critique.missing_facets) if history else "")
    )
    plan = QuestionPlan(
        claim_id=claim.id,
        attack_surface_id=surface.id,
        operator=operator,
        target_concept=target,
        alternative=alternative,
        assumptions_to_test=attack.unresolved_facets or [claim.proposition],
        expected_points=attack.unresolved_facets or [surface.dimension.value, claim.proposition],
        followup_candidates=[o.value for o in allowed if o != operator],
        corpus_match_ids=[m.id for m, _ in selected],
        pattern_ids=[p.id for _, p in selected],
        transition_ids=[t.id for t in selected_transitions],
        style_profile_id=style.id,
        style_backoff_path=style.backoff_path,
        adaptation_reason=attack.rationale
        + (
            " Abstract corpus operator adapted to the resume; source-specific technologies omitted."
            if selected
            else " Authored fallback for this surface; no corpus support claimed."
        ),
        previous_answer_trigger=trigger[:300],
    )
    return plan, selected, selected_transitions
