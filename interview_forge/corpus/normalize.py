"""Normalize heterogeneous, untrusted posts without inventing chronology or metadata."""

import hashlib
import json
import re
from pydantic import Field
from interview_forge.schemas.models import Model
from interview_forge.semantics import technologies
from interview_forge.llm import prompt
from .models import InterviewCase, CorpusQuestion
from .patterns import SPEC, identify_operator
from .chains import answer_features
from .dedup import fingerprint

COMPANIES = {
    "bytedance": ("bytedance", "字节跳动", "字节"),
    "alibaba": ("alibaba", "阿里巴巴", "阿里"),
    "tencent": ("tencent", "腾讯"),
    "meituan": ("meituan", "美团"),
    "baidu": ("baidu", "百度"),
}


def company_name(value):
    if not value or str(value).lower() in {"unknown", "none", "未知"}:
        return None
    return next(
        (name for name, aliases in COMPANIES.items() if str(value).casefold() in aliases), str(value).strip()
    )


def role_name(value):
    if not value or str(value).lower() in {"unknown", "none", "未知"}:
        return None
    text = str(value).casefold()
    if re.search("backend|后端", text):
        return "backend"
    if re.search("ai|算法|大模型", text):
        return "ai-engineer"
    return text.strip()


class NormalizedQuestion(Model):
    text: str = Field(min_length=1, max_length=2000)
    answer: str | None = Field(default=None, max_length=4000)


class NormalizedPost(Model):
    company: str | None = None
    role: str | None = None
    round: str | None = None
    seniority: str | None = None
    questions: list[NormalizedQuestion] = Field(default_factory=list, max_length=200)
    ordered: bool = False


def _json_post(data):
    if isinstance(data, str):
        return data, {}
    if not isinstance(data, dict):
        raise ValueError("Corpus JSON records must be objects or strings")
    metadata = {key: data.get(key) for key in ("company", "role", "round", "seniority")}
    lines = []
    for key in ("title", "text", "content", "body", "resume_context", "project_context"):
        value = data.get(key)
        if isinstance(value, str):
            lines.append(value)
        elif isinstance(value, list):
            lines.extend(str(item) for item in value if isinstance(item, str))
    questions = data.get("questions", data.get("conversation", data.get("messages", [])))
    if isinstance(questions, list):
        for item in questions:
            if isinstance(item, str):
                lines.append("Q: " + item)
            elif isinstance(item, dict):
                if item.get("question") or item.get("q"):
                    lines.append("Q: " + str(item.get("question", item.get("q"))))
                    if item.get("answer") or item.get("a"):
                        lines.append("A: " + str(item.get("answer", item.get("a"))))
                    for followup in item.get("followups", []):
                        if isinstance(followup, str):
                            lines.append("追问：" + followup)
                elif item.get("role") in {"interviewer", "candidate"}:
                    lines.append(
                        ("Q: " if item["role"] == "interviewer" else "A: ") + str(item.get("content", ""))
                    )
    if not lines:
        # Preserve odd but valid post shapes for inspect; do not invent questions.
        lines = [json.dumps(data, ensure_ascii=False)]
    return "\n".join(lines), metadata


def _offline(text):
    questions = []
    ordered = False
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|→|->)\s*", "", raw).strip()
        q = re.match(r"^(?:Q(?:uestion)?\d*|问题\d*|问|追问\d*|面试官)\s*[:：]\s*(.+)", line, re.I)
        a = re.match(r"^(?:A(?:nswer)?\d*|回答|答案|我答|答|候选人)\s*[:：]\s*(.+)", line, re.I)
        numbered = re.match(r"^\d+[.)、]\s*(.+)", line)
        if a and questions:
            questions[-1].answer = ((questions[-1].answer or "") + " " + a.group(1)).strip()
        elif (
            numbered
            and questions
            and questions[-1].answer
            and not re.search(r"[？?]|如何|为什么|怎么", numbered.group(1))
        ):
            questions[-1].answer += " " + line
        elif q or numbered:
            body = (q or numbered).group(1)
            if len(body) > 2000:
                raise ValueError("Corpus question exceeds 2,000 characters; split the source")
            if len(body) <= 2000:
                questions.append(NormalizedQuestion(text=body))
                ordered = True
        elif line.endswith(("?", "？")) or re.match(r"^(?:为什么|为何|怎么|如何|快在哪)", line):
            if 3 <= len(line) <= 2000:
                questions.append(NormalizedQuestion(text=line))
                ordered = True
        elif questions and (
            raw.lstrip().startswith(("→", "->")) or re.match(r"^(因为|我说|我用|我的回答)", line)
        ):
            questions[-1].answer = line
    return NormalizedPost(questions=questions, ordered=ordered)


