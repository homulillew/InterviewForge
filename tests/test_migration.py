import json
from pathlib import Path
import pytest
from interview_forge.schemas.legacy_v1 import InterviewSession as LegacySession, RetestAttempt, MasteryState
from interview_forge.storage.migrate import migrate_v1
from interview_forge.storage.session import SessionStore

ROOT = Path(__file__).resolve().parents[1]


def legacy():
    return LegacySession.model_validate_json((ROOT / "examples/demo-output/interview_state.json").read_text())


def test_explicit_migration_preserves_history_and_archives_exact_source(tmp_path):
    old = legacy()
    raw = old.model_dump_json(indent=2)
    store = SessionStore(tmp_path)
    store.path.write_text(raw)
    with pytest.raises(ValueError, match="explicit migration"):
        store.load()
    with store.lock():
        updated = store.migrate()
    assert updated.schema_version == "2.0"
    assert len(updated.claims) < len(old.claims)
    assert [t.answer.direct_interview_answer for t in updated.transcript] == [
        t.answer.direct_interview_answer for t in old.transcript
    ]
    assert [n.id for n in updated.knowledge_graph.nodes] == [n.id for n in old.knowledge_graph.nodes]
    assert all(t.question.provenance.origin == "migration" for t in updated.transcript)
    assert next((tmp_path / "archives").glob("schema-1.0-*.json")).read_text() == raw
    assert store.migrate() == updated


def test_migration_preserves_human_answers_reviews_and_ready_node():
    old = legacy()
    node = old.knowledge_graph.nodes[0]
    claim = next(c for c in old.claims if c.id == node.source_claims[0])
    attempts = []
    for i in range(2):
        q = old.transcript[0].question.model_copy(
            update={"id": f"rq{i}", "claim_id": claim.id, "text": f"场景 {i} 如何解释机制边界？"}
        )
        attempts.append(
            RetestAttempt(
                id=f"r{i}",
                node_id=node.id,
                question=q,
                human_answer=f"独立回答 {i}",
                reference=old.transcript[0].answer.model_copy(update={"question_id": q.id}),
                assessment={
                    "score": 0.95,
                    "missed_points": [],
                    "rationale": "真实人工复核记录",
                    "assessor": "human_reviewer",
                },
            )
        )
    data = old.model_dump()
    data["retests"] = attempts
    data["knowledge_graph"]["nodes"][0]["mastery"] = MasteryState(
        status="interview_ready", evidence=["r0", "r1"], assessed_by="human_reviewer"
    )
    old = LegacySession.model_validate(data)
    updated = migrate_v1(old.model_dump())
    assert [r.human_answer for r in updated.retests] == ["独立回答 0", "独立回答 1"]
    assert all(r.assessment.assessor == "human_reviewer" for r in updated.retests)
    assert updated.knowledge_graph.nodes[0].mastery.status == "interview_ready"
    assert updated.knowledge_graph.nodes[0].mastery.evidence == ["r0", "r1"]


def test_invalid_migration_never_overwrites_original(tmp_path):
    store = SessionStore(tmp_path)
    data = legacy().model_dump()
    data["claims"][0]["source_quote"] = "invented"
    raw = json.dumps(data, ensure_ascii=False)
    store.path.write_text(raw)
    with pytest.raises(ValueError):
        store.migrate()
    assert store.path.read_text() == raw
    assert not (tmp_path / "archives").exists()
