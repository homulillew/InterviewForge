"""User flows across import, live sessions, source snapshots and spoken reports."""
import json
from pathlib import Path

import pytest

from interview_forge.cli.main import main
from interview_forge.interview.engine import advance, question_seeds, start_session
from interview_forge.interview.retest import begin_retest, grade_retest, record_submission
from interview_forge.llm import ProviderError
from interview_forge.materials.library import MaterialLibrary
from interview_forge.schemas.models import InterviewSession, SessionConfig
from interview_forge.storage.reports import export_reports
from interview_forge.storage.session import SessionStore

ROOT = Path(__file__).resolve().parents[1]


def source(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_cli_live_import_and_removal_keep_historical_sources(tmp_path):
    library_path, output = tmp_path / "资料库", tmp_path / "面试"
    example = ROOT / "examples/redis"
    assert main(["start", "--resume", str(example / "resume.md"), "--repo", str(example / "repo"),
                 "--session", str(output), "--library", str(library_path), "--max-turns", "4"]) == 0
    interview = source(tmp_path, "面经.md", "Q: Redis Lua 为什么能把库存检查和扣减做成原子操作？\n")
    reference = source(tmp_path, "参考.md", "Q: Redis 库存如何与订单状态保持一致？\nA: 通过 outbox 记录事务消息，消费者按订单 ID 幂等处理。\n")
    for path, kind in ((interview, "interview"), (reference, "answer")):
        assert main(["library", "add", str(path), "--kind", kind, "--library", str(library_path)]) == 0
    assert main(["run", "--session", str(output), "--turns", "1"]) == 0
    first = SessionStore(output).load()
    turn = first.transcript[0]
    assert turn.question.material_ids and turn.answer.reference_material_ids
    assert "outbox" in turn.answer.direct_interview_answer
    library = MaterialLibrary(library_path)
    original_document = library.get_item(turn.question.material_ids[0]).document_id
    assert main(["library", "remove", original_document, "--library", str(library_path)]) == 0
    interview.unlink()
    fresh = source(tmp_path, "新面经.txt", "Q: Redis 请求已执行但响应丢失，使用相同订单 ID 重试如何避免重复扣减？\n")
    assert main(["library", "add", str(fresh), "--kind", "interview", "--library", str(library_path)]) == 0
    assert main(["run", "--session", str(output), "--turns", "1"]) == 0
    updated = SessionStore(output).load()
    assert updated.transcript[0] == turn
    assert updated.transcript[1].question.material_ids
    assert updated.transcript[1].question.material_ids != turn.question.material_ids
    assert updated.transcript[1].question.material_question != turn.question.material_question
    assert updated.transcript[1].question.based_on_turn == turn.id
    assert main(["report", "--session", str(output)]) == 0
    usages = json.loads((output / "material_usage.json").read_text())
    assert any(item["source_file"] == str(interview) and item["record_id"] == turn.id for item in usages)
    for name in ("transcript.md", "best_answer_cards.md"):
        spoken = (output / name).read_text()
        assert turn.answer.direct_interview_answer in spoken
        assert "Unsupported / Unverified" not in spoken
        assert "Project Grounding" not in spoken
        assert "证据不足" not in spoken
    audit = (output / "answer_audit.md").read_text()
    assert str(interview) in audit and "Unsupported / Unverified" in audit


def test_old_session_attaches_library_without_rebuilding(session, tmp_path):
    store = SessionStore(tmp_path / "old")
    legacy = session.model_dump()
    legacy.pop("materials")
    legacy["config"].pop("library_path")
    restored = InterviewSession.model_validate(legacy)
    store.save(restored)
    library_path = tmp_path / "later"
    document = MaterialLibrary(library_path).add(source(tmp_path, "later.md", "Q: Redis Lua 原子性如何保证？"))
    assert main(["attach-library", "--session", str(store.directory), "--library", str(library_path)]) == 0
    assert main(["run", "--session", str(store.directory), "--turns", "1"]) == 0
    updated = store.load()
    assert updated.id == session.id
    assert updated.repository_map == session.repository_map
    assert updated.transcript[0].question.material_ids == document.item_ids


def test_imported_material_is_never_scanned_as_repository_evidence(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "stock.py").write_text("def reserve(redis, key):\n    return redis.decr(key)\n")
    library_path = repo / "custom-references"
    material = source(tmp_path, "reference.md", "Q: Redis 性能如何？\nA: 实测吞吐 123456 QPS。")
    MaterialLibrary(library_path).add(material, kind="answer")
    session = start_session("# 库存服务\n使用 Redis 实现库存扣减。", repo, "", SessionConfig(
        library_path=str(library_path)), tmp_path / "state")
    assert all("custom-references" not in evidence.file_path for evidence in session.evidences)
    assert all("123456" not in evidence.excerpt for evidence in session.evidences)


def test_material_references_commit_only_with_successful_turn(session, tmp_path, monkeypatch):
    library = MaterialLibrary(tmp_path / "library")
    library.add(source(tmp_path, "experience.md", "Q: Redis Lua 原子性如何保证？"))
    session.config.library_path = str(library.directory)
    before = session.model_dump()
    def fail(*args, **kwargs):
        raise ProviderError("provider unavailable")
    monkeypatch.setattr("interview_forge.interview.engine.RepositoryAnswerer.answer", fail)
    with pytest.raises(ProviderError):
        advance(session)
    assert session.model_dump() == before


@pytest.mark.parametrize("target", ["question", "answer"])
def test_session_rejects_missing_material_references(session, target):
    advance(session)
    data = session.model_dump()
    key = "material_ids" if target == "question" else "reference_material_ids"
    data["transcript"][0][target][key] = ["missing"]
    with pytest.raises(ValueError, match="missing material snapshot"):
        InterviewSession.model_validate(data)


def test_retest_uses_reference_imported_after_question(session, tmp_path):
    advance(session)
    session, _ = begin_retest(session)
    library = MaterialLibrary(tmp_path / "library")
    document = library.add(source(tmp_path, "late-answer.md", "Q: Redis 库存扣减如何处理订单一致性？\nA: 通过 outbox 记录事务消息，并以订单 ID 幂等消费。"), kind="answer")
    session.config.library_path = str(library.directory)
    assert session.retests[0].reference is None
    session, _ = record_submission(session, "Lua 串行执行库存检查和扣减，订单 ID 用于防止重试重复扣减。")
    graded, attempt = grade_retest(session)
    assert attempt.reference.reference_material_ids == document.item_ids
    assert "outbox" in attempt.reference.direct_interview_answer
    assert graded.materials and not session.materials
    store = SessionStore(tmp_path / "export")
    export_reports(store, graded)
    usages = json.loads((store.directory / "material_usage.json").read_text())
    assert any(item["record_id"] == attempt.id for item in usages)


def test_cli_directory_import_and_errors_preserve_library(tmp_path, capsys):
    folder, library_path = tmp_path / "inputs", tmp_path / "library"
    folder.mkdir()
    source(folder, "first.md", "Q: Redis 为什么用 Lua？")
    source(folder, "second.txt", "Q: Redis Lua 执行出错会回滚吗？")
    source(folder, "ignored.bin", "unrelated")
    assert main(["library", "add", str(folder), "--kind", "interview", "--library", str(library_path), "--json"]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert len(imported) == 2
    assert main(["library", "search", "回滚", "--library", str(library_path), "--json"]) == 0
    assert "回滚" in json.loads(capsys.readouterr().out)[0]["question"]
    before = (library_path / "materials.json").read_bytes()
    assert main(["library", "add", str(folder / "missing.pdf"), "--kind", "interview", "--library", str(library_path)]) == 2
    assert main(["library", "search", "Redis", "--limit", "0", "--library", str(library_path)]) == 2
    assert (library_path / "materials.json").read_bytes() == before


def test_long_material_keeps_exact_followup_in_bounded_interviewer_context(tmp_path):
    library = MaterialLibrary(tmp_path / "library")
    library.add(source(tmp_path, "long.md", "Q: Redis 为什么 " + "长段背景" * 2000 + "？\n追问：Lua 脚本执行失败会回滚吗？"))
    materials = library.items()
    seeds = question_seeds(materials)
    assert seeds[0].question == ""
    assert seeds[0].followups == ["Lua 脚本执行失败会回滚吗？"]
    assert seeds[0].id == materials[0].id
    assert len(seeds[0].model_dump_json()) < 1000
    assert len(materials[0].question) > 8000


def test_mixed_subject_library_keeps_full_interview_on_its_claim(session, tmp_path):
    library = MaterialLibrary(tmp_path / "mixed")
    library.add(ROOT / "examples/materials/interview.md", kind="interview")
    library.add(ROOT / "examples/materials/reference_answer.md", kind="answer")
    library.add(ROOT / "examples/materials/redis-answer.docx", kind="answer")
    session.config.library_path = str(library.directory)
    session.jd += "；同时了解 RAG 检索系统"
    while advance(session):
        pass
    assert len(session.transcript) == 6
    sources = {item.id: item for item in session.materials}
    for turn in session.transcript:
        assert "RAG" not in turn.question.text
        assert "Recall@K" not in turn.question.text
        assert all("RAG" not in sources[mid].question for mid in turn.answer.reference_material_ids)
        assert not ("200 个" in turn.answer.direct_interview_answer and "1,000" in turn.answer.direct_interview_answer)
