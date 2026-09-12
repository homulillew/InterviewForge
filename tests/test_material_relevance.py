from interview_forge.materials.library import MaterialLibrary
from interview_forge.quality import question_quality
from interview_forge.agents.interviewer import infer_dimension
from interview_forge.agents.repository_answerer import RepositoryAnswerer
from interview_forge.schemas.models import Dimension


def test_natural_followup_wording_is_accepted():
    assert question_quality("客户端在扣减成功后超时，重试怎样避免重复扣减？")[0]
    assert question_quality("补偿任务重复执行会不会多加库存？")[0]
    assert infer_dimension("补偿任务重复执行会不会多加库存？", Dimension.decision)[0] == Dimension.failure


def test_compensation_answer_addresses_duplicate_recovery(session):
    from interview_forge.interview.engine import advance
    advance(session)
    question = session.transcript[0].question.model_copy(update={
        "text": "补偿任务重复执行会不会多加库存？", "dimension": Dimension.failure})
    answer = RepositoryAnswerer().answer(question, session.claims[0], [])
    assert "已补偿" in answer.direct_interview_answer
    assert "重复任务" in answer.direct_interview_answer
    assert "重放" in answer.direct_interview_answer
    assert "性能实验" not in answer.direct_interview_answer


def test_mixed_library_keeps_questions_and_answers_on_the_requested_subject(tmp_path):
    source = tmp_path / "mixed.md"
    source.write_text(
        "Q: Redis 库存扣减如何验证并发正确性？\nA: 使用库存不变量检查并发请求。\n\n"
        "Q: RAG 召回和重排如何评测延迟？\nA: 固定查询集并记录 Recall@K 和 NDCG。\n"
        "追问：如何同时比较 Recall@K、NDCG 和端到端延迟？\n\n"
        "Q: 并发增加后吞吐不再增长，P99 变高，怎么定位瓶颈？\nA: 检查连接池排队和慢依赖。\n",
        encoding="utf-8")
    library = MaterialLibrary(tmp_path / "library")
    for kind in ("interview", "answer"):
        library.add(source, kind=kind)
        backend = library.search("Redis 后端工程师 并发控制 性能测试 故障恢复", kind=kind, limit=20)
        assert backend and all("RAG" not in item.question for item in backend)
        assert any("定位瓶颈" in item.question for item in backend)
        retrieval = library.search("RAG 检索重排 评测 性能", kind=kind, limit=20)
        assert any("RAG" in item.question for item in retrieval)
        assert all("Redis" not in item.question for item in retrieval)
        combined = library.search("Redis RAG", kind=kind, limit=20)
        assert any("Redis" in item.question for item in combined)
        assert any("RAG" in item.question for item in combined)
        focused = library.search("Redis RAG 后端研发", kind=kind, limit=20, focus="Redis 库存")
        assert focused and all("RAG" not in item.question for item in focused)