def normalize_post(data, source_file, record_index=0, client=None):
    text, metadata = _json_post(data)
    if len(text) > 200_000:
        raise ValueError("Corpus post exceeds 200,000 characters; split the post before ingest")
    if client:
        if len(text) > 32_000:
            raise ValueError(
                "Semantic corpus normalization accepts 32,000 characters per post; split large posts"
            )
        post = client.structured_generate(
            prompt("corpus_normalize"), {"text": text, "explicit_metadata": metadata}, NormalizedPost
        )
        post = NormalizedPost.model_validate(post)
        from .dedup import normalized

        for q in post.questions:
            if normalized(q.text) not in normalized(text) or (
                q.answer and normalized(q.answer) not in normalized(text)
            ):
                raise ValueError("Corpus model invented question or answer context")
        for field in ("company", "role", "round", "seniority"):
            value = getattr(post, field)
            if value and value != metadata.get(field) and value.casefold() not in text.casefold():
                raise ValueError("Corpus model invented unknown metadata")
            if value:
                metadata[field] = value
        # Ordering must have an observable list/trace, not merely a model assertion.
        post.ordered = post.ordered and _offline(text).ordered
    else:
        post = _offline(text)
    header = "\n".join(text.splitlines()[:3])[:500]
    company = company_name(metadata.get("company"))
    if not company:
        found = [
            name
            for name, aliases in COMPANIES.items()
            if any(alias in header.casefold() for alias in aliases)
        ]
        company = found[0] if len(found) == 1 else None
    role = role_name(metadata.get("role"))
    if not role:
        matched = re.search(r"(后端|backend|ai-engineer|大模型算法)", header, re.I)
        role = role_name(matched.group()) if matched else None
    round_value = metadata.get("round")
    if not round_value:
        matched = re.search(r"(?:tech[- ]?[123]|[一二三]面)", header, re.I)
        round_value = matched.group() if matched else None
    round_value = {"一面": "tech-1", "二面": "tech-2", "三面": "tech-3"}.get(round_value, round_value)
    if isinstance(data, dict) and data.get("source_type") == "unordered_summary":
        post.ordered = False
    source_hash = hashlib.sha256(text.encode()).hexdigest()
    cid = (
        "case-"
        + hashlib.sha256(
            (str(source_file) + ":" + str(record_index) + ":" + source_hash).encode()
        ).hexdigest()[:20]
    )
    source_type = (
        "trace"
        if post.ordered and any(q.answer for q in post.questions)
        else ("ordered_list" if post.ordered and post.questions else "unordered_summary")
    )
    qs = []
    context_techs = technologies(header) if not post.questions or post.questions[0].text not in header else []
    for index, q in enumerate(post.questions if post.ordered else []):
        context_techs = technologies(q.text) or context_techs
        operator = identify_operator(q.text)
        qs.append(
            CorpusQuestion(
                id=f"{cid}-q{index + 1}",
                case_id=cid,
                text=q.text,
                topic=context_techs,
                probe_intent=SPEC[operator][0],
                challenge_operator=operator,
                order=index + 1,
                previous_question_id=qs[-1].id if qs else None,
                answer_context=q.answer,
                answer_feature=answer_features(q.answer),
                confidence=0.9 if q.answer else 0.65,
            )
        )
    quality = {"trace": 0.75, "ordered_list": 0.5, "unordered_summary": 0.1}[source_type]
    quality = min(1, quality + 0.1 * bool(technologies(text)) + 0.05 * bool(company) + 0.05 * bool(role))
    if re.search(r"加微信|付费领取|营销|广告", text):
        quality *= 0.5
    return InterviewCase(
        id=cid,
        source_file=str(source_file),
        record_index=record_index,
        source_hash=source_hash,
        source_locations=data.get("source_locations", []) if isinstance(data, dict) else [],
        reader_warnings=data.get("reader_warnings", []) if isinstance(data, dict) else [],
        normalized_hash=fingerprint(text),
        source_type=source_type,
        company=company,
        role=role,
        round=round_value,
        seniority=metadata.get("seniority"),
        company_confidence=0.9 if company else 0,
        role_confidence=0.9 if role else 0,
        round_confidence=0.9 if round_value else 0,
        resume_context=(
            [data["resume_context"]]
            if isinstance(data.get("resume_context"), str)
            else data.get("resume_context", [])
        )
        if isinstance(data, dict)
        else [],
        project_context=(
            [data["project_context"]]
            if isinstance(data.get("project_context"), str)
            else data.get("project_context", [])
        )
        if isinstance(data, dict)
        else [],
        technologies=technologies(text),
        questions=qs,
        case_quality=quality,
    )
