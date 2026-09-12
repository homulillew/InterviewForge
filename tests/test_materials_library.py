from pathlib import Path
import json

import pytest

from interview_forge.llm import ProviderError
from interview_forge.materials.extraction import MaterialExtraction, extract_materials
from interview_forge.materials.library import MaterialLibrary, search_items
from interview_forge.materials.models import SourceBlock


def write_material(tmp_path, name="面经.md", text=None):
    path = tmp_path / name
    path.write_text(text or "# 后端面经\n1. Redis 如何保证原子性？\n追问：超时重试如何做到幂等？\n2. MySQL 索引为什么失效？\n", encoding="utf-8")
    return path


def test_import_preserves_unicode_provenance_and_explicit_followups(tmp_path):
    source = write_material(tmp_path)
    library = MaterialLibrary(tmp_path / "库")
    document = library.add(source, tags=["后端", "后端", " 缓存 "], company="某公司", role="后端研发")
    items = library.items()
    assert len(items) == 2
    assert items[0].question == "Redis 如何保证原子性？"
    assert items[0].followups == ["超时重试如何做到幂等？"]
    assert items[0].source_file == str(source)
    assert "Redis 如何保证原子性？" in items[0].source_quote
    assert items[0].location.startswith("lines:")
    assert items[0].tags == ["后端", "缓存"]
    assert items[0].company == document.company == "某公司"
    assert document.item_ids == [item.id for item in items]
    assert MaterialLibrary(library.directory).get(document.id) == document
    source.unlink()
    assert library.documents()[0].blocks[0].text
    assert library.get_item(items[0].id).question == items[0].question


def test_dedup_is_content_and_kind_not_filename(tmp_path):
    library = MaterialLibrary(tmp_path / "library")
    source = write_material(tmp_path, text="Q: Redis 原子性如何实现？\nA: 使用 Lua 将读检查写放在一次执行中。\n")
    same = write_material(tmp_path, name="copy.txt", text=source.read_text())
    first = library.add(source)
    duplicate = library.add(same)
    answer = library.add(source, kind="answer")
    assert first.id == duplicate.id != answer.id
    assert len(library.documents()) == len(library.items()) == 2
    assert answer.kind == "answer"
    assert library.search("Redis", kind="answer")[0].answer.startswith("使用 Lua")


def test_reference_prose_keeps_heading_and_multiblock_answer(tmp_path):
    source = write_material(tmp_path, text="# Redis 重试方案\n\n首先写入业务幂等键。\n\n超时时检查已有操作状态，再决定是否重试。\n")
    library = MaterialLibrary(tmp_path / "library")
    library.add(source, kind="answer")
    item = library.items()[0]
    assert item.question == "Redis 重试方案"
    assert "首先写入业务幂等键。" in item.answer
    assert "再决定是否重试" in item.answer
    assert " → " in item.location


def test_ranking_prefers_specific_question_and_supports_chinese(tmp_path):
    source = write_material(tmp_path, text="Q: Redis 内存淘汰策略有哪些？\nA: 缓存容量不足时执行淘汰。\nQ: Redis 缓存穿透如何处理？\nA: 使用空值缓存和布隆过滤器。\nQ: MySQL 最左前缀是什么？\nA: 联合索引按列顺序匹配。\n")
    library = MaterialLibrary(tmp_path / "library")
    library.add(source)
    assert library.search("缓存穿透")[0].question == "Redis 缓存穿透如何处理？"
    assert "最左前缀" in library.search("联合索引 最左前缀")[0].question
    assert library.search("zxqnonexistent") == []
    assert len(library.search("Redis", limit=1)) == 1
    assert library.search("Redis", limit=0) == []
    assert search_items(library.items(), "缓存穿透")[0] == library.search("缓存穿透")[0]


def test_remove_document_cascades_items_and_keeps_other_imports(tmp_path):
    library = MaterialLibrary(tmp_path / "library")
    first = library.add(write_material(tmp_path))
    second = library.add(write_material(tmp_path, "回答.md", "Q: 幂等键如何设计？\nA: 使用业务操作 ID。"), kind="answer")
    assert library.remove(first.id) == first
    assert [document.id for document in library.documents()] == [second.id]
    assert all(item.document_id == second.id for item in library.items())
    with pytest.raises(ValueError, match="Unknown material document"):
        library.get(first.id)
    with pytest.raises(ValueError, match="Unknown material document"):
        library.remove(first.id)


