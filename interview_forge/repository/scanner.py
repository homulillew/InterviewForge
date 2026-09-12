"""Bounded text snapshot with exact, traceable evidence. Never executes target code."""
import ast
import hashlib
import os
from pathlib import Path
import re
import subprocess

from interview_forge.curricula import TOPICS, topic_for
from interview_forge.schemas.models import CapabilityClaim, RepoEvidence, RepositoryMap

SKIP_DIRS = {".interviewforge", ".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache", "sessions", ".idea"}
EXTENSIONS = {".py", ".java", ".go", ".js", ".ts", ".tsx", ".rs", ".lua", ".sql", ".md", ".txt", ".toml", ".json", ".yaml", ".yml", ".xml", ".sh", ".gradle", ".properties"}
SECRET_FILE = re.compile(r"(^\.env($|\.)|credential|secret|id_rsa|id_ed25519|\.pem$|\.key$)", re.I)
SECRET_LINE = re.compile(r"(?:api[_-]?key|password|secret|access[_-]?token)\s*[=:]\s*[\"']?[^\s\"']{8,}|-----BEGIN .*PRIVATE KEY|(?:sk-|ghp_)[A-Za-z0-9_-]{16,}", re.I)
SECTIONS = ("README", "Languages", "Dependencies", "Directory Structure", "Entry Points", "Core Modules", "Data Flow", "API", "Database", "Config", "Infrastructure", "Tests", "Evaluation", "Deployment", "Scripts", "Observability", "Performance")


def classify(path: str) -> str:
    lower = path.lower()
    name = Path(path).name.lower()
    if "test" in lower:
        return "test"
    if any(x in lower for x in ("eval", "benchmark", "perf")):
        return "evaluation"
    if name in {"requirements.txt", "pyproject.toml", "package.json", "pom.xml", "go.mod", "cargo.toml", "build.gradle"}:
        return "dependency"
    if Path(path).suffix == ".md":
        return "documentation"
    if Path(path).suffix in {".json", ".yaml", ".yml", ".toml", ".properties"}:
        return "config"
    return "implementation"


