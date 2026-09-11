from pathlib import Path
import hashlib
import subprocess
from interview_forge.claims.pipeline import extract_claims
from interview_forge.repository.scanner import scan_repository


def test_evidence_exact_linked_source(session):
    claims = {c.id: c for c in session.claims}
    for e in session.evidences:
        path = Path(session.repository_map.root) / e.file_path
        lines = path.read_text().splitlines()
        assert e.excerpt == "\n".join(lines[e.line_start-1:e.line_end])
        assert e.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        assert all(e.id in claims[c].evidence_ids for c in e.supports_claim)
    assert session.repository_map.sections["Core Modules"]


def test_scanner_ignores_secrets_symlinks_and_limits(tmp_path):
    repo = tmp_path/"repo"
    repo.mkdir()
    (repo/".env").write_text("API_KEY=secretstuff")
    (repo/"config.py").write_text('api_key = "sk-' + 'a'*25 + '"')
    (repo/"main.py").write_text("def redis_reserve():\n    return 1\n")
    outside = tmp_path/"outside.py"
    outside.write_text("private resume")
    (repo/"linked.py").symlink_to(outside)
    (repo/"huge.py").write_text("x"*130000)
    _, claims = extract_claims("使用 Redis Lua 扣减库存")
    mapping, evidences = scan_repository(repo, claims)
    assert mapping.files == ["main.py"]
    assert len(mapping.skipped) == 4
    assert evidences[0].file_path == "main.py"
    mapping, _ = scan_repository(repo, claims, max_bytes=1)
    assert not mapping.files
    assert any("budget" in x for x in mapping.skipped)


def test_gitignore_and_snapshot_exclusion(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    (tmp_path/".gitignore").write_text("ignored.py\n")
    (tmp_path/"ignored.py").write_text("redis secret")
    (tmp_path/"main.py").write_text("redis = 1")
    out = tmp_path/"output"
    out.mkdir()
    (out/"report.md").write_text("redis")
    _, claims = extract_claims("理解 Redis")
    mapping, _ = scan_repository(tmp_path, claims, exclude=out)
    assert mapping.files == ["main.py"]
