---
name: nebius-cloud-basics
description: Foundation for the nebius CLI. Check before running Nebius CLI commands, or if the CLI is not installed or configured, or a nebius command needs the right profile, --parent-id, or output format, or fails with an unclear error. Public documentation questions do not require CLI setup.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.247) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile list:*)
  - Bash(nebius profile current:*)
  - Bash(nebius profile active:*)
  - Bash(nebius config get:*)
  - Bash(nebius config list:*)
  - Bash(nebius iam whoami:*)
---

# Nebius Cloud Basics

Consult this skill for any nebius CLI question the other `nebius-*` skills don't cover.
Everything the other `nebius-*` skills assume: how to pick a profile, resolve the right `--parent-id`, get machine-readable output, wait on operations, and stay inside the safety tiers.

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

If any check fails or an ID comes back empty, stop and walk the user through [CLI installation and profile setup](https://docs.nebius.com/cli/install): `curl -sSL https://artifacts.nebius.cloud/cli/install.sh | bash`, then `nebius profile create --parent-id <project-id>`. **Print those commands for the user to run — do not run them yourself**: the installer writes to their machine and the shown federation-profile command opens a browser and blocks. An expired session does not show up here; it surfaces on the first real API call, and re-auth is the same human task.

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

## Grounding sequence

The four checks in the preamble above establish that the CLI, a profile, and both IDs exist. Two more are worth running before acting:

```bash
nebius profile current                 # profile actually in effect (can differ from [default]); prints a bare name, --format is ignored
nebius iam whoami --format json        # the session's token still works
```

`whoami` is the only one that touches the API — a profile passes every local check and still fails here once its session expires. See *Decoding errors* below.

If the user names a profile ("use the testing profile"), append `-p <profile>` to **every** subsequent command — the active profile is easy to forget mid-session and mixing scopes across profiles is the top source of confusing permission errors.

Some profiles have no `parent-id` or `tenant-id` configured — `config get` then returns an error or empty value. In that case ask the user which project/tenant to target; do not borrow IDs from another profile.

## Which --parent-id does a command want?

| Command family | Scope to pass |
|---|---|
| `compute *` (instances, disks, filesystems, gpu-clusters, project images, platforms) | project (`project-...`) |
| `compute image list-public` | region via required `--region`; no `--parent-id` or `--all` |
| `quotas quota-allowance *` | project (or tenant for tenant-wide quotas) |
| `capacity resource-advice list` | **tenant** (`tenant-...`) — required to compute quota-clipped availability |
| `capacity capacity-block-group *`, `capacity capacity-interval *` | **tenant** |
| `capacity capacity-allowance *` | project |

## Decoding errors

- **Permission denied / empty list where resources should exist** — usually the wrong `--parent-id` scope (project vs tenant) or the wrong profile. Re-run the grounding sequence before retrying.
- **Authentication errors** — the profile's session expired. Re-auth is a human task (`nebius profile create` opens a browser); tell the user, don't attempt it.
- **Unknown flag / command** — the CLI is auto-generated and changes between versions. Treat `nebius <cmd> --help` as ground truth, never a memorized flag list.
- The CLI retries transient errors itself (`--retries`, default 3). Do not wrap read calls in your own retry loop; never retry a mutation after an ambiguous failure — check actual state with `get`/`list` first.

## Going deeper

- [references/context-resolution.md](references/context-resolution.md) — profiles, `~/.nebius/config.yaml`, NID formats, auth types, multi-profile work
- [references/output-and-paging.md](references/output-and-paging.md) — `--format json|yaml|jsonpath`, jq recipes, `--page-size`/`--page-token`/`--all`
- [references/operations.md](references/operations.md) — async operations, `operation wait`, polling patterns, timeouts and retries
- [references/safety-tiers.md](references/safety-tiers.md) — the full tier table with rationale and the complete refuse list
