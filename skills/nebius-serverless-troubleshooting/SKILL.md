---
name: nebius-serverless-troubleshooting
description: Diagnose Nebius Serverless jobs and endpoints. Use for "my job is stuck", "endpoint returns nothing", "no logs", "PermissionDenied", "RESOURCE_EXHAUSTED", "quota exceeded", "job failed, why" - any status, log, or error investigation.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.277) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius iam whoami:*)
  - Bash(nebius ai job list:*)
  - Bash(nebius ai job get:*)
  - Bash(nebius ai job get-by-name:*)
  - Bash(nebius ai job logs:*)
  - Bash(nebius ai endpoint list:*)
  - Bash(nebius ai endpoint get:*)
  - Bash(nebius ai endpoint get-by-name:*)
  - Bash(nebius ai endpoint logs:*)
  - Bash(nebius compute platform list:*)
---

# Nebius Serverless Troubleshooting

Work out why a job or endpoint is stuck, failing, or silent — from state and logs, without mutating anything. Fixes that re-create or cancel resources hand back to the gated skills. Remember while you debug: anything not in a terminal state is billing.

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

These skills require CLI `0.12.247` or newer; an individual skill may state a higher floor (the Serverless skills need `0.12.277`) — the stricter number wins. If `nebius version` is older, stop and ask the user to update the CLI before relying on the commands or schemas below.

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

**Safety tiers.** Every operation falls in exactly one tier; when a command fits two, the higher (more restrictive) tier wins.

