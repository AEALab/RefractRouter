from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from pathlib import Path

from .schemas import SourceDocument, TaskDAG


_SOURCE_ID_PATTERN = re.compile(r"source_\d{3}")


def load_source_pack(directory: str | Path) -> tuple[SourceDocument, ...]:
    source_dir = Path(directory)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source pack directory does not exist: {source_dir}")

    documents: list[SourceDocument] = []
    seen_ids: set[str] = set()
    for path in sorted(source_dir.glob("*.md")):
        source_id = path.stem
        if not _SOURCE_ID_PATTERN.fullmatch(source_id):
            raise ValueError(f"Invalid source filename: {path.name}")
        if source_id in seen_ids:
            raise ValueError(f"Duplicate source id: {source_id}")

        raw = path.read_text(encoding="utf-8")
        lines = raw.splitlines()
        if not lines or not lines[0].startswith("# "):
            raise ValueError(f"Source must start with a level-one title: {path}")
        title = lines[0][2:].strip()
        content = "\n".join(lines[1:]).strip()
        if not title or not content:
            raise ValueError(f"Source title and content must be non-empty: {path}")

        documents.append(
            SourceDocument(
                source_id=source_id,
                title=title,
                content=content,
                content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            )
        )
        seen_ids.add(source_id)

    if not documents:
        raise ValueError(f"Source pack contains no Markdown sources: {source_dir}")
    return tuple(documents)


def attach_source_pack(task: TaskDAG, source_pack_root: str | Path) -> TaskDAG:
    if task.source_pack_id is None:
        return task
    directory = Path(source_pack_root) / task.source_pack_id
    return replace(task, source_documents=load_source_pack(directory))
