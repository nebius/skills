#!/usr/bin/env python3
"""Portability lint for skills/*/SKILL.md frontmatter.

Enforces the repo's authoring conventions (see CONTRIBUTING.md):
  - frontmatter uses ONLY the six spec keys
    (claude.ai upload / Skills API hard-error on anything else)
  - name matches the directory name and the nebius-<domain> pattern
  - description is single-line, non-empty, <= 600 chars (Codex listing budget)
  - body <= 500 lines
  - no real tenant/project NIDs committed anywhere in the skill dir
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
DESCRIPTION_MAX = 600
BODY_MAX_LINES = 500
# Real NIDs are a routing code (e0t, e1t, ...) plus a long random suffix;
# templates use short placeholders like project-e00example, which don't match.
REAL_NID = re.compile(r"\b(?:tenant|project)-e[0-9a-z]{2}[a-z0-9]{12,}\b")


def parse_frontmatter(text: str):
    if not text.startswith("---\n"):
        return None, None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, None
    fm = text[4:end]
    body = text[end + 5:]
    top_keys = {}
    current = None
    for line in fm.splitlines():
        m = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):(.*)$", line)
        if m:
            current = m.group(1)
            top_keys[current] = m.group(2).strip()
    return top_keys, body


def main() -> int:
    errors = []
    skill_dirs = sorted(p.parent for p in ROOT.glob("skills/*/SKILL.md"))
    if not skill_dirs:
        print("ERROR: no skills found", file=sys.stderr)
        return 2

    for d in skill_dirs:
        rel = d.relative_to(ROOT)
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        keys, body = parse_frontmatter(text)
        if keys is None:
            errors.append(f"{rel}: missing or malformed frontmatter")
            continue

        extra = set(keys) - SPEC_KEYS
        if extra:
            errors.append(f"{rel}: non-spec frontmatter keys {sorted(extra)}")
        for required in ("name", "description"):
            if required not in keys:
                errors.append(f"{rel}: missing required key '{required}'")

        name = keys.get("name", "")
        if name and name != d.name:
            errors.append(f"{rel}: name '{name}' != directory '{d.name}'")
        if name and not re.fullmatch(r"nebius-[a-z0-9-]+", name):
            errors.append(f"{rel}: name '{name}' must match nebius-<domain>")

        desc = keys.get("description", "")
        if not desc:
            errors.append(f"{rel}: description is empty or not single-line")
        elif len(desc) > DESCRIPTION_MAX:
            errors.append(f"{rel}: description {len(desc)} chars > {DESCRIPTION_MAX}")

        if body is not None:
            n_lines = body.count("\n") + 1
            if n_lines > BODY_MAX_LINES:
                errors.append(f"{rel}: body {n_lines} lines > {BODY_MAX_LINES}")

        for f in sorted(d.rglob("*")):
            if f.is_file() and REAL_NID.search(f.read_text(encoding="utf-8", errors="ignore")):
                errors.append(f"{f.relative_to(ROOT)}: looks like a real tenant/project NID")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(f"ok: {len(skill_dirs)} skills pass frontmatter/portability lint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