def test_semantic_extraction_uses_untrusted_source_and_validates_quotes(tmp_path):
    source = write_material(tmp_path, text="Q: Redis 为什么使用 Lua？\nA: 多个命令在一个脚本中执行。\n追问：脚本报错会回滚吗？")
    class Client:
        def structured_generate(self, system, payload, schema):
            assert "untrusted" in system and "external_reference_only" == payload["source_role"]
            assert schema is MaterialExtraction
            return schema(items=[{"block_indices": [0], "source_quote": "Redis 为什么使用 Lua？",
                "question": "Redis 中使用 Lua 的原因是什么？", "answer": "多个命令在一个脚本中执行。",
                "followups": ["脚本报错会回滚吗？"], "topics": ["Redis"]}])
    library = MaterialLibrary(tmp_path / "library")
    document = library.add(source, client=Client())
    assert document.extraction_method == "model"
    assert library.items()[0].question == "Redis 中使用 Lua 的原因是什么？"
    assert library.items()[0].followups == ["脚本报错会回滚吗？"]


@pytest.mark.parametrize("changes", [
    {"source_quote": "没有出现在文档中的话"},
    {"answer": "生产环境压测达到 100 万 QPS。"},
    {"block_indices": [99]},
    {"followups": ["这是模型虚构的追问？"]},
])
def test_unanchored_model_output_does_not_commit(tmp_path, changes):
    library = MaterialLibrary(tmp_path / "library")
    library.add(write_material(tmp_path))
    before = library.path.read_bytes()
    source = write_material(tmp_path, "other.md", "Q: RAG 如何重排？\nA: 用交叉编码器评分。")
    class Client:
        def structured_generate(self, system, payload, schema):
            item = {"block_indices": [0], "source_quote": "RAG 如何重排？", "question": "RAG 如何重排？", "answer": "用交叉编码器评分。"}
            item.update(changes)
            return schema(items=[item])
    with pytest.raises(ValueError):
        library.add(source, client=Client())
    assert library.path.read_bytes() == before


def test_provider_failure_has_no_partial_import(tmp_path):
    library = MaterialLibrary(tmp_path / "library")
    source = write_material(tmp_path)
    class Broken:
        def structured_generate(self, *args):
            raise ProviderError("offline")
    with pytest.raises(ProviderError):
        library.add(source, client=Broken())
    assert library.documents() == library.items() == []
    assert not library.path.exists()


def test_atomic_write_failure_retains_previous_snapshot(tmp_path, monkeypatch):
    library = MaterialLibrary(tmp_path / "library")
    library.add(write_material(tmp_path))
    before = library.path.read_bytes()
    second = write_material(tmp_path, "second.md", "Q: RAG 如何评测？")
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr("interview_forge.materials.library.os.replace", fail)
    with pytest.raises(OSError, match="disk full"):
        library.add(second)
    assert library.path.read_bytes() == before
    assert not list(library.directory.glob(".materials-*"))


def test_lock_prevents_competing_writer_without_partial_save(tmp_path):
    library = MaterialLibrary(tmp_path / "library")
    source = write_material(tmp_path)
    with library.lock():
        with pytest.raises(ValueError, match="busy"):
            MaterialLibrary(library.directory).add(source)
    assert library.documents() == []
    assert library.add(source).item_ids


def test_refreshes_snapshot_after_extraction_avoiding_lost_updates(tmp_path, monkeypatch):
    import interview_forge.materials.library as module
    library = MaterialLibrary(tmp_path / "library")
    first = write_material(tmp_path)
    second = write_material(tmp_path, "second.md", "Q: RAG 如何评测？")
    original = module.extract_materials
    pending = True
    def extract(*args, **kwargs):
        nonlocal pending
        if pending:
            pending = False
            MaterialLibrary(library.directory).add(second)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "extract_materials", extract)
    library.add(first)
    assert len(library.documents()) == 2
    assert len(library.items()) == 3


def test_rejects_symlink_library_and_corrupt_snapshot(tmp_path):
    library = MaterialLibrary(tmp_path / "library")
    library.directory.mkdir()
    other = tmp_path / "other.json"
    other.write_text("{}")
    library.path.symlink_to(other)
    with pytest.raises(ValueError, match="symlink"):
        library.documents()
    library.path.unlink()
    library.path.write_text("bad json")
    with pytest.raises(ValueError, match="invalid"):
        library.documents()


