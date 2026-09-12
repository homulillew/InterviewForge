"""Three independent retrieval lanes: content, answer transitions, statistical style."""

import hashlib
from interview_forge.schemas.models import Applicability, CorpusMatchRef
from interview_forge.semantics import tokens
from .applicability import applicability
from .normalize import company_name, role_name
from .style import retrieve_style


def retrieve_content(corpus, revision, claim, surface, company=None, role=None, fts_ids=(), limit=6):
    cases = {c.id: c for c in corpus.cases}
    ranked = []
    query = tokens(claim.source_quote + " " + " ".join(claim.technologies))
    for pattern in corpus.patterns:
        kind, reason = applicability(claim, surface, pattern)
        if kind in {Applicability.reject, Applicability.style_only}:
            continue
        direct = kind == Applicability.direct
        overlap = len(query & tokens(" ".join(pattern.applicable_topics)))
        # Resume and surface contributions dwarf company/role metadata bonuses.
        score = (
            60 * direct
            + 20 * (pattern.attack_dimension == surface.dimension)
            + min(10, overlap * 2)
            + 5 * pattern.quality
        )
        score += 2 * any(cases[cid].role == role_name(role) for cid in pattern.source_case_ids) if role else 0
        score += (
            1 * any(cases[cid].company == company_name(company) for cid in pattern.source_case_ids)
            if company
            else 0
        )
        score += 2 * bool(set(pattern.source_question_ids) & set(fts_ids))
        mid = (
            "match-"
            + hashlib.sha256((revision + claim.id + surface.id + pattern.id).encode()).hexdigest()[:18]
        )
        match = CorpusMatchRef(
            id=mid,
            revision=revision,
            pattern_id=pattern.id,
            source_case_ids=pattern.source_case_ids,
            applicability=kind,
            relevance=min(1, score / 100),
            reason=reason,
        )
        ranked.append((score, pattern.id, match, pattern))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [(m, p) for _, _, m, p in ranked[:limit]]


def retrieve_transitions(corpus, previous_intent, features, claim, coverage=(), limit=4):
    ranked = []
    patterns = {qid: p for p in corpus.patterns for qid in p.source_question_ids}
    for transition in corpus.transitions:
        if transition.from_intent != previous_intent:
            continue
        pattern = patterns.get(transition.example_question_id)
        if pattern is None:
            continue
        shared = set(claim.technologies) & set(pattern.applicable_topics)
        from .applicability import TRANSFERABLE

        if not shared and pattern.challenge_operator not in TRANSFERABLE:
            continue
        matches = set(features) & set(transition.candidate_answer_features)
        if transition.observed_answer and transition.candidate_answer_features and not matches:
            continue
        score = 3 * len(matches) + transition.confidence + bool(shared)
        if transition.to_intent.value in coverage:
            score -= 1
        ranked.append((score, transition.id, transition))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [t for _, _, t in ranked[:limit]]


__all__ = ["retrieve_content", "retrieve_transitions", "retrieve_style"]
