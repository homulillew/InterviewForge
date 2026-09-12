"""Explicit technical vocabulary shared by guards, never a company curriculum."""
import re

TECHNOLOGIES = {
    "Redis": r"\bredis\b", "Lua": r"\blua\b", "RAG": r"\brag\b|检索增强",
    "reranker": r"rerank|重排", "embedding": r"embedding|向量", "Kafka": r"\bkafka\b",
    "MySQL": r"\bmysql\b", "PostgreSQL": r"postgres", "SQL": r"\bsql\b|数据库",
    "Spring Cloud": r"spring\s*cloud", "Java": r"\bjava\b|jvm", "Python": r"\bpython\b",
    "Go": r"\bgo\b|golang", "Transformer": r"transformer|sqrt\s*\(?d[_ ]?k",
    "Kubernetes": r"kubernetes|\bk8s\b", "Docker": r"docker", "Agent": r"\bagent\b|智能体",
    "HTTP": r"\bhttp\b|\bapi\b|接口", "BM25": r"\bbm25\b",
}


def technologies(text):
    return [name for name, pattern in TECHNOLOGIES.items() if re.search(pattern, text, re.I)]


def tokens(text):
    result = set(re.findall(r"[a-z0-9_+#]+", text.casefold()))
    for word in re.findall(r"[\u4e00-\u9fff]+", text):
        result.update(word[i:i + 2] for i in range(len(word) - 1))
    return result - {"how", "why", "what", "the", "and", "如何", "为什么", "什么", "我们", "项目", "可以", "这个"}


def family(techs):
    names, result = {t.casefold() for t in techs}, set()
    if names & {"rag", "reranker", "embedding", "bm25", "transformer", "agent"}:
        result.add("retrieval_ai")
    if names & {"redis", "lua", "kafka", "mysql", "postgresql", "sql", "spring cloud", "http"}:
        result.add("backend")
    return result
