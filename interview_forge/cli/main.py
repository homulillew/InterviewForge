import argparse
from pathlib import Path
import sys

from interview_forge.interview.engine import advance, start_session
from interview_forge.interview.retest import begin_retest, grade_retest, record_submission, review_retest
from interview_forge.knowledge.graph import tree_view
from interview_forge.llm import ProviderError, make_client
from interview_forge.schemas.models import SessionConfig
from interview_forge.storage.reports import export_reports
from interview_forge.storage.session import SessionStore


def positive(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return n


def parser():
    p = argparse.ArgumentParser(prog="interview-forge", description="Resume → grounded interview → targeted learning → human retest")
    sub = p.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="Extract claims and build repository evidence snapshot")
    start.add_argument("--resume", type=Path, required=True)
    start.add_argument("--repo", type=Path, required=True)
    start.add_argument("--jd", type=Path)
    start.add_argument("--provider", choices=["offline", "compatible"], default="offline")
    start.add_argument("--base-url")
    start.add_argument("--model")
    start.add_argument("--max-turns", type=positive, default=12)
    start.add_argument("--max-depth", type=positive, default=5)
    start.add_argument("--deep-dive", action="store_true")
    start.add_argument("--run", action="store_true", help="Run simulation immediately after setup")
    commands = {"start": start}
    for name, help_text in {
        "run": "Continue the simulation", "pause": "Pause a simulation", "resume": "Resume a paused simulation",
        "status": "Show saved progress", "score": "Show answerability and human mastery separately",
        "report": "Regenerate Markdown/JSON artifacts", "tree": "Show knowledge tree",
        "retest": "Ask one human retest question without reference", "answer": "Submit human retest answer",
        "grade-retest": "Retry feedback for an already saved answer",
        "review-retest": "Record an explicit human rubric review", "reset": "Archive and reset interview history",
    }.items():
        commands[name] = sub.add_parser(name, help=help_text)
    for cmd in commands.values():
        cmd.add_argument("--session", type=Path, required=True)
    for name in ("run", "resume"):
        commands[name].add_argument("--turns", type=positive, help="Run only this many additional turns")
    commands["retest"].add_argument("--node")
    commands["grade-retest"].add_argument("--attempt")
    answers = commands["answer"].add_mutually_exclusive_group(required=True)
    answers.add_argument("--text")
    answers.add_argument("--file", type=Path)
    review = commands["review-retest"]
    review.add_argument("--attempt", required=True)
    review.add_argument("--score", type=float, required=True)
    review.add_argument("--rationale", required=True)
    review.add_argument("--missed", action="append", default=[])
    schema = sub.add_parser("schemas", help="Export all JSON Schemas")
    schema.add_argument("--output", type=Path, default=Path("schemas"))
    return p


def run_loop(session, store, limit=None):
    if session.status == "paused":
        raise ValueError("Session paused; use resume")
    client = make_client(session.config)
    count = 0
    while limit is None or count < limit:
        if not advance(session, client):
            store.save(session)
            break
        store.save(session)
        count += 1
        turn = session.transcript[-1]
        print(f"{turn.id} [{turn.question.claim_id}/L{turn.question.level}] {turn.question.text}", flush=True)
    export_reports(store, session)
    print(f"Saved {len(session.transcript)} turns; status={session.status}; {store.directory}")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "schemas":
            from interview_forge.schemas.export import export_schemas
            export_schemas(args.output)
            print(args.output)
            return 0
        store = SessionStore(args.session)
        with store.lock():
            if args.command == "start":
                if store.path.exists():
                    raise ValueError("Session already exists; use resume or a new session directory")
                # Do not place state in the repository root or an ancestor of the repository.
                if args.repo.resolve().is_relative_to(args.session.resolve()):
                    raise ValueError("Session must not be the repository root or its ancestor")
                config = SessionConfig(provider=args.provider, model=args.model, base_url=args.base_url,
                    max_turns=args.max_turns, max_depth=args.max_depth, deep_dive=args.deep_dive)
                session = start_session(args.resume.read_text(encoding="utf-8"), args.repo,
                    args.jd.read_text(encoding="utf-8") if args.jd else "", config, args.session)
                store.save(session)
                export_reports(store, session)
                print(f"Created {len(session.claims)} claims, {len(session.evidences)} evidence excerpts ({config.provider})")
                if args.run:
                    run_loop(session, store)
                return 0
            session = store.load()
            if args.command in {"run", "resume"}:
                if args.command == "resume" and session.status == "paused":
                    session.status = "running"
                run_loop(session, store, args.turns)
            elif args.command == "pause":
                if session.status == "completed":
                    raise ValueError("Completed session cannot be paused")
                session.status = "paused"
                store.save(session)
                print("Paused")
            elif args.command == "reset":
                session = store.archive_reset(session)
                export_reports(store, session)
                print("Previous state archived; interview reset")
            elif args.command == "retest":
                session, attempt = begin_retest(session, args.node)
                store.save(session)
                export_reports(store, session)
                print(f"{attempt.id} · {attempt.node_id}\n{attempt.question.text}")
            elif args.command in {"answer", "grade-retest"}:
                if args.command == "answer":
                    text = args.text if args.text is not None else args.file.read_text(encoding="utf-8")
                    session, attempt = record_submission(session, text)
                    store.save(session)
                    export_reports(store, session)
                    print(f"Answer {attempt.id} saved. If feedback fails, use grade-retest.", flush=True)
                    attempt_id = attempt.id
                else:
                    attempt_id = args.attempt
                session, attempt = grade_retest(session, make_client(session.config), attempt_id)
                store.save(session)
                export_reports(store, session)
                print(attempt.assessment.model_dump_json(indent=2))
                print("\nReference (after submission):\n" + attempt.reference.direct_interview_answer)
            elif args.command == "review-retest":
                session = review_retest(session, args.attempt, args.score, args.rationale, args.missed)
                store.save(session)
                export_reports(store, session)
                print("Human review saved; readiness requires two distinct, reviewed passing answers")
            elif args.command == "tree":
                print(tree_view(session.knowledge_graph))
            elif args.command == "report":
                export_reports(store, session)
                print(store.directory / "post_interview_review.md")
            elif args.command == "score":
                for claim in session.claims:
                    print(f"{claim.id}: answerability={claim.answerability}; mastery={claim.mastery.status}")
            else:
                print(f"{session.id}: {session.status}; turns={len(session.transcript)}/{session.config.max_turns}; provider={session.config.provider}")
                for attempt in session.retests:
                    if attempt.human_answer is None:
                        print(f"{attempt.id}: awaiting candidate answer")
                    elif attempt.reference is None or attempt.assessment is None:
                        print(f"{attempt.id}: answer saved, feedback pending; use grade-retest")
        return 0
    except (OSError, ValueError, ProviderError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
