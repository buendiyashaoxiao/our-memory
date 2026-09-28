"""Generic CSV / TSV chat export with a header row.

Column names are matched case-insensitively against common aliases
(``timestamp``/``time``/``时间``, ``sender``/``发送者``, ``text``/``content``/``内容`` ...).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Iterator

from memory_museum.parsers.base import (
    TEXT_KEYS,
    TS_KEYS,
    ChatParser,
    ImportReport,
    ParsedMessage,
    detect_encoding,
)
from memory_museum.parsers.records import record_to_message

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


class GenericCSVParser(ChatParser):
    name = "csv"
    description = "CSV/TSV with a header row (timestamp, sender, text, type, media, id ...)"
    extensions = (".csv", ".tsv")

    def sniff(self, path: Path, head: str) -> float:
        if path.suffix.lower() not in self.extensions:
            return 0.0
        first = head.splitlines()[0].lower() if head else ""
        hits = sum(1 for k in TS_KEYS + TEXT_KEYS if k.lower() in first)
        return 0.9 if hits else 0.3

    def parse(self, path: Path, report: ImportReport, *, tz=None) -> Iterator[ParsedMessage]:
        enc = detect_encoding(path)
        try:
            fh = path.open("r", encoding=enc, errors="replace", newline="")
        except OSError as e:
            report.issue("unreadable_file", path, None, str(e))
            return
        with fh:
            sample = fh.read(8192)
            fh.seek(0)
            if path.suffix.lower() == ".tsv":
                dialect: type[csv.Dialect] | csv.Dialect = csv.excel_tab
            else:
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
            reader = csv.DictReader(fh, dialect=dialect)
            if not reader.fieldnames:
                report.issue("malformed", path, None, "CSV has no header row")
                return
            width = len(reader.fieldnames)
            try:
                for row in reader:
                    report.records_seen += 1
                    where = f"line {reader.line_num}"
                    if None in row:  # more cells than headers
                        report.issue("malformed", path, where, f"row has more than {width} columns; extra cells kept in metadata")
                        row["_extra"] = row.pop(None)
                    if all(v in (None, "") for k, v in row.items() if k != "_extra"):
                        report.issue("malformed", path, where, "empty row")
                        continue
                    msg = record_to_message(row, source=path, where=where, report=report, tz=tz)
                    if msg:
                        yield msg
            except csv.Error as e:
                report.issue("malformed", path, f"line {reader.line_num}", f"CSV error, stopped reading file: {e}")
