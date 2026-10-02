# Contributing

## Adding or changing a skill

1. Create `skills/nebius-<domain>/SKILL.md` (see any existing skill for the shape).
2. For CLI skills, add the shared-preamble markers right after the intro paragraph, then run `python3 scripts/sync-shared.py`. Documentation-only skills must be explicitly listed in `DOCS_ONLY_SKILLS` in that script and omit CLI preamble markers.
3. Add ≥3 eval scenarios in `evals/nebius-<domain>/`.
4. Run `bash scripts/validate.sh` — it must pass clean.
5. For CLI skills, verify at least one live read-only command from the skill against the **testing** profile. For documentation-only skills, verify public index discovery and retrieval of a relevant page without cloud credentials or CLI setup.

## Authoring conventions (enforced by `scripts/validate.sh` where possible)

1. **Name**: `nebius-<domain>`, noun phrase, lowercase-hyphen, identical to the directory name. The `nebius-` prefix keeps triggering unambiguous when many sibling skills coexist.
2. **Description** = *what it does* + *when to use it*, third person, front-loaded with the highest-value trigger, containing the literal words a user would type ("GPU capacity", "how much did we spend", "list instances"). Hard cap **600 chars** — Codex truncates its ~8,000-char startup skill listing silently, and descriptions are what get cut.
3. **Frontmatter: only the six spec keys** — `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. Claude Code tolerates its own extensions; claude.ai upload and the Skills API hard-error on them. Spec-only frontmatter runs everywhere.
4. **Body under 500 lines**, ideally under ~150. Long material goes to `references/` — one level deep, never nested. Reference files over 100 lines start with a table of contents.
5. **Degrees of freedom match fragility**: inventory/read work gets high-freedom prose; provisioning gets a low-freedom numbered workflow with exact command sequences.
6. **`compatibility`** states the real prerequisite. Documentation-only skills require web access, without a Nebius account or CLI. The baseline for CLI skills is `Requires the nebius CLI (>=0.12.247) with a configured profile; jq recommended`. When a skill adopts a newer CLI command or flag, raise the floor in every affected skill and the README.
7. **Templates over flag soup**: every `create` path ships a commented `-f` YAML request template in `assets/`, used as `nebius <svc> <res> create -f <file>`. Where the CLI is flags-only (e.g. `ai job create` / `ai endpoint create` have no `-f`/`--file` input), ship a fully commented command skeleton in `assets/` instead — every valid flag listed, placeholders marked.
8. Documentation-only skills omit `allowed-tools` and use the host's normal web-access permissions. For CLI skills, **`allowed-tools` enumerates read-only command prefixes only** — never `Bash(nebius:*)`, which would pre-approve `delete`. Mutations must go through the client's normal permission flow. Nothing outside `nebius` belongs there either: `Bash(jq:*)` would pre-approve `jq . ~/.nebius/credentials.json`, so jq stays on the normal permission flow (a pipe whose left side is allowed still only prompts once).
9. **No time-sensitive statements** in skill bodies. Deprecations go in a collapsed "Old patterns" section with their sunset date.
10. **No secrets, no real IDs**: never print/persist tokens or keys; never commit real tenant/project NIDs — templates use `project-e00example` style placeholders (the lint checks this).

## Shared preamble

`shared/preamble.md` is stamped into every CLI `SKILL.md` between generated markers at build time (no cross-skill runtime references — they break when a client installs a single skill). Edit the preamble, run `scripts/sync-shared.py`, commit both. CI fails on drift or missing markers in CLI skills. The explicit `DOCS_ONLY_SKILLS` list exempts public documentation research; exempt skills are checked to ensure they do not contain CLI preamble markers.

## Releasing

Installed marketplaces update by the `version` field (git SHA is only the fallback), so users get controlled updates exactly when we bump it. Per release:

1. Bump `version` in **all three** manifests — `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (`metadata.version`), and `.codex-plugin/plugin.json` — keep them identical (`scripts/validate.sh` enforces this). Codex users pull the bump via `codex plugin marketplace upgrade nebius`; Claude Code marketplaces can auto-update.
2. Add a `CHANGELOG.md` entry.
3. Tag the release commit `vX.Y.Z` (matching the version) and create a GitHub Release.

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
