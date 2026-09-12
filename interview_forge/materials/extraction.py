"""Extract source-bound questions and answers, with a deterministic offline mode."""
from __future__ import annotations

import hashlib
import json
import re

from pydantic import BaseModel, ConfigDict, Field

from interview_forge.llm import prompt
from .models import MaterialItem, MaterialKind, SourceBlock


TOPICS = {
    "Redis": ("redis", "缓存", "lua", "哨兵", "持久化"),
    "RAG": ("rag", "检索增强", "embedding", "向量", "召回", "重排"),
    "数据库": ("mysql", "postgres", "数据库", "索引", "事务", "sql"),
    "并发与一致性": ("并发", "一致性", "幂等", "分布式锁", "atomic", "concurrent"),
    "性能与评测": ("性能", "压测", "评测", "延迟", "吞吐", "p99", "benchmark"),
    "系统设计": ("系统设计", "架构", "微服务", "熔断", "限流", "高可用"),
    "Agent": ("agent", "智能体", "工具调用", "function calling"),
    "算法": ("算法", "动态规划", "二叉树", "链表", "leetcode"),
}

QUESTION_LABEL = re.compile(r"^(?:Q(?:uestion)?\s*\d*|问题\s*\d*|面试题\s*\d*|问)\s*[:：.、)]\s*(.+)$", re.I)
ANSWER_LABEL = re.compile(r"^(?:A(?:nswer)?\s*\d*|答案|回答|答)\s*[:：.、)]\s*(.*)$", re.I)
FOLLOWUP_LABEL = re.compile(r"^(?:追问\s*\d*|follow[- ]?up\s*\d*)\s*[:：.、)]\s*(.+)$", re.I)
NUMBERED = re.compile(r"^(?:\d{1,3}[.)、．]|[一二三四五六七八九十]+[、.])\s*(.+)$")
QUESTION_WORDS = re.compile(r"^(?:如何|为什么|为何|怎么|怎样|什么是|是否|有没有|介绍一下|谈谈|说说|解释|请介绍|请说明|请设计|how\b|why\b|what\b|explain\b|describe\b)", re.I)


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


def topic_labels(text: str) -> list[str]:
    text = text.lower()
    return [name for name, aliases in TOPICS.items() if any(alias in text for alias in aliases)]


class ExtractedMaterial(BaseModel):
    """Model output cites indices in the supplied block batch, never arbitrary files."""
    model_config = ConfigDict(extra="forbid")
    block_indices: list[int] = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str = ""
    title: str = ""
    followups: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class MaterialExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ExtractedMaterial] = Field(default_factory=list)


def _location(blocks: list[SourceBlock]) -> str:
    locations = list(dict.fromkeys(block.location for block in blocks))
    return locations[0] if len(locations) == 1 else locations[0] + " → " + locations[-1]


def _item(document_id, kind, filename, question, answer, followups, blocks, quote, tags, company, role, title="", topics=None):
    payload = dict(
        document_id=document_id, kind=kind, title=title or question[:100],
        question=question.strip(), answer=answer.strip(), followups=list(dict.fromkeys(followups)),
        topics=list(dict.fromkeys(topics or topic_labels(question + " " + answer))),
        tags=list(tags), company=company, role=role, source_file=filename,
        location=_location(blocks), source_quote=quote,
    )
    # A reimport can produce a new extraction from unchanged source bytes. Version the
    # complete record so immutable session snapshots cannot shadow new follow-ups or
    # provenance under an old ID. Existing stored IDs remain valid and are never rewritten.
    identity = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return MaterialItem(id="item_" + hashlib.sha256(identity.encode()).hexdigest()[:20], **payload)


