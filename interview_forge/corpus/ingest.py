"""Compile user-owned posts. No source commands, HTML or code are executed."""

import json
from pathlib import Path
from interview_forge.materials.reader import read_document, SUPPORTED_EXTENSIONS
from .normalize import normalize_post
from .dedup import group_duplicates
from .chains import compile_chains
from .patterns import compile_patterns
from .style import compile_styles
from .models import CompiledCorpus
from .storage import CorpusStore

FORMATS = SUPPORTED_EXTENSIONS | {".json", ".jsonl"}


def read_posts(path, client=None, ocr="auto", ocr_language="chi_sim+eng"):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("Corpus sources must be regular files of at most 25 MiB")
    if path.suffix.casefold() in {".json", ".jsonl"}:
        text = path.read_text(encoding="utf-8-sig")
        if path.suffix.casefold() == ".jsonl":
            values = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            parsed = json.loads(text)
            values = (
                parsed
                if isinstance(parsed, list)
                else (
                    parsed["cases"]
                    if isinstance(parsed, dict) and isinstance(parsed.get("cases"), list)
                    else [parsed]
                )
            )
        if len(values) > 500:
            raise ValueError("Corpus input exceeds 500 posts; split the file")
        return values
    document = read_document(path, client=client, ocr=ocr, ocr_language=ocr_language)
    return [
        {
            "text": "\n".join(block.text for block in document.blocks),
            "source_locations": [block.location for block in document.blocks],
            "reader_warnings": document.warnings,
        }
    ]


def compile_corpus(cases):
    cases = group_duplicates(sorted(cases, key=lambda c: c.id))
    transitions = []
    for case in cases:
        chains, links = compile_chains(case)
        case.chains = chains
        transitions.extend(links)
    patterns = compile_patterns(cases, transitions)
    return CompiledCorpus(
        cases=cases,
        transitions=transitions,
        patterns=patterns,
        style_profiles=compile_styles(cases, transitions),
    )


def ingest(paths, db_path, client=None, *, ocr="auto", ocr_language="chi_sim+eng"):
    files = []
    for given in paths:
        path = Path(given).expanduser()
        if path.is_symlink():
            raise ValueError("Corpus input cannot be a symlink")
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_file() and not candidate.is_symlink() and candidate.suffix.casefold() in FORMATS:
                if (
                    any(part.startswith(".") for part in candidate.relative_to(path).parts)
                    if path.is_dir()
                    else False
                ):
                    continue
                files.append(candidate.resolve())
                if len(files) > 200:
                    raise ValueError("Corpus ingest batch exceeds 200 files")
    files = list(dict.fromkeys(files))
    if not files:
        raise ValueError("No supported corpus files found")
    store = CorpusStore(db_path)
    revision = store.current() if store.path.exists() else None
    existing = store.load(revision).cases if revision else []
    updated = []
    for path in files:
        for index, post in enumerate(read_posts(path, client, ocr, ocr_language)):
            updated.append(normalize_post(post, str(path), index, client))
    # Replace all records from a changed file; keep other files, and commit the entire batch.
    sources = {str(path) for path in files}
    compiled = compile_corpus([c for c in existing if c.source_file not in sources] + updated)
    return store.commit(compiled, expected_revision=revision)


def rebuild(db_path):
    store = CorpusStore(db_path)
    revision = store.current()
    return store.commit(compile_corpus(store.load(revision).cases), expected_revision=revision)
