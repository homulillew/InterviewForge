"""CLI for a reusable interview experience and reference-answer collection."""
import json
import os
from pathlib import Path

from interview_forge.llm import make_client
from interview_forge.materials.library import MaterialLibrary
from interview_forge.materials.reader import SUPPORTED_EXTENSIONS
from interview_forge.schemas.models import SessionConfig

DEFAULT_LIBRARY = Path('.interviewforge/library')
FORMATS = SUPPORTED_EXTENSIONS


def add_library_parser(sub):
    library = sub.add_parser('library', help='Import/search interview experiences and reference answers')
    commands = library.add_subparsers(dest='library_command', required=True)
    add = commands.add_parser('add', help='Extract material from images, documents or folders')
    add.add_argument('paths', nargs='+', type=Path)
    add.add_argument('--kind', choices=['interview', 'answer'], required=True)
    add.add_argument('--tag', action='append', default=[])
    add.add_argument('--company', default='')
    add.add_argument('--role', default='')
    add.add_argument('--provider', choices=['offline', 'compatible'], default='offline')
    add.add_argument('--base-url')
    add.add_argument('--model')
    add.add_argument('--ocr-language', default='chi_sim+eng')
    add.add_argument('--ocr', choices=['auto', 'local', 'off', 'vision'], default='auto')
    listing = commands.add_parser('list', help='List imported documents')
    search = commands.add_parser('search', help='Find questions or reference answers')
    search.add_argument('query', nargs='+')
    search.add_argument('--kind', choices=['interview', 'answer'])
    search.add_argument('--limit', type=int, default=5)
    show = commands.add_parser('show', help='Show one document or extracted item')
    show.add_argument('id')
    remove = commands.add_parser('remove', help='Remove a document and its indexed items')
    remove.add_argument('id')
    for command in (add, listing, search, show, remove):
        command.add_argument('--library', type=Path, default=DEFAULT_LIBRARY)
        command.add_argument('--json', action='store_true')


def input_files(paths, library_path):
    result = []
    seen = set()
    for path in paths:
        if path.is_symlink():
            raise ValueError('Symlink imports are not supported')
        if path.is_dir():
            files = []
            for base, dirs, names in os.walk(path, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(base)/d).is_symlink()
                                 and not (Path(base)/d).resolve().is_relative_to(library_path.resolve()))
                files.extend(Path(base)/name for name in sorted(names) if Path(name).suffix.lower() in FORMATS)
        else:
            files = [path]
        for file in files:
            if file.is_symlink() or file.resolve().is_relative_to(library_path.resolve()):
                continue
            if file.resolve() not in seen:
                result.append(file)
                seen.add(file.resolve())
            if len(result) > 200:
                raise ValueError('Import batch exceeds 200 files; split the folder into smaller batches')
    if not result:
        raise ValueError('No supported input files found')
    return result


def run_library(args):
    library = MaterialLibrary(args.library)
    command = args.library_command
    if command == 'add':
        client = make_client(SessionConfig(provider=args.provider, base_url=args.base_url, model=args.model))
        documents = []
        for path in input_files(args.paths, args.library):
            document = library.add(path, kind=args.kind, client=client, tags=args.tag,
                company=args.company, role=args.role, ocr_language=args.ocr_language, ocr=args.ocr)
            documents.append(document)
            if not args.json:
                print(f'{document.id} · {document.kind} · {len(document.item_ids)} items · {document.filename}', flush=True)
                for warning in document.warnings:
                    print('Note: ' + warning, flush=True)
        if args.json:
            print(json.dumps([d.model_dump(mode='json') for d in documents], ensure_ascii=False, indent=2))
    elif command == 'list':
        documents = library.documents()
        if args.json:
            print(json.dumps([d.model_dump(mode='json') for d in documents], ensure_ascii=False, indent=2))
        else:
            for document in documents:
                print(f'{document.id} · {document.kind} · {len(document.item_ids)} items · {document.filename}')
            if not documents:
                print('Library is empty. Add an interview image/document or a reference answer.')
    elif command == 'search':
        if not 1 <= args.limit <= 50:
            raise ValueError('--limit must be between 1 and 50')
        items = library.search(' '.join(args.query), kind=args.kind, limit=args.limit)
        if args.json:
            print(json.dumps([item.model_dump(mode='json') for item in items], ensure_ascii=False, indent=2))
        else:
            for item in items:
                print(f'{item.id} [{item.kind}] {item.title}\n{item.question}\n{item.source_file} · {item.location}\n')
            if not items:
                print('No matching material.')
    elif command == 'show':
        try:
            value = library.get(args.id)
        except ValueError:
            value = library.get_item(args.id)
        print(value.model_dump_json(indent=2))
    else:
        document = library.remove(args.id)
        print(document.model_dump_json(indent=2) if args.json else f'Removed {document.id}')
    return 0
