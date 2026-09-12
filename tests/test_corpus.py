import json
import sqlite3
from pathlib import Path
import pytest
from interview_forge.corpus.normalize import normalize_post
from interview_forge.corpus.ingest import compile_corpus, ingest, rebuild
from interview_forge.corpus.storage import CorpusStore
from interview_forge.corpus.models import CompiledCorpus
from interview_forge.corpus.style import retrieve_style
from interview_forge.corpus.applicability import applicability
from interview_forge.corpus.retrieval import retrieve_content, retrieve_transitions
from interview_forge.claims.pipeline import extract_claims, generate_surfaces
from interview_forge.schemas.models import Applicability, ChallengeOperator as O, Dimension, ProbeIntent

ROOT = Path(__file__).resolve().parents[1]


def compile_posts(*posts):
    return compile_corpus(
        [normalize_post(post, f"/synthetic/{index}.md") for index, post in enumerate(posts)]
    )


@pytest.mark.parametrize(
    "post,kind,count",
    [
        ("Q: Redis 为什么快？\nA: 因为在内存中。\nQ: 如何测量？", "trace", 2),
        ("1. Redis 如何保证原子性？\n2. 出错会回滚吗？", "ordered_list", 2),
        ("讨论了 Redis 和 MySQL，以及一些项目问题。", "unordered_summary", 0),
        ({"questions": ["为什么使用 Kafka？", "为什么不直接使用线程池？"]}, "ordered_list", 2),
        (
            {
                "messages": [
                    {"role": "interviewer", "content": "Redis 为什么快？"},
                    {"role": "candidate", "content": "因为内存。"},
                ]
            },
            "trace",
            1,
        ),
        ("用了 Redis\n→ 为什么用？\n→ 因为快\n→ 快在哪里？", "trace", 2),
        (
            {"source_type": "unordered_summary", "questions": ["Redis 如何工作？", "如何压测？"]},
            "unordered_summary",
            0,
        ),
    ],
)
def test_heterogeneous_normalization(post, kind, count):
    case = normalize_post(post, "/synthetic/post.md")
    assert case.source_type == kind and len(case.questions) == count
    if kind == "unordered_summary":
        assert compile_corpus([case]).transitions == []


def test_numbered_answer_steps_are_not_questions():
    case = normalize_post(
        "Q: Redis 如何实现幂等？\nA: 采用业务键。\n1. 校验输入。\n2. 保存结果。\nQ: 为什么不能只查缓存？", "x"
    )
    assert len(case.questions) == 2
    assert "保存结果" in case.questions[0].answer_context


@pytest.mark.parametrize(
    "post",
    [
        "普通面经\n1. Redis 如何实现原子性？",
        {"questions": ["Redis 如何实现原子性？"]},
        {"company": "unknown", "text": "讨论 Redis。"},
    ],
)
def test_unknown_metadata_is_not_invented(post):
    case = normalize_post(post, "/bytedance/tech-2.md")
    assert case.company is None and case.round is None


def test_explicit_metadata_context_and_round_normalization():
    case = normalize_post(
        {
            "company": "字节",
            "role": "后端",
            "round": "二面",
            "resume_context": "实现库存系统",
            "project_context": ["Redis 扣减"],
            "questions": ["如何验证 Redis 原子性？"],
        },
        "x",
    )
    assert (case.company, case.role, case.round) == ("bytedance", "backend", "tech-2")
    assert case.resume_context == ["实现库存系统"] and case.project_context == ["Redis 扣减"]


def test_question_topics_do_not_borrow_later_technology():
    case = normalize_post(
        "Q: Redis 如何实现原子性？\nQ: 边界是什么？\nQ: Transformer 为什么除以 sqrt(d_k)？", "x"
    )
    assert case.questions[1].topic == ["Redis"]
    assert "Redis" not in case.questions[2].topic


