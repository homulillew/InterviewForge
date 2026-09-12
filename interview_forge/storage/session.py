"""One authoritative atomic snapshot; denormalized exports are disposable views."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile

from interview_forge.schemas.models import InterviewSession


def atomic_write(path: Path, content: str):
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlink artifact")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".forge-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SessionStore:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.path = self.directory / "interview_state.json"

    @contextmanager
    def lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        lockpath = self.directory / ".interviewforge.lock"
        if lockpath.is_symlink():
            raise ValueError("Unsafe lock path")
        with lockpath.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Session busy in another process") from None
            try:
                yield self
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def load(self):
        if not self.path.is_file():
            raise ValueError("No session here; use start")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema_version") == "1.0":
            raise ValueError("Schema 1.0 requires explicit migration: interview-forge migrate-session --session " + str(self.directory))
        return InterviewSession.model_validate(data)

    def migrate(self):
        from interview_forge.storage.migrate import migrate_v1
        raw = self.path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if data.get("schema_version") == "2.0":
            return InterviewSession.model_validate(data)
        migrated = migrate_v1(data)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        atomic_write(self.directory / "archives" / f"schema-1.0-{stamp}.json", raw)
        self.save(migrated)
        return migrated

    def save(self, session):
        validated = InterviewSession.model_validate(session.model_dump())
        atomic_write(self.path, validated.model_dump_json(indent=2))

    def archive_reset(self, session):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        atomic_write(self.directory / "archives" / f"{stamp}.json", session.model_dump_json(indent=2))
        data = session.model_dump()
        data.update(status="ready", transcript=[], knowledge_graph={"nodes": [], "edges": []},
                    study_cards=[], study_plan=[], retests=[], review=None, stop_reason=None)
        data.update(corpus_matches=[], corpus_transitions=[])
        for surface in data["attack_surfaces"]:
            surface.update(coverage="untouched", question_count=0, last_turn_id=None, corpus_support=0)
        for c in data["claims"]:
            c.update(answerability="unknown", mastery={"status": "unknown", "evidence": [], "assessed_by": "none"})
        result = InterviewSession.model_validate(data)
        self.save(result)
        return result

    def export_json(self, name, value):
        atomic_write(self.directory / name, json.dumps(value, ensure_ascii=False, indent=2))
