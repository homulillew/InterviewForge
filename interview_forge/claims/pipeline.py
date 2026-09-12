"""Resume assertions and interview attack angles are separate contracts."""

import re
from pydantic import Field
from interview_forge.curricula import TOPICS, topic_for
from interview_forge.llm import LLMClient, prompt
from interview_forge.semantics import technologies
from interview_forge.schemas.models import (
    AtomicClaim,
    AttackSurface,
    ClaimType,
    Dimension,
    Model,
    ResumeStatement,
)


class ClaimBatch(Model):
    claims: list[AtomicClaim] = Field(min_length=1, max_length=80)


def statements_from_resume(resume):
    project, result = "项目经历", []
    for line, raw in enumerate(resume.splitlines(), 1):
        text = raw.strip()
        if not text:
            continue
        if text.startswith("#"):
            project = text.lstrip("# ") or project
            continue
        result.append(
            ResumeStatement(
                id=f"s{len(result) + 1}", text=re.sub(r"^[-*•]\s*", "", text), project=project, line=line
            )
        )
    if not result:
        raise ValueError("Resume contains no statements; supply plain text or Markdown project bullets")
    return result


def claim_type(text):
    if re.search(r"\d+(?:\.\d+)?\s*(?:%|％|倍|ms|qps|tps)", text, re.I):
        return ClaimType.metric
    if re.search(r"百万|千万|亿|规模|\d+\s*(?:用户|节点|台|万)", text):
        return ClaimType.scale
    if re.search(r"解决|避免|防止|消除|correctness|prevent", text, re.I):
        return ClaimType.outcome
    if re.search(r"熔断|容灾|高可用|恢复|reliab|failover", text, re.I):
        return ClaimType.reliability
    if re.search(r"优化|提升|改善|optimi|improv", text, re.I):
        return ClaimType.optimization
    if re.search(r"架构|architecture", text, re.I):
        return ClaimType.architecture
    if re.search(r"选择|选型|采用|chose|selected", text, re.I):
        return ClaimType.technology_choice
    return ClaimType.implementation


def rank_claims(claims, jd):
    for claim in claims:
        factors = {
            "jd_relevance": 1.0 if any(t.casefold() in jd.casefold() for t in claim.technologies) else 0.4,
            "claim_strength": 1.0
            if re.search(r"主导|设计|提升|解决|designed|led", claim.source_quote, re.I)
            else 0.5,
            "metric_boldness": 1.0 if claim.claim_type == ClaimType.metric else 0.2,
            "ownership_ambiguity": 0.8 if claim.claim_type == ClaimType.ownership else 0.4,
            "technical_depth": min(1, 0.5 + len(claim.technologies) * 0.12),
            "business_importance": 0.9
            if claim.claim_type in {ClaimType.outcome, ClaimType.reliability}
            else 0.6,
            "evidence_weakness": 1.0,  # Lexical links never establish support for an assertion.
            "interview_probability": 0.9
            if claim.claim_type in {ClaimType.metric, ClaimType.implementation}
            else 0.7,
        }
        claim.risk_factors = factors
        claim.risk_score = round(100 * sum(factors.values()) / len(factors), 1)
        claim.risk_reasons = [f"{key}={value:.2f}" for key, value in factors.items() if value >= 0.8]
    return sorted(claims, key=lambda c: (-c.risk_score, c.id))