def test_observed_vs_weak_transitions():
    corpus = compile_posts(
        "Q: 为什么使用 Redis？\nA: 因为快。\nQ: 快在哪里，如何测量？",
        "1. 为什么使用 Redis？\n2. Redis 如何设计对照？",
    )
    observed = next(t for t in corpus.transitions if t.observed_answer)
    weak = next(t for t in corpus.transitions if not t.observed_answer)
    assert "performance_claim_without_measurement" in observed.candidate_answer_features
    assert observed.confidence > weak.confidence and not weak.candidate_answer_features
    assert observed.challenge_operator == O.METRIC_PRESSURE


def test_duplicate_posts_count_once_in_style_and_pattern():
    post = {
        "company": "bytedance",
        "role": "backend",
        "questions": ["为什么使用 Redis？", "Redis 如何测量吞吐？"],
    }
    corpus = compile_posts(post, post, post)
    assert len(corpus.cases) == 3
    assert len({c.duplicate_group for c in corpus.cases}) == 1
    assert all(p.sample_size == 1 for p in corpus.style_profiles)
    assert all(p.support_count == 1 for p in corpus.patterns)


def test_near_duplicate_shingles():
    text = "Q: Redis 如何保证一次库存扣减在并发调用过程中不出现检查与写入之间的交错执行，并解释相关的输入参数校验、业务不变量与原子操作保证的范围？\nQ: 在客户端发生超时以及相同业务请求重复提交的场景下，如何避免同一库存被多次扣减，并通过受控实验验证恢复流程与返回结果的一致性？"
    corpus = compile_posts(text, text.replace("客户端", "调用端"))
    assert len({c.duplicate_group for c in corpus.cases}) == 1


def test_style_backoff_and_empty_neutral():
    corpus = compile_posts(
        {
            "company": "bytedance",
            "role": "backend",
            "round": "tech-2",
            "questions": ["Redis 为什么需要 Lua？"],
        },
        {"company": "tencent", "role": "backend", "questions": ["为什么不直接使用数据库？"]},
    )
    style = retrieve_style(corpus.style_profiles, "bytedance", "backend", "tech-2", "senior")
    assert 0 < style.confidence < 0.5
    assert abs(sum(style.profile_weights.values()) - 1) < 1e-9
    assert any("*/*/*/*" in step for step in style.backoff_path)
    missing = retrieve_style([], "bytedance", "backend")
    assert not missing.id and missing.confidence == 0


def test_resume_content_outranks_company_and_rejects_unrelated_fundamentals():
    corpus = compile_posts(
        {"company": "bytedance", "questions": ["Transformer attention 为什么除以 sqrt(d_k)？"]},
        {"company": "tencent", "questions": ["Redis Lua 如何实现原子性？"]},
    )
    _, claims = extract_claims("使用 Redis Lua 实现库存扣减")
    claim = claims[0]
    surface = generate_surfaces(claims)[0]
    matches = retrieve_content(corpus, "revision", claim, surface, "bytedance")
    assert matches and "Redis" in matches[0][1].applicable_topics
    transformer = next(p for p in corpus.patterns if "Transformer" in p.applicable_topics)
    assert applicability(claim, surface, transformer)[0] == Applicability.reject


def test_simpler_operator_transfers_without_kafka_facts():
    corpus = compile_posts("Q: 为什么不直接使用线程池替代 Kafka？")
    _, claims = extract_claims("引入 RAG reranker 提升检索效果")
    surface = next(s for s in generate_surfaces(claims) if s.dimension == Dimension.decision)
    matches = retrieve_content(corpus, "revision", claims[0], surface)
    assert matches[0][0].applicability == Applicability.transferable
    assert matches[0][1].challenge_operator == O.WHY_NOT_SIMPLER


def test_transitions_use_observed_answer_features():
    corpus = compile_posts("Q: 为什么使用 Redis？\nA: 因为快。\nQ: 快在哪里，如何测量？")
    _, claims = extract_claims("使用 Redis 实现缓存")
    assert retrieve_transitions(
        corpus, ProbeIntent.problem, ["performance_claim_without_measurement"], claims[0]
    )
    assert not retrieve_transitions(corpus, ProbeIntent.problem, ["api_only_description"], claims[0])


