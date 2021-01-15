#!/usr/bin/env python3
# Copyright 2026- majvan (majvan@gmail.com)
"""
Validate visa_check.py textual output for sequencing issues.

Detected issues:
1) person reneging earlier than announced deadline
2) person not reneging after announced deadline
3) waiting clerk not serving although they could
4) waiting clerk closing earlier than timeout
5) waiting clerk closing after timeout

Usage:
  PYTHONPATH=. python3 examples/pubsub/visa_check.py > /tmp/visa.log
  python3 examples/output_parser/visa_check_parser.py /tmp/visa.log
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
TIME_PREFIX_RE = re.compile(r"^\s*(?P<time>\d+(?:\.\d+)?)\s+(?P<body>.+?)\s*$")

PERSON_TOKEN_RE = r"Person[A-Za-z]+\[\d+\]"
CLERK_TOKEN_RE = r"Check[A-Za-z]+\[\d+\]"

QUEUE_RE = re.compile(
    rf"^(?P<person>{PERSON_TOKEN_RE}): Queueing with max\. waiting time "
    rf"(?P<wait>\d+) at position (?P<pos>\d+)\."
)
QUEUE_TOO_LONG_RE = re.compile(
    rf"^(?P<person>{PERSON_TOKEN_RE}): queue too long, giving up, I do not queue\.$"
)
RENEGE_RE = re.compile(
    rf"^(?P<person>{PERSON_TOKEN_RE}): Giving up waiting in queue\."
)
WAIT_RE = re.compile(
    rf"^(?P<clerk>{CLERK_TOKEN_RE}): Waiting for a person"
    rf"(?: \(timeout (?P<timeout>\d+)\))?; first one is (?P<first>.+)$"
)
PROCESS_RE = re.compile(
    rf"^(?P<clerk>{CLERK_TOKEN_RE}): Going to process (?P<person>{PERSON_TOKEN_RE}) "
    rf"for (?P<busy>\d+) minutes; first one is (?P<first>.+)$"
)
CLOSE_RE = re.compile(
    rf"^(?P<clerk>{CLERK_TOKEN_RE}): No person in the queue, closing\.$"
)


EPS = 1e-9


@dataclass
class PersonState:
    name: str
    kind: str
    queue_time: float
    announced_wait: float
    deadline: float
    served_time: Optional[float] = None
    reneged_time: Optional[float] = None
    cancelled: bool = False


@dataclass
class ClerkWaitState:
    start_time: float
    timeout: Optional[float]
    line_no: int


@dataclass
class PendingServeExpectation:
    time: float
    line_no: int
    clerk_kind: str
    reason: str


@dataclass
class Issue:
    code: str
    time: float
    line_no: int
    message: str


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def entity_kind(name: str, prefix: str) -> str:
    # PersonEU[1] -> EU; CheckWW[0] -> WW
    left = name[len(prefix):]
    return left.split("[", 1)[0]


def is_clerk_eligible_for_person(clerk: str, person: str) -> bool:
    clerk_kind = entity_kind(clerk, "Check")
    person_kind = entity_kind(person, "Person")
    return person_kind in clerk_kind


def parse_log(lines: Iterable[str]) -> Tuple[List[Issue], Dict[str, int]]:
    queue: List[str] = []
    people: Dict[str, PersonState] = {}
    clerk_waiting: Dict[str, ClerkWaitState] = {}
    pending_serve: Dict[str, PendingServeExpectation] = {}
    issues: List[Issue] = []

    last_time = 0.0
    seen_any_time = False

    def add_issue(code: str, time: float, line_no: int, message: str) -> None:
        issues.append(Issue(code=code, time=time, line_no=line_no, message=message))

    def flush_pending_before(new_time: float) -> None:
        for clerk, exp in list(pending_serve.items()):
            if exp.time + EPS < new_time:
                add_issue(
                    "waiting_clerk_not_serving_if_he_could",
                    exp.time,
                    exp.line_no,
                    f"{clerk} was waiting and could serve, but did not serve at time {exp.time:g}.",
                )
                pending_serve.pop(clerk, None)

    for line_no, raw in enumerate(lines, 1):
        clean = strip_ansi(raw.rstrip("\n"))
        if not clean.strip():
            continue

        tm = TIME_PREFIX_RE.match(clean)
        if not tm:
            # Ignore non-timestamp lines (e.g. "Done.")
            continue

        t = float(tm.group("time"))
        body = tm.group("body")
        seen_any_time = True
        flush_pending_before(t)
        last_time = max(last_time, t)

        m = QUEUE_RE.match(body)
        if m:
            person = m.group("person")
            wait = float(m.group("wait"))
            people[person] = PersonState(
                name=person,
                kind=entity_kind(person, "Person"),
                queue_time=t,
                announced_wait=wait,
                deadline=t + wait,
            )
            queue.append(person)
            continue

        m = QUEUE_TOO_LONG_RE.match(body)
        if m:
            # Person never entered the queue; no waiting/reneging obligations.
            person = m.group("person")
            ps = people.get(person)
            if ps is not None:
                ps.cancelled = True
            try:
                queue.remove(person)
            except ValueError:
                pass
            continue

        m = RENEGE_RE.match(body)
        if m:
            person = m.group("person")
            ps = people.get(person)
            if ps is not None and t + EPS < ps.deadline:
                add_issue(
                    "person_reneging_earlier_than_announced",
                    t,
                    line_no,
                    f"{person} reneged at {t:g}, deadline was {ps.deadline:g}.",
                )
            if ps is not None:
                ps.reneged_time = t
            try:
                queue.remove(person)
            except ValueError:
                pass
            continue

        m = WAIT_RE.match(body)
        if m:
            clerk = m.group("clerk")
            timeout = float(m.group("timeout")) if m.group("timeout") is not None else None
            clerk_waiting[clerk] = ClerkWaitState(start_time=t, timeout=timeout, line_no=line_no)

            first_txt = m.group("first")
            first_match = re.search(PERSON_TOKEN_RE, first_txt)
            first_person = first_match.group(0) if first_match else None
            # Rule 3 check:
            # If first queued person (as printed by producer) is eligible, serving
            # should happen now unless another same-kind clerk serves at this same
            # timestamp.
            if first_person is not None and is_clerk_eligible_for_person(clerk, first_person):
                pending_serve[clerk] = PendingServeExpectation(
                    time=t,
                    line_no=line_no,
                    clerk_kind=entity_kind(clerk, "Check"),
                    reason=f"eligible head-of-queue {first_person} exists",
                )
            else:
                pending_serve.pop(clerk, None)
            continue

        m = PROCESS_RE.match(body)
        if m:
            clerk = m.group("clerk")
            person = m.group("person")
            clerk_kind = entity_kind(clerk, "Check")

            # If one clerk of this kind served at this timestamp, do not
            # report same-kind waiting clerks as failures for that same
            # timestamp (same-time contention/ordering corner case).
            for c, exp in list(pending_serve.items()):
                if abs(exp.time - t) <= EPS and exp.clerk_kind == clerk_kind:
                    pending_serve.pop(c, None)

            exp = pending_serve.get(clerk)
            if exp is not None and abs(exp.time - t) <= EPS:
                pending_serve.pop(clerk, None)

            clerk_waiting.pop(clerk, None)

            ps = people.get(person)
            if ps is not None:
                ps.served_time = t
                if t - ps.deadline > EPS:
                    add_issue(
                        "person_not_reneging_after_announced",
                        t,
                        line_no,
                        f"{person} started service at {t:g} after deadline {ps.deadline:g} without reneging.",
                    )
            try:
                queue.remove(person)
            except ValueError:
                pass
            continue

        m = CLOSE_RE.match(body)
        if m:
            clerk = m.group("clerk")
            ws = clerk_waiting.get(clerk)
            if ws is not None:
                if ws.timeout is None:
                    # Cannot evaluate early/late timeout checks without timeout.
                    pass
                else:
                    expected = ws.start_time + ws.timeout
                    if t + EPS < expected:
                        add_issue(
                            "waiting_clerk_closing_earlier_than_timeout",
                            t,
                            line_no,
                            f"{clerk} closed at {t:g}, expected earliest close at {expected:g}.",
                        )
                    elif t - expected > EPS:
                        add_issue(
                            "waiting_clerk_closing_after_timeout",
                            t,
                            line_no,
                            f"{clerk} closed at {t:g}, expected close at {expected:g}.",
                        )
            pending_serve.pop(clerk, None)
            clerk_waiting.pop(clerk, None)
            continue

    # End-of-log checks.
    if seen_any_time:
        flush_pending_before(last_time + 1.0)

    for person, ps in people.items():
        if ps.cancelled:
            continue
        # If never reneged, ensure no waited span exceeded deadline.
        if ps.reneged_time is None:
            waited_until = ps.served_time if ps.served_time is not None else last_time
            if waited_until - ps.deadline > EPS:
                add_issue(
                    "person_not_reneging_after_announced",
                    waited_until,
                    0,
                    f"{person} waited until {waited_until:g} past deadline {ps.deadline:g} without reneging.",
                )

    return issues, Counter(i.code for i in issues)


def _iter_input(path: Optional[str]) -> Iterable[str]:
    if path is None or path == "-":
        return sys.stdin
    return open(path, "r", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate visa_check.py event sequencing from textual logs.")
    ap.add_argument("input", nargs="?", default="-", help="Path to log file (default: stdin).")
    args = ap.parse_args()

    with _iter_input(args.input) as f:
        issues, summary = parse_log(f)

    if not issues:
        print("OK: no sequencing issues found.")
        return 0

    print("ISSUES:")
    for i in issues:
        line = f"line={i.line_no}" if i.line_no else "line=?"
        print(f"- [{i.code}] t={i.time:g} {line}: {i.message}")
    print("\nSUMMARY:")
    for code, count in sorted(summary.items()):
        print(f"- {code}: {count}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