def test_offline_keeps_numbered_answer_steps_and_code():
    blocks = [SourceBlock(location="paragraph:1", text="Q: 如何保证幂等？\nA: 按操作 ID 去重。\n1. 生成稳定键。\n2. 保存操作结果。\n```python\nif key in cache:\n    return cache[key]\n```")]
    items = extract_materials(blocks, document_id="doc_1", kind="answer", source_file="回答.md")
    assert len(items) == 1
    assert "2. 保存操作结果。" in items[0].answer
    assert "return cache[key]" in items[0].answer


def test_empty_extraction_is_actionable_and_does_not_create_document(tmp_path):
    source = write_material(tmp_path, text="今天心情很好，先记一份面试随笔。")
    library = MaterialLibrary(tmp_path / "library")
    with pytest.raises(ValueError, match="No interview questions"):
        library.add(source)
    assert library.documents() == []


def test_semantic_large_documents_are_batched_without_silent_truncation():
    blocks = [SourceBlock(location=f"page:{index}", text=f"第 {index} 页的问题？\n" + "说明文本" * 5000) for index in range(1, 5)]
    seen = []
    class Client:
        def structured_generate(self, system, payload, schema):
            seen.extend(block["text"] for block in payload["blocks"])
            block = payload["blocks"][0]
            return schema(items=[{"block_indices": [0], "source_quote": block["text"][:10], "question": block["text"][:10]}])
    result = extract_materials(blocks, document_id="doc_big", kind="interview", source_file="large.pdf", client=Client())
    assert "".join(seen) == "".join(block.text for block in blocks)
    assert len(result) >= 2
    assert any("chars:" in item.location for item in result)


def test_packaged_prompt_matches_repository_mirror():
    root = Path(__file__).resolve().parents[1]
    assert (root / "prompts/material_extraction.md").read_bytes() == (root / "interview_forge/prompts/material_extraction.md").read_bytes()


@pytest.mark.parametrize("field,value", [
    ("source_quote", "文档中没有的内容"),
    ("location", "page:999"),
    ("source_file", "another-document.md"),
    ("kind", "answer"),
])
def test_persisted_reference_tampering_is_rejected(tmp_path, field, value):
    library = MaterialLibrary(tmp_path / "library")
    library.add(write_material(tmp_path))
    data = json.loads(library.path.read_text())
    data["items"][0][field] = value
    library.path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        library.items()


def test_symlink_and_oversized_sources_are_rejected_before_hashing(tmp_path, monkeypatch):
    from interview_forge.materials.reader import MAX_FILE_BYTES
    library = MaterialLibrary(tmp_path / "library")
    source = write_material(tmp_path)
    symlink = tmp_path / "symlink.md"
    symlink.symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        library.add(symlink)
    large = tmp_path / "large.txt"
    with large.open("wb") as handle:
        handle.truncate(MAX_FILE_BYTES + 1)
    def unexpected(*args):
        raise AssertionError("should not hash a rejected file")
    monkeypatch.setattr("interview_forge.materials.library._file_hash", unexpected)
    with pytest.raises(ValueError, match="file limit"):
        library.add(large)


def test_changed_source_during_read_is_not_committed(tmp_path, monkeypatch):
    import interview_forge.materials.reader as reader
    original = reader.read_document
    source = write_material(tmp_path)
    def mutate(path, **kwargs):
        read = original(path, **kwargs)
        path.write_text("Q: 新问题？")
        return read
    monkeypatch.setattr(reader, "read_document", mutate)
    library = MaterialLibrary(tmp_path / "library")
    with pytest.raises(ValueError, match="changed during import"):
        library.add(source)
    assert library.items() == []


def test_model_chunk_provenance_roundtrips_in_library(tmp_path):
    source = write_material(tmp_path, text="Q: 为什么 Redis 需要 Lua？\n" + "源文档" * 12000)
    class Client:
        def structured_generate(self, system, payload, schema):
            return schema(items=[{"block_indices": [index], "source_quote": block["text"][:20],
                "question": f"第 {block['location']} 段问题？"} for index, block in enumerate(payload["blocks"])])
    library = MaterialLibrary(tmp_path / "library")
    document = library.add(source, client=Client())
    assert len(document.item_ids) == 3
    assert all("chars:" in item.location for item in library.items())


