---
name: nebius-grafana-mcp-install
description: Installs and verifies Grafana MCP for Nebius in local Codex or Claude Code on explicit invocation. Runs bundled setup, reuses owned bindings and handles credentials privately with supervised renewal/reconnection. Also supports credential-free checks and owned updates. Not for telemetry queries, IAM repair or direct agent token commands.
license: Apache-2.0
compatibility: Requires local macOS/Linux, Bash, Python >=3.11, nebius CLI >=0.12.247 with bounded authentication options, and Codex CLI or Claude Code. Bundled setup installs verified mcp-grafana 1.4.0.
metadata:
  version: "0.1.0"
  status: agent-run
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

Install and verify read-only access to an existing, explicitly trusted Nebius Grafana for
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

If any check fails or an ID comes back empty, stop and walk the user through [CLI installation and profile setup](https://docs.nebius.com/cli/install): `curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash`, then `nebius profile create --parent-id <project-id>`. **Print those commands for the user to run — do not run them yourself**: the installer writes to their machine and the shown federation-profile command opens a browser and blocks. An expired session does not show up here; it surfaces on the first real API call. The Grafana installer exception below owns its browser authentication; other skills retain the human re-authentication handoff.

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
| C — refuse | `delete`, `purge`, credential issuance (`iam get-access-token`, access keys; `iam auth-public-key generate` is Tier B; bounded Grafana installer exception below), `-I`/`--impersonate-service-account-id` (a global flag, valid on *every* command — including otherwise-free reads) | Do not run. Print the exact command for the human to run themselves and explain the blast radius. |

**Grafana installer exception.** Explicit invocation of `nebius-grafana-mcp-install` to install or update authorizes the agent to run that skill's bundled setup helper for the selected local client, human profile and trusted HTTPS Grafana origin. Its helper owns prerequisite checks, browser authentication when needed, private token capture, verified runtime installation, client registration and bounded MCP verification; use that workflow instead of the generic CLI checks above. Its fixed supervised runtime may renew the same pinned human identity. This exception permits only helper-owned credential handling and mode-0600 private token state. It does not permit direct agent token commands, credential inspection, copying the credential workflow, other credential/IAM operations or changes to native permission controls. Check-only intent remains non-mutating. Other skills retain the tier rules above.

**Secrets.** Never expose tokens, access keys or `~/.nebius/credentials.json` contents to agent context, tool output, chat, logs or repository files. Never persist them except in the Grafana installer's narrowly defined private runtime state. No broad helper/interpreter permission grant is allowed.
<!-- END SHARED PREAMBLE -->

## Invocation Policy

Explicitly invoking this skill to install or update authorizes its bundled
setup workflow. The agent runs setup; the user does not copy terminal commands.
Check-only requests remain credential-free and non-mutating. Installing the
skill folder alone does not install or activate MCP.

## Credential boundary

The bundled helper and supervised runtime handle credentials internally. They
never place the Nebius token in agent-visible tool output, prompts, chat, logs
or documentation. The agent must never read token files, run token commands
directly, or reproduce that workflow. The helper stores credentials in protected
private files and sends them only to the validated, trusted Grafana origin.
This protects the supported workflow; it is not isolation from other processes
running as the same OS user. Read [runtime security](references/runtime-security.md).

## Workflow

1. Select the current local client (`codex` or `claude`) from the host context.
   Ask only if the client is ambiguous. Read [client setup](references/client-setup.md).
   Run the bundled helper from this installed skill directory, using quoted
   arguments and only non-secret selectors already supplied by the user:

   ```bash
   bash scripts/ensure-local-config.sh --agent codex --check
   ```

   Use `--agent claude` for Claude Code. The helper reuses a unique validated
   installer-owned binding. If it reports missing or ambiguous inputs, ask once
   for the requested human profile, trusted HTTPS Grafana origin and, when
   necessary, installation name. The user must establish that this Grafana
   accepts their Nebius IAM credential. Never infer the origin from ambient
   profiles, unrelated client config, old donor installations or project IDs.
2. Check-only intent ends after reporting the helper's local result. For install
   or update intent, explain briefly that setup installs a verified runtime,
   prepares private credentials, updates this client's user settings and checks
   connectivity. Then **run** the helper with `--apply`; the explicit invocation
   already authorizes this workflow. Supply missing selectors as arguments:

   ```bash
   bash scripts/ensure-local-config.sh --agent codex --user-profile <human-profile> --grafana-url https://<trusted-grafana-host> --apply
   ```

   Reused bindings need only `--agent` and `--apply`. Include `--update` when the
   local check reports `update_required: true`, or the user explicitly requests
   an owned update or authentication recovery. Missing prerequisites are reported
   for the user to install; do not bootstrap Python, the CLI or the client.
3. Let the helper perform authentication and setup. Tell the user to complete
   browser sign-in only if needed. Do not inspect CLI credentials, copy login
   URLs, expose raw configuration or run the wrapper's private renewal action.
   Consume only the helper's sanitized progress and JSON result. Preserve native
   permission controls; explicit invocation does not bypass a host permission
   prompt. If the host blocks execution, report its concrete blocker.
4. Reuse only exactly owned state. A donor/unrelated registration is a collision:
   select a distinct `--mcp-server-name`. Configuration, identity or origin drift
   is refused. Never adopt credentials, overwrite unrelated settings, delete lock
   residue or modify another installed skill to complete setup.
5. Report registration, independent runtime readiness and current-chat activation
   separately. Setup verifies MCP initialization, tool discovery and one bounded
   datasource list; an empty list is valid. It does not grade datasource health.
   If the host supports safe MCP reconnect/reload, use it and verify the expected
   server's tools. Otherwise ask for a client reload, then verify availability.
   Never kill the active host or claim the tools are active before observing them.
   A runtime verification failure retains owned registration and reports failure;
   it does not authorize IAM grants, datasource changes or authentication bypass.
6. Read [authentication lifecycle](references/auth-lifecycle.md) for recovery.
   Rotation ends the connection with exit 75; reconnect to load the new generation.
   Do not promise automatic same-chat recovery, authoritative expiry or indefinite
   human-login renewal. Ordinary observability queries are a separate task.

## Public helper interface

```text
python3 scripts/setup.py --agent codex|claude [--user-profile NAME]
                        [--grafana-url HTTPS_ORIGIN] [--check | --apply]
                        [--mcp-server-name NAME] [--update]
```

`bash scripts/ensure-local-config.sh` exposes the same arguments and checks Python.

- `--agent`: one local client; run twice only when both clients were requested.
- `--user-profile`: human Nebius CLI profile; omit to reuse a unique owned binding.
- `--grafana-url`: trusted HTTPS origin; omit to reuse a unique owned binding.
- `--check`: default, local inspection without credential access or MCP startup.
- `--apply`: install, authenticate, register and independently verify MCP.
- `--mcp-server-name`: reuse an owned name or default to `grafana-nebius`; 1-64 letters, digits, `_`, `-`, starting with a letter or digit.
- `--update`: with apply, renew credentials and update an exactly owned installation.
- `-h`, `--help`: help only. No additional public flags.

Exit statuses: 0 local check matches or apply verified, 3 setup/update needed,
4 registered but runtime verification failed, 1 failure, 2 missing/invalid inputs,
130 cancellation. Runtime exit 75 requests reconnection.

## Boundaries

Codex metadata disables implicit invocation; explicit intent is required in both
clients. Claude support means Claude Code, not Desktop/Cowork/cloud agents.
No companion skill or donor repository is required. Service-account/static-key
setup, impersonation, datasource provisioning and telemetry analysis are outside
this skill. Never broaden allowed-tools for credential helpers.

## Learning Loop

When using this skill, capture durable, reusable, public-safe learnings
in the narrowest appropriate surface only when the task contract allows source edits.
For read-only/report-only work, or when a learning is not public-safe,
evidence-backed, in scope, or free of unverified/vendor-specific claims, do not
edit skill sources; report that it was skipped. Do not capture secrets, private
URLs, customer data, raw logs, or one-off local state.
