"""Exact normalization and light character-shingle near duplicate groups."""

import hashlib
import re


def normalized(text):
    return re.sub(r"\W+", "", text.casefold())


def fingerprint(text):
    return hashlib.sha256(normalized(text).encode()).hexdigest()


def shingles(text, n=4):
    text = normalized(text)
    return {text[i : i + n] for i in range(max(1, len(text) - n + 1))}


def similarity(a, b):
    left, right = shingles(a), shingles(b)
    return len(left & right) / max(1, len(left | right))


def group_duplicates(cases):
    representatives = []
    for case in sorted(cases, key=lambda c: c.id):
        text = "\n".join(q.text + " " + (q.answer_context or "") for q in case.questions)
        if not text:
            text = " ".join(case.technologies)
        group = next(
            (
                c.duplicate_group
                for c, other in representatives
                if case.normalized_hash == c.normalized_hash
                or (len(text) > 80 and similarity(text, other) >= 0.88)
            ),
            None,
        )
        case.duplicate_group = group or "dup-" + case.id
        if group is None:
            representatives.append((case, text))
    return cases
