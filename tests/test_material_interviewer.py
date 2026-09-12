"""Material questions retain their own intent and stay separate from answer references."""
import json
from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from interview_forge.agents.interviewer import (
    Interviewer, InterviewerView, QuestionSeed, SpokenTurn, infer_dimension,
)
from interview_forge.schemas.models import Dimension, InterviewQuestion
from interview_forge.interview.engine import question_seeds
from interview_forge.interview.material_context import material_context
from interview_forge.materials.library import MaterialLibrary


def _view(session, seeds, *, history=None, used=None):
    claim = session.claims[0].model_copy(deep=True)
    claim.dimension = Dimension.mechanism
    return InterviewerView(claim=claim, jd="后端岗位", history=history or [], knowledge_titles=[],
                           depth=len(history or []), experience_questions=seeds, used_material_questions=used or [])


@pytest.mark.parametrize("text, expected", [
    ("如何用并发压测证明库存没有扣成负数？", (Dimension.evaluation, "evaluation", 4)),
    ("如何设计实验验证超时重试不会重复扣减？", (Dimension.evaluation, "evaluation", 4)),
    ("How would you test that concurrent requests cannot oversell inventory?", (Dimension.evaluation, "evaluation", 4)),
    ("Redis Lua 脚本为什么能防止库存超卖？", (Dimension.mechanism, "mechanism", 2)),
    ("Why does the Lua script prevent concurrent stock updates?", (Dimension.mechanism, "mechanism", 2)),
    ("脚本执行成功但客户端超时，重试怎么办？", (Dimension.failure, "failure", 5)),
    ("为什么选择 Redis 而不是数据库条件更新？", (Dimension.decision, "decision", 3)),
    ("线上指标突然恶化时如何排查根因？", (Dimension.failure, "debugging", 6)),
    ("并发增加后吞吐不再增长，P99却变高，怎么定位瓶颈？", (Dimension.failure, "debugging", 6)),
    ("数据库已经提交但连接断开时，客户端如何拿到最终结果？", (Dimension.failure, "failure", 5)),
    ("如何同时比较Recall@K、NDCG和端到端延迟？", (Dimension.evaluation, "evaluation", 4)),
    ("向量索引如何快速定位最近邻，背后是什么原理？", (Dimension.mechanism, "mechanism", 2)),
])
def test_material_intent_overrides_scheduled_dimension(text, expected):
    assert infer_dimension(text, Dimension.decision) == expected


def test_unknown_intent_preserves_consistent_default_tuple():
    assert infer_dimension("谈谈这个问题？", Dimension.evaluation) == (Dimension.evaluation, "evaluation", 4)
    assert infer_dimension("谈谈这个问题？", Dimension.decision) == (Dimension.decision, "decision", 3)


@pytest.mark.parametrize("live", [True, False])
def test_retrieval_filters_covered_materials_before_top_four(session, tmp_path, live):
    library = MaterialLibrary(tmp_path / "library")
    for index in range(6):
        path = tmp_path / f"redis-{index}.md"
        path.write_text(f"Q: Redis Lua 为什么能保证库存并发扣减？请分析场景 {index}。", encoding="utf-8")
        library.add(path)
    context = SimpleNamespace(config=SimpleNamespace(library_path=str(library.directory) if live else None),
                              transcript=[], materials=library.items())
    first = material_context(context, "Redis Lua 库存 并发", "interview")
    assert len(first) == 4
    context.transcript = [SimpleNamespace(question=SimpleNamespace(material_question=item.question)) for item in first]
    remaining = material_context(context, "Redis Lua 库存 并发", "interview")
    assert len(remaining) == 2
    assert not {item.id for item in remaining} & {item.id for item in first}
    question = Interviewer().ask(_view(session, question_seeds(remaining), used=[item.question for item in first]), "q5")
    assert question.material_ids and question.material_question in {item.question for item in remaining}


def test_retrieval_retains_unused_followup_and_does_not_filter_answer_references(tmp_path):
    library = MaterialLibrary(tmp_path / "library")
    path = tmp_path / "redis.md"
    path.write_text("Q: Redis Lua 为什么能保证库存不超卖？\n追问：客户端超时后如何安全重试？\nA: 复用订单号并返回同一处理结果。", encoding="utf-8")
    question_document = library.add(path)
    answer_document = library.add(path, kind="answer")
    context = SimpleNamespace(config=SimpleNamespace(library_path=str(library.directory)), materials=[],
        transcript=[SimpleNamespace(question=SimpleNamespace(material_question="Redis Lua 为什么能保证库存不超卖 ?"))])
    followup_items = material_context(context, "Redis Lua 库存", "interview")
    assert [item.id for item in followup_items] == question_document.item_ids
    context.transcript.append(SimpleNamespace(question=SimpleNamespace(material_question="客户端超时后如何安全重试？")))
    assert material_context(context, "Redis Lua 库存", "interview") == []
    assert [item.id for item in material_context(context, "Redis Lua 库存", "answer")] == answer_document.item_ids


