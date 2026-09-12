"""Bounded challenge operators are compiled from questions, never brand stereotypes."""

import hashlib
import re
from collections import defaultdict
from interview_forge.schemas.models import ChallengeOperator as O, ProbeIntent as I, Dimension as D, ClaimType
from interview_forge.semantics import family
from .models import ProbePattern

# intent, dimension, abstract behavior. No source text is used as the abstraction.
SPEC = {
    O.WHY_NECESSARY: (
        I.problem,
        D.problem,
        "Challenge the necessity of the claimed solution against its business constraint.",
    ),
    O.WHY_NOT_SIMPLER: (
        I.decision,
        D.decision,
        "Compare the chosen component with a simpler plausible solution to the same requirement.",
    ),
    O.WHY_NOT_ALTERNATIVE: (
        I.decision,
        D.decision,
        "Compare alternatives under the same constraints and expose the deciding trade-off.",
    ),
    O.MECHANISM_PRESSURE: (
        I.mechanism,
        D.mechanism,
        "Demand the causal steps between input, state change and claimed guarantee.",
    ),
    O.IMPLEMENTATION_PRESSURE: (
        I.implementation,
        D.engineering,
        "Trace input validation, state transitions and error handling in a concrete implementation.",
    ),
    O.OWNERSHIP_PRESSURE: (
        I.ownership,
        D.ownership,
        "Distinguish explicitly claimed personal decisions from shared team capabilities.",
    ),
    O.METRIC_PRESSURE: (
        I.evaluation,
        D.evaluation,
        "Define the metric and reproducible experiment behind a claimed improvement.",
    ),
    O.BASELINE_PRESSURE: (
        I.evaluation,
        D.evaluation,
        "Require a controlled baseline and isolate attribution of the improvement.",
    ),
    O.FAILURE_PRESSURE: (
        I.failure,
        D.failure,
        "Inject a plausible partial failure and examine recovery and duplicate execution.",
    ),
    O.BOUNDARY_PRESSURE: (
        I.boundary,
        D.tradeoff,
        "Identify the exact scope of a guarantee and a condition where it ceases to hold.",
    ),
    O.SCALE_PRESSURE: (
        I.scaling,
        D.scaling,
        "Increase load under fixed resources and identify the first bottleneck.",
    ),
    O.DEBUG_PRESSURE: (
        I.debugging,
        D.debugging,
        "Localize a symptom using observations, competing hypotheses and a controlled check.",
    ),
    O.COUNTEREXAMPLE: (
        I.boundary,
        D.tradeoff,
        "Construct a counterexample that could falsify the stated claim.",
    ),
    O.CONSISTENCY_PRESSURE: (
        I.boundary,
        D.tradeoff,
        "Resolve an apparent conflict between stated guarantees or state transitions.",
    ),
    O.FUNDAMENTAL_DRILL: (
        I.fundamentals,
        D.fundamentals,
        "Explain the prerequisite concept that the current claim relies on.",
    ),
}


def identify_operator(text):
    tests = [
        (r"不直接|更简单|简单方案|why.not.simpl|直接.*(?:线程|top_k)", O.WHY_NOT_SIMPLER),
        (r"基线|baseline|对照|归因|公平比较", O.BASELINE_PRESSURE),
        (
            r"指标|测量|评测|吞吐提升|多少|数据|证明|测得|实验|性能提升|metric|benchmark|快在哪里|快在哪",
            O.METRIC_PRESSURE,
        ),
        (r"排查|定位|诊断|debug|瓶颈", O.DEBUG_PRESSURE),
        (r"反例|推翻|counterexample", O.COUNTEREXAMPLE),
        (r"矛盾|前后不一致|contradict", O.CONSISTENCY_PRESSURE),
        (r"负责|主导|贡献|ownership", O.OWNERSHIP_PRESSURE),
        (r"不用|而不是|替代|相比|versus|alternative", O.WHY_NOT_ALTERNATIVE),
        (r"故障|超时|重试|失败|报错|补偿|断开|failure|timeout|retry", O.FAILURE_PRESSURE),
        (r"边界|保证|回滚|持久|boundary", O.BOUNDARY_PRESSURE),
        (r"扩大|扩容|十倍|scale|流量", O.SCALE_PRESSURE),
        (r"实现|流程|落地|implement", O.IMPLEMENTATION_PRESSURE),
        (r"什么是|区别|定义|sqrt|fundamental", O.FUNDAMENTAL_DRILL),
        (r"为什么.*(?:需要|使用|用)|why.*(?:use|need)", O.WHY_NECESSARY),
    ]
    return next(
        (operator for pattern, operator in tests if re.search(pattern, text, re.I)), O.MECHANISM_PRESSURE
    )


def compile_patterns(cases, transitions):
    grouped = defaultdict(list)
    for case in cases:
        for q in case.questions:
            if case.source_type != "unordered_summary":
                grouped[(q.challenge_operator, tuple(sorted(q.topic)))].append((case, q))
    output = []
    for (operator, topics), rows in sorted(grouped.items(), key=lambda row: str(row[0])):
        operator = operator or O.MECHANISM_PRESSURE
        intent, dimension, abstract = SPEC[operator]
        types = (
            [ClaimType.metric, ClaimType.optimization]
            if intent == I.evaluation
            else (
                [ClaimType.ownership]
                if intent == I.ownership
                else [t for t in ClaimType if t != ClaimType.ownership]
            )
        )
        groups = {c.duplicate_group or c.id for c, _ in rows}
        qids = {q.id for _, q in rows}
        features = sorted(
            {f for t in transitions if t.example_question_id in qids for f in t.candidate_answer_features}
        )
        output.append(
            ProbePattern(
                id="pattern-" + hashlib.sha256((operator.value + str(topics)).encode()).hexdigest()[:16],
                source_case_ids=sorted({c.id for c, _ in rows}),
                source_question_ids=sorted(qids),
                applicable_topics=list(topics),
                applicable_technology_families=sorted(family(topics)),
                trigger_claim_types=types,
                trigger_answer_features=features,
                attack_dimension=dimension,
                challenge_operator=operator,
                abstract_pattern=abstract,
                next_intents=[intent],
                support_count=len(groups),
                quality=sum(c.case_quality for c, _ in rows) / len(rows),
            )
        )
    return output
