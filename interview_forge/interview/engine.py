from collections import Counter
from uuid import uuid4
from pathlib import Path
from interview_forge.agents.interviewer import Interviewer, InterviewerView, SpokenTurn
from interview_forge.agents.repository_answerer import RepositoryAnswerer
from interview_forge.claims.pipeline import extract_claims, rank_claims, generate_surfaces
from interview_forge.knowledge.graph import extract_knowledge, merge_graph
from interview_forge.learning.planner import build_learning
from interview_forge.llm import make_client
from interview_forge.repository.scanner import scan_repository
from interview_forge.schemas.models import (
    InterviewSession,
    InterviewTurn,
    PostInterviewReview,
    EvidenceRelation,
    CorpusPin,
    EffectiveStyle,
    QuestionProvenance,
    TransitionRef,
    AnswerGap,
)
from interview_forge.corpus.storage import CorpusStore
from interview_forge.corpus.retrieval import retrieve_content, retrieve_transitions, retrieve_style
from .attack_planner import choose_attack, update_coverage, intent_for
from .question_planner import make_question_plan
from .critic import critique_answer, blind_claim


def pinned_corpus(session):
    if session.corpus_pin is None:
        return None, None
    if not session.config.corpus_path:
        raise ValueError("Pinned corpus database path is missing")
    store = CorpusStore(session.config.corpus_path)
    if store.fingerprint() != session.corpus_pin.database_fingerprint:
        raise ValueError("Corpus database fingerprint changed; restore the original database")
    corpus = store.load(session.corpus_pin.revision)
    if not set(session.corpus_pin.profile_ids) <= {p.id for p in corpus.style_profiles}:
        raise ValueError("Pinned style profiles are missing")
    patterns = {p.id: p for p in corpus.patterns}
    transitions = {t.id: t for t in corpus.transitions}
    for match in session.corpus_matches:
        if (
            match.pattern_id not in patterns
            or match.source_case_ids != patterns[match.pattern_id].source_case_ids
        ):
            raise ValueError("Corpus match provenance does not exist in the pinned revision")
    for ref in session.corpus_transitions:
        source = transitions.get(ref.id)
        if source is None or (source.example_question_id, source.from_question_id) != (
            ref.example_question_id,
            ref.from_question_id,
        ):
            raise ValueError("Transition provenance does not exist in the pinned revision")
    if session.config.style == "corpus":
        expected = retrieve_style(
            corpus.style_profiles,
            session.config.company,
            session.config.role,
            session.config.round,
            session.config.seniority,
        )
        if expected != session.effective_style:
            raise ValueError("Effective style differs from its pinned corpus statistics")
    return store, corpus


def start_session(resume: str, repo: Path, jd: str, config, output: Path):
    client = make_client(config)
    statements, claims = extract_claims(resume, jd, client)
    if not claims:
        raise ValueError("No explicit technical assertions were found in the resume")
    exclusions = [Path(p) for p in (config.library_path, config.corpus_path) if p]
    repo_map, evidence = scan_repository(repo, claims, exclude=output, excludes=exclusions)
    claims = rank_claims(claims, jd)
    pin, style = None, EffectiveStyle()
    config = config.model_copy(deep=True)
    if config.corpus_path:
        store = CorpusStore(config.corpus_path)
        revision = store.current()
        corpus = store.load(revision)
        config.corpus_path = str(store.path)
        if config.style == "corpus":
            style = retrieve_style(
                corpus.style_profiles, config.company, config.role, config.round, config.seniority
            )
        pin = CorpusPin(
            revision=revision,
            database_fingerprint=store.fingerprint(),
            profile_ids=list(style.profile_weights),
        )
    elif config.style == "corpus":
        raise ValueError("--style corpus requires --corpus with a compiled database")
    relations = [
        EvidenceRelation(
            evidence_id=e.id,
            claim_id=cid,
            facets=[],
            confidence=e.confidence,
            rationale="Static lexical relevance only; no claim support or measured result inferred.",
        )
        for e in evidence
        for cid in e.related_claim_ids
    ]
    return InterviewSession(
        id=str(uuid4()),
        resume=resume,
        jd=jd,
        config=config,
        statements=statements,
        claims=claims,
        attack_surfaces=generate_surfaces(claims),
        repository_map=repo_map,
        evidences=evidence,
        evidence_relations=relations,
        corpus_pin=pin,
        effective_style=style,
    )


