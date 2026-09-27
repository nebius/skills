#!/usr/bin/env python3
"""Stamp shared/preamble.md into CLI skills/*/SKILL.md between markers.

Usage:
  python3 scripts/sync-shared.py           # rewrite drifted files
  python3 scripts/sync-shared.py --check   # exit 1 if any file drifted (CI)
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BEGIN = ("<!-- BEGIN SHARED PREAMBLE (generated from shared/preamble.md — "
         "edit there, then run scripts/sync-shared.py) -->")
END = "<!-- END SHARED PREAMBLE -->"
# Explicit exemptions keep missing markers an error for every CLI skill.
DOCS_ONLY_SKILLS = {"nebius-public-docs"}


def main() -> int:
    check = "--check" in sys.argv[1:]
    preamble = (ROOT / "shared" / "preamble.md").read_text(encoding="utf-8").strip()
    block = f"{BEGIN}\n{preamble}\n{END}"
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)

    skill_files = sorted(ROOT.glob("skills/*/SKILL.md"))
    if not skill_files:
        print("ERROR: no skills/*/SKILL.md found", file=sys.stderr)
        return 2

    drifted = []
    for skill_md in skill_files:
        text = skill_md.read_text(encoding="utf-8")
        if skill_md.parent.name in DOCS_ONLY_SKILLS:
            if BEGIN in text or END in text:
                print(f"ERROR: {skill_md.relative_to(ROOT)} is docs-only but has CLI preamble markers",
                      file=sys.stderr)
                return 2
            continue
        if BEGIN not in text or END not in text:
            print(f"ERROR: {skill_md.relative_to(ROOT)} is missing preamble markers",
                  file=sys.stderr)
            return 2
        new = pattern.sub(lambda _m: block, text, count=1)
        if new != text:
            drifted.append(skill_md)
            if not check:
                skill_md.write_text(new, encoding="utf-8")
                print(f"updated {skill_md.relative_to(ROOT)}")

    if check and drifted:
        for p in drifted:
            print(f"DRIFT: {p.relative_to(ROOT)} — run scripts/sync-shared.py",
                  file=sys.stderr)
        return 1
    print(f"{'ok' if check else 'done'}: {len(skill_files)} skills, "
          f"{len(drifted)} {'drifted' if check else 'updated'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
