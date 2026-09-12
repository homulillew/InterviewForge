"""Preparation imports persist, while runtime sessions pin only compiled corpus references."""
import json
from pathlib import Path
import pytest
from interview_forge.cli.main import main
from interview_forge.interview.engine import advance, start_session
from interview_forge.interview.retest import begin_retest, grade_retest, record_submission
from interview_forge.materials.library import MaterialLibrary
from interview_forge.corpus.ingest import ingest
from interview_forge.corpus.storage import CorpusStore
from interview_forge.schemas.models import SessionConfig
from interview_forge.storage.session import SessionStore

ROOT = Path(__file__).resolve().parents[1]


def source(tmp_path, name, text):
    path = tmp_path/name
    path.write_text(text, encoding='utf-8')
    return path


def test_cli_pinned_import_history_and_explanation(tmp_path, capsys):
    corpus, output = tmp_path/'corpus.sqlite3', tmp_path/'session'
    example = ROOT/'examples/redis'
    first = source(tmp_path, 'first.md', 'Q: Redis Lua 如何实现库存扣减？\nA: 因为 Redis 快。\nQ: 快在哪里，如何测量？')
    assert main(['corpus','ingest',str(first),'--corpus',str(corpus)]) == 0
    assert main(['start','--resume',str(example/'resume.md'),'--repo',str(example/'repo'),
        '--session',str(output),'--corpus',str(corpus),'--style','corpus','--max-turns','4']) == 0
    pin = SessionStore(output).load().corpus_pin
    assert main(['run','--session',str(output),'--turns','1']) == 0
    old_turn = SessionStore(output).load().transcript[0]
    new = source(tmp_path, 'later.txt', 'Q: Transformer 为什么需要除以 sqrt(d_k)？')
    ingest([new],corpus)
    first.unlink()
    assert CorpusStore(corpus).current() != pin.revision
    assert main(['run','--session',str(output),'--turns','1']) == 0
    updated = SessionStore(output).load()
    assert updated.corpus_pin == pin and updated.transcript[0] == old_turn
    assert not updated.materials
    assert all(not t.answer.reference_material_ids for t in updated.transcript)
    assert 'Transformer' not in updated.transcript[-1].question.text
    capsys.readouterr()
    assert main(['explain-question','--session',str(output),'--question','q1']) == 0
    explained = json.loads(capsys.readouterr().out)
    assert explained['question']['provenance']['atomic_claim_id']
    assert explained['corpus_pin']['revision'] == pin.revision
    assert (output/'interview_style_trace.md').is_file()


def test_preparation_library_never_becomes_defender_runtime(session, tmp_path):
    library = MaterialLibrary(tmp_path/'library')
    library.add(source(tmp_path,'reference.md','Q: Redis 如何实现幂等？\nA: PRIVATE_CORPUS_SENTINEL'),kind='answer')
    session.config.library_path = str(library.directory)
    advance(session)
    session, _ = begin_retest(session)
    session, _ = record_submission(session,'独立回答')
    graded, attempt = grade_retest(session)
    assert not attempt.reference.reference_material_ids
    assert 'PRIVATE_CORPUS_SENTINEL' not in attempt.reference.model_dump_json()
    assert not graded.materials


def test_imported_material_is_never_scanned_as_repository_evidence(tmp_path):
    repo = tmp_path/'repo'
    repo.mkdir()
    (repo/'stock.py').write_text('def reserve(redis, key):\n    return redis.decr(key)\n')
    library_path = repo/'custom-references'
    MaterialLibrary(library_path).add(source(tmp_path,'reference.md','Q: Redis 性能如何？\nA: 实测吞吐 123456 QPS。'),kind='answer')
    session = start_session('使用 Redis 实现库存扣减。',repo,'',SessionConfig(library_path=str(library_path)),tmp_path/'state')
    assert all('custom-references' not in e.file_path and '123456' not in e.excerpt for e in session.evidences)


def test_missing_or_replaced_pinned_database_fails_without_mutation(tmp_path):
    db = tmp_path/'corpus.sqlite3'
    post = source(tmp_path,'post.md','Q: Redis 如何实现原子操作？')
    ingest([post],db)
    s = start_session('使用 Redis Lua 实现库存扣减',ROOT/'examples/redis/repo','',SessionConfig(corpus_path=str(db)),tmp_path/'state')
    before = s.model_dump()
    db.unlink()
    ingest([post],db)
    with pytest.raises(ValueError,match='fingerprint'):
        advance(s)
    assert s.model_dump() == before
