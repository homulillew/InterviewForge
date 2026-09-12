import pytest
from pydantic import ValidationError
from interview_forge.quality import claim_quality, question_quality
from interview_forge.schemas.models import CapabilityClaim, Dimension, InterviewSession, MasteryState


def test_claim_is_capability_and_risk_is_bounded(session):
    assert all(c.proposition in c.source_quote for c in session.claims)
    assert all("dimension" not in c.model_dump() for c in session.claims)
    assert len(session.attack_surfaces) > len(session.claims)
    assert session.claims[0].risk_score >= session.claims[-1].risk_score
    assert session.claims[0].risk_reasons
    with pytest.raises(ValidationError):
        CapabilityClaim(id="c", statement_id="s", proposition="理解并发", dimension=Dimension.mechanism,
                        topic="Redis", project="shop", source_quote="Redis", risk_score=101)


@pytest.mark.parametrize("text", ["仓库有 Redis dependency", "存在 Lua 文件", "某文件调用 Lua"])
def test_bad_claims(text):
    assert not claim_quality(text)[0]


@pytest.mark.parametrize("text", ["你的 Lua 文件在哪里？", "仓库里有没有 reranker？", "你的 top_k 在哪个配置文件？", "Which file contains the function?"])
def test_trivia_rejected(text):
    assert not question_quality(text)[0]


@pytest.mark.parametrize("text", ["为什么 Redis Lua 的原子性不等于持久性？", "top_k 从 20 改到 100，如何权衡召回与延迟？", "How do you validate correctness under retries?"])
def test_reasoning_accepted(text):
    assert question_quality(text)[0]


def test_mastery_requires_human_evidence():
    with pytest.raises(ValidationError):
        MasteryState(status="interview_ready")


def test_source_quote_and_links_are_validated(session):
    data = session.model_dump()
    data["claims"][0]["source_quote"] = "invented experience"
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)
    data = session.model_dump()
    data["evidences"][0]["related_claim_ids"] = ["missing"]
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)


def test_offline_claim_extraction_skips_contact_and_name():
    from interview_forge.claims.pipeline import extract_claims
    statements, claims = extract_claims("张三\n邮箱：person@example.com\n使用 Redis Lua 实现库存扣减")
    assert len(statements) == 3
    assert {c.statement_id for c in claims} == {"s3"}
