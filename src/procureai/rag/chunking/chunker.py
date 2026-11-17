"""Section-aware chunking that preserves page numbers for citations."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s+)?[A-Z][A-Za-z0-9 ,&/\-()]{2,70}$")
TOKENS_PER_WORD = 1.3


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    page: int
    section: str


def _is_heading(line: str) -> bool:
    s = line.strip()
    if not s or s.endswith((".", ",", ";", ":")) or s == "[TABLE]":
        return False
    return len(s.split()) <= 9 and bool(_HEADING.match(s)) and (s.isupper() or s.istitle() or s[0].isdigit())


def _window(words: list[str], max_words: int, overlap_words: int) -> list[list[str]]:
    if len(words) <= max_words:
        return [words]
    step = max(1, max_words - overlap_words)
    return [words[i : i + max_words] for i in range(0, len(words), step) if words[i : i + max_words]]


def _chunk_page(page_number: int, text: str, max_words: int, overlap_words: int, start_index: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer: list[str] = []

    def flush() -> None:
        body = " ".join(" ".join(buffer).split())
        buffer.clear()
        if body:
            for win in _window(body.split(), max_words, overlap_words):
                chunks.append(Chunk(start_index + len(chunks), " ".join(win), page_number, current[0]))

    current = [""]
    for line in text.splitlines():
        if _is_heading(line):
            flush()
            current[0] = line.strip()
            buffer.append(line.strip())  # keep the heading in the chunk text for retrieval
        elif line.strip():
            buffer.append(line.strip())
    flush()
    return chunks


def chunk_pages(pages: list[tuple[int, str]], target_tokens: int = 220, overlap_tokens: int = 40) -> list[Chunk]:
    max_words = max(20, int(target_tokens / TOKENS_PER_WORD))
    overlap_words = min(int(overlap_tokens / TOKENS_PER_WORD), max_words // 2)
    chunks: list[Chunk] = []
    for page_number, text in pages:
        chunks.extend(_chunk_page(page_number, text, max_words, overlap_words, len(chunks)))
    return chunks
