#!/usr/bin/env python3
"""Snapshot PRD.md sections, then verify an edit only touched declared sections.

Usage:
  check_headings.py snapshot PRD.md SNAP.json
  check_headings.py check SNAP.json PRD.md [--edit "Section"]... [--structure-change] [--stale TERM]...

Exit 0 = all gates pass, 1 = a gate failed, 2 = usage error.
"""
import argparse
import hashlib
import json
import sys

PREAMBLE = "(preamble)"


def split_sections(text):
    """Return ordered list of (heading, body) split on '## ' lines outside code fences."""
    sections = [[PREAMBLE, []]]
    in_fence = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            sections.append([line[3:].strip(), []])
        sections[-1][1].append(line)
    return [(h, "".join(body)) for h, body in sections]


def snapshot(text):
    secs = split_sections(text)
    return {
        "headings": [h for h, _ in secs],
        "hashes": {h: hashlib.sha256(b.encode()).hexdigest() for h, b in secs},
    }


def check(before, text, edits, structure_change, stale):
    """Return (changed_sections, list_of_failure_messages)."""
    after = snapshot(text)
    failures = []

    # Gate 2: heading structure
    if after["headings"] != before["headings"] and not structure_change:
        failures.append(
            "Heading structure changed:\n  before: %s\n  after:  %s"
            % (before["headings"], after["headings"])
        )

    # Gate 1: only declared sections changed
    changed = [
        h for h in after["headings"]
        if h in before["hashes"] and before["hashes"][h] != after["hashes"][h]
    ]
    unknown = [e for e in edits if e not in before["hashes"] and e not in after["hashes"]]
    if unknown:
        failures.append("Declared --edit sections not found in PRD: %s" % unknown)
    undeclared = [h for h in changed if h not in edits]
    if undeclared:
        failures.append("Undeclared sections changed: %s" % undeclared)

    # Gate 3: no stale references
    for term in stale:
        hits = [
            i + 1 for i, line in enumerate(text.splitlines())
            if term.lower() in line.lower()
        ]
        if hits:
            failures.append("Stale term %r still present on lines %s" % (term, hits))

    return changed, failures


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("prd")
    s.add_argument("snap")
    c = sub.add_parser("check")
    c.add_argument("snap")
    c.add_argument("prd")
    c.add_argument("--edit", action="append", default=[])
    c.add_argument("--structure-change", action="store_true")
    c.add_argument("--stale", action="append", default=[])
    args = p.parse_args(argv)

    if args.cmd == "snapshot":
        with open(args.prd) as f:
            snap = snapshot(f.read())
        with open(args.snap, "w") as f:
            json.dump(snap, f, indent=2)
        print("Snapshot: %d sections -> %s" % (len(snap["headings"]), args.snap))
        return 0

    with open(args.snap) as f:
        before = json.load(f)
    with open(args.prd) as f:
        text = f.read()
    changed, failures = check(before, text, args.edit, args.structure_change, args.stale)
    print("Changed sections: %s" % (changed or "none"))
    if failures:
        for msg in failures:
            print("FAIL: " + msg)
        return 1
    print("PASS: all gates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