def _offline(blocks, document_id, kind, filename, tags, company, role):
    results = []
    current = None
    heading = None
    orphan = []
    in_code = False

    def finish():
        nonlocal current
        if current is None:
            return
        answer = "\n".join(current["answers"]).strip()
        if kind == "answer" and not answer:
            current = None
            return
        cited = list(dict.fromkeys(index for index, _ in current["sources"]))
        selected = [blocks[index] for index in cited]
        # The quote is a readable excerpt; full parsed text remains in the document snapshot.
        quote = "\n".join(line for _, line in current["sources"])[:4000]
        results.append(_item(document_id, kind, filename, current["question"], answer,
            current["followups"], selected, quote, tags, company, role))
        current = None

    def start(question, index, original):
        nonlocal current
        finish()
        current = {"question": question, "answers": [], "followups": [], "sources": [(index, original)],
                   "explicit_answer": False}

    for index, block in enumerate(blocks):
        for original in block.text.splitlines():
            line = original.strip()
            if not line:
                if current and current["answers"]:
                    current["answers"].append("")
                continue
            if line.startswith("```") or line.startswith("~~~"):
                in_code = not in_code
                if current:
                    current["answers"].append(original)
                    current["sources"].append((index, original))
                continue
            if in_code:
                if current:
                    current["answers"].append(original)
                    current["sources"].append((index, original))
                continue

            # Ignore Markdown presentation when recognizing labels, preserve it in source quotes.
            clean = re.sub(r"^[-*+]\s+", "", line).replace("**", "")
            match = FOLLOWUP_LABEL.match(clean)
            if match and current:
                current["followups"].append(match.group(1).strip())
                current["sources"].append((index, original))
                continue
            match = ANSWER_LABEL.match(clean)
            if match:
                if current is None and heading:
                    start(heading[0], heading[1], heading[2])
                if current:
                    current["explicit_answer"] = True
                    current["answers"].append(match.group(1))
                    current["sources"].append((index, original))
                continue
            match = QUESTION_LABEL.match(clean)
            if match:
                start(match.group(1), index, original)
                continue
            header = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", clean)
            if header:
                title = header.group(2)
                if "?" in title or "？" in title or QUESTION_WORDS.match(title):
                    start(title, index, original)
                else:
                    finish()
                    heading = (title, index, original)
                continue
            numbered = NUMBERED.match(clean)
            candidate = numbered.group(1) if numbered else clean
            is_question = len(candidate) <= 500 and (
                candidate.endswith(("?", "？")) or QUESTION_WORDS.match(candidate)
                or (kind == "interview" and numbered and len(candidate) <= 200
                    and (not current or not current["explicit_answer"] or topic_labels(candidate)))
            )
            if is_question:
                start(candidate, index, original)
                continue
            if current is None and heading and kind == "answer":
                start(heading[0], heading[1], heading[2])
            if current:
                current["answers"].append(original)
                current["sources"].append((index, original))
            else:
                orphan.append((index, original))
    finish()

    if not results and kind == "answer" and orphan:
        # A prose answer document may contain no explicit question. Keep its title and text together.
        indices = list(dict.fromkeys(index for index, _ in orphan))
        answer = "\n".join(line for _, line in orphan)
        title = heading[0] if heading else filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        results.append(_item(document_id, kind, filename, title, answer, [],
            [blocks[index] for index in indices], answer[:4000], tags, company, role))
    if not results and kind == "interview":
        # OCR often loses numbering. Preserve short topical lines as prompts without making up answers.
        for index, original in orphan:
            if 3 <= len(original) <= 200 and topic_labels(original):
                results.append(_item(document_id, kind, filename, original, "", [],
                    [blocks[index]], original, tags, company, role))
    return results


def _batches(blocks):
    batch, size = [], 0
    for block in blocks:
        for offset in range(0, len(block.text), 16000):
            piece = block.model_copy(update={"text": block.text[offset:offset + 16000]})
            if len(block.text) > 16000:
                piece.location += f"/chars:{offset + 1}-{offset + len(piece.text)}"
            if size + len(piece.text) > 32000 and batch:
                yield batch
                batch, size = [], 0
            batch.append(piece)
            size += len(piece.text)
    if batch:
        yield batch


def extract_materials(blocks: list[SourceBlock], *, document_id: str, kind: MaterialKind,
                      source_file: str, client=None, tags=None, company="", role="") -> list[MaterialItem]:
    tags = tags or []
    if client is None:
        results = _offline(blocks, document_id, kind, source_file, tags, company, role)
    else:
        results = []
        for batch in _batches(blocks):
            response = client.structured_generate(prompt("material_extraction"), {
                "kind": kind, "blocks": [{"index": i, **block.model_dump()} for i, block in enumerate(batch)],
                "source_role": "external_reference_only", "company": company, "role": role,
            }, MaterialExtraction)
            response = MaterialExtraction.model_validate(response)
            for draft in response.items:
                indices = sorted(set(draft.block_indices))
                if any(index < 0 or index >= len(batch) for index in indices):
                    raise ValueError("Material extraction cited an unknown source block")
                if indices != list(range(indices[0], indices[-1] + 1)):
                    raise ValueError("Material extraction must cite a contiguous block range")
                selected = [batch[index] for index in indices]
                original = compact("\n".join(block.text for block in selected))
                if not compact(draft.source_quote) or compact(draft.source_quote) not in original:
                    raise ValueError("Material extraction source quote does not match the document")
                if not draft.question.strip():
                    raise ValueError("Material extraction question must not be blank")
                if draft.answer and compact(draft.answer) not in original:
                    raise ValueError("Material extraction answer must be copied from its source blocks")
                if any(compact(followup) not in original for followup in draft.followups):
                    raise ValueError("Material extraction follow-up does not occur in its source blocks")
                if kind == "answer" and not draft.answer.strip():
                    continue
                results.append(_item(document_id, kind, source_file, draft.question, draft.answer,
                    draft.followups, selected, draft.source_quote, tags, company, role,
                    title=draft.title, topics=draft.topics))
    # Repeated text inside a document is only stored once, with the first source location retained.
    unique = {}
    for item in results:
        key = (compact(item.question), compact(item.answer))
        unique.setdefault(key, item)
    if not unique:
        raise ValueError("No interview questions or reference answers found; use explicit Q:/A: labels or semantic extraction")
    return list(unique.values())
