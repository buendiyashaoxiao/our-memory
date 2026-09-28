"""Parser registry. Add new adapters to ``PARSERS`` (see docs/ADDING_A_PARSER.md)."""

from __future__ import annotations

from pathlib import Path

from memory_museum.parsers.base import ChatParser, ImportReport, ParsedMessage, read_text_head
from memory_museum.parsers.generic_csv import GenericCSVParser
from memory_museum.parsers.generic_json import GenericJSONParser
from memory_museum.parsers.generic_txt import GenericTXTParser

PARSERS: list[ChatParser] = [
    GenericJSONParser(),
    GenericCSVParser(),
    GenericTXTParser(),
]


def get_parser(name: str) -> ChatParser:
    for p in PARSERS:
        if p.name == name:
            return p
    raise KeyError(f"unknown parser {name!r}; available: {', '.join(p.name for p in PARSERS)}")


def detect_parser(path: Path) -> ChatParser | None:
    head = read_text_head(path)
    scored = [(p.sniff(path, head), p) for p in PARSERS]
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        return None
    return max(scored, key=lambda s: s[0])[1]


__all__ = ["PARSERS", "ChatParser", "ImportReport", "ParsedMessage", "detect_parser", "get_parser"]
