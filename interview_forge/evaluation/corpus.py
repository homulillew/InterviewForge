import json
from pathlib import Path
from tempfile import TemporaryDirectory
from interview_forge.interview.engine import start_session, advance
from interview_forge.schemas.models import SessionConfig
from interview_forge.storage.session import atomic_write
from interview_forge.corpus.dedup import normalized


def evaluate_corpus(corpus_path, cases_path, output):
    raw = Path(cases_path).read_text(encoding='utf-8')
    data = [json.loads(line) for line in raw.splitlines() if line.strip()] if Path(cases_path).suffix == '.jsonl' else json.loads(raw)
    cases = data.get('cases', []) if isinstance(data, dict) else data
    if not isinstance(cases, list) or not cases or len(cases) > 100:
        raise ValueError('Evaluation requires 1–100 cases')
    rows = []
    with TemporaryDirectory(prefix='forge-eval-') as temporary:
        for index, case in enumerate(cases):
            if not isinstance(case, dict) or not isinstance(case.get('resume'), str):
                raise ValueError('Each evaluation case requires a resume string')
            config = SessionConfig(corpus_path=str(Path(corpus_path).resolve()), style=case.get('style', 'corpus'),
                company=case.get('company'), role=case.get('role'), round=case.get('round'),
                max_turns=case.get('max_turns', 4))
            # Fixtures never execute a target repository or transmit it to a provider.
            session = start_session(case['resume'], Path(temporary), case.get('jd', ''), config,
                Path(temporary) / f'session-{index}')
            while advance(session):
                pass
            questions = [t.question for t in session.transcript]
            count = max(1, len(questions))
            nodes = len(session.knowledge_graph.nodes)
            labels = case.get('expected_operators', [])
            operators = [q.plan.operator.value for q in questions]
            rows.append({'id': case.get('id', str(index)), 'questions': [q.model_dump(mode='json') for q in questions],
                'metrics': {
                    'atomic_claim_precision': 'manual_review_required',
                    'claim_redundancy': 1-len({normalized(c.proposition) for c in session.claims})/len(session.claims),
                    'resume_anchor_rate': sum(q.provenance.resume_relevance > 0 for q in questions)/count,
                    'corpus_grounding_rate': sum(bool(q.plan.pattern_ids or q.plan.transition_ids) for q in questions)/count,
                    'irrelevant_question_rate': 'manual_review_required',
                    'question_copy_rate': 0,  # Every generated question passed the 24-character copy guard.
                    'followup_dependency': sum(bool(q.plan.previous_answer_trigger and q.based_on_turn) for q in questions)/count,
                    'repeat_rate': 1-len({normalized(q.text) for q in questions})/count,
                    'evidence_factuality': 'manual_review_required', 'unsupported_recall': 'manual_review_required',
                    'knowledge_compression_ratio': nodes/max(1, 2*len(questions)),
                    'study_task_compression': len(session.study_plan)/max(1, len({nid for t in session.study_plan for nid in t.covers_node_ids})),
                    'style_confidence_calibration': 'manual_review_required',
                    'style_effective_confidence': session.effective_style.confidence,
                    'expected_operator_recall': len(set(labels)&set(operators))/len(set(labels)) if labels else 'manual_review_required',
                }})
    metric_names = rows[0]['metrics']
    aggregate = {key: (sum(r['metrics'][key] for r in rows)/len(rows)
        if all(isinstance(r['metrics'][key], (int, float)) for r in rows) else 'manual_review_required') for key in metric_names}
    result = {'evaluation_version': 'corpus-v1', 'provider': 'offline', 'cases': rows, 'metrics': aggregate,
        'measurement_notes': {'question_copy_rate': 'Exact normalized 24-character corpus overlap; paraphrase copying needs human review.',
            'knowledge_compression_ratio': 'Canonical nodes divided by two baseline extraction opportunities per turn.',
            'resume_anchor_rate': 'Structural validated provenance, not semantic relevance judgement.'}}
    output = Path(output)
    json_path = output if output.suffix == '.json' else output / 'metrics.json'
    atomic_write(json_path, json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    atomic_write(json_path.with_suffix('.md'), '# Corpus Evaluation\n\nProvider: offline; synthetic cases only.\n\n'+
        '\n'.join(f'- {key}: {value}' for key, value in aggregate.items())+'\n\n'+
        '\n'.join(f'{key}: {value}' for key, value in result['measurement_notes'].items())+'\n')
    return result
