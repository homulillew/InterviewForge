"""Explicit schema 1.0 → 2.0 migration; historical human records keep their IDs."""
from interview_forge.schemas.legacy_v1 import InterviewSession as LegacySession
from interview_forge.schemas.models import (
    InterviewSession, QuestionPlan, QuestionProvenance, AttackSurface,
    EvidenceRelation, MasteryState,
)
from interview_forge.claims.pipeline import extract_claims, generate_surfaces
from interview_forge.corpus.patterns import identify_operator
from interview_forge.semantics import tokens


def migrate_v1(data):
    old = LegacySession.model_validate(data)
    statements, claims = extract_claims(old.resume, old.jd)
    # Preserve original statement IDs because historical material refers to them.
    statement_ids = {s.text: s.id for s in old.statements}
    for s in statements:
        original = s.id
        s.id = statement_ids.get(s.text, s.id)
        for claim in claims:
            if claim.statement_id == original:
                claim.statement_id = s.id
    if not claims:
        raise ValueError('Migration found no explicit assertions; original session is unchanged')
    remap = {}
    for previous in old.claims:
        candidates = [c for c in claims if c.statement_id == previous.statement_id]
        if not candidates:
            raise ValueError('Cannot map a legacy claim to its resume assertion; original session is unchanged')
        remap[previous.id] = max(candidates, key=lambda c: len(tokens(c.proposition) & tokens(previous.proposition))).id
    state = old.model_dump()
    state.update(schema_version='2.0', statements=statements, claims=claims,
        attack_surfaces=generate_surfaces(claims), evidence_relations=[], corpus_pin=None,
        effective_style={}, corpus_matches=[], corpus_transitions=[], migration_notes=[
            'Migrated schema 1.0 explicitly. Atomic assertions were re-extracted from the original resume.',
            'Historical questions, answers, node IDs, human submissions and reviews are retained.',
            'Historical corpus/style provenance is unknown; migrated questions claim no compiled corpus support.',
            'Legacy material snapshots remain archival only. New turns use the corpus harness.'])
    by_id = {c.id: c for c in claims}
    for evidence in state['evidences']:
        evidence['related_claim_ids'] = list(dict.fromkeys(remap[cid] for cid in evidence.pop('supports_claim')))
        for cid in evidence['related_claim_ids']:
            by_id[cid].evidence_ids.append(evidence['id'])
            state['evidence_relations'].append(EvidenceRelation(evidence_id=evidence['id'], claim_id=cid,
                confidence=evidence['confidence'], facets=[], rationale='Migrated lexical association; support is unassessed.'))
    for claim in claims:
        claim.evidence_ids = list(dict.fromkeys(claim.evidence_ids))
    surfaces = state['attack_surfaces']
    for record in [*state['transcript'], *state['retests']]:
        q = record['question']
        q['claim_id'] = remap[q['claim_id']]
        claim = by_id[q['claim_id']]
        surface = next((s for s in surfaces if s.claim_id == claim.id and s.dimension == q['dimension']), None)
        if surface is None:
            surface = AttackSurface(id=f'migrated-surface-{len(surfaces)+1}', claim_id=claim.id,
                dimension=q['dimension'], relevance=.7, priority='P1', rationale='Preserved historical question dimension')
            surfaces.append(surface)
        operator = identify_operator(q['text'])
        plan = QuestionPlan(claim_id=claim.id, attack_surface_id=surface.id, operator=operator,
            target_concept=claim.topic, expected_points=q['expected_points'], adaptation_reason='Preserved historical question; corpus provenance unavailable')
        q.update(plan=plan, provenance=QuestionProvenance(resume_statement_id=claim.statement_id,
            atomic_claim_id=claim.id, attack_surface_id=surface.id, challenge_operator=operator,
            adaptation_reason=plan.adaptation_reason, origin='migration'))
        if record in state['transcript']:
            surface.question_count += 1
            surface.last_turn_id = record['id']
            surface.coverage = 'exhausted' if surface.question_count >= 2 else 'partial'
    for node in state['knowledge_graph']['nodes']:
        node['source_claims'] = list(dict.fromkeys(remap[cid] for cid in node['source_claims']))
    for task in state['study_plan']:
        task['covers_node_ids'] = [task['node_id']]
    for claim in claims:
        nodes = [n for n in state['knowledge_graph']['nodes'] if claim.id in n['source_claims']]
        evidence = list(dict.fromkeys(rid for n in nodes for rid in n['mastery']['evidence']))
        if evidence:
            ready = all(n['mastery']['status'] == 'interview_ready' for n in nodes)
            claim.mastery = MasteryState(status='interview_ready' if ready else 'needs_practice',
                evidence=evidence, assessed_by='human_reviewer' if ready else 'heuristic')
    if state['review']:
        review = state['review']
        review['claim_coverage'] = {c.id: sum(t['question']['claim_id'] == c.id for t in state['transcript']) for c in claims}
        for name in ('strongly_defended_claims', 'weakly_defended_claims'):
            review[name] = list(dict.fromkeys(remap[cid] for cid in review[name]))
    return InterviewSession.model_validate(state)