def test_explicit_interview_answer_does_not_turn_steps_into_questions():
    blocks = [SourceBlock(location="lines:1-4", text="Q: 如何保证幂等？\nA: 按操作 ID 去重。\n1. 生成稳定键。\n2. 保存操作结果。")]
    items = extract_materials(blocks, document_id="doc_1", kind="interview", source_file="面经.md")
    assert len(items) == 1
    assert "2. 保存操作结果。" in items[0].answer


def test_reimport_versions_changed_followups_and_preserves_session_history(session, tmp_path):
    from interview_forge.interview.engine import advance
    from interview_forge.storage.reports import export_reports
    from interview_forge.storage.session import SessionStore

    question = "Redis Lua 为什么能把库存检查和扣减做成原子操作？"
    followup = "Redis 客户端在扣减成功后超时，重试如何避免重复扣减？"
    source = write_material(tmp_path, text=f"Q: {question}\n追问：{followup}\n")
    library = MaterialLibrary(tmp_path / "library")
    class Client:
        def __init__(self, followups):
            self.followups = followups
        def structured_generate(self, system, payload, schema):
            return schema(items=[{"block_indices": [0], "source_quote": question,
                "question": question, "followups": self.followups, "topics": ["Redis"]}])

    original_document = library.add(source, client=Client([]))
    original_item = library.items()[0]
    session.config.library_path = str(library.directory)
    assert advance(session)
    first_turn = session.transcript[0].model_copy(deep=True)
    assert not first_turn.question.material_ids
    assert first_turn.question.material_question is None

    library.remove(original_document.id)
    replacement_document = library.add(source, client=Client([followup]))
    replacement_item = library.items()[0]
    assert replacement_document.id == original_document.id
    assert replacement_item.id != original_item.id
    assert replacement_item.followups == [followup]
    assert library.add(source, client=Client([followup])).item_ids == replacement_document.item_ids
    assert advance(session)
    assert session.transcript[0] == first_turn
    assert not session.transcript[1].question.material_ids
    assert not session.materials
    store = SessionStore(tmp_path / "session")
    store.save(session)
    assert store.load() == session
    export_reports(store, session)
    assert json.loads((store.directory / "material_usage.json").read_text()) == []


def test_legacy_material_ids_are_loaded_and_deduplicated_without_rewriting(tmp_path):
    library = MaterialLibrary(tmp_path / "library")
    source = write_material(tmp_path, text="Q: Redis Lua 原子性如何保证？")
    document = library.add(source)
    data = json.loads(library.path.read_text())
    legacy_id = "item_0123456789abcdef0123"
    data["items"][0]["id"] = legacy_id
    data["documents"][0]["item_ids"] = [legacy_id]
    library.path.write_text(json.dumps(data, ensure_ascii=False))
    before = library.path.read_bytes()
    assert library.items()[0].id == legacy_id
    assert library.add(source).item_ids == [legacy_id]
    assert library.get(document.id).item_ids == [legacy_id]
    assert library.path.read_bytes() == before


@pytest.mark.parametrize("change", [
    {"title": "原子操作"},
    {"topics": ["并发与一致性"]},
    {"source_quote": "Q: Redis 原子性如何实现？"},
    {"tags": ["复习"]},
    {"company": "示例公司"},
    {"role": "高级后端"},
    {"source_file": "另一个来源.md"},
])
def test_material_identity_versions_extraction_and_provenance(change):
    question = "Redis 原子性如何实现？"
    blocks = [SourceBlock(location="lines:1-2", text=f"Q: {question}\nA: 执行 Lua 脚本。")]
    def extract(overrides):
        draft = {"block_indices": [0], "source_quote": question, "question": question,
                 "answer": "执行 Lua 脚本。", "title": question, "topics": ["Redis"]}
        metadata = {"document_id": "doc_stable", "kind": "interview", "source_file": "来源.md"}
        for key, value in overrides.items():
            (draft if key in draft else metadata)[key] = value
        class Client:
            def structured_generate(self, system, payload, schema):
                return schema(items=[draft])
        return extract_materials(blocks, client=Client(), **metadata)[0]
    original = extract({})
    assert extract({}).id == original.id
    assert extract(change).id != original.id
