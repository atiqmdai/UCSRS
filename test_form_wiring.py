#!/usr/bin/env python3
"""
End-to-end form-wiring check for index.html.

Cross-engine parity cannot catch a disconnected field. The parity harness hands both
engines the same dictionary directly, so a key the *form* never assigns still agrees
perfectly between Python and JavaScript while contributing nothing to any score a
user would ever see.

That is exactly what happened to `pulmStatus` on 15 September 2026: read at four
branches of the v3.0 baseline, assigned zero times by the form, and therefore worth
0 log-odds for chronic lung disease, home oxygen, acute disease and pre-operative
ventilation alike -- while the EuroSCORE II comparator, which reads its own derived
flag, went on charging for all of them.

This script is the check that would have caught it. It reads index.html as text and
asserts that every key the shipped engine reads off the patient object is assigned
somewhere in the same file.

Limitation, stated plainly: this proves a key is assigned *somewhere*, not that it is
assigned on the object that calc() actually passes to the engine, and not that the
value assigned is correct. It is a floor, not a ceiling. It catches the silent-zero
class of defect and nothing more.

Exit code 0 on pass, 1 on failure.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE / "index.html"

# Identifiers that appear as `p.<name>` or `patient.<name>` but are method calls or
# array/string members rather than patient fields.
NOT_FIELDS = {
    "push", "length", "toFixed", "value", "map", "filter", "forEach",
    "get", "indexOf", "join", "slice", "split", "concat", "sort",
    # returned-object members of the engine's own result, not inputs
    "final", "ok", "tests", "points", "missing", "partial",
}


def keys_read(src: str) -> set[str]:
    """Every field the engine reads off the patient object."""
    found = set(re.findall(r"\bp\.([a-zA-Z_][a-zA-Z0-9_]*)", src))
    found |= set(re.findall(r"\bpatient\.([a-zA-Z_][a-zA-Z0-9_]*)", src))
    return found - NOT_FIELDS


def keys_assigned(src: str) -> set[str]:
    """Every identifier assigned as an object property or onto `patient`."""
    found = set(re.findall(r"(?:^|[,{(]|\s)([a-zA-Z_][a-zA-Z0-9_]*)\s*:", src, re.M))
    found |= set(re.findall(r"patient\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=", src))
    return found


def main() -> int:
    if not PAGE.exists():
        print(f"FAILED - {PAGE.name} not found", file=sys.stderr)
        return 1

    src = PAGE.read_text(encoding="utf-8")
    read = keys_read(src)
    assigned = keys_assigned(src)
    orphans = sorted(k for k in read if k not in assigned)

    print("UCSRS form wiring - every key the engine reads must be assigned by the form")
    print(f"keys read off the patient object : {len(read)}")
    print(f"keys never assigned              : {len(orphans)}")

    if orphans:
        print(f"\nFAILED - {len(orphans)} key(s) read but never assigned:")
        for k in orphans:
            n = len(re.findall(r"\b(?:p|patient)\." + k + r"\b", src))
            print(f"  {k:<24} read {n}x, assigned 0x")
        print("\nA key in this list scores zero in the live page regardless of what the")
        print("user enters. The parity suite will not detect it.")
        return 1

    print("\nPASSED - every key the engine reads is supplied by the form.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
