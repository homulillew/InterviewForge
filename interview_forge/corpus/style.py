"""Sample-aware statistics and hierarchical backoff, never brand personalities."""

import hashlib
import json
from collections import Counter
from statistics import median
from interview_forge.schemas.models import EffectiveStyle
from .models import InterviewerStyleProfile
from .normalize import company_name, role_name


def distribution(values):
    counts = Counter(values)
    total = sum(counts.values())
    return {key: count / total for key, count in sorted(counts.items())} if total else {}


def keys(company, role, round_value, seniority):
    values = [
        (company, role, round_value, seniority),
        (company, role, round_value, None),
        (company, role, None, None),
        (company, None, None, None),
        (None, role, round_value, None),
        (None, role, None, None),
        (None, None, None, None),
    ]
    return list(dict.fromkeys(values))


def compile_styles(cases, transitions):
    # One independent sample per duplicate group; summaries cannot teach attack style.
    unique = {}
    for case in sorted(cases, key=lambda c: (-c.case_quality, c.id)):
        if case.questions and case.source_type != "unordered_summary":
            unique.setdefault(case.duplicate_group or case.id, case)
    groups = {}
    for case in unique.values():
        for key in keys(case.company, case.role, case.round, case.seniority):
            groups.setdefault(key, []).append(case)
    output = []
    for key, rows in sorted(groups.items(), key=lambda row: str(row[0])):
        ids = {c.id for c in rows}
        qs = [q for c in rows for q in c.questions]
        depths = sorted(len(c.questions) for c in rows)
        identity = json.dumps([key, sorted(ids)], ensure_ascii=False)
        output.append(
            InterviewerStyleProfile(
                id="style-" + hashlib.sha256(identity.encode()).hexdigest()[:16],
                company=key[0],
                role_family=key[1],
                round=key[2],
                seniority=key[3],
                sample_size=len(rows),
                median_chain_depth=median(depths),
                p75_chain_depth=depths[min(len(depths) - 1, int(len(depths) * 0.75))],
                probe_distribution=distribution(q.probe_intent.value for q in qs),
                operator_distribution=distribution(q.challenge_operator.value for q in qs),
                transition_distribution=distribution(
                    t.from_intent.value + "->" + t.to_intent.value
                    for t in transitions
                    if t.source_case_id in ids
                ),
                question_length_median=median(len(q.text) for q in qs),
                style_features=[
                    f"{len(rows)} independent observed cases; distributions are descriptive, not company stereotypes."
                ],
                confidence=min(0.95, len(rows) / (len(rows) + 12)),
            )
        )
    lookup = {(p.company, p.role_family, p.round, p.seniority): p.id for p in output}
    for p in output:
        p.parent_profile_ids = [
            lookup[k]
            for k in keys(p.company, p.role_family, p.round, p.seniority)[1:]
            if k in lookup and lookup[k] != p.id
        ]
    return output


def retrieve_style(profiles, company=None, role=None, round_value=None, seniority=None):
    lookup = {(p.company, p.role_family, p.round, p.seniority): p for p in profiles}
    path = []
    remaining = 1.0
    weights = {}
    selected = []
    for key in keys(company_name(company), role_name(role), round_value, seniority):
        p = lookup.get(key)
        label = "/".join(str(v) if v is not None else "*" for v in key)
        path.append(f"{label}: {p.sample_size if p else 0} samples")
        if p is None:
            continue
        weight = remaining if key == (None, None, None, None) else remaining * p.confidence
        if weight > 0:
            weights[p.id] = weight
            selected.append(p)
            remaining -= weight
        if remaining < 0.001:
            break
    if not selected:
        return EffectiveStyle(backoff_path=path)
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}
    operators = Counter()
    transitions = Counter()
    for p in selected:
        operators.update({k: v * weights[p.id] for k, v in p.operator_distribution.items()})
        transitions.update({k: v * weights[p.id] for k, v in p.transition_distribution.items()})
    identity = json.dumps(weights, sort_keys=True)
    return EffectiveStyle(
        id="effective-" + hashlib.sha256(identity.encode()).hexdigest()[:16],
        sample_size=max(p.sample_size for p in selected),
        confidence=sum(weights[p.id] * p.confidence for p in selected),
        profile_weights=weights,
        backoff_path=path,
        operator_distribution=dict(operators),
        transition_distribution=dict(transitions),
        median_chain_depth=sum(weights[p.id] * p.median_chain_depth for p in selected),
        question_length_median=sum(weights[p.id] * p.question_length_median for p in selected),
    )
