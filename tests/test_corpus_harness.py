import json
from pathlib import Path
import pytest
from interview_forge.agents.interviewer import (
    Interviewer,
    InterviewerView,
    RenderedQuestion,
    authored_question,
    guard_question,
    SpokenTurn,
)
from interview_forge.interview.critic import blind_claim, critique_answer
from interview_forge.interview.engine import advance
from interview_forge.interview.attack_planner import choose_attack
from interview_forge.interview.question_planner import make_question_plan
from interview_forge.schemas.models import (
    QuestionProvenance,
    InterviewSession,
    AnswerCritique,
    ChallengeOperator as O,
)
from interview_forge.corpus.normalize import normalize_post
from interview_forge.corpus.ingest import compile_corpus
from interview_forge.corpus.retrieval import retrieve_content


def view_and_provenance(session):
    attack = choose_attack(session)
    claim = next(c for c in session.claims if c.id == attack.claim_id)
    surface = next(s for s in session.attack_surfaces if s.id == attack.attack_surface_id)
    plan, _, _ = make_question_plan(claim, surface, attack, [], [], session.effective_style, [])
    view = InterviewerView(
        claim=blind_claim(claim), surface=surface, plan=plan, style=session.effective_style
    )
    provenance = QuestionProvenance(
        resume_statement_id=claim.statement_id,
        atomic_claim_id=claim.id,
        attack_surface_id=surface.id,
        challenge_operator=plan.operator,
        adaptation_reason=plan.adaptation_reason,
    )
    return view, provenance


def test_red_interviewer_and_critic_payloads_are_repository_blind(session):
    view, provenance = view_and_provenance(session)
    secret_keys = {
        "evidences",
        "evidence_ids",
        "evidence_selection",
        "repository_map",
        "answerability",
        "reasoning_basis",
        "audit",
        "signals",
    }
    calls = []

    class Capture:
        def structured_generate(self, system, payload, schema):
            calls.append(schema)
            rendered = json.dumps(payload, ensure_ascii=False)
            assert all(f'"{key}"' not in rendered for key in secret_keys)
            assert session.repository_map.root not in rendered
            assert all(e.file_path not in rendered for e in session.evidences)
            if schema is RenderedQuestion:
                assert not payload["abstract_patterns"]
                return RenderedQuestion(text=authored_question(view))
            return AnswerCritique(missing_facets=["baseline"], answer_quality=0.3)

    question = Interviewer(Capture()).ask(view, "q1", provenance)
    claim = next(c for c in session.claims if c.id == question.claim_id)
    critique_answer(claim, view.surface, question, "因为 Redis 快。", [], Capture())
    assert calls == [RenderedQuestion, AnswerCritique]


@pytest.mark.parametrize(
    "text,reason",
    [
        ("Redis 的 Lua 脚本在哪个文件里，如何找到？", "trivia"),
        ("Transformer 如何解释 sqrt(d_k) 的缩放？", "unrelated"),
        ("Redis 如何测量性能？如何设置压测？", "one primary"),
        ("Redis 实测吞吐提升了999%，为什么？", "premise"),
        ("如何验证这个方案的正确性？", "resume anchor"),
    ],
)
def test_question_guards(session, text, reason):
    view, _ = view_and_provenance(session)
    assert reason in guard_question(text, view).lower()


def test_copy_and_repeat_guard(session):
    view, _ = view_and_provenance(session)
    text = authored_question(view)
    assert "copied" in guard_question(text, view, [text])
    view.history = [SpokenTurn(id="t0", question=text, answer="因为快", subtopic="evaluation")]
    assert "repeated" in guard_question(text, view)


def test_failing_renderer_does_not_fallback_or_mutate(session):
    before = session.model_dump()

    class Bad:
        def structured_generate(self, system, payload, schema):
            return RenderedQuestion(text="Transformer 如何解释注意力的缩放系数？")

    with pytest.raises(ValueError, match="failed guards"):
        advance(session, Bad())
    assert session.model_dump() == before


def test_blue_self_signals_do_not_select_next_attack(session):
    advance(session)
    original = choose_attack(session)
    session.transcript[-1].answer.signals = ["no_decision", "failure_gap", "vague"]
    session.transcript[-1].answer.likely_followups = ["Transformer 如何工作？"]
    assert choose_attack(session) == original


def test_material_gaps_do_not_become_mastery_gaps(session):
    advance(session)
    turn = session.transcript[-1]
    assert turn.answer.material_gaps
    assert all(c.mastery.status == "unknown" for c in session.claims)
    assert all(task.gap_kind != "mastery_gap" for task in session.study_plan)
    assert not set(turn.answer.unsupported_claims) & set(turn.critique.missing_facets)


