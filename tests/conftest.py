from pathlib import Path
import pytest
from interview_forge.interview.engine import start_session
from interview_forge.schemas.models import SessionConfig

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def session(tmp_path):
    return start_session((ROOT/"examples/redis/resume.md").read_text(), ROOT/"examples/redis/repo",
        "Redis backend", SessionConfig(max_turns=6), tmp_path/"session")
