"""Atomic, immutable compiled revisions in a private local SQLite/FTS5 database."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote
from uuid import uuid4
from .models import CompiledCorpus

TABLES = ("cases", "questions", "chains", "transitions", "patterns", "style_profiles", "duplicate_groups")


class CorpusStore:
    def __init__(self, path):
        self.path = Path(path).expanduser().absolute()
        if self.path.is_symlink():
            raise ValueError("Corpus database cannot be a symlink")

    @contextmanager
    def connect(self, write=False):
        if self.path.is_symlink():
            raise ValueError("Corpus database cannot be a symlink")
        if not write and not self.path.is_file():
            raise ValueError("Corpus database does not exist; use corpus ingest")
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(
            str(self.path) if write else "file:" + quote(str(self.path)) + "?mode=ro",
            uri=not write,
            timeout=1,
        )
        try:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported corpus database schema version")
            if write:
                if (
                    version == 0
                    and db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone()
                ):
                    raise ValueError("Refusing to initialize an unrelated SQLite database")
                db.execute("BEGIN IMMEDIATE")
                db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS revisions (id TEXT PRIMARY KEY,payload TEXT NOT NULL)")
                for table in TABLES:
                    db.execute(
                        f"CREATE TABLE IF NOT EXISTS {table} (revision TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(revision,id))"
                    )
                db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS question_fts USING fts5(revision UNINDEXED,id UNINDEXED,text)"
                )
                db.execute("INSERT OR IGNORE INTO metadata VALUES (?,?)", ("database_id", str(uuid4())))
                db.execute("PRAGMA user_version=1")
            elif version != 1:
                raise ValueError("Not an initialized corpus database; use corpus ingest")
            yield db
            if write:
                db.commit()
        except sqlite3.Error as exc:
            db.rollback()
            raise ValueError(f"Corpus database operation failed: {exc}") from exc
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def load(self, revision=None):
        with self.connect() as db:
            if revision is None:
                row = db.execute("SELECT value FROM metadata WHERE key=?", ("current_revision",)).fetchone()
                revision = row[0] if row else None
            row = db.execute("SELECT payload FROM revisions WHERE id=?", (revision,)).fetchone()
            if not row:
                raise ValueError(
                    "Pinned corpus revision is unavailable; restore its database or start a new session"
                )
            if hashlib.sha256(("compiler-v1:" + row[0]).encode()).hexdigest() != revision:
                raise ValueError("Pinned corpus revision payload failed its integrity hash")
            return CompiledCorpus.model_validate_json(row[0])

    def current(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key=?", ("current_revision",)).fetchone()
            if not row:
                raise ValueError("Corpus has no compiled revision; use corpus ingest")
            return row[0]

    def fingerprint(self):
        with self.connect() as db:
            return db.execute("SELECT value FROM metadata WHERE key=?", ("database_id",)).fetchone()[0]

    def commit(self, corpus, expected_revision=None):
        corpus = CompiledCorpus.model_validate(corpus.model_dump())
        payload = corpus.model_dump_json()
        revision = hashlib.sha256(("compiler-v1:" + payload).encode()).hexdigest()
        with self.connect(write=True) as db:
            current = db.execute("SELECT value FROM metadata WHERE key=?", ("current_revision",)).fetchone()
            if (current[0] if current else None) != expected_revision:
                raise ValueError("Corpus changed during compilation; retry ingest")
            if db.execute("SELECT 1 FROM revisions WHERE id=?", (revision,)).fetchone() is None:
                db.execute("INSERT INTO revisions VALUES (?,?)", (revision, payload))
                rows = {
                    "cases": corpus.cases,
                    "questions": [q for c in corpus.cases for q in c.questions],
                    "chains": [ch for c in corpus.cases for ch in c.chains],
                    "transitions": corpus.transitions,
                    "patterns": corpus.patterns,
                    "style_profiles": corpus.style_profiles,
                }
                for table, items in rows.items():
                    db.executemany(
                        f"INSERT INTO {table} VALUES (?,?,?)",
                        [(revision, x.id, x.model_dump_json()) for x in items],
                    )
                groups = {}
                for c in corpus.cases:
                    groups.setdefault(c.duplicate_group, []).append(c.id)
                db.executemany(
                    "INSERT INTO duplicate_groups VALUES (?,?,?)",
                    [(revision, key, json.dumps(value)) for key, value in groups.items()],
                )
                db.executemany(
                    "INSERT INTO question_fts VALUES (?,?,?)",
                    [
                        (revision, q.id, q.text + " " + " ".join(q.topic))
                        for c in corpus.cases
                        for q in c.questions
                    ],
                )
            db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", ("current_revision", revision))
        return revision

    def search_question_ids(self, query, revision, limit=50):
        from interview_forge.semantics import tokens

        words = sorted(tokens(query))[:40]
        if not words:
            return []
        expression = " OR ".join('"' + word.replace('"', '""') + '"' for word in words)
        with self.connect() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT id FROM question_fts WHERE question_fts MATCH ? AND revision=? ORDER BY rank LIMIT ?",
                    (expression, revision, limit),
                )
            ]
