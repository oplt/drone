"""Dependency-light versioned hybrid retrieval foundation."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalChunk:
    chunk_id: str
    text: str
    source: str
    version: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RetrievalHit:
    chunk: RetrievalChunk
    score: float
    citation: str


def chunk_document(
    text: str,
    *,
    source: str,
    version: str = "v1",
    max_chars: int = 1200,
    overlap_chars: int = 150,
    metadata: dict[str, Any] | None = None,
) -> list[RetrievalChunk]:
    if max_chars <= overlap_chars:
        raise ValueError("max_chars must be greater than overlap_chars")
    normalized = re.sub(r"\s+", " ", text).strip()
    chunks: list[RetrievalChunk] = []
    start = 0
    index = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        chunk_text = normalized[start:end].strip()
        if chunk_text:
            chunks.append(
                RetrievalChunk(
                    chunk_id=f"{version}:{source}:{index}",
                    text=chunk_text,
                    source=source,
                    version=version,
                    metadata=dict(metadata or {}),
                )
            )
            index += 1
        if end == len(normalized):
            break
        start = max(start + 1, end - overlap_chars)
    return chunks


def _terms(value: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[a-zA-Z0-9_]+", value) if len(term) > 2}


def retrieve(
    query: str,
    chunks: Iterable[RetrievalChunk],
    *,
    metadata_filter: dict[str, Any] | None = None,
    limit: int = 5,
) -> list[RetrievalHit]:
    query_terms = _terms(query)
    candidates: list[RetrievalHit] = []
    for chunk in chunks:
        if metadata_filter and any(
            chunk.metadata.get(key) != value for key, value in metadata_filter.items()
        ):
            continue
        terms = _terms(chunk.text)
        lexical = len(query_terms & terms) / max(1, len(query_terms))
        phrase_bonus = 0.25 if query.lower() in chunk.text.lower() else 0.0
        score = lexical + phrase_bonus
        if score > 0:
            candidates.append(
                RetrievalHit(
                    chunk=chunk,
                    score=score,
                    citation=f"[{chunk.source}#{chunk.chunk_id}]",
                )
            )
    return sorted(candidates, key=lambda hit: (-hit.score, hit.chunk.chunk_id))[: max(1, limit)]
