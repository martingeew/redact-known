"""
redact_known.py

Sanitises every CSV in a folder before any of it is shown to an LLM.

Two layers of redaction, applied with one shared mapping and one shared
column list across every file in the input folder:
  - Shape-based identifiers (account number, email, phone, tax ID) are
    found and replaced automatically with regex. The two ACCOUNT_NUMBER
    patterns and TAX_ID below are representative shapes, not universal
    ones - resize the digit counts and separators to match your own bank
    or country, or add another pattern under the same entity type.
  - Name-shaped values have no predictable pattern, so they come from a
    small local mapping file you fill in yourself (mapping.json), never
    pasted into any AI conversation. One mapping file covers every kind of
    detail (names, account holders, anything else you recognise by eye) -
    the entity type plus the real string is the lookup key, so there's no
    need for a separate file per account.

Placeholders are STABLE and shared across the whole run: the same real
value always gets the same placeholder in every file it appears in, so
patterns across months ("this person paid three times") survive.

Inputs:
    --input     Folder of raw CSVs. Every *.csv in it is processed.
    --output    Folder to write sanitised copies to (created if missing).
                Each file keeps its original name.
    --mapping   Path to a local JSON file of {"real value": "placeholder"}
                pairs, e.g. {"John Smith": "<PERSON_1>"}. Optional - if
                omitted or the file doesn't exist, only the regex-based
                redaction runs.
    --columns   Comma-separated column names to scan, applied to every file.

Outputs:
    One sanitised CSV per input file in --output. Only a COUNT of
    replacements per type is printed to the terminal, never the matched
    values themselves, so the output you'd screenshot or paste stays safe.

Usage:
    python redact_known.py --input raw/ --output sanitised/ \
        --mapping mapping.json --columns "Payee,Description"
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

# Dots are reserved for DD.MM.YYYY dates in this data, so phone numbers are
# matched only on space/hyphen separators to avoid colliding with a date in
# the same free-text field (e.g. "ref 13.03.2026").
#
# Two account number shapes are shown here on purpose: an international
# one (IBAN-style letters+digits) and a domestic one (digit-and-dash).
# Both feed the same ACCOUNT_NUMBER entity type - add a third pattern the
# same way for your own bank's format.
ACCOUNT_PATTERN_INTL = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")  # e.g. IBAN
ACCOUNT_PATTERN_LOCAL = re.compile(r"\b\d{2}-\d{4}-\d{7}-\d{2,3}\b")  # e.g. NZ bank account
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_PATTERN = re.compile(r"\b(?:\+\d{1,3}[\s-])?0\d{1,4}[\s-]\d{3,10}\b")
TAX_ID_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")  # e.g. US SSN shape

# Order matters: PHONE is the loosest pattern (just a leading 0 and a
# separator), so it runs last - otherwise it partially matches inside an
# account number or tax ID before those more specific patterns get a turn.
REGEX_RULES: Tuple[Tuple[str, re.Pattern], ...] = (
    ("ACCOUNT_NUMBER", ACCOUNT_PATTERN_INTL),
    ("EMAIL", EMAIL_PATTERN),
    ("ACCOUNT_NUMBER", ACCOUNT_PATTERN_LOCAL),
    ("TAX_ID", TAX_ID_PATTERN),
    ("PHONE", PHONE_PATTERN),
)


class PlaceholderAssigner:
    """Gives each distinct real value the same placeholder everywhere."""

    def __init__(self) -> None:
        self._seen: Dict[Tuple[str, str], str] = {}
        self._counts: Counter = Counter()

    def get(self, entity_type: str, value: str) -> str:
        key = (entity_type, value)
        if key not in self._seen:
            self._counts[entity_type] += 1
            self._seen[key] = f"<{entity_type}_{self._counts[entity_type]}>"
        return self._seen[key]

    @property
    def counts(self) -> Counter:
        return self._counts


def _load_mapping(path: str | None) -> Dict[str, str]:
    if not path:
        return {}
    mapping_path = Path(path)
    if not mapping_path.exists():
        print(f"Note: mapping file '{path}' not found - skipping name redaction.")
        return {}
    return json.loads(mapping_path.read_text(encoding="utf-8"))


def _apply_mapping(text: str, mapping: Dict[str, str], counts: Counter) -> str:
    # Longest keys first, so a name that's a substring of a longer one
    # (e.g. "John" inside "John Smith") never gets swapped first by mistake.
    for real_value in sorted(mapping, key=len, reverse=True):
        if real_value and real_value in text:
            counts["MAPPED"] += text.count(real_value)
            text = text.replace(real_value, mapping[real_value])
    return text


def _apply_regex(text: str, assigner: PlaceholderAssigner) -> str:
    for entity_type, pattern in REGEX_RULES:
        text = pattern.sub(lambda m: assigner.get(entity_type, m.group(0)), text)
    return text


def redact_file(
    input_path: Path,
    output_path: Path,
    columns: list[str],
    mapping: Dict[str, str],
    assigner: PlaceholderAssigner,
    mapped_counts: Counter,
) -> int:
    frame = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"Column(s) not found in {input_path.name}: {', '.join(missing)}")

    for column in columns:
        frame[column] = frame[column].map(
            lambda value: _apply_regex(_apply_mapping(value, mapping, mapped_counts), assigner)
        )
    frame.to_csv(output_path, index=False, encoding="utf-8")
    return len(frame)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Folder of raw CSVs")
    parser.add_argument("--output", required=True, help="Folder to write sanitised CSVs to")
    parser.add_argument("--mapping", default=None, help="Path to a local {real: placeholder} JSON file")
    parser.add_argument("--columns", required=True, help="Comma-separated column names to scan")
    args = parser.parse_args()

    columns = [c.strip() for c in args.columns.split(",") if c.strip()]
    mapping = _load_mapping(args.mapping)
    assigner = PlaceholderAssigner()
    mapped_counts: Counter = Counter()

    input_dir, output_dir = Path(args.input), Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {input_dir}")
        return

    for csv_path in csv_files:
        out_path = output_dir / csv_path.name
        rows = redact_file(csv_path, out_path, columns, mapping, assigner, mapped_counts)
        print(f"Sanitised {rows} row(s): {csv_path.name} -> {out_path}")

    print("\nTotal replacements across all files (values never printed):")
    if mapped_counts["MAPPED"]:
        print(f"  MAPPED (from mapping.json): {mapped_counts['MAPPED']}")
    for entity_type, count in assigner.counts.items():
        print(f"  {entity_type}: {count}")
    if not mapped_counts and not assigner.counts:
        print("  none found")


if __name__ == "__main__":
    main()