def test_coverage_and_plan_persist_and_forged_provenance_fails(session):
    advance(session)
    q = session.transcript[0].question
    surface = next(a for a in session.attack_surfaces if a.id == q.provenance.attack_surface_id)
    assert surface.coverage in {"partial", "covered", "exhausted"}
    assert surface.question_count == 1 and surface.last_turn_id == "t1"
    bad = session.model_dump()
    bad["transcript"][0]["question"]["provenance"]["atomic_claim_id"] = "missing"
    with pytest.raises(ValueError, match="atomic resume anchor"):
        InterviewSession.model_validate(bad)
    bad = session.model_dump()
    bad["transcript"][0]["question"]["plan"]["transition_ids"] = ["missing"]
    with pytest.raises(ValueError, match="provenance lists disagree"):
        InterviewSession.model_validate(bad)


def test_transferred_question_plan_uses_resume_alternative(session):
    from interview_forge.claims.pipeline import extract_claims, generate_surfaces
    from interview_forge.schemas.models import AttackPlan, Dimension

    _, claims = extract_claims("引入 RAG reranker 提升检索效果")
    claim = claims[0]
    surface = next(s for s in generate_surfaces(claims) if s.dimension == Dimension.decision)
    corpus = compile_corpus([normalize_post("Q: 为什么不直接用线程池替代 Kafka？", "synthetic")])
    matches = retrieve_content(corpus, "rev", claim, surface)
    attack = AttackPlan(
        claim_id=claim.id,
        attack_surface_id=surface.id,
        goal="compare",
        preferred_operators=[O.WHY_NOT_SIMPLER],
        rationale="test",
    )
    plan, selected, _ = make_question_plan(claim, surface, attack, matches, [], session.effective_style, [])
    assert selected and "top_k" in plan.alternative
    view = InterviewerView(
        claim=blind_claim(claim),
        surface=surface,
        plan=plan,
        style=session.effective_style,
        abstract_patterns=[p.abstract_pattern for _, p in selected],
    )
    text = authored_question(view)
    assert "Kafka" not in text and "线程池" not in text and "top_k" in text


def test_canonical_cards_answer_followups_and_exercise_compresses(session):
    while advance(session):
        pass
    assert all(card.followup_qa and all(qa.answer for qa in card.followup_qa) for card in session.study_cards)
    assert all(card.title and card.must_know and card.project_anchors for card in session.study_cards)
    assert any(len(task.covers_node_ids) > 1 for task in session.study_plan)
    assert len(session.knowledge_graph.nodes) < 2 * len(session.transcript)
    assert not any("：选型权衡" in n.title or "：故障边界" in n.title for n in session.knowledge_graph.nodes)


def test_corpus_eval_reports_manual_metrics(tmp_path):
    from interview_forge.evaluation.corpus import evaluate_corpus
    from interview_forge.corpus.ingest import ingest

    root = Path(__file__).resolve().parents[1]
    db = tmp_path / "corpus.sqlite3"
    ingest([root / "examples/corpus/synthetic.json"], db)
    result = evaluate_corpus(db, root / "evals/corpus/cases.json", tmp_path / "metrics.json")
    assert result["metrics"]["resume_anchor_rate"] == 1
    assert result["metrics"]["evidence_factuality"] == "manual_review_required"
    assert result["metrics"]["question_copy_rate"] == 0
    assert (tmp_path / "metrics.md").is_file()


def test_overlapping_atomic_claims_do_not_repeat_the_same_project_probe(session):
    while advance(session):
        pass
    focuses = [t.question.text.rsplit('”。', 1)[-1] for t in session.transcript]
    assert len(focuses) == len(set(focuses))
    operators = [t.question.plan.operator for t in session.transcript]
    assert len(operators) == len(set(operators))


def test_explicit_ownership_is_separate_without_invented_competency():
    from interview_forge.claims.pipeline import extract_claims
    from interview_forge.schemas.models import ClaimType
    _, claims = extract_claims('主导设计 Redis 库存扣减，解决并发超卖，吞吐提升40%。')
    assert len(claims) == 4
    assert sum(c.claim_type == ClaimType.ownership for c in claims) == 1
    assert all(c.proposition in c.source_quote for c in claims)
    assert not any('能够解释' in c.proposition for c in claims)


def test_wrong_operator_is_rejected(session):
    view, _ = view_and_provenance(session)
    assert view.plan.operator == O.METRIC_PRESSURE
    assert 'planned challenge operator' in guard_question('Redis Lua 的原子执行机制是什么，为什么？', view)
