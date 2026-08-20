# Contributing

## Adding or changing a skill

1. Create `skills/nebius-<domain>/SKILL.md` (see any existing skill for the shape).
2. Add the shared-preamble markers right after the intro paragraph, then run `python3 scripts/sync-shared.py`.
3. Add ≥3 eval scenarios in `evals/nebius-<domain>/`.
4. Run `bash scripts/validate.sh` — it must pass clean.
5. Verify at least one live read-only command from the skill against the **testing** profile

## Authoring conventions (enforced by `scripts/validate.sh` where possible)

1. **Name**: `nebius-<domain>`, noun phrase, lowercase-hyphen, identical to the directory name. The `nebius-` prefix keeps triggering unambiguous when many sibling skills coexist.
2. **Description** = *what it does* + *when to use it*, third person, front-loaded with the highest-value trigger, containing the literal words a user would type ("GPU capacity", "how much did we spend", "list instances"). Hard cap **600 chars** — Codex truncates its ~8,000-char startup skill listing silently, and descriptions are what get cut.
3. **Frontmatter: only the six spec keys** — `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. Claude Code tolerates its own extensions; claude.ai upload and the Skills API hard-error on them. Spec-only frontmatter runs everywhere.
4. **Body under 500 lines**, ideally under ~150. Long material goes to `references/` — one level deep, never nested. Reference files over 100 lines start with a table of contents.
5. **Degrees of freedom match fragility**: inventory/read work gets high-freedom prose; provisioning gets a low-freedom numbered workflow with exact command sequences.
6. **`compatibility`** states the real prerequisite (e.g. `Requires the nebius CLI (>=0.12) with a configured profile; jq recommended`).
7. **Templates over flag soup**: every `create` path ships a commented YAML request template in `assets/`, used as `nebius <svc> <res> create -f <file>`.
8. **`allowed-tools` enumerates read-only command prefixes only** — never `Bash(nebius:*)`, which would pre-approve `delete`. Mutations must go through the client's normal permission flow.
9. **No time-sensitive statements** in skill bodies. Deprecations go in a collapsed "Old patterns" section with their sunset date.
10. **No secrets, no real IDs**: never print/persist tokens or keys; never commit real tenant/project NIDs — templates use `project-e00example` style placeholders (the lint checks this).

## Shared preamble

`shared/preamble.md` is stamped into every `SKILL.md` between generated markers at build time (no cross-skill runtime references — they break when a client installs a single skill). Edit the preamble, run `scripts/sync-shared.py`, commit both. CI fails on drift.

## Eval scenario shape

```json
{
  "skills": ["nebius-cloud-basics", "nebius-capacity-quotas"],
  "query": "what a real user would type",
  "expected_behavior": [
    "observable, checkable behaviors — commands chosen, scopes resolved, confirmations requested"
  ]
}
```

Keep queries realistic (paths, typos, casual phrasing included) and behaviors observable. Before trusting a new skill, run its evals *without* the skill too — the value is the delta.
