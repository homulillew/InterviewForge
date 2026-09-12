"""Refresh live library retrieval while retaining immutable session citation snapshots."""
from pathlib import Path
import re

from interview_forge.materials.library import MaterialLibrary, search_items
from interview_forge.quality import question_quality


def material_context(session, query, kind, limit=4, focus=None):
    if session.config.library_path:
        items = MaterialLibrary(Path(session.config.library_path)).items()
    else:
        items = session.materials
    if kind == "interview":
        used = {re.sub(r"\W+", "", turn.question.material_question.casefold())
                for turn in session.transcript if turn.question.material_question}
        # Filter before ranking/truncation so exhausted high-ranked items cannot hide new questions.
        items = [item for item in items if any(
            0 < len(text) <= 1200 and question_quality(text)[0]
            and re.sub(r"\W+", "", text.casefold()) not in used
            for text in [item.question, *item.followups])]
    return search_items(items, query, kind=kind, limit=limit, focus=focus)


def merge_snapshots(session, items):
    snapshots = {item.id: item for item in session.materials}
    for item in items:
        snapshots.setdefault(item.id, item.model_copy(deep=True))
    return list(snapshots.values())