def scan_repository(root: Path, claims: list[CapabilityClaim], exclude: Path | None = None,
                    max_files: int = 300, max_bytes: int = 2_000_000, excludes: list[Path] | None = None):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Repository must be a directory")
    skipped = []
    try:
        actual_root = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        is_repo = actual_root.returncode == 0 and Path(actual_root.stdout.strip()).resolve() == root
        revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip() if is_repo else None
        if is_repo:
            result = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True, timeout=10, check=True)
            candidates = sorted(set(result.stdout.decode().split("\0")) - {""})
        else:
            candidates = []
            for base, dirs, files in os.walk(root, followlinks=False):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(base)/d).is_symlink())
                candidates.extend(str((Path(base)/f).relative_to(root)) for f in sorted(files))
    except (OSError, subprocess.SubprocessError):
        raise ValueError("Cannot enumerate repository safely") from None
    repo_map = RepositoryMap(root=str(root), revision=revision or None, sections={s: [] for s in SECTIONS})
    evidence = []
    total_bytes = 0
    for relative in candidates:
        path = root / relative
        if any(p in SKIP_DIRS for p in Path(relative).parts):
            continue
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root and root in p.parents):
            skipped.append(relative + ": symlink")
            continue
        resolved = path.resolve()
        excluded = [*(excludes or []), *([exclude] if exclude else [])]
        if not resolved.is_relative_to(root) or any(resolved.is_relative_to(p.resolve()) for p in excluded):
            continue
        if SECRET_FILE.search(path.name):
            skipped.append(relative + ": sensitive filename")
            continue
        if path.suffix.lower() not in EXTENSIONS and path.name not in {"Dockerfile", "Makefile", "go.mod"}:
            continue
        try:
            size = path.stat().st_size
            if size > 128_000:
                skipped.append(relative + ": file exceeds 128KB")
                continue
            if len(repo_map.files) >= max_files or total_bytes + size > max_bytes:
                skipped.append("snapshot budget reached; remaining files unscanned")
                break
            raw = path.read_bytes()
            content = raw.decode("utf-8")
        except (OSError, UnicodeError):
            skipped.append(relative + ": unreadable/non-UTF8")
            continue
        if "\0" in content:
            continue
        if SECRET_LINE.search(content):
            skipped.append(relative + ": possible credential; omitted entire file")
            continue
        total_bytes += len(raw)
        repo_map.files.append(relative)
        ext = path.suffix or path.name
        repo_map.languages[ext] = repo_map.languages.get(ext, 0) + 1
        kind = classify(relative)
        section = {"test": "Tests", "evaluation": "Evaluation", "dependency": "Dependencies", "documentation": "README", "config": "Config", "implementation": "Core Modules"}[kind]
        repo_map.sections[section].append(relative)
        for key, pattern in {"Entry Points": r"(__main__|main\(|app\.run|listen\()", "API": r"(@.*route|@.*\.(get|post)|http|router)",
                             "Database": r"(SELECT |INSERT |CREATE TABLE|sqlalchemy)", "Deployment": r"(Dockerfile|docker|kubernetes)",
                             "Observability": r"(logging|logger|prometheus|tracing)", "Performance": r"(benchmark|latency|p99)",
                             "Infrastructure": r"(terraform|ansible|helm)", "Scripts": r"(#!/|\.sh$)"}.items():
            if re.search(pattern, relative + "\n" + content, re.I):
                repo_map.sections[key].append(relative)
        symbols = []
        if path.suffix == ".py":
            try:
                symbols = [(n.name, n.lineno, n.end_lineno) for n in ast.walk(ast.parse(content)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            except SyntaxError:
                skipped.append(relative + ": Python AST parse failed; text retained")
        repo_map.symbols[relative] = [s[0] for s in symbols]
        lines = content.splitlines()
        for start in range(0, len(lines), 40):
            excerpt = "\n".join(lines[start:start+40])
            if not excerpt.strip() or len(excerpt) > 16000:
                continue
            lower = (relative + "\n" + excerpt).lower()
            linked = []
            for claim in claims:
                key = topic_for(claim.topic)
                terms = TOPICS[key].aliases if key != "service" else tuple(set(re.findall(r"[a-zA-Z][a-zA-Z0-9_+]{2,}", claim.source_quote.lower()))) + TOPICS[key].aliases
                if any(t in lower for t in terms) or (key == "service" and kind in {"implementation", "test"}):
                    linked.append(claim.id)
            if not linked:
                continue
            eid = "e" + hashlib.sha256(f"{relative}:{start}:{excerpt}".encode()).hexdigest()[:14]
            symbol = next((name for name, a, b in symbols if a <= start+1 <= (b or a)), None)
            evidence.append(RepoEvidence(id=eid, file_path=relative, symbol=symbol, line_start=start+1,
                line_end=min(start+40, len(lines)), evidence_type=kind, summary=f"Source excerpt ({kind}); relevance is a search hypothesis",
                excerpt=excerpt, sha256=hashlib.sha256(raw).hexdigest(), confidence=0.65 if kind == "implementation" else 0.4,
                related_claim_ids=linked, limitations=["Static source observation; not runtime verification, ownership or measured improvement."]))
    repo_map.skipped = skipped
    repo_map.sections["Languages"] = sorted(repo_map.languages)
    repo_map.sections["Directory Structure"] = sorted({str(Path(p).parent) for p in repo_map.files})
    repo_map.limitations = ["Bounded static scan; omitted or unmatched code remains unverified.",
                           "Data Flow requires semantic inspection; file categories are search hints, not confirmed architecture.",
                           "Possible credentials are filtered heuristically; review inputs before using a remote provider."]
    for c in claims:
        c.evidence_ids = [e.id for e in evidence if c.id in e.related_claim_ids]
    return repo_map, evidence
