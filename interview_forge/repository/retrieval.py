"""Question-aware lexical retrieval. Scores express relevance, never factual support."""
from collections import Counter
import math
import re

from interview_forge.schemas.models import Dimension, EvidenceMatch

STOP = {"the", "and", "with", "why", "how", "this", "that", "for", "from", "what", "you", "your", "have", "does", "into", "will"}
CONCEPTS = {
    "原子": ("atomic", "lua", "transaction"),
    "库存": ("stock", "inventory", "reserve", "decrby"),
    "幂等": ("idempotency", "idempotent", "dedup", "request_id"),
    "重试": ("retry", "retries", "idempotency"),
    "超时": ("timeout", "deadline"),
    "熔断": ("circuit", "breaker"),
    "评测": ("evaluation", "evaluate", "benchmark", "ndcg", "mrr", "recall"),
    "测量": ("benchmark", "latency", "p99", "throughput"),
    "验证": ("test", "assert", "correctness", "benchmark"),
    "延迟": ("latency", "p99", "timeout"),
    "检索": ("retrieval", "retriever", "search"),
    "重排": ("reranker", "rerank", "rank"),
    "故障": ("failure", "failover", "recovery", "exception"),
    "并发": ("concurrency", "concurrent", "thread", "atomic"),
}


def terms(text):
    result = {w for w in re.findall(r"[a-z][a-z0-9_]{1,}", text.lower()) if w not in STOP}
    result.update(part for w in list(result) for part in w.split("_") if len(part) > 1)
    for concept, aliases in CONCEPTS.items():
        if concept in text:
            result.update(aliases)
    return result


def select_evidence(question, claim, evidences, max_chars=10000, max_items=8):
    candidates = [e for e in evidences if claim.id in e.supports_claim]
    primary = question.text.split("”；", 1)[-1]
    query = terms(primary + " " + question.subtopic)
    context = terms(claim.source_quote + " " + claim.topic)
    documents = {e.id: terms(e.file_path + " " + (e.symbol or "") + " " + e.excerpt) for e in candidates}
    frequency = Counter(term for document in documents.values() for term in document)
    ranked = []
    for evidence in candidates:
        tokens = documents[evidence.id]
        query_hits, context_hits = sorted(query & tokens), sorted(context & tokens)
        if not query_hits and not context_hits:
            continue
        def weight(term):
            return 1 + math.log((len(candidates) + 1) / (frequency[term] + 1))
        score = sum(3 * weight(t) for t in query_hits) + sum(weight(t) for t in context_hits)
        reasons = []
        if query_hits:
            reasons.append("question terms: " + ", ".join(query_hits))
        if context_hits:
            reasons.append("claim terms: " + ", ".join(context_hits))
        preferred = {"implementation"}
        if question.dimension == Dimension.evaluation:
            preferred = {"evaluation", "test"}
        if evidence.evidence_type in preferred:
            score *= 1.25
            reasons.append("artifact type relevant to question dimension")
        ranked.append((score, evidence, reasons))
    ranked.sort(key=lambda row: (-row[0], row[1].file_path, row[1].line_start, row[1].id))
    selected, matches, counts = [], [], Counter()
    for score, evidence, reasons in ranked:
        # Keep room for different sources; never truncate an excerpt and invalidate its line range.
        if len(selected) >= max_items:
            break
        if len(evidence.excerpt) > max_chars or counts[evidence.file_path] >= 2:
            continue
        selected.append(evidence)
        matches.append(EvidenceMatch(evidence_id=evidence.id, relevance_score=round(score, 3), reasons=reasons))
        counts[evidence.file_path] += 1
        max_chars -= len(evidence.excerpt)
    return selected, matches
