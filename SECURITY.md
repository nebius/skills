# Security

## Threat model

These skills instruct an AI agent to run `nebius` CLI commands with the user's existing credentials. The primary risks are (1) an agent executing a destructive or credential-emitting command, and (2) skill text being modified to smuggle such commands in. Mitigations:

## The three-tier model

| Tier | Operations | Enforcement |
|---|---|---|
| A — read | `list`, `get*`, `batch-get`, `logs`, capacity/quota reads and cost estimates | Pre-approved via each skill's `allowed-tools` (explicit command prefixes, never a blanket `Bash(nebius:*)`). |
| B — gated write | `create`, `update`, `start`, `stop`, quota changes | Never pre-approved. Skill prose requires: print the resolved command verbatim, state effect + cost, wait for explicit user confirmation, run once, never batch, never retry after ambiguous failure. |
| C — refuse | `delete`, `purge`, quota-allowance delete, access-key/static-key/auth-public-key operations, `iam get-access-token`, `--impersonate-service-account-id` | Structurally refused in every skill. The agent prints the command for a human and explains the blast radius. |

Additional invariants baked into every skill:

- Never print or persist tokens, access keys, or `~/.nebius/credentials.json` contents.
- Never run `edit`/`edit-by-name` (interactive `$EDITOR`), `-i/--interactive`, or unbounded `--follow` streams.
- No real tenant/project NIDs in the repo (CI lint).

## Limits of enforcement

`allowed-tools` is enforced by Claude Code; Codex enforces via its own sandbox/approval modes; other Agent-Skills clients may enforce nothing. In all clients the tier model still applies as prose instructions, but prose is advice, not a sandbox. IAM remains the real boundary: run agents with least-privilege identities — a read-only role for exploration, a scoped project role for provisioning. Prompt injection is not fully solvable at the skill layer.

## Audit before installing

Skills are instructions your agent will follow. Before installing this or any skill repo: read every `SKILL.md` and `references/` file, check `allowed-tools` for over-broad grants, and pin to a reviewed commit.

## Reporting

Report vulnerabilities or unsafe skill behavior via the repository's private security advisory channel (or to the maintainers in CODEOWNERS) rather than a public issue.