def test_ownership_is_not_inferred_from_shared_technology():
    corpus = compile_posts("Q: 你在 Redis 库存模块负责什么？")
    _, claims = extract_claims("使用 Redis 实现库存扣减")
    assert (
        applicability(claims[0], generate_surfaces(claims)[0], corpus.patterns[0])[0] == Applicability.reject
    )


@pytest.mark.parametrize("suffix", [".md", ".txt", ".json", ".jsonl"])
def test_versioned_store_and_fts(tmp_path, suffix):
    source = tmp_path / ("post" + suffix)
    post = {"questions": ["Redis 如何保证原子性？", "如何测量 Redis 吞吐？"]}
    source.write_text(
        json.dumps(post, ensure_ascii=False)
        if suffix in {".json", ".jsonl"}
        else "Q: Redis 如何保证原子性？\nQ: 如何测量 Redis 吞吐？"
    )
    db = tmp_path / "corpus.sqlite3"
    revision = ingest([source], db)
    store = CorpusStore(db)
    assert store.current() == revision
    assert store.search_question_ids("Redis", revision)
    assert rebuild(db) == revision
    source.write_text(
        "Q: Kafka 为什么需要分区？"
        if suffix in {".md", ".txt"}
        else json.dumps({"questions": ["Kafka 为什么需要分区？"]})
    )
    changed = ingest([source], db)
    assert changed != revision and store.load(revision).cases[0].questions
    assert "Kafka" in store.load().cases[0].technologies


def test_atomic_ingest_failure_preserves_revision(tmp_path):
    post = tmp_path / "good.md"
    post.write_text("Q: Redis 如何实现原子性？")
    db = tmp_path / "corpus.sqlite3"
    revision = ingest([post], db)
    broken = tmp_path / "broken.json"
    broken.write_text("{")
    with pytest.raises(ValueError):
        ingest([post, broken], db)
    assert CorpusStore(db).current() == revision


def test_concurrent_revision_conflict(tmp_path):
    store = CorpusStore(tmp_path / "corpus.sqlite3")
    corpus = compile_posts("Q: Redis 为什么使用 Lua？")
    revision = store.commit(corpus)
    with pytest.raises(ValueError, match="changed during"):
        store.commit(corpus, expected_revision="stale")
    assert store.current() == revision


def test_payload_integrity_and_unrelated_database(tmp_path):
    db = tmp_path / "foreign.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("create table private_data (value text)")
    with pytest.raises(ValueError, match="unrelated"):
        CorpusStore(db).commit(compile_posts("Q: Redis 如何工作？"))
    store = CorpusStore(tmp_path / "corpus.sqlite3")
    revision = store.commit(compile_posts("Q: Redis 如何工作？"))
    with sqlite3.connect(store.path) as conn:
        conn.execute("update revisions set payload=? where id=?", ("{}", revision))
    with pytest.raises(ValueError, match="integrity"):
        store.load(revision)


def test_fabricated_answer_transition_rejected():
    corpus = compile_posts("1. Redis 为什么快？\n2. Redis 如何测量？")
    data = corpus.model_dump()
    data["transitions"][0]["candidate_answer_features"] = ["performance_claim_without_measurement"]
    with pytest.raises(ValueError, match="unobserved"):
        CompiledCorpus.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [("company", "bytedance"), ("questions", [{"text": "Redis 为什么回滚？", "answer": "我测得42%"}])],
)
def test_normalizer_model_cannot_invent_metadata_or_answer(field, value):
    from interview_forge.corpus.normalize import NormalizedPost

    class Fabricator:
        def structured_generate(self, system, payload, schema):
            return NormalizedPost.model_validate({"ordered": True, field: value})

    with pytest.raises(ValueError, match="invented"):
        normalize_post("Q: Redis 如何实现原子性？", "x", client=Fabricator())


def test_no_silent_truncation(tmp_path):
    source = tmp_path / "many.md"
    source.write_text("\n".join(f"Q: Redis 如何验证第 {i} 个输入？" for i in range(201)))
    with pytest.raises(ValueError):
        ingest([source], tmp_path / "corpus.sqlite3")
    assert not (tmp_path / "corpus.sqlite3").exists()