def extract_claims(resume, jd="", client: LLMClient | None = None):
    statements = statements_from_resume(resume)
    if client:
        claims = client.structured_generate(
            prompt("claim_extraction"),
            {"statements": [s.model_dump() for s in statements], "jd": jd},
            ClaimBatch,
        ).claims
    else:
        claims = []
        for statement in statements:
            if re.match(r"^(邮箱|电话|手机|email|phone)\s*[:：]", statement.text, re.I):
                continue
            techs = technologies(statement.text)
            if not techs and not re.search(r"实现|设计|开发|优化|服务|检索|算法|库存", statement.text):
                continue
            parts = re.split(r"[，,；;。]\s*|(?=解决|吞吐提升|性能提升)", statement.text)
            for part in (p.strip() for p in parts if len(p.strip()) >= 3):
                if not re.search(
                    r"使用|设计|实现|开发|采用|解决|提升|降低|优化|负责|主导|完成|构建|支持|防止|引入|搭建|\d|built|used|designed|implement|develop|improv|using|led",
                    part,
                    re.I,
                ):
                    continue
                claims.append(
                    AtomicClaim(
                        id=f"c{len(claims) + 1}",
                        statement_id=statement.id,
                        proposition=re.sub(r"^(?:我)?(?:独立|负责|主导)", "", part).strip() or part,
                        source_quote=part,
                        project=statement.project,
                        claim_type=claim_type(part),
                        technologies=techs,
                        concepts=["库存一致性"] if "库存" in statement.text else [],
                        topic=TOPICS[topic_for(statement.text)].title,
                    )
                )
            ownership = re.search(r"(?:独立|负责|主导)[^，,；;。]{1,70}", statement.text)
            if ownership and not any(
                c.statement_id == statement.id and c.proposition == ownership.group() for c in claims
            ):
                claims.append(
                    AtomicClaim(
                        id=f"c{len(claims) + 1}",
                        statement_id=statement.id,
                        proposition=ownership.group(),
                        source_quote=ownership.group(),
                        project=statement.project,
                        claim_type=ClaimType.ownership,
                        technologies=techs,
                        topic=TOPICS[topic_for(statement.text)].title,
                    )
                )
    if not claims:
        raise ValueError(
            "No atomic technical assertions found; supply project bullets or use compatible mode"
        )
    if len(claims) > 80:
        raise ValueError("Resume exceeds 80 atomic assertions; split the resume")
    sources, seen = {s.id: s for s in statements}, set()
    for claim in claims:
        if (
            claim.id in seen
            or claim.statement_id not in sources
            or claim.source_quote not in sources[claim.statement_id].text
        ):
            raise ValueError("Generated claim not grounded in resume statement or duplicate ID")
        seen.add(claim.id)
        if (
            re.match(r"(?:理解|能够解释|应该懂|需要掌握)", claim.proposition)
            and claim.proposition not in claim.source_quote
        ):
            raise ValueError("Atomic claim cannot be an invented interview competency")
        source = sources[claim.statement_id].text
        if claim.claim_type == ClaimType.ownership and not re.search(
            r"负责|主导|独立|owned|led|responsib", claim.source_quote, re.I
        ):
            raise ValueError("Ownership must be explicit in resume")
        if not set(technologies(claim.proposition)) <= set(technologies(source)):
            raise ValueError("Claim invented resume technology")
        if not set(re.findall(r"\d+(?:\.\d+)?", claim.proposition)) <= set(
            re.findall(r"\d+(?:\.\d+)?", source)
        ):
            raise ValueError("Claim invented resume metric")
        claim.technologies = technologies(source)
        claim.project = sources[claim.statement_id].project
        claim.evidence_ids = []
        claim.answerability = "unknown"
        from interview_forge.schemas.models import MasteryState

        claim.mastery = MasteryState()
    return statements, rank_claims(claims, jd)


def generate_surfaces(claims):
    defaults = [
        Dimension.mechanism,
        Dimension.decision,
        Dimension.engineering,
        Dimension.evaluation,
        Dimension.failure,
    ]
    choices = {
        ClaimType.metric: [Dimension.evaluation, Dimension.tradeoff, Dimension.debugging],
        ClaimType.ownership: [Dimension.ownership, Dimension.engineering],
        ClaimType.scale: [Dimension.scaling, Dimension.evaluation, Dimension.failure],
        ClaimType.outcome: [Dimension.problem, Dimension.mechanism, Dimension.evaluation, Dimension.failure],
        ClaimType.reliability: [
            Dimension.failure,
            Dimension.engineering,
            Dimension.evaluation,
            Dimension.debugging,
        ],
        ClaimType.technology_choice: [
            Dimension.decision,
            Dimension.tradeoff,
            Dimension.mechanism,
            Dimension.evaluation,
        ],
    }
    result = []
    for claim in claims:
        for index, dimension in enumerate(choices.get(claim.claim_type, defaults)):
            result.append(
                AttackSurface(
                    id=f"as-{claim.id}-{dimension.name}",
                    claim_id=claim.id,
                    dimension=dimension,
                    relevance=max(0.5, 1 - index * 0.1),
                    priority="P0" if index < 3 else "P1",
                    rationale=f"{claim.claim_type.value} assertion can be tested through {dimension.value}",
                )
            )
    return result