def advance(session, client=None):
    if session.status == "paused":
        raise ValueError("Session paused; use resume")
    if session.status == "completed":
        return False
    if len(session.transcript) >= session.config.max_turns:
        session.status, session.stop_reason = "completed", "max_turns"
        return False
    store, corpus = pinned_corpus(session)
    attack = choose_attack(session, corpus)
    if attack is None:
        session.status, session.stop_reason = "completed", "attack_surfaces_exhausted_or_depth_limit"
        return False
    claim = next(c for c in session.claims if c.id == attack.claim_id)
    surface = next(s for s in session.attack_surfaces if s.id == attack.attack_surface_id)
    history = [t for t in session.transcript if t.question.claim_id == claim.id]
    matches, transitions = [], []
    if corpus:
        revision = session.corpus_pin.revision
        fts = store.search_question_ids(claim.source_quote, revision)
        matches = retrieve_content(
            corpus, revision, claim, surface, session.config.company, session.config.role, fts
        )
        if history:
            transitions = retrieve_transitions(
                corpus,
                intent_for(history[-1].question),
                history[-1].critique.answer_features,
                claim,
                [intent_for(t.question).value for t in history],
            )
    plan, selected, selected_transitions = make_question_plan(
        claim, surface, attack, matches, transitions, session.effective_style, history
    )
    provenance = QuestionProvenance(
        resume_statement_id=claim.statement_id,
        atomic_claim_id=claim.id,
        attack_surface_id=surface.id,
        corpus_match_ids=plan.corpus_match_ids,
        probe_pattern_ids=plan.pattern_ids,
        transition_ids=plan.transition_ids,
        challenge_operator=plan.operator,
        style_profile_id=plan.style_profile_id,
        style_backoff_path=plan.style_backoff_path,
        adaptation_reason=plan.adaptation_reason,
        corpus_support=max((p.quality for _, p in selected), default=0),
        style_confidence=session.effective_style.confidence,
        origin="corpus" if selected or selected_transitions else "authored_baseline",
    )
    view = InterviewerView(
        claim=blind_claim(claim),
        surface=surface,
        plan=plan,
        style=session.effective_style,
        history=[
            SpokenTurn(
                id=t.id, question=t.question.text, answer=t.answer.spoken_answer, subtopic=t.question.subtopic
            )
            for t in history
        ],
        abstract_patterns=[p.abstract_pattern for _, p in selected],
        depth=len(history),
    )
    raw_questions = [q.text for c in corpus.cases for q in c.questions] if corpus else []
    question = Interviewer(client).ask(
        view,
        f"q{len(session.transcript) + 1}",
        provenance,
        raw_questions,
        [t.question.text for t in session.transcript],
    )
    answer = RepositoryAnswerer(client).answer(question, claim, session.evidences)
    critique = critique_answer(
        claim,
        surface,
        question,
        answer.spoken_answer,
        [(t.question.text, t.answer.spoken_answer) for t in history],
        client,
    )
    gaps = [AnswerGap(description=x) for x in [*critique.missing_facets, *critique.contradictions]]
    turn = InterviewTurn(
        id=f"t{len(session.transcript) + 1}",
        question=question,
        answer=answer,
        critique=critique,
        attack_plan=attack,
        answer_gaps=gaps,
        weaknesses_observed=[g.description for g in gaps],
    )
    graph, new = merge_graph(session.knowledge_graph, extract_knowledge(claim, turn, client))
    turn.new_knowledge_ids = new
    match_refs = {m.id: m for m in session.corpus_matches}
    match_refs.update({m.id: m for m, _ in selected})
    transition_refs = {t.id: t for t in session.corpus_transitions}
    if session.corpus_pin:
        transition_refs.update(
            {
                t.id: TransitionRef(
                    id=t.id,
                    revision=session.corpus_pin.revision,
                    example_question_id=t.example_question_id,
                    from_question_id=t.from_question_id,
                )
                for t in selected_transitions
            }
        )
    candidate = session.model_dump()
    candidate.update(
        status="running",
        transcript=[*session.transcript, turn],
        knowledge_graph=graph,
        attack_surfaces=update_coverage(session.attack_surfaces, question, critique, turn.id),
        corpus_matches=list(match_refs.values()),
        corpus_transitions=list(transition_refs.values()),
    )
    for c in candidate["claims"]:
        if c["id"] == claim.id:
            c["answerability"] = answer.answerability
    if len(candidate["transcript"]) >= session.config.max_turns:
        candidate.update(status="completed", stop_reason="max_turns")
    for c in candidate["claims"]:
        if c["mastery"]["status"] == "interview_ready":
            nodes = [n for n in graph.nodes if c["id"] in n.source_claims]
            if any(n.mastery.status != "interview_ready" for n in nodes):
                c["mastery"]["status"] = "needs_practice"
    updated = InterviewSession.model_validate(candidate)
    cards, tasks = build_learning(updated)
    updated = InterviewSession.model_validate(
        {**updated.model_dump(), "study_cards": cards, "study_plan": tasks}
    )
    updated.review = review_session(updated)
    session.__dict__.update(updated.__dict__)
    return True


def review_session(session):
    counts = Counter(t.question.claim_id for t in session.transcript)
    tested = [c for c in session.claims if counts[c.id]]

    def by_signal(signal):
        return [t.id for t in session.transcript if signal in t.critique.answer_features]

    return PostInterviewReview(
        claim_coverage={c.id: counts[c.id] for c in session.claims},
        strongly_defended_claims=[c.id for c in tested if c.answerability == "high"],
        weakly_defended_claims=[c.id for c in tested if c.answerability in {"low", "medium"}],
        unsupported_claims=list(
            dict.fromkeys(x for t in session.transcript for x in t.answer.unsupported_claims)
        ),
        knowledge_gaps=[task.root_knowledge_gap for task in session.study_plan],
        engineering_gaps=by_signal("no_implementation"),
        decision_making_gaps=by_signal("no_decision"),
        failure_mode_gaps=by_signal("failure_gap"),
        evaluation_gaps=by_signal("no_measurement"),
        recommended_next_round=[
            f"练习并复测 {task.node_id}: {task.root_knowledge_gap}" for task in session.study_plan[:5]
        ]
        + [f"尚未覆盖 {c.id}: {c.proposition}" for c in session.claims if not counts[c.id]][:3],
        study_tasks=[t.id for t in session.study_plan],
        knowledge_graph_update=[n.id for n in session.knowledge_graph.nodes],
    )
