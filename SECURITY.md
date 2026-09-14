# Security

## Threat model

These skills instruct an AI agent to run `nebius` CLI commands with the user's existing credentials. The primary risks are (1) an agent executing a destructive or credential-emitting command, and (2) skill text being modified to smuggle such commands in. Mitigations:

## The three-tier model

| Tier | Operations | Enforcement |
|---|---|---|
| A — read | `list`, `get*`, `batch-get`, `logs`, capacity/quota reads and cost estimates | Pre-approved via each skill's `allowed-tools` (explicit command prefixes, never a blanket `Bash(nebius:*)`). |
| B — gated write | `create`, `update`, `start`, `stop`, quota changes | Never pre-approved. Skill prose requires: print the resolved command verbatim, state effect + cost, wait for explicit user confirmation, run once, never batch, never retry after ambiguous failure. |
| C — refuse | `delete`, `purge`, quota-allowance delete, access-key/static-key/auth-public-key operations, `iam get-access-token`, `--impersonate-service-account-id` | Refused, apart from the bounded Grafana installer exception below. The agent prints the command for a human and explains the blast radius. |

Additional invariants baked into every skill:

- Never expose tokens, access keys or `~/.nebius/credentials.json` contents to agent context, tool output, chat, logs or repository files. Private persistence is limited to the Grafana runtime exception below.
- Never run `edit`/`edit-by-name` (interactive `$EDITOR`), `-i/--interactive`, or unbounded `--follow` streams.
- No real tenant/project NIDs in the repo (CI lint).

## Grafana installer exception

Explicitly invoking `nebius-grafana-mcp-install` to install or update authorizes
its bundled setup helper to configure the selected local client and private
runtime. The helper validates a pinned human profile and trusted HTTPS Grafana
origin, opens browser authentication if needed, captures credentials internally,
and verifies the resulting MCP connection. Its fixed supervisor may renew that
same identity and store tokens only in its protected mode-0600 state. Check-only
invocation does not authorize setup or credential operations.

The agent must not run token commands directly, read token files, copy or
reproduce the credential workflow, grant IAM access, substitute identities,
or weaken native permissions. The exception does not extend to other skills,
arbitrary Python/shell helpers, service accounts, access keys or impersonation.
No broad `allowed-tools` entry pre-approves the installer. Existing host
permission controls remain in force; the explicit setup request supplies task
authorization without requiring another skill-level confirmation.

Credential bytes remain inside helper/runtime processes and private files.
Fixed setup statuses and filtered runtime output keep those bytes out of the
agent context in the supported workflow. This is not OS isolation: another
process with the same user's access can inspect private files or environments.
The proxy checks only credentials it handles, not unrelated secrets in telemetry.
See [runtime security](skills/nebius-grafana-mcp-install/references/runtime-security.md).

## Limits of enforcement

`allowed-tools` is enforced by Claude Code; Codex enforces via its own sandbox/approval modes; other Agent-Skills clients may enforce nothing. In all clients the tier model still applies as prose instructions, but prose is advice, not a sandbox. IAM remains the real boundary: run agents with least-privilege identities — a read-only role for exploration, a scoped project role for provisioning. Prompt injection is not fully solvable at the skill layer.

## Audit before installing

Skills are instructions your agent will follow. Before installing this or any skill repo: read every `SKILL.md` and `references/` file, check `allowed-tools` for over-broad grants, and pin to a reviewed commit.

The content is best-effort guidance, not official Nebius documentation — commands, flags, presets etc are verified at authoring time and drift with the CLI and the platform. Review every command an agent proposes before it runs, most of all `create`, quota changes, and anything with `delete` in it.

## Reporting

**Security** — a skill that emits credentials, runs or induces a destructive command, or looks deliberately malicious: report it privately via the GitHub Security Advisory ["Report a Vulnerability"](https://github.com/nebius/skills/security/advisories/new) tab rather than a public issue. Include the skill name, the commit or release you installed, and the agent transcript if you have one, with secrets redacted.

**Incorrect guidance** — a wrong flag or preset, a command the CLI no longer has: not a vulnerability, so open a public [issue](https://github.com/nebius/skills/issues/new) with the skill name, the command, your `nebius version`, and the actual output.

If you are unsure which it is, treat it as a security report.
