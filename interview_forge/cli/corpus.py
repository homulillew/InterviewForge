"""Private corpus management and inspection."""

import json
from pathlib import Path
from interview_forge.corpus.storage import CorpusStore
from interview_forge.corpus.ingest import ingest, rebuild
from interview_forge.corpus.stats import corpus_stats
from interview_forge.llm import make_client
from interview_forge.schemas.models import SessionConfig

DEFAULT_CORPUS = Path.home() / ".interviewforge" / "corpus.sqlite3"


def add_corpus_parser(sub):
    corpus = sub.add_parser("corpus", help="Compile private interview materials into versioned local SQLite")
    actions = corpus.add_subparsers(dest="corpus_command", required=True)
    for name in ("ingest", "rebuild", "stats", "inspect"):
        command = actions.add_parser(name)
        command.add_argument("--corpus", "--db", dest="corpus", type=Path, default=DEFAULT_CORPUS)
        if name == "ingest":
            command.add_argument("paths", type=Path, nargs="+")
            command.add_argument("--provider", choices=["offline", "compatible"], default="offline")
            command.add_argument("--base-url")
            command.add_argument("--model")
            command.add_argument("--ocr", choices=["auto", "local", "vision", "off"], default="auto")
            command.add_argument("--ocr-language", default="chi_sim+eng")
        if name == "inspect":
            command.add_argument("--id", help="Case, question, pattern, transition or style ID")
            command.add_argument("--revision")
            command.add_argument("--company")
            command.add_argument("--role")


def run_corpus(args):
    store = CorpusStore(args.corpus)
    if args.corpus_command == "ingest":
        client = make_client(SessionConfig(provider=args.provider, model=args.model, base_url=args.base_url))
        revision = ingest(args.paths, store.path, client, ocr=args.ocr, ocr_language=args.ocr_language)
        print("Compiled revision: " + revision)
    elif args.corpus_command == "rebuild":
        print("Compiled revision: " + rebuild(store.path))
    elif args.corpus_command == "inspect":
        corpus = store.load(args.revision)
        records = [
            *corpus.cases,
            *corpus.patterns,
            *corpus.transitions,
            *corpus.style_profiles,
            *(q for c in corpus.cases for q in c.questions),
        ]
        selected = [r for r in records if r.id == args.id] if args.id else corpus.cases
        if not args.id:
            from interview_forge.corpus.normalize import company_name, role_name

            selected = [
                r
                for r in selected
                if (not args.company or r.company == company_name(args.company))
                and (not args.role or r.role == role_name(args.role))
            ]
        if args.id and not selected:
            raise ValueError("Unknown corpus record ID")
        print(json.dumps([r.model_dump(mode="json") for r in selected], ensure_ascii=False, indent=2))
        return 0
    print(
        json.dumps({"revision": store.current(), **corpus_stats(store.load())}, ensure_ascii=False, indent=2)
    )
    return 0