| Tier | Operations | Behavior |
|---|---|---|
| A — read | `list`, `get`, `get-by-name`, `batch-get`, `list-*`, `logs`, `--help` | Run freely — unless the command emits credential material, which puts it in C whatever its verb. |
| B — gated write | `create`, `update`, `start`, `stop`, quota/capacity allowance changes | Print the fully resolved command verbatim, state what it changes and the cost implication, wait for explicit user confirmation, then run it exactly once. Never batch mutations; never retry one after an ambiguous failure. A command or rendered template carrying a literal secret is never printed and never run: it *accepts* key material, so it is Tier C — replace the literal with a secret selector, or hand the command to the human with the value left as a placeholder. |
| C — refuse | `delete`, `purge`, credential issuance (`iam get-access-token`, access keys; sole exception: `iam auth-public-key generate` is Tier B), any command that emits or accepts token/key material whatever its verb — a raw read whose output carries a token (secret-store payloads, an endpoint spec's auth token) included, `-I`/`--impersonate-service-account-id` (a global flag, valid on *every* command — including otherwise-free reads) | Do not run. Print the exact command for the human to run themselves and explain the blast radius. **Exposure is the line, not handling:** a credential captured into an unechoed shell variable and consumed inside the same compound command stays at its verb's own tier — what Tier C refuses is the value reaching tool output, the transcript, shell history, or a file. So the endpoint smoke test (`TOKEN=$(… | jq -r '.spec.auth_token') && curl -H "Authorization: Bearer $TOKEN" …`) is permitted, while a raw spec dump, `echo $TOKEN`, or a literal token typed into a flag is not. |

**Secrets.** Never print or persist tokens, access keys, or the contents of `~/.nebius/credentials.json`. Some Tier A reads carry credential material in their output: on a token-auth endpoint `ai endpoint get`/`get-by-name` return the bearer token at `.spec.auth_token` and `ai endpoint list` returns it for every item it lists, while job and endpoint specs carry plain `--env` values and registry passwords. Never read those raw — project the fields you need, e.g. `| jq '{id: .metadata.id, state: .status.state, urls: .status.public_endpoints}'`, or `| jq '.items[]? | {…}'` on a list (the `?` matters: an empty list can come back as bare `{}`, and `.items[]` on that aborts with "Cannot iterate over null").
<!-- END SHARED PREAMBLE -->

## Start from state, not logs

```bash
nebius ai job get --id <job-id> --format json        # or: endpoint get
```

On a token-auth **endpoint**, pipe `get`/`get-by-name`/`list` through a jq filter (e.g. `| jq '{state: .status.state, urls: .status.public_endpoints}'`, or `| jq '.items[]? | {…}'` for a list — `?` because an empty list is bare `{}`) — the raw output carries the token at `.spec.auth_token`, one per item on `list`, and it must never land in the transcript.

States: `PROVISIONING → STARTING → RUNNING →` terminal. Read `status.state` **and how long it has been there** — the state alone under-informs:

- **`STARTING` > ~10 min** → almost certainly a failing image pull. Today `STARTING` exposes no pull progress and no pull error (MSPDEV-323), so don't wait: check the image reference exists (exact registry/path:tag), check registry auth (`--registry-secret` present for private images), then cancel and re-create via the gated skill. A broken image otherwise sits there billing until the job `--timeout` (default 24h).
- **`PROVISIONING` stuck** → capacity, not your container. See `RESOURCE_EXHAUSTED` below.
- **`RUNNING` but misbehaving** → now logs are the tool.

## Reading logs

```bash
nebius ai job logs <id> --tail 200 --timestamps      # endpoint logs <id> works the same
```

- The id is **positional** — `job logs --id <id>` fails while `job get --id <id>` works; known inconsistency, don't fight it.
- Always bound the read: `--tail N`, `--since 1h` (the default window is 1h — pass `--since` explicitly for older jobs), `--until` for a window. Never `--follow` (hangs unattended sessions; poll bounded reads instead).
- **No logs ≠ no problem.** `logs` returns empty with exit code 0 for a workload that never started — verified. Never conclude health from empty logs: cross-check `get` state and elapsed time first. Empty logs + non-terminal state + minutes elapsed = startup failure until proven otherwise.
- **Retention is not guaranteed after `delete`.** Logs disappear some time after the resource is deleted, and the retention window is undocumented — so `logs` is not a durable record for a long run. For anything you need to keep, have the **container itself** write logs to a mounted bucket (or your own collector) during the run; don't rely on querying them later.

## Error catalog

Errors print as **plain text even with `--format json`** (until MSPDEV-778) — branch on exit code, read stderr, never parse stdout of a failed command.

- **`PermissionDenied` mentioning the VPC API** on job/endpoint create → the account has Serverless permissions but lacks a VPC grant (MSPDEV-784). Retrying cannot help; report the missing VPC grant on the project and hand the role fix to the user.
- **Other `PermissionDenied` / empty lists where resources exist** → wrong `--parent-id` scope or wrong profile; re-run the grounding checks before anything else.
- **`RESOURCE_EXHAUSTED` / "not enough resources"** → the platform is out of capacity in that region. Offer: a different preset size, a sibling platform (L40S, or RTX 6000-class in regions that have it — verify with `nebius compute platform list`), `--preemptible`, or another region/project. Quota increases go through the console (Quotas page) — that's a human step.
- **Quota errors** arrive **in batches** — one response can carry several violated quota codes. Read them all and address the full set; fixing one and retrying discovers the next the slow way.
- **Authentication errors** → session or token expired; re-auth is a human step → `nebius-serverless-setup`.
- **Unknown flag/command** → CLI drift; `nebius <cmd> --help` is ground truth, and the Serverless skills need >= 0.12.277 (ask the user to run `nebius update` — never run it yourself).

## Escalating

Every CLI error prints a **request ID and a Trace ID** — include both verbatim in any support report or issue, with the exact command (secrets redacted) and timestamp. Without them support starts from zero.

## Last resort: SSH

`nebius ai job ssh <id>` / `nebius ai endpoint ssh <id>` opens a shell in the running container — interactive, so a human runs it, not you: print the command and what to look at (`df -h` for disk, `env` for missing vars, the mount path for volumes). Requires the workload to have reached a running container; it cannot rescue a failed pull.

## Hand-offs

- The fix is cancel / re-create / stop → `nebius-serverless-jobs` or `nebius-serverless-endpoints` (gated there, including the cost statement).
- Volume mounted empty, secret not arriving → `nebius-serverless-data-secrets`.
- Profile/scope confusion, general error decoding → `nebius-cloud-basics`.
