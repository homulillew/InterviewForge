import re
from pydantic import Field
from interview_forge.curricula import TOPICS, topic_for
from interview_forge.llm import LLMClient, prompt
from interview_forge.quality import claim_quality
from interview_forge.schemas.models import CapabilityClaim, Dimension, Model, ResumeStatement


class ClaimBatch(Model):
    claims: list[CapabilityClaim] = Field(min_length=1, max_length=80)


def statements_from_resume(resume: str) -> list[ResumeStatement]:
    project = "项目经历"
    result = []
    for i, raw in enumerate(resume.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            project = line.lstrip("# ") or project
            continue
        text = re.sub(r"^[-*•]\s*", "", line)
        result.append(ResumeStatement(id=f"s{len(result)+1}", text=text, project=project, line=i))
    if not result:
        raise ValueError("Resume contains no statements; supply plain text or Markdown project bullets")
    return result


PHRASES = {
    Dimension.problem: "能够解释{topic}所解决的问题、竞争条件或业务不变量",
    Dimension.mechanism: "理解{topic}的核心机制及其保证边界",
    Dimension.decision: "能够解释{topic}的选型依据及替代方案",
    Dimension.engineering: "能够解释{topic}在业务流程中的落地与接口边界",
    Dimension.failure: "理解{topic}的故障模式、恢复与降级约束",
    Dimension.evaluation: "能够设计验证{topic}正确性与性能的实验",
    Dimension.scaling: "能够解释{topic}在规模扩大后的瓶颈与扩展方式",
    Dimension.ownership: "能够解释自己在{topic}中的职责、决策与协作边界",
}


def rank_claims(claims: list[CapabilityClaim], jd: str) -> list[CapabilityClaim]:
    for c in claims:
        source = c.source_quote
        aliases = TOPICS[topic_for(c.topic)].aliases
        factors = {
            "jd_relevance": 1.0 if any(a in jd.lower() for a in aliases) else 0.4,
            "wording_strength": 1.0 if re.search(r"主导|设计|优化|提升|解决|自研|led|designed|optimized", source, re.I) else 0.4,
            "metric_boldness": 1.0 if re.search(r"\d+(?:\.\d+)?\s*(?:%|倍|ms|qps)", source, re.I) else 0.2,
            "engineering_complexity": 0.9 if topic_for(c.topic) != "service" else 0.6,
            "depth_potential": 1.0 if c.dimension in {Dimension.mechanism, Dimension.failure, Dimension.decision} else 0.7,
            "ownership_ambiguity": 0.8 if not re.search(r"独立|负责|implemented|owned", source, re.I) else 0.5,
            "evidence_weakness": 1.0 if not c.evidence_ids else 0.6,
            "interview_probability": 0.9 if c.dimension != Dimension.scaling else 0.6,
        }
        c.risk_factors = factors
        c.risk_score = round(sum(factors.values()) / len(factors) * 100, 1)
        c.risk_reasons = [f"{k}={v:.1f}" for k, v in factors.items() if v >= 0.8]
    return sorted(claims, key=lambda c: (-c.risk_score, c.id))


def extract_claims(resume: str, jd: str = "", client: LLMClient | None = None):
    statements = statements_from_resume(resume)
    if client:
        claims = client.structured_generate(prompt("claim_extraction"), {
            "statements": [s.model_dump() for s in statements], "jd": jd}, ClaimBatch).claims
    else:
        claims = []
        technical = re.compile(
            r"redis|lua|rag|rerank|python|java|golang|\bgo\b|c\+\+|sql|http|api|kafka|mq|"
            r"docker|kubernetes|agent|search|cache|service|backend|frontend|model|pipeline|"
            r"实现|设计|优化|开发|服务|接口|系统|并发|检索|模型|缓存|数据库|网络|算法|事务|库存", re.I)
        relevant = [s for s in statements if technical.search(s.text) and not re.match(
            r"^(邮箱|电话|手机|email|phone)\s*[:：]", s.text, re.I)]
        if not relevant:
            raise ValueError("Offline mode found no technical project statement; supply project bullets or use compatible mode")
        if len(relevant) > 10:
            raise ValueError("Offline mode supports up to 10 technical statements; narrow resume scope or use compatible mode")
        for statement in relevant:
            topic = TOPICS[topic_for(statement.text)].title
            for dimension, phrase in PHRASES.items():
                claims.append(CapabilityClaim(
                    id=f"c{len(claims)+1}", statement_id=statement.id,
                    proposition=phrase.format(topic=topic), dimension=dimension, topic=topic,
                    project=statement.project, source_quote=statement.text))
    source = {s.id: s for s in statements}
    for c in claims:
        ok, reason = claim_quality(c.proposition)
        if not ok:
            raise ValueError(reason)
        if c.statement_id not in source or c.source_quote not in source[c.statement_id].text:
            raise ValueError("Generated claim not grounded in resume statement")
        c.evidence_ids = []
        c.answerability = "unknown"
        from interview_forge.schemas.models import MasteryState
        c.mastery = MasteryState()
    return statements, rank_claims(claims, jd)
