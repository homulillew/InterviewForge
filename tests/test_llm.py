import json
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from interview_forge.llm import CompatibleClient, ProviderError
from interview_forge.schemas.models import Assessment
from interview_forge.agents.repository_answerer import RepositoryAnswerer, AnswerDraft
from interview_forge.interview.engine import advance


def test_compatible_http_and_structured_repair():
    received = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(data)
            assert self.path == "/v1/chat/completions"
            content = "invalid JSON" if len(received) == 1 else json.dumps({"score": 0.7, "missed_points": ["counterexample"], "rationale": "partial", "assessor": "model"})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": content}}]}).encode())
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = CompatibleClient(f"http://127.0.0.1:{server.server_port}/v1", "test-model", api_key="")
        result = client.structured_generate("Evaluate", {"answer": "human answer"}, Assessment)
        assert result.score == 0.7
        assert len(received) == 2
        assert "output_json_schema" in received[0]["messages"][1]["content"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_malformed_provider_output_fails_without_silent_demo():
    client = CompatibleClient("http://localhost:1234/v1", "test")
    client.generate = lambda *args: '{"score": 9}'
    with pytest.raises(ProviderError, match="twice"):
        client.structured_generate("system", {}, Assessment)


def test_failed_turn_does_not_mutate_session(session):
    before = session.model_dump()
    class Broken:
        def structured_generate(self, *args):
            raise ProviderError("unavailable")
    with pytest.raises(ProviderError):
        advance(session, Broken())
    assert session.model_dump() == before


def test_model_cannot_smuggle_project_claim_into_general_knowledge(session):
    advance(session)
    class Dishonest:
        def structured_generate(self, *args):
            return AnswerDraft(evidence_ids=[], technical_explanation="我们项目实现了熔断。", technology_decision="选择依据",
                failure_modes=[], unsupported_claims=[], likely_followups=[], related_knowledge=[], improvement_directions=[], signals=[])
    with pytest.raises(ValueError, match="Project assertion"):
        RepositoryAnswerer(Dishonest()).answer(session.transcript[0].question, session.claims[0], session.evidences)


def test_semantic_pipeline_contracts_and_retest(session, tmp_path):
    """Exercise every typed model boundary with a fixture client; not a model-quality eval."""
    from interview_forge.agents.interviewer import RenderedQuestion, InterviewerView, authored_question
    from interview_forge.claims.pipeline import ClaimBatch, extract_claims
    from interview_forge.knowledge.graph import KnowledgeBatch, extract_knowledge
    from interview_forge.schemas.models import CapabilityClaim, InterviewTurn, AnswerCritique
    from interview_forge.interview.retest import begin_retest, submit_retest
    calls = []
    class FixtureClient:
        def structured_generate(self, system, payload, schema):
            calls.append(schema.__name__)
            assert system
            if schema is ClaimBatch:
                _, claims = extract_claims("\n".join(s["text"] for s in payload["statements"]))
                return ClaimBatch(claims=claims)
            if schema is RenderedQuestion:
                from interview_forge.schemas.models import QuestionPlan, AttackSurface, EffectiveStyle
                plan = QuestionPlan.model_validate(payload["plan"])
                view = InterviewerView(claim=payload["claim"], plan=plan,
                    surface=AttackSurface(id=plan.attack_surface_id, claim_id=plan.claim_id,
                        dimension=payload["surface"]["dimension"], priority="P0", relevance=1, rationale="fixture"),
                    style=EffectiveStyle.model_validate(payload["style"]))
                return RenderedQuestion(text=authored_question(view))
            if schema is AnswerCritique:
                return AnswerCritique(missing_facets=["baseline"], answer_quality=.5)
            if schema is AnswerDraft:
                return AnswerDraft(evidence_ids=[e["id"] for e in payload["evidences"][:2]],
                    technical_explanation="原子执行需要明确读检查写的范围；超时重试还需要幂等保证。",
                    technology_decision="比较数据库条件更新与 Redis 的事务范围和吞吐需求。",
                    failure_modes=["运行时错误不会回滚已完成写入"], unsupported_claims=["没有生产评测结果"],
                    likely_followups=["如何测试重试场景？"], related_knowledge=["原子性"], improvement_directions=["改进方向：补充并发测试"], signals=["no_measurement"])
            if schema is KnowledgeBatch:
                return extract_knowledge(CapabilityClaim.model_validate(payload["claim"]), InterviewTurn.model_validate(payload["turn"]))
            if schema is Assessment:
                return Assessment(score=0.4, missed_points=["缺少反例"], rationale="回答只说了原子执行", assessor="model")
            raise AssertionError(schema)
    client = FixtureClient()
    _, claims = extract_claims(session.resume, session.jd, client)
    assert claims
    assert advance(session, client)
    assert session.transcript[0].answer.provenance == "model"
    assert set(calls) >= {"ClaimBatch", "RenderedQuestion", "AnswerDraft", "AnswerCritique", "KnowledgeBatch"}
    before = len(calls)
    session, pending = begin_retest(session)
    assert len(calls) == before and pending.reference is None
    session, answered = submit_retest(session, "原子执行", client)
    assert answered.assessment.assessor == "model"
    assert session.study_plan[0].gap_kind == "mastery_gap"
