"""A persistent, atomic material library shared by interview sessions."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import math
import os
from pathlib import Path
import re
import tempfile

from pydantic import ValidationError

from .extraction import TOPICS, compact, extract_materials
from .models import MaterialDocument, MaterialItem, MaterialKind, MaterialState


STOP = {"the", "and", "how", "what", "why", "with", "from", "your", "about", "this", "that",
        "如何", "怎么", "什么", "为什么", "介绍", "一下", "请问", "项目", "我们", "你们", "可以",
        "为何", "问题", "解决", "设计", "系统", "场景", "方案", "通过", "保证", "具体", "使用"}


def _domains(text):
    """Distinguish explicit subject areas from shared words like latency or testing."""
    patterns = {
        "backend": r"redis|\blua\b|mysql|postgres|\bsql\b|数据库|库存|订单|分布式锁",
        "retrieval": r"\brag\b|embedding|rerank|召回|重排|向量检索|检索增强|\bbm25\b|\bndcg\b|recall@",
        "agent": r"\bagent\b|智能体|function.calling|工具调用",
        "algorithm": r"leetcode|动态规划|二叉树|链表|排序算法",
    }
    return {domain for domain, pattern in patterns.items() if re.search(pattern, text, re.I)}


def _source_text(document: MaterialDocument, location: str) -> str:
    endpoints = location.split(" → ")
    if len(endpoints) not in {1, 2}:
        raise ValueError("Material library item has an invalid source location")
    positions = []
    for endpoint in endpoints:
        match = re.fullmatch(r"(.+)/chars:(\d+)-(\d+)", endpoint)
        base = match.group(1) if match else endpoint
        index = next((index for index, block in enumerate(document.blocks) if block.location == base), None)
        if index is None:
            raise ValueError("Material library item cites an unknown source location")
        length = len(document.blocks[index].text)
        start, end = (int(match.group(2)) - 1, int(match.group(3))) if match else (0, length)
        if start < 0 or end <= start or end > length:
            raise ValueError("Material library item cites an invalid source character range")
        positions.append((index, start, end))
    first, last = positions[0], positions[-1]
    if first[0] > last[0] or (first[0] == last[0] and first[1] >= last[2]):
        raise ValueError("Material library item cites a reversed source range")
    if first[0] == last[0]:
        return document.blocks[first[0]].text[first[1]:last[2]]
    texts = [block.text for block in document.blocks[first[0]:last[0] + 1]]
    texts[0] = texts[0][first[1]:]
    texts[-1] = texts[-1][:last[2]]
    return "\n".join(texts)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_state(state: MaterialState):
    if state.schema_version != 1:
        raise ValueError(f"Unsupported material library schema version: {state.schema_version}")
    documents = {document.id: document for document in state.documents}
    items = {item.id: item for item in state.items}
    if len(documents) != len(state.documents) or len(items) != len(state.items):
        raise ValueError("Material library has duplicate record IDs")
    source_texts = {}
    for item in state.items:
        document = documents.get(item.document_id)
        if document is None or item.id not in document.item_ids or item.kind != document.kind:
            raise ValueError("Material library contains an invalid document reference")
        if item.source_file != document.source_file:
            raise ValueError("Material library item source file does not match its document")
        quote = compact(item.source_quote)
        source_key = (document.id, item.location)
        if source_key not in source_texts:
            source_texts[source_key] = compact(_source_text(document, item.location))
        if not quote or quote not in source_texts[source_key]:
            raise ValueError("Material library source quote does not match its source location")
    for document in state.documents:
        if len(document.item_ids) != len(set(document.item_ids)) or any(
            item_id not in items or items[item_id].document_id != document.id for item_id in document.item_ids
        ):
            raise ValueError("Material library contains an invalid item reference")


def _terms(text: str) -> set[str]:
    text = text.lower()
    tokens = set(re.findall(r"[a-z0-9][a-z0-9_+#.-]*", text))
    for phrase in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(phrase) == 1:
            continue
        tokens.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    for topic, aliases in TOPICS.items():
        if any(alias in text for alias in aliases):
            tokens.add("topic:" + topic)
    return tokens - STOP


def search_items(items: list[MaterialItem], query: str, kind: MaterialKind | None = None,
                 limit: int = 5, focus: str | None = None) -> list[MaterialItem]:
    """Rank a library or a session snapshot without promoting references to evidence."""
    candidates = [item for item in items if kind is None or item.kind == kind]
    if limit <= 0:
        return []
    if not query.strip():
        return candidates[:limit]
    query_terms = _terms(query)
    query_domains = _domains(focus if focus is not None else query)
    indexed = []
    for item in candidates:
        item_domains = _domains(item.question + " " + item.title)
        # Shared evaluation/performance terms cannot turn a RAG question into a Redis
        # interview. Unlabelled engineering questions and explicit cross-topic items
        # remain eligible; a query naming both domains can retrieve both.
        if query_domains and item_domains and query_domains.isdisjoint(item_domains):
            continue
        question = _terms(item.question + " " + item.title)
        labels = _terms(" ".join(item.topics + item.tags + [item.company, item.role]))
        detail = _terms(item.answer + " " + " ".join(item.followups))
        indexed.append((item, question, labels, detail))
    frequency = Counter(term for _, question, labels, detail in indexed for term in question | labels | detail)
    ranked = []
    for item, question, labels, detail in indexed:
        def score(tokens, boost):
            return sum(boost * (1 + math.log((len(candidates) + 1) / (frequency[term] + 1)))
                       for term in query_terms & tokens)
        relevance = score(question, 4) + score(labels, 2) + score(detail, 1)
        if query.casefold() in (item.question + " " + item.title).casefold():
            relevance += 8
        if relevance > 0:
            ranked.append((relevance, item))
    ranked.sort(key=lambda entry: (-entry[0], entry[1].id))
    return [item for _, item in ranked[:limit]]


class MaterialLibrary:
    def __init__(self, directory: Path):
        self.directory = Path(directory).expanduser().resolve()
        self.path = self.directory / "materials.json"

    @contextmanager
    def lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        lockpath = self.directory / ".materials.lock"
        if lockpath.is_symlink():
            raise ValueError("Refusing a symlink material library lock")
        fd = os.open(lockpath, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Material library is busy in another process; retry the operation") from None
            try:
                yield self
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _load(self) -> MaterialState:
        if self.path.is_symlink():
            raise ValueError("Refusing a symlink material library")
        if not self.path.exists():
            return MaterialState()
        try:
            state = MaterialState.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (ValidationError, UnicodeError) as exc:
            raise ValueError("Material library is invalid; restore materials.json from a backup") from exc
        _validate_state(state)
        return state

    def _save(self, state: MaterialState):
        if self.path.is_symlink():
            raise ValueError("Refusing to overwrite a symlink material library")
        state = MaterialState.model_validate(state.model_dump())
        _validate_state(state)
        content = state.model_dump_json(indent=2)
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".materials-", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def add(self, path: Path, kind: MaterialKind = "interview", client=None, tags=None,
            company: str = "", role: str = "", ocr_language: str = "chi_sim+eng",
            ocr: str = "auto") -> MaterialDocument:
        from .reader import MAX_FILE_BYTES, read_document

        if kind not in {"interview", "answer"}:
            raise ValueError("Material kind must be interview or answer")
        source = Path(path).expanduser()
        if source.is_symlink():
            raise ValueError("Refusing to import a symlink material file")
        source = source.resolve()
        if not source.is_file():
            raise ValueError(f"Material file does not exist: {source}")
        if source.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"Material document exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MiB file limit")
        source_hash = _file_hash(source)
        document_id = "doc_" + hashlib.sha256((kind + ":" + source_hash).encode()).hexdigest()[:20]
        existing = next((document for document in self._load().documents if document.id == document_id), None)
        if existing is not None:
            return existing
        # Reading and model work complete before the one authoritative snapshot is changed.
        read = read_document(source, ocr_language=ocr_language, client=client, ocr=ocr)
        if _file_hash(source) != source_hash:
            raise ValueError("Material source changed during import; retry with a stable file")
        blocks = [block for block in read.blocks if block.text.strip()]
        if not blocks:
            raise ValueError("Material document contains no readable text")
        normalized_tags = list(dict.fromkeys(tag.strip() for tag in (tags or []) if tag.strip()))
        extracted = extract_materials(blocks, document_id=document_id, kind=kind, source_file=str(source),
            client=client, tags=normalized_tags, company=company, role=role)
        document = MaterialDocument(id=document_id, kind=kind, filename=source.name, source_file=str(source),
            source_hash=source_hash, imported_at=datetime.now(timezone.utc).isoformat(),
            tags=normalized_tags, company=company, role=role, blocks=blocks, warnings=read.warnings,
            item_ids=[item.id for item in extracted], extraction_method="model" if client else "offline")
        with self.lock():
            state = self._load()
            # Another writer may have completed the same import while extraction was in progress.
            existing = next((record for record in state.documents if record.id == document_id), None)
            if existing is not None:
                return existing
            state.documents.append(document)
            state.items.extend(extracted)
            self._save(state)
        return document

    def documents(self) -> list[MaterialDocument]:
        return self._load().documents

    def items(self) -> list[MaterialItem]:
        return self._load().items

    def get(self, document_id: str) -> MaterialDocument:
        document = next((record for record in self._load().documents if record.id == document_id), None)
        if document is None:
            raise ValueError(f"Unknown material document: {document_id}")
        return document

    def get_item(self, item_id: str) -> MaterialItem:
        item = next((record for record in self._load().items if record.id == item_id), None)
        if item is None:
            raise ValueError(f"Unknown material item: {item_id}")
        return item

    def search(self, query: str, kind: MaterialKind | None = None, limit: int = 5,
               focus: str | None = None) -> list[MaterialItem]:
        return search_items(self.items(), query, kind, limit, focus)

    def remove(self, document_id: str) -> MaterialDocument:
        with self.lock():
            state = self._load()
            document = next((record for record in state.documents if record.id == document_id), None)
            if document is None:
                raise ValueError(f"Unknown material document: {document_id}")
            state.documents = [record for record in state.documents if record.id != document_id]
            state.items = [item for item in state.items if item.document_id != document_id]
            self._save(state)
        return document
