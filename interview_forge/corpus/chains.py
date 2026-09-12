import re
from .models import QuestionChain, QuestionTransition


def answer_features(text):
    if not text:
        return []
    features = []
    if re.search(r"快|性能|吞吐|提升|faster|perform", text, re.I) and not re.search(
        r"baseline|基线|对照|P99|\d+\s*(?:%|ms)", text, re.I
    ):
        features.extend(["performance_claim_without_measurement", "vague_technology_justification"])
    if re.search(r"调用|API|接口|library", text, re.I) and len(text) < 70:
        features.append("api_only_description")
    if re.search(r"保证|一定|不会|always|never", text, re.I):
        features.append("unqualified_guarantee")
    return features


def compile_chains(case):
    if not case.questions or case.source_type == "unordered_summary":
        return [], []
    chains = [
        QuestionChain(
            id="chain-" + case.id,
            case_id=case.id,
            question_ids=[q.id for q in case.questions],
            topic=case.technologies,
            depth=len(case.questions),
            quality=case.case_quality,
        )
    ]
    transitions = []
    for before, after in zip(case.questions, case.questions[1:]):
        observed = bool(before.answer_context)
        transitions.append(
            QuestionTransition(
                id="transition-" + before.id + "-" + after.id,
                from_question_id=before.id,
                from_intent=before.probe_intent,
                candidate_answer_features=answer_features(before.answer_context),
                trigger_summary="Observed candidate answer features precede the next probe."
                if observed
                else "Observed question order only; candidate answer and causal trigger are unknown.",
                to_intent=after.probe_intent,
                challenge_operator=after.challenge_operator,
                example_question_id=after.id,
                confidence=0.9 if observed else 0.4,
                source_case_id=case.id,
                observed_answer=observed,
            )
        )
    return chains, transitions