def test_evaluation_seed_keeps_source_wording_id_and_level(session):
    source = "如何用并发压测证明库存没有扣成负数 ?"
    view = _view(session, [QuestionSeed(id="experience_ocr", question=source)])
    question = Interviewer().ask(view, "q1")
    assert (question.dimension, question.subtopic, question.level) == (Dimension.evaluation, "evaluation", 4)
    assert question.material_ids == ["experience_ocr"]
    assert question.material_question == source
    assert question.text.endswith(source)


def test_mechanism_seed_after_evaluation_is_not_classified_by_previous_answer(session):
    previous = SpokenTurn(id="t1", question="如何做库存压测？", answer="我会设计实验验证库存非负。",
                          signals=["solid"], subtopic="evaluation")
    source = "Redis Lua 脚本为什么能防止库存超卖？"
    view = _view(session, [QuestionSeed(id="experience_atomic", question=source)], history=[previous])
    question = Interviewer().ask(view, "q2")
    assert (question.dimension, question.subtopic, question.level) == (Dimension.mechanism, "mechanism", 2)
    assert question.based_on_turn == "t1"
    assert "上一答提到" in question.text and question.material_question == source
    assert infer_dimension(question.text, Dimension.decision) == (Dimension.mechanism, "mechanism", 2)


def test_used_question_skips_ocr_spacing_variant_and_selects_actual_followup(session):
    original = "Redis Lua 脚本为什么能防止库存超卖？"
    followup = "脚本执行成功但客户端超时，重试怎么办？"
    seed = QuestionSeed(id="experience_atomic", question="Redis Lua 脚本为什么能防止库存超卖 ?", followups=[followup])
    previous = SpokenTurn(id="t1", question=original, answer="读检查写由 Lua 串行执行。",
                          signals=["solid"], subtopic="mechanism")
    view = _view(session, [seed], history=[previous], used=[original])
    question = Interviewer().ask(view, "q2")
    assert question.material_question == followup
    assert question.material_ids == [seed.id]
    assert (question.dimension, question.subtopic, question.level) == (Dimension.failure, "failure", 5)
    view.used_material_questions.append(followup)
    fallback = Interviewer().ask(view, "q2")
    assert fallback.material_ids == [] and fallback.material_question is None


def test_interviewer_context_contains_question_seeds_without_reference_answers(session):
    secret = "私有参考答案包含从源码推演的实验结果"
    with pytest.raises(ValidationError):
        QuestionSeed.model_validate({"id": "experience", "question": "为什么使用 Redis 原子扣减？", "answer": secret})
    seed = QuestionSeed(id="experience", question="如何用实验验证库存不超卖？", followups=["如何设计并发请求？"])
    view = _view(session, [seed])
    with pytest.raises(ValidationError):
        InterviewerView.model_validate({**view.model_dump(), "reference_materials": [{"answer": secret}]})
    class Capture:
        def structured_generate(self, system, payload, schema):
            assert secret not in json.dumps(payload, ensure_ascii=False)
            assert set(payload["experience_questions"][0]) == {"id", "question", "followups", "topics", "company", "role"}
            assert "evidence_ids" not in payload["claim"]
            assert "answerability" not in payload["claim"]
            assert "reference_materials" not in payload and "evidences" not in payload
            return InterviewQuestion(id="ignored", claim_id=view.claim.id, text=seed.question,
                dimension=Dimension.decision, level=3, depth=0, subtopic="decision", rationale="来源题",
                material_ids=[seed.id], material_question=seed.question)
    question = Interviewer(Capture()).ask(view, "q1")
    assert question.id == "q1"
    assert (question.dimension, question.subtopic, question.level) == (Dimension.evaluation, "evaluation", 4)
    assert question.material_ids == [seed.id] and question.material_question == seed.question


@pytest.mark.parametrize("kind", ["unknown_id", "invented_source", "repeated_source"])
def test_model_cannot_fabricate_or_repeat_material_provenance(session, kind):
    seed = QuestionSeed(id="experience", question="为什么使用 Redis Lua 防止库存超卖？")
    view = _view(session, [seed], used=[seed.question] if kind == "repeated_source" else [])
    class Incorrect:
        def structured_generate(self, system, payload, schema):
            return InterviewQuestion(id="q1", claim_id=view.claim.id,
                text="为什么使用 Redis Lua 防止库存超卖？", dimension=Dimension.mechanism,
                level=2, depth=0, subtopic="mechanism", rationale="测试",
                material_ids=["unknown" if kind == "unknown_id" else seed.id],
                material_question="如何改用数据库保证库存一致性？" if kind == "invented_source" else seed.question)
    with pytest.raises(ValueError, match="unknown experience|not present|already covered"):
        Interviewer(Incorrect()).ask(view, "q1")
