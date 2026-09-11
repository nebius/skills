---
name: nebius-grafana-mcp-install
description: Prepares Grafana MCP setup for Nebius in Codex or Claude Code when the user explicitly requests installation, local checks or an owned update. Provides a human-run installer with a private credential proxy and renewal/restart. Not for observability queries or agent-run credential issuance.
license: Apache-2.0
compatibility: Requires local macOS/Linux, Bash, Python >=3.11, nebius CLI >=0.12.247 with bounded authentication options, and Codex CLI or Claude Code. Human setup installs verified mcp-grafana 1.4.0.
metadata:
  version: "0.1.0"
  status: human-operated
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile list:*)
  - Bash(nebius config get:*)
---

# Install Grafana MCP for Nebius

## Help

For `$nebius-grafana-mcp-install --help` or `$nebius-grafana-mcp-install -h`, return concise help and stop before
any workflow step. State the purpose and invocation policy. Show exact usage
for every public action. Describe each public action, positional
argument, and flag in one concise line, including `-h, --help`; say "No
additional public flags" when there are no others. Use only the documented
public interface. For internal or coordinator-only skills, state that boundary
and that no standalone public workflow action exists. After the selected
`SKILL.md` is loaded, help is report-only: do not call any additional tools,
inspect project state, or modify files, private state, Git, or external systems.
Never expose private helper actions or flags or treat help as workflow
authorization.

## Purpose

Prepare read-only access to an existing, explicitly trusted Nebius Grafana for
one local Codex or Claude Code client and one human Nebius profile.

<!-- BEGIN SHARED PREAMBLE (generated from shared/preamble.md — edit there, then run scripts/sync-shared.py) -->
## Nebius CLI ground rules

These rules apply to every command in this skill. Full detail lives in the `nebius-cloud-basics` skill.

**Agent identification.** Export `AI_AGENT` before any Nebius CLI call, including preflight and `--help`. Keep non-empty harness-set value; unset or empty → set own harness slug. Every call must inherit it, including new shells.

**CLI present and configured.** Before the first Nebius call in a session:

```bash
nebius version                 # CLI installed (a subcommand — there is no --version flag)
nebius profile list            # at least one profile; [default] marks the active one
nebius config get parent-id    # project-...
nebius config get tenant-id    # tenant-...
```

These skills require CLI `0.12.247` or newer; an individual skill may state a higher floor (the Serverless skills need `0.12.265`) — the stricter number wins. If `nebius version` is older, stop and ask the user to update the CLI before relying on the commands or schemas below.

