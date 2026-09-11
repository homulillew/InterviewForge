from pathlib import Path
import subprocess
import sys
import pytest
from interview_forge.cli.main import main
from interview_forge.storage.session import SessionStore
from interview_forge.quality import question_quality

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scenario", ["redis", "rag", "service"])
def test_golden_end_to_end(scenario, tmp_path):
    ex = ROOT/"examples"/scenario
    out = tmp_path/scenario
    assert main(["start", "--resume", str(ex/"resume.md"), "--repo", str(ex/"repo"),
        "--jd", str(ex/"jd.md"), "--session", str(out), "--max-turns", "6", "--run"]) == 0
    session = SessionStore(out).load()
    assert len(session.transcript) == 6
    assert all(question_quality(t.question.text)[0] for t in session.transcript)
    assert session.study_cards and session.study_plan and session.knowledge_graph.edges
    assert (out/"best_answer_cards.md").is_file()
    assert (out/"post_interview_review.md").is_file()
    assert (out/"next_round_plan.md").is_file()
    questions = " ".join(t.question.text for t in session.transcript)
    if scenario == "redis":
        assert "原子性" in questions and "乐观锁" in questions
    elif scenario == "rag":
        assert "first-stage" in questions and "衡量" in questions and "top_k" in questions
    else:
        assert all("我们项目实现了熔断" not in t.answer.direct_interview_answer for t in session.transcript)
        assert any("熔断" in x for t in session.transcript for x in t.answer.unsupported_claims)


def test_cli_errors_have_nonzero_exit(tmp_path):
    proc = subprocess.run([sys.executable, "-m", "interview_forge", "status", "--session", str(tmp_path)], capture_output=True, text=True)
    assert proc.returncode == 2
    assert "No session" in proc.stderr


def test_cli_schema_export(tmp_path):
    assert main(["schemas", "--output", str(tmp_path)]) == 0
    assert (tmp_path/"CapabilityClaim.schema.json").is_file()
    assert (tmp_path/"InterviewSession.schema.json").is_file()
