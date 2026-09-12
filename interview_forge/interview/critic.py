"""Red-side service: only spoken content and resume assertions, never source evidence."""

import re
from interview_forge.schemas.models import AnswerCritique, ChallengeOperator as O
from interview_forge.corpus.chains import answer_features
from interview_forge.llm import prompt
from interview_forge.semantics import tokens


def blind_claim(claim):
    return claim.model_dump(
        include={
            "id",
            "statement_id",
            "proposition",
            "source_quote",
            "project",
            "claim_type",
            "technologies",
            "concepts",
            "topic",
        }
    )


def critique_answer(claim, surface, question, spoken, history=(), client=None):
    payload = {
        "claim": blind_claim(claim),
        "attack_surface": surface.model_dump(include={"id", "dimension", "rationale"}),
        "question": question.text,
        "spoken_answer": spoken,
        "expected_points": question.expected_points,
        "previous_spoken_qa": [{"question": q, "answer": a} for q, a in history[-3:]],
    }
    if client:
        result = client.structured_generate(prompt("answer_critique"), payload, AnswerCritique)
        if result.suggested_next_surfaces and any(s != surface.id for s in result.suggested_next_surfaces):
            # Surface routing is controlled by the planner, not arbitrary model identifiers.
            result.suggested_next_surfaces = []
        return result
    features = answer_features(spoken)
    covered = []
    missing = []
    operators = []
    checks = {
        "mechanism": r"原子|状态|先.{1,25}再|因为.{8,}|编码|召回|唯一约束|事务|state|atomic",
        "decision": r"相比|而不是|优先|取舍|权衡|选择|选型|替代|baseline|对照",
        "baseline": r"基线|baseline|对照|固定.{0,30}(?:配置|资源|环境|机器)|控制变量",
        "measurement": r"P99|NDCG|MRR|Recall|吞吐|成功数|正确率|重复次数",
        "failure": r"超时|重试|失败|回滚|补偿|断开|降级|漏召回",
        "implementation": r"脚本|唯一约束|函数|事务|chunk|状态迁移|请求路径",
    }
    needed = {
        "mechanism": ["mechanism"],
        "decision": ["decision", "baseline"],
        "evaluation": ["baseline", "measurement"],
        "failure": ["failure", "mechanism"],
        "debugging": ["measurement", "failure"],
        "implementation": ["implementation", "failure"],
        "scaling": ["measurement", "decision"],
        "ownership": ["implementation"],
    }.get(question.subtopic, ["mechanism"])
    for facet in needed:
        (covered if re.search(checks[facet], spoken, re.I) else missing).append(facet)
    if "performance_claim_without_measurement" in features:
        missing = list(dict.fromkeys([*missing, "original_bottleneck", "baseline", "mechanism"]))
        operators = [O.MECHANISM_PRESSURE, O.METRIC_PRESSURE, O.BASELINE_PRESSURE]
    else:
        routing = {
            "mechanism": O.MECHANISM_PRESSURE,
            "baseline": O.BASELINE_PRESSURE,
            "measurement": O.METRIC_PRESSURE,
            "decision": O.WHY_NOT_ALTERNATIVE,
            "failure": O.FAILURE_PRESSURE,
            "implementation": O.IMPLEMENTATION_PRESSURE,
        }
        operators = [routing[m] for m in missing if m in routing]
    if len(spoken.strip()) < 45:
        features.append("vague_answer")
    contradictions = []
    if re.search(r"Lua.{0,15}(?:自动回滚|保证持久)|超时.{0,10}(?:一定|说明).{0,8}没.{0,3}执行", spoken, re.I):
        contradictions.append("A local execution or timeout guarantee was extended beyond its scope.")
        operators.insert(0, O.CONSISTENCY_PRESSURE)
    previous = tokens(history[-1][1]) if history else set()
    current = tokens(spoken)
    novelty = 1 - len(previous & current) / max(1, len(previous | current)) if previous else 1
    quality = max(
        0,
        min(
            1,
            len(covered) / max(1, len(needed))
            - 0.2 * bool(contradictions)
            - 0.25 * ("vague_answer" in features),
        ),
    )
    return AnswerCritique(
        covered_facets=covered,
        missing_facets=missing,
        vague_assertions=[spoken[:160]] if "vague_answer" in features else [],
        new_assertions=[spoken[:160]] if features else [],
        contradictions=contradictions,
        answer_features=list(dict.fromkeys(features)),
        followup_operators=list(dict.fromkeys(operators)),
        answer_quality=quality,
        novelty=novelty,
    )
