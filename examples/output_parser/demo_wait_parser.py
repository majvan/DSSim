#!/usr/bin/env python3
# Copyright 2026- majvan (majvan@gmail.com)
"""
Validate output from:
  - examples/pubsub/Demo wait.py
  - examples/pubsub/Demo wait (mutex).py
  - examples/pubsub/Demo wait (signal).py

Checks focus on event-sequence correctness and final summary-table consistency.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
TIME_LINE_RE = re.compile(r"^\s*(?P<time>\d+)\s+(?P<body>.+?)\s*$")

GOING_RE = re.compile(r"^(?P<prince>Prince\.\d+)\s+going to live till\s+(?P<live>\d+)$")
VIVE_RE = re.compile(r"^(?P<prince>Prince\.\d+)\s+Vive le roi!$")
KING_DIED_RE = re.compile(r"^(?P<prince>Prince\.\d+)\s+Le roi est mort\.$")
DIED_WAITING_RE = re.compile(r"^(?P<prince>Prince\.\d+)\s+dies before getting to the throne$")

TABLE_HEADER_RE = re.compile(r"^\s*king\s+from\s+to\s+duration\s*$")
TABLE_ROW_RE = re.compile(r"^\s*(?P<name>Prince\.\d+|no king)\s+(?P<frm>\d+)\s+(?P<to>\d+)\s+(?P<dur>\d+)\s*$")


@dataclass
class Issue:
    code: str
    line_no: int
    message: str


@dataclass
class TableRow:
    name: str
    frm: int
    to: int
    dur: int
    line_no: int


def _strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def parse_demo_wait_output(lines: Iterable[str]) -> Tuple[List[Issue], Counter]:
    issues: List[Issue] = []

    def add_issue(code: str, line_no: int, message: str) -> None:
        issues.append(Issue(code=code, line_no=line_no, message=message))

    live_till: Dict[str, int] = {}
    born_at: Dict[str, int] = {}
    became_king_at: Dict[str, int] = {}
    died_waiting_at: Dict[str, int] = {}
    king_died_at: Dict[str, int] = {}
    current_king: Optional[str] = None
    table_rows: List[TableRow] = []
    in_table = False
    max_event_time = 0

    for line_no, raw in enumerate(lines, 1):
        line = _strip_ansi(raw.rstrip("\n"))
        if not line.strip():
            continue

        if TABLE_HEADER_RE.match(line):
            in_table = True
            continue

        if in_table:
            m = TABLE_ROW_RE.match(line)
            if m:
                table_rows.append(
                    TableRow(
                        name=m.group("name"),
                        frm=int(m.group("frm")),
                        to=int(m.group("to")),
                        dur=int(m.group("dur")),
                        line_no=line_no,
                    )
                )
            continue

        tm = TIME_LINE_RE.match(line)
        if not tm:
            continue
        t = int(tm.group("time"))
        body = tm.group("body")
        if t > max_event_time:
            max_event_time = t

        m = GOING_RE.match(body)
        if m:
            prince = m.group("prince")
            lt = int(m.group("live"))
            if prince in live_till:
                add_issue("duplicate_going_line", line_no, f"{prince} has multiple 'going to live till' lines.")
            live_till[prince] = lt
            born_at[prince] = t
            if lt < t:
                add_issue("live_till_before_birth", line_no, f"{prince} live_till={lt} before event time={t}.")
            continue

        m = VIVE_RE.match(body)
        if m:
            prince = m.group("prince")
            if prince not in live_till:
                add_issue("king_without_birth", line_no, f"{prince} became king before 'going to live till'.")
            else:
                if t > live_till[prince]:
                    add_issue(
                        "became_king_after_deadline",
                        line_no,
                        f"{prince} became king at {t}, live_till={live_till[prince]}.",
                    )
            if prince in died_waiting_at:
                add_issue("king_after_waiting_death", line_no, f"{prince} became king after waiting death.")
            if prince in became_king_at:
                add_issue("duplicate_vive", line_no, f"{prince} has multiple 'Vive le roi!' lines.")
            if current_king is not None and current_king != prince:
                add_issue(
                    "overlapping_kings",
                    line_no,
                    f"{prince} became king while current king is {current_king}.",
                )
            became_king_at[prince] = t
            current_king = prince
            continue

        m = KING_DIED_RE.match(body)
        if m:
            prince = m.group("prince")
            if prince not in became_king_at:
                add_issue("king_death_without_reign", line_no, f"{prince} died as king without becoming king.")
            if prince in king_died_at:
                add_issue("duplicate_king_death", line_no, f"{prince} has multiple 'Le roi est mort.' lines.")
            if prince in live_till and t != live_till[prince]:
                add_issue(
                    "king_death_time_mismatch",
                    line_no,
                    f"{prince} king death at {t}, expected {live_till[prince]}.",
                )
            if current_king != prince:
                add_issue(
                    "king_death_wrong_current",
                    line_no,
                    f"{prince} died as king but current king is {current_king}.",
                )
            king_died_at[prince] = t
            if current_king == prince:
                current_king = None
            continue

        m = DIED_WAITING_RE.match(body)
        if m:
            prince = m.group("prince")
            if prince not in live_till:
                add_issue(
                    "waiting_death_without_birth",
                    line_no,
                    f"{prince} died waiting before 'going to live till'.",
                )
            else:
                if t != live_till[prince]:
                    add_issue(
                        "waiting_death_time_mismatch",
                        line_no,
                        f"{prince} died waiting at {t}, expected {live_till[prince]}.",
                    )
            if prince in became_king_at:
                add_issue("waiting_death_after_king", line_no, f"{prince} died waiting after becoming king.")
            if prince in died_waiting_at:
                add_issue("duplicate_waiting_death", line_no, f"{prince} has multiple waiting-death lines.")
            died_waiting_at[prince] = t
            continue

    # Post event-sequence checks.
    for prince, lt in live_till.items():
        is_king = prince in became_king_at
        died_waiting = prince in died_waiting_at
        if is_king and died_waiting:
            add_issue("dual_outcome_prince", 0, f"{prince} both became king and died waiting.")
        if (not is_king) and (not died_waiting) and lt <= max_event_time:
            add_issue(
                "missing_prince_outcome",
                0,
                f"{prince} has no outcome by time {max_event_time} (live_till={lt}).",
            )
        if is_king and prince not in king_died_at and lt <= max_event_time:
            add_issue(
                "missing_king_death",
                0,
                f"{prince} became king but has no king-death event by time {max_event_time}.",
            )

    # Table checks.
    seen_king_rows: Dict[str, int] = {}
    for idx, row in enumerate(table_rows):
        if row.dur != row.to - row.frm:
            add_issue(
                "table_duration_mismatch",
                row.line_no,
                f"Row {row.name} duration {row.dur} != {row.to - row.frm}.",
            )
        if idx > 0:
            prev = table_rows[idx - 1]
            if row.frm != prev.to:
                add_issue(
                    "table_gap_or_overlap",
                    row.line_no,
                    f"Row {row.name} starts at {row.frm}, previous ended at {prev.to}.",
                )
        if row.name.startswith("Prince."):
            seen_king_rows[row.name] = seen_king_rows.get(row.name, 0) + 1
            if row.name not in became_king_at:
                add_issue(
                    "table_king_not_in_events",
                    row.line_no,
                    f"Table contains {row.name}, but no 'Vive le roi!' event.",
                )
            else:
                if row.frm != became_king_at[row.name]:
                    add_issue(
                        "table_from_mismatch",
                        row.line_no,
                        f"Table row {row.name} from={row.frm}, expected {became_king_at[row.name]}.",
                    )
            if row.name in live_till and row.to != live_till[row.name]:
                add_issue(
                    "table_to_mismatch",
                    row.line_no,
                    f"Table row {row.name} to={row.to}, expected live_till={live_till[row.name]}.",
                )

    for prince, count in seen_king_rows.items():
        if count > 1:
            add_issue("duplicate_table_king_row", 0, f"{prince} appears {count}x in table.")

    for prince in became_king_at:
        if seen_king_rows.get(prince, 0) == 0:
            add_issue("missing_table_king_row", 0, f"{prince} became king but is missing from table.")

    return issues, Counter(i.code for i in issues)


def _iter_input(path: Optional[str]) -> Iterable[str]:
    if path is None or path == "-":
        return sys.stdin
    return open(path, "r", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate Demo wait parity example output.")
    ap.add_argument("input", nargs="?", default="-", help="Path to log file (default: stdin).")
    args = ap.parse_args()

    with _iter_input(args.input) as f:
        issues, summary = parse_demo_wait_output(f)

    if not issues:
        print("OK: demo wait output is consistent.")
        return 0

    print("ISSUES:")
    for i in issues:
        ln = f"line={i.line_no}" if i.line_no else "line=?"
        print(f"- [{i.code}] {ln}: {i.message}")
    print("\nSUMMARY:")
    for code, count in sorted(summary.items()):
        print(f"- {code}: {count}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