If any check fails or an ID comes back empty, stop and walk the user through [CLI installation and profile setup](https://docs.nebius.com/cli/install): `curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash`, then `nebius profile create --parent-id <project-id>`. **Print those commands for the user to run — do not run them yourself**: the installer writes to their machine and the shown federation-profile command opens a browser and blocks. An expired session does not show up here; it surfaces on the first real API call, and re-auth is the same human task.

**Resolve context first — never guess IDs.** Nearly every call needs `--parent-id`, and the CLI does not say which scope it wants:

```bash
nebius profile current                        # which profile is active
nebius config get parent-id  [-p <profile>]   # project-...  (project scope)
nebius config get tenant-id  [-p <profile>]   # tenant-...   (tenant scope)
```

Compute resources are generally **project**-scoped; public-image discovery is region-scoped. Quota allowances may be project- or tenant-scoped. Capacity advice, capacity block groups, and capacity intervals are **tenant**-scoped. The wrong scope often returns empty lists or permission errors, not a helpful message. Pass `-p <profile>` explicitly whenever the user names a profile.

**Output.** Add `--format json` to API calls and parse that; the default table output is for humans. On paginated `list` calls, add `--all` only when `--help` exposes it. Some list-like commands differ: for example, `compute image list-public` requires `--region` and has no `--all`. Never pass `-i`/`--interactive`: it opens interactive entry or alternate-screen pagination and hangs unattended sessions. Never pass `--follow` (e.g. `compute instance logs --follow`, `logging query --follow`): it streams until killed and hangs an unattended session the same way.

**Editing.** Never run `edit` or `edit-by-name`: they open `$EDITOR` and hang in a non-interactive shell. Use `update` with explicit flags or `update -f <file>` instead.

**Async operations.** Mutations return an operation; by default the CLI blocks until it completes. With `--async` it returns an operation id — poll with `nebius <service> <resource> operation wait <operation-id>`.

**Safety tiers.**

| Tier | Operations | Behavior |
|---|---|---|
| A — read | `list`, `get`, `get-by-name`, `batch-get`, `list-*`, `logs`, `--help` | Run freely. |
| B — gated write | `create`, `update`, `start`, `stop`, quota/capacity allowance changes | Print the fully resolved command verbatim, state what it changes and the cost implication, wait for explicit user confirmation, then run it exactly once. Never batch mutations; never retry one after an ambiguous failure. |
| C — refuse | `delete`, `purge`, credential issuance (`iam get-access-token`, access keys; sole exception: `iam auth-public-key generate` is Tier B), `-I`/`--impersonate-service-account-id` (a global flag, valid on *every* command — including otherwise-free reads) | Do not run. Print the exact command for the human to run themselves and explain the blast radius. |

**Secrets.** Never print or persist tokens, access keys, or the contents of `~/.nebius/credentials.json`.
<!-- END SHARED PREAMBLE -->

## Invocation Policy

This skill requires explicit invocation. Prepare installation only when the user
explicitly asks to install, check or update this MCP integration.

## Operator boundary

Installing this skill distributes instructions and helpers; it does not install
or activate MCP. Read the [operator and policy boundaries](references/runtime-security.md).
The human runs setup and initial authentication in their terminal. The agent may
run `--check`, explain results and present the resolved setup command. Do not
execute `--apply`, start credential renewal, read token files, reproduce the
credential workflow or modify permission controls from the agent.

The helper is functional without a maintainer switch. Its private token storage
and automatic renewal remain explicit deviations from the repository's unchanged
credential policy. These instructions do not declare an exception approved.

## Workflow

1. Require explicit installation/check/update intent and an explicit client,
   human profile and trusted HTTPS Grafana origin. The operator must establish
   that this Grafana accepts their Nebius IAM credential. Do not infer these
   inputs from old installations, ambient profiles or unrelated project IDs.
2. Read [client setup](references/client-setup.md). From this installed skill
   directory, perform credential-free local inspection with quoted arguments:

   ```bash
   python3 scripts/setup.py --agent codex --user-profile <human-profile> --grafana-url https://<trusted-grafana-host> --check
   ```

   Use `--agent claude` for Claude Code. Check never authenticates, reads tokens,
   starts MCP or performs a network health check. Never print raw client config,
   credential bindings, environment values or private state contents.
3. Explain the concrete local file effects and show the same command with
   `--apply` for the human to execute. Setup downloads or verifies the pinned
   binary, binds the origin and human identity, prepares protected token state,
   and registers only the selected client. It creates no cloud resources.
4. Reuse only exactly owned state. A donor/unrelated registration is a collision:
   select a distinct `--mcp-server-name`. Never adopt its credentials or change
   the source/installed donor skill. An owned update requires `--apply --update`;
   unexpected configuration or origin changes are refused.
5. Report local setup separately from live readiness. The human restarts the
   selected client; verify MCP initialization and a bounded datasource list
   only on an authorized target. The default server name is `grafana-nebius`.
   Setup does not authorize datasource, IAM or dashboard mutations.
6. Read [authentication lifecycle](references/auth-lifecycle.md) for renewal or
   restart-required status. Rotation ends the connection with exit 75. Reconnect
   to load the new generation; never promise automatic same-chat recovery,
   authoritative expiry or uninterrupted operation beyond twelve hours.

## Public helper interface

```text
python3 scripts/setup.py --agent codex|claude --user-profile NAME
                        --grafana-url HTTPS_ORIGIN [--check | --apply]
                        [--mcp-server-name NAME] [--update]
```

`bash scripts/ensure-local-config.sh` exposes the same arguments and checks Python.

- `--agent`: exactly one local client; run twice to configure both.
- `--user-profile`: explicitly selected human Nebius CLI profile.
- `--grafana-url`: trusted HTTPS origin receiving that profile's credential.
- `--check`: default, non-mutating local inspection with no credential access.
- `--apply`: human-run installation and protected credential setup.
- `--mcp-server-name`: default `grafana-nebius`; 1-64 letters, digits, `_`, `-`, starting with a letter or digit.
- `--update`: with apply, renew credentials and update an exactly owned installation.
- `-h`, `--help`: help only. No additional public flags.

Exit statuses: 0 local configuration ready, 3 setup/update needed, 1 failure,
2 invalid arguments, 130 cancellation. Runtime exit 75 requests reconnection.

## Boundaries

The shared runtime owns the proxy, verified binary and renewal. Client adapters
own registration and startup settings. The proxy holds the Nebius token; MCP
receives a temporary local credential. Modes 0700/0600 and guarded output reduce
exposure; another process under the same OS user can still read private files.

Codex metadata disables implicit invocation; explicit intent is required in
both clients. Claude support means Claude Code, not Desktop/Cowork/cloud agents.
No companion skill or donor repository is required. Service-account/static-key
setup, impersonation, datasource provisioning and ordinary telemetry analysis
are outside this skill. Never broaden allowed-tools for credential helpers.

## Learning Loop

When using this skill, capture durable, reusable, public-safe learnings
in the narrowest appropriate surface only when the task contract allows source edits.
For read-only/report-only work, or when a learning is not public-safe,
evidence-backed, in scope, or free of unverified/vendor-specific claims, do not
edit skill sources; report that it was skipped. Do not capture secrets, private
URLs, customer data, raw logs, or one-off local state.
